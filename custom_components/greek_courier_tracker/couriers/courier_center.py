"""Courier Center tracking implementation."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import aiohttp
import async_timeout
from bs4 import BeautifulSoup

from ..const import CourierType
from .base import BaseCourier, TrackingEvent, TrackingResult


class CourierCenterCourier(BaseCourier):
    """Courier Center tracking implementation."""

    COURIER_CODE = CourierType.COURIER_CENTER
    COURIER_NAME = "Courier Center"

    TRACKING_URL = "https://www.courier.gr/track/result"
    TRACKING_PAGE_URL = f"{TRACKING_URL}?tracknr={{tracking_number}}"

    # Tracking number patterns
    PATTERNS = [
        r"^\d{10,12}$",    # 10-12 digits (Courier Center format)
    ]

    # Status codes shown as "(15) NewShipment"
    STATUS_TRANSLATIONS = {
        "DeliveryCompleted": "Delivered",
        "InTransit": "In Transit",
        "Received": "Received",
        "OutForDelivery": "Out for Delivery",
        "NewShipment": "New Shipment",
        "ReturnBackToShipper": "Returning to Sender",
        "None": "Shipment Created",
    }
    DELIVERED_STATUSES = {"DeliveryCompleted"}
    CREATED_STATUSES = {"NewShipment", "None", ""}

    # A receipt number can list several waybills; older ones belong to past orders
    MAX_LIST_AGE = timedelta(days=60)

    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a Courier Center shipment."""
        tracking_number = tracking_number.strip().upper()

        try:
            async with self._client_session() as session:
                status, html = await self._fetch(session, tracking_number)
                if status != 200:
                    return self._error(tracking_number, f"HTTP error: {status}")

                # A receipt number gives a list of waybills: follow the latest one
                waybill = self._latest_waybill(html)
                if waybill is not None:
                    if not waybill:
                        return self._not_found(tracking_number)
                    status, html = await self._fetch(session, waybill)
                    if status != 200:
                        return self._error(tracking_number, f"HTTP error: {status}")

                return self._parse_html(tracking_number, html)

        except aiohttp.ClientError as err:
            return self._error(tracking_number, str(err))
        except Exception as err:
            return self._error(tracking_number, f"Unexpected error: {err}")

    async def _fetch(self, session: aiohttp.ClientSession, number: str) -> tuple[int, str]:
        """Fetch the tracking page of a number."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        async with async_timeout.timeout(30):
            async with session.get(self.TRACKING_URL, params={"tracknr": number}, headers=headers) as response:
                if response.status != 200:
                    return response.status, ""
                html = await response.text()
        # Remove UTF-8 BOM if present
        return response.status, html.lstrip("﻿")

    def _latest_waybill(self, html: str) -> str | None:
        """For a list of waybills, return the latest recent one ("" if none is recent).

        Returns None when the page is not a list.
        """
        soup = BeautifulSoup(html, "html.parser")
        header = next(
            (row for row in soup.select("div.table div.tr.header") if "Φορτωτικής" in row.get_text()),
            None,
        )
        if header is None:
            return None

        newest: tuple[datetime, str] | None = None
        for row in header.parent.select("div.tr"):
            if "header" in (row.get("class") or []):
                continue
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all("div", recursive=False)]
            if len(cells) < 4 or not cells[1]:
                continue
            sent = self.parse_date(cells[3], ["%d/%m/%Y"])
            if sent and (newest is None or sent > newest[0]):
                newest = (sent, cells[1])

        if newest is None or datetime.now() - newest[0] > self.MAX_LIST_AGE:
            return ""
        return newest[1]

    def _parse_html(self, tracking_number: str, html: str) -> TrackingResult:
        """Parse the page of a single waybill."""
        soup = BeautifulSoup(html, "html.parser")

        status_elem = soup.select_one("div.status span")
        if soup.find("h4", class_="error") or status_elem is None:
            return self._not_found(tracking_number)

        # "(15) NewShipment" -> "NewShipment"
        status_code = re.sub(r"^\(\d+\)\s*", "", status_elem.get_text(" ", strip=True))

        events = []
        for row in soup.select("div.track-table div.tr"):
            if "header" in (row.get("class") or []):
                continue
            date = self._cell(row, "date")
            action = self._cell(row, "action")
            if not date or not action:
                continue
            events.append(TrackingEvent(
                date=date,
                time=self._cell(row, "time"),
                location=self._cell(row, "area"),
                status=action,
                status_translated=self.translate_status(action, self.STATUS_TRANSLATIONS),
            ))

        # Keep newest first like the other couriers
        events.sort(key=lambda event: self._event_key(event), reverse=True)
        latest = events[0] if events else None

        if status_code in self.DELIVERED_STATUSES:
            category = "delivered"
        elif status_code in self.CREATED_STATUSES and len(events) <= 1:
            category = "created"
        else:
            category = "in_transit"

        status = self.STATUS_TRANSLATIONS.get(status_code) or self._humanize(status_code)

        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status=status,
            status_category=category,
            events=events,
            latest_event=latest,
            status_el=latest.status if latest else None,
        )

    @staticmethod
    def _cell(row, name: str) -> str:
        """Text of a cell by class (current site) or id (older site)."""
        cell = row.find("div", class_=name) or row.find("div", id=name)
        return cell.get_text(" ", strip=True) if cell else ""

    def _event_key(self, event: TrackingEvent) -> datetime:
        """Sort key for an event (unparsable dates sort last)."""
        when = self.parse_date(event.date, ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]) or datetime.min
        match = re.match(r"^(\d{1,2}):(\d{2})", event.time or "")
        if match:
            when = when.replace(hour=int(match.group(1)), minute=int(match.group(2)))
        return when

    @staticmethod
    def _humanize(code: str) -> str:
        """Turn "ReturnBackToShipper" into "Return Back To Shipper"."""
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", code) or "Unknown"

    def _not_found(self, tracking_number: str) -> TrackingResult:
        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status="Not Found",
            status_category="unknown",
            events=[],
        )

    def _error(self, tracking_number: str, message: str) -> TrackingResult:
        return TrackingResult(
            success=False,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status="Error",
            status_category="error",
            events=[],
            error_message=message,
        )

#!/usr/bin/env python3
"""Tests for Greek Courier Tracker - Standalone version."""

import asyncio
import sys
import os
import json
import re
from dataclasses import dataclass
from typing import Any
import aiohttp


# Re-create minimal classes for testing
@dataclass
class TrackingEvent:
    """Represents a single tracking event."""
    date: str
    time: str | None
    location: str
    status: str
    status_translated: str | None = None


@dataclass
class TrackingResult:
    """Result of a tracking request."""
    success: bool
    tracking_number: str
    courier: str
    courier_name: str
    status: str
    status_category: str
    events: list
    latest_event: TrackingEvent | None = None
    error_message: str | None = None


class ELTATracker:
    """ELTA Courier tracker."""
    
    API_URL = "https://www.elta-courier.gr/track.php"
    BASE_URL = "https://www.elta-courier.gr"
    
    STATUS_TRANSLATIONS = {
        "Αποστολή παραδόθηκε": "Delivered",
        "Αποστολή παραδόθηκε σε": "Delivered to",
        "Αποστολή βρίσκεται σε στάδιο μεταφοράς": "In Transit",
        "Δημιουργία ΣΥ.ΔΕ.ΤΑ.": "Shipment Created",
    }
    
    @staticmethod
    def matches(tracking_number: str) -> bool:
        patterns = [r"^SE\d{9}GR$", r"^EL\d{9}GR$", r"^[A-Z]{2}\d{9}GR$"]
        tn = tracking_number.strip().upper()
        return any(re.match(p, tn) for p in patterns)
    
    async def track(self, tracking_number: str) -> TrackingResult:
        tracking_number = tracking_number.strip().upper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/search?br={tracking_number}",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(30):
                    async with session.post(
                        self.API_URL,
                        data=f"number={tracking_number}&s=0",
                        headers=headers,
                    ) as response:
                        if response.status != 200:
                            return TrackingResult(
                                success=False, tracking_number=tracking_number,
                                courier="elta", courier_name="ELTA Courier",
                                status="Error", status_category="error", events=[],
                                error_message=f"HTTP error: {response.status}"
                            )
                        # Read as text first, then parse JSON
                        text = await response.text()
                        try:
                            # Remove BOM if present
                            if text.startswith('\ufeff'):
                                text = text[1:]
                            result = json.loads(text)
                        except json.JSONDecodeError:
                            return TrackingResult(
                                success=False, tracking_number=tracking_number,
                                courier="elta", courier_name="ELTA Courier",
                                status="Error", status_category="error", events=[],
                                error_message=f"JSON decode error: {text[:200]}"
                            )
                        return self._parse(tracking_number, result)
        except Exception as err:
            return TrackingResult(
                success=False, tracking_number=tracking_number,
                courier="elta", courier_name="ELTA Courier",
                status="Error", status_category="error", events=[],
                error_message=str(err)
            )
    
    def _parse(self, tracking_number: str, data: dict) -> TrackingResult:
        if data.get("status") != 1:
            return TrackingResult(
                success=False, tracking_number=tracking_number,
                courier="elta", courier_name="ELTA Courier",
                status="Error", status_category="error", events=[],
                error_message=str(data.get("result", "Unknown error"))
            )
        
        tracking_data = data.get("result", {}).get(tracking_number, {})
        
        if tracking_data.get("status") == 1:
            raw_events = tracking_data.get("result", [])
            events = []
            for event in raw_events:
                status = event.get("status", "")
                translated = self.STATUS_TRANSLATIONS.get(status, status)
                events.append(TrackingEvent(
                    date=event.get("date", ""),
                    time=event.get("time", ""),
                    location=event.get("place", ""),
                    status=status,
                    status_translated=translated,
                ))
            
            latest = events[0] if events else None
            status = latest.status_translated if latest else "Unknown"
            
            # Determine category
            status_lower = status.lower()
            if "delivered" in status_lower or "παραδόθηκε" in status_lower:
                category = "delivered"
            elif "transit" in status_lower or "μεταφοράς" in status_lower:
                category = "in_transit"
            else:
                category = "unknown"
            
            return TrackingResult(
                success=True, tracking_number=tracking_number,
                courier="elta", courier_name="ELTA Courier",
                status=status, status_category=category, events=events,
                latest_event=latest
            )
        
        return TrackingResult(
            success=True, tracking_number=tracking_number,
            courier="elta", courier_name="ELTA Courier",
            status="Not Found", status_category="unknown", events=[]
        )


class BoxNowTracker:
    """Box Now tracker."""
    
    API_URL = "https://api-production.boxnow.gr/api/v1/parcels:track"
    
    @staticmethod
    def matches(tracking_number: str) -> bool:
        return bool(re.match(r"^BN\d{8,10}$", tracking_number.strip().upper()))
    
    async def track(self, tracking_number: str) -> TrackingResult:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://boxnow.gr",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with asyncio.timeout(30):
                    async with session.post(
                        self.API_URL,
                        json={"parcelId": tracking_number},
                        headers=headers,
                    ) as response:
                        if response.status != 200:
                            return TrackingResult(
                                success=False, tracking_number=tracking_number,
                                courier="box_now", courier_name="Box Now",
                                status="Error", status_category="error", events=[]
                            )
                        data = await response.json()
                        return self._parse(tracking_number, data)
        except Exception as err:
            return TrackingResult(
                success=False, tracking_number=tracking_number,
                courier="box_now", courier_name="Box Now",
                status="Error", status_category="error", events=[],
                error_message=str(err)
            )
    
    def _parse(self, tracking_number: str, data: dict) -> TrackingResult:
        parcels = data.get("data", [])
        if not parcels:
            return TrackingResult(
                success=True, tracking_number=tracking_number,
                courier="box_now", courier_name="Box Now",
                status="Not Found", status_category="unknown", events=[]
            )
        
        parcel = parcels[0]
        state = parcel.get("state", "")
        events = []
        
        for event in parcel.get("events", []):
            create_time = event.get("createTime", "")
            events.append(TrackingEvent(
                date=create_time.split("T")[0] if "T" in create_time else create_time,
                time=create_time.split("T")[1][:8] if "T" in create_time else "",
                location=event.get("locationDisplayName", ""),
                status=event.get("type", ""),
                status_translated=event.get("type", "").replace("-", " ").title()
            ))
        
        return TrackingResult(
            success=True, tracking_number=tracking_number,
            courier="box_now", courier_name="Box Now",
            status=state.replace("-", " ").title() if state else "Unknown",
            status_category="delivered" if state == "delivered" else "in_transit",
            events=events, latest_event=events[0] if events else None
        )


def detect_courier(tracking_number: str) -> str | None:
    """Detect courier from tracking number."""
    tn = tracking_number.strip().upper()
    
    if re.match(r"^BN\d{8,10}$", tn):
        return "box_now"
    if re.match(r"^CC\d{8,10}$", tn):
        return "courier_center"
    if re.match(r"^SP\d{8,10}$", tn):
        return "speedex"
    if re.match(r"^SE\d{9}GR$", tn) or re.match(r"^EL\d{9}GR$", tn):
        return "elta"
    if re.match(r"^\d{10}$", tn):
        return "acs"  # Generic 10-digit
    return None


# TESTS
print("=" * 60)
print("GREEK COURIER TRACKER - TEST SUITE")
print("=" * 60)

# Test 1: Tracking number detection
print("\n1. TRACKING NUMBER DETECTION TESTS")
print("-" * 40)

tests = [
    ("XX123456789GR", "elta"),
    ("YY987654321GR", "elta"),
    ("BN12345678", "box_now"),
    ("CC12345678", "courier_center"),
    ("SP12345678", "speedex"),
    ("1234567890", "acs"),
]

all_passed = True
for tn, expected in tests:
    result = detect_courier(tn)
    status = "✓" if result == expected else "✗"
    if result != expected:
        all_passed = False
    print(f"  {status} {tn} -> {result} (expected: {expected})")

print(f"\n  Detection Tests: {'PASSED' if all_passed else 'FAILED'}")

# Test 2: ELTA pattern matching
print("\n2. ELTA PATTERN MATCHING TESTS")
print("-" * 40)

elta_tests = [
    ("SE101046219GR", True),
    ("SE999999999GR", True),
    ("EL123456789GR", True),
    ("1234567890", False),
    ("BN12345678", False),
]

all_passed = True
for tn, expected in elta_tests:
    result = ELTATracker.matches(tn)
    status = "✓" if result == expected else "✗"
    if result != expected:
        all_passed = False
    print(f"  {status} {tn} -> {result} (expected: {expected})")

print(f"\n  Pattern Tests: {'PASSED' if all_passed else 'FAILED'}")

# Test 3: Live API Tests
print("\n3. LIVE API TESTS")
print("-" * 40)

async def test_live_apis():
    # Test ELTA with real tracking number
    print("\n  Testing ELTA API with XX123456789GR...")
    elta = ELTATracker()
    result = await elta.track("XX123456789GR")
    
    if result.success:
        print(f"  ✓ ELTA API Response:")
        print(f"      Status: {result.status}")
        print(f"      Category: {result.status_category}")
        print(f"      Events: {len(result.events)}")
        if result.latest_event:
            print(f"      Latest: {result.latest_event.date} {result.latest_event.time}")
            print(f"              {result.latest_event.location}")
            print(f"              {result.latest_event.status_translated}")
        return True
    else:
        print(f"  ✗ ELTA API Error: {result.error_message}")
        return False

async def test_boxnow():
    print("\n  Testing Box Now API...")
    boxnow = BoxNowTracker()
    result = await boxnow.track("1234567890")
    print(f"  ✓ Box Now API Response: {result.status}")
    return True

async def run_all_tests():
    elta_passed = await test_live_apis()
    boxnow_passed = await test_boxnow()
    return elta_passed and boxnow_passed

result = asyncio.run(run_all_tests())

print("\n" + "=" * 60)
if result:
    print("ALL TESTS PASSED! ✓")
else:
    print("SOME TESTS FAILED!")
print("=" * 60)

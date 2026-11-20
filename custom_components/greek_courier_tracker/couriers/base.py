"""Base courier tracking module."""

from __future__ import annotations

import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from urllib.parse import quote

import aiohttp

_LOGGER = logging.getLogger(__name__)

# How far a shipment has got (TrackingResult.stage). The last mile goes either to
# the door or to a locker/store, so those two share a level.
STAGE_CREATED: Final = "created"
STAGE_IN_TRANSIT: Final = "in_transit"
STAGE_OUT_FOR_DELIVERY: Final = "out_for_delivery"
STAGE_READY_FOR_PICKUP: Final = "ready_for_pickup"
STAGE_DELIVERED: Final = "delivered"
STAGE_LEVELS: Final[dict[str, int]] = {
    STAGE_CREATED: 1,
    STAGE_IN_TRANSIT: 2,
    STAGE_OUT_FOR_DELIVERY: 3,
    STAGE_READY_FOR_PICKUP: 3,
    STAGE_DELIVERED: 4,
}

# Something went wrong on the way (TrackingResult.problem). It is shown on top of
# the stage and doesn't move the progress bar.
PROBLEM_ATTEMPT_FAILED: Final = "attempt_failed"  # nobody home, closed, refused
PROBLEM_REROUTED: Final = "rerouted"  # new delivery date or address
PROBLEM_HELD: Final = "held"  # address issue, customs, kept at the depot
PROBLEM_RETURNING: Final = "returning"  # on its way back to the sender
PROBLEM_RETURNED: Final = "returned"  # back at the sender
PROBLEM_CANCELLED: Final = "cancelled"
PROBLEM_EXPIRED: Final = "expired"  # not collected from the locker in time
# These end the trip: later events don't clear them
FINAL_PROBLEMS: Final = frozenset(
    {PROBLEM_RETURNING, PROBLEM_RETURNED, PROBLEM_CANCELLED, PROBLEM_EXPIRED}
)

# (phrase, stage, problem): phrases are lowercase and without Greek accents, the
# first one found in an event's text wins
StatusRule = tuple[str, str | None, str | None]

# Problems come first, so "δεν παραδόθηκε" isn't read as delivered
PROBLEM_RULES: Final[list[StatusRule]] = [
    ("επιστραφηκε", None, PROBLEM_RETURNED),
    ("παραδοθηκε στον αποστολεα", None, PROBLEM_RETURNED),
    ("returned to sender", None, PROBLEM_RETURNED),
    ("επιστροφ", None, PROBLEM_RETURNING),
    ("επιστρεφ", None, PROBLEM_RETURNING),
    ("προς αποστολεα", None, PROBLEM_RETURNING),
    ("return", None, PROBLEM_RETURNING),
    ("ακυρω", None, PROBLEM_CANCELLED),
    ("cancel", None, PROBLEM_CANCELLED),
    ("ανεπιτυχ", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("αποτυχ", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("δεν παραδοθηκε", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("δεν ηταν δυνατη", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("αδυναμια", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("απουσια", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("απων παραληπτ", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("κλειστ", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("αρνηση", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("failed", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("not delivered", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("unsuccessful", STAGE_OUT_FOR_DELIVERY, PROBLEM_ATTEMPT_FAILED),
    ("επαναδρομολογ", None, PROBLEM_REROUTED),
    ("αναδρομολογ", None, PROBLEM_REROUTED),
    ("ανακατευθυν", None, PROBLEM_REROUTED),
    ("επαναπρογραμματ", None, PROBLEM_REROUTED),
    ("νεα ημερομηνια", None, PROBLEM_REROUTED),
    ("αλλαγη διευθυνσης", None, PROBLEM_REROUTED),
    ("reroute", None, PROBLEM_REROUTED),
    ("reschedul", None, PROBLEM_REROUTED),
    ("ελλιπ", None, PROBLEM_HELD),
    ("ανεπαρκ", None, PROBLEM_HELD),
    ("λαθος διευθυνση", None, PROBLEM_HELD),
    ("λανθασμεν", None, PROBLEM_HELD),
    ("τελωνει", None, PROBLEM_HELD),
    ("customs", None, PROBLEM_HELD),
]

# Plain progress, checked after the courier's own phrases
STAGE_RULES: Final[list[StatusRule]] = [
    ("παραδοθηκε", STAGE_DELIVERED, None),
    ("επιτυχης παραδοση", STAGE_DELIVERED, None),
    ("delivered", STAGE_DELIVERED, None),
    ("σε διανομεα", STAGE_OUT_FOR_DELIVERY, None),
    ("σε διανομη", STAGE_OUT_FOR_DELIVERY, None),
    ("προς παραδοση", STAGE_OUT_FOR_DELIVERY, None),
    ("out for delivery", STAGE_OUT_FOR_DELIVERY, None),
    ("δυνατοτητα παραλαβης", STAGE_READY_FOR_PICKUP, None),
    ("διαθεσιμ", STAGE_READY_FOR_PICKUP, None),
    ("ready for pick", STAGE_READY_FOR_PICKUP, None),
    ("available for pick", STAGE_READY_FOR_PICKUP, None),
    ("awaiting pick", STAGE_READY_FOR_PICKUP, None),
    ("δημιουργ", STAGE_CREATED, None),
    ("created", STAGE_CREATED, None),
    ("μεταφορ", STAGE_IN_TRANSIT, None),
    ("διαλογ", STAGE_IN_TRANSIT, None),
    ("αφιξη", STAGE_IN_TRANSIT, None),
    ("αναχωρ", STAGE_IN_TRANSIT, None),
    ("transit", STAGE_IN_TRANSIT, None),
    ("hub", STAGE_IN_TRANSIT, None),
    ("picked up", STAGE_IN_TRANSIT, None),
]


def higher_stage(first: str | None, second: str | None) -> str | None:
    """The stage further along (None when neither is known)."""
    if first is None:
        return second
    if second is None:
        return first
    return second if STAGE_LEVELS[second] > STAGE_LEVELS[first] else first


def stage_category(stage: str | None) -> str:
    """The older status_category of a stage (created, in_transit, delivered, unknown)."""
    if stage in (STAGE_CREATED, STAGE_DELIVERED):
        return stage
    return "unknown" if stage is None else "in_transit"


def summarize_progress(
    events: list["TrackingEvent"], fallback: str | None = None
) -> tuple[str | None, str | None]:
    """Return the stage reached and the current problem, from events newest first.

    The stage is the furthest any event got, so the bar never goes back. A problem
    holds until a newer event shows progress (a new attempt, a delivery), except
    returns, cancellations and expiries, which end the trip. Events that say
    nothing known count as `fallback`, or as in transit once there is more than one.
    """
    final_index = next((index for index, event in enumerate(events) if event.problem in FINAL_PROBLEMS), None)

    if final_index is not None:
        # Whatever happens after a return is the return trip
        stage = None
        for event in events[final_index:]:
            stage = higher_stage(stage, event.stage)
        problem = events[final_index].problem
        if problem == PROBLEM_RETURNING and any(event.stage == STAGE_DELIVERED for event in events[:final_index]):
            problem = PROBLEM_RETURNED
        if stage == STAGE_DELIVERED:
            stage = STAGE_OUT_FOR_DELIVERY
    else:
        stage = None
        for event in events:
            stage = higher_stage(stage, event.stage)
        problem = None
        for event in events:
            if event.problem:
                problem = event.problem
                break
            if event.stage:
                break
        if stage == STAGE_DELIVERED:
            problem = None

    if stage is None and events:
        stage = fallback or (STAGE_IN_TRANSIT if len(events) > 1 else STAGE_CREATED)
    return stage, problem


@dataclass
class TrackingEvent:
    """Represents a single tracking event."""
    date: str
    time: str | None
    location: str
    status: str
    status_translated: str | None = None
    stage: str | None = None  # STAGE_*, when the event says how far the shipment got
    problem: str | None = None  # PROBLEM_*, when the event reports one


@dataclass
class TrackingResult:
    """Result of a tracking request."""
    success: bool
    tracking_number: str
    courier: str
    courier_name: str
    status: str
    status_category: str  # delivered, in_transit, created, unknown, error
    events: list[TrackingEvent]
    latest_event: TrackingEvent | None = None
    error_message: str | None = None
    raw_data: dict[str, Any] | None = None
    last_updated: str | None = None  # ISO timestamp of last successful update
    estimated_delivery: str | None = None  # ISO date (or start/end) given by the courier
    status_el: str | None = None  # Greek status text, when the courier provides one
    stage: str | None = None  # STAGE_*: how far the shipment has got
    problem: str | None = None  # PROBLEM_*: what went wrong, if anything


# Answers that mean "stop asking for now": rate limited, or refused by a firewall
_REFUSED = re.compile(r"^HTTP error: (403|429|503)\b")


def is_refused(result: TrackingResult) -> bool:
    """Return whether the courier refused the request instead of answering it."""
    return not result.success and bool(_REFUSED.match(result.error_message or ""))


class BaseCourier(ABC):
    """Base class for courier tracking implementations."""
    
    # Subclasses must define these
    COURIER_CODE: str = ""
    COURIER_NAME: str = ""
    # The courier's own tracking page, with a {tracking_number} placeholder
    TRACKING_PAGE_URL: str = ""
    # How many numbers fit in one request (more than 1: implement track_many)
    BATCH_SIZE: int = 1
    # The courier's own phrases, checked between PROBLEM_RULES and STAGE_RULES
    STATUS_RULES: list[StatusRule] = []
    # Stage of shipments whose events say nothing known (None: by event count)
    FALLBACK_STAGE: str | None = None

    # Phrases already logged as unknown, so each is logged once
    _unclassified: set[tuple[str, str]] = set()

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        """Use the given HTTP session (Home Assistant's shared one), if any."""
        self._session = session
        self.retry_after: float | None = None

    def _note_refusal(self, response: aiohttp.ClientResponse) -> None:
        """Remember how long the courier asked us to wait (seconds), if it did."""
        try:
            self.retry_after = float(response.headers.get("Retry-After"))
        except (AttributeError, TypeError, ValueError):
            self.retry_after = None

    @asynccontextmanager
    async def _client_session(self) -> AsyncIterator[aiohttp.ClientSession]:
        """Yield the shared session, or a short-lived one when none was given."""
        if self._session is not None:
            yield self._session
            return
        async with aiohttp.ClientSession() as session:
            yield session
    
    @abstractmethod
    async def track(self, tracking_number: str) -> TrackingResult:
        """Track a shipment by tracking number.

        Args:
            tracking_number: The tracking number to look up

        Returns:
            TrackingResult with shipment status and events
        """
        pass

    async def track_many(self, tracking_numbers: list[str]) -> dict[str, TrackingResult]:
        """Track up to BATCH_SIZE numbers with one request."""
        raise NotImplementedError

    def _error_result(self, tracking_number: str, message: str) -> TrackingResult:
        """Build the result of a failed request."""
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

    def _not_found_result(self, tracking_number: str) -> TrackingResult:
        """Build the result of a number the courier doesn't know."""
        return TrackingResult(
            success=True,
            tracking_number=tracking_number,
            courier=self.COURIER_CODE,
            courier_name=self.COURIER_NAME,
            status="Not Found",
            status_category="unknown",
            events=[],
        )

    @classmethod
    def tracking_page_url(cls, tracking_number: str) -> str | None:
        """Return the courier's own tracking page for a number, if it has one."""
        if not cls.TRACKING_PAGE_URL:
            return None
        return cls.TRACKING_PAGE_URL.format(tracking_number=quote(tracking_number, safe=""))

    def _normalize(self, text: str) -> str:
        """Lowercase text and strip Greek accents for keyword matching."""
        decomposed = unicodedata.normalize("NFD", text.lower())
        return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")

    def classify(self, *texts: str | None, problems_only: bool = False) -> tuple[str | None, str | None]:
        """Return the (stage, problem) of an event from its texts (Greek and/or English)."""
        text = self._normalize(" ".join(text for text in texts if text))
        if not text:
            return None, None
        rules = PROBLEM_RULES if problems_only else [*PROBLEM_RULES, *self.STATUS_RULES, *STAGE_RULES]
        for phrase, stage, problem in rules:
            if phrase in text:
                return stage, problem
        return None, None

    def classify_events(self, events: list[TrackingEvent]) -> None:
        """Set the stage and problem of events from their texts."""
        for event in events:
            event.stage, event.problem = self.classify(event.status, event.status_translated)

    def progress(self, events: list[TrackingEvent]) -> tuple[str | None, str | None]:
        """Stage and problem of a shipment from its classified events (newest first)."""
        for event in events:
            if event.stage is None and event.problem is None:
                key = (str(self.COURIER_CODE), event.status)
                if event.status and key not in BaseCourier._unclassified:
                    BaseCourier._unclassified.add(key)
                    _LOGGER.info("%s: status not recognised yet: %s", self.COURIER_NAME, event.status)
        return summarize_progress(events, self.FALLBACK_STAGE)

    def translate_status(self, status: str, translations: dict[str, str]) -> str:
        """Translate Greek status to English.
        
        Args:
            status: The status text (may be in Greek)
            translations: Dictionary of translations
            
        Returns:
            Translated status or original if no translation found
        """
        status_lower = status.lower()
        # An empty status is "in" every phrase: it has no translation
        if not status_lower.strip():
            return status

        # Check for exact match
        for greek, english in translations.items():
            if greek.lower() == status_lower:
                return english
        
        # Check for partial match
        for greek, english in translations.items():
            if greek.lower() in status_lower or status_lower in greek.lower():
                return english
        
        return status
    
    def get_status_category(self, status: str, delivered_keywords: list[str], 
                           in_transit_keywords: list[str], 
                           created_keywords: list[str]) -> str:
        """Determine the status category from status text.
        
        Args:
            status: The status text
            delivered_keywords: Keywords indicating delivery
            in_transit_keywords: Keywords indicating transit
            created_keywords: Keywords indicating creation
            
        Returns:
            Category string: delivered, in_transit, created, or unknown
        """
        status_lower = status.lower()
        
        for keyword in delivered_keywords:
            if keyword.lower() in status_lower:
                return "delivered"
        
        for keyword in in_transit_keywords:
            if keyword.lower() in status_lower:
                return "in_transit"
        
        for keyword in created_keywords:
            if keyword.lower() in status_lower:
                return "created"
        
        return "unknown"
    
    def parse_date(self, date_str: str, formats: list[str] | None = None) -> datetime | None:
        """Parse a date string into a datetime object.
        
        Args:
            date_str: The date string to parse
            formats: List of format strings to try
            
        Returns:
            Parsed datetime or None if parsing failed
        """
        if formats is None:
            formats = ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        
        return None

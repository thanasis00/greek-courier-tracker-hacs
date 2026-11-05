"""Decide when each courier is asked again.

The couriers publish no rate limits, so requests are kept low and spread out:
every courier gets its own cycle that grows with the requests it needs, and a
courier that starts refusing requests is left alone for a while.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .const import (
    AUTO_DETECT_MIN_INTERVAL,
    BACKOFF_BASE_MINUTES,
    BACKOFF_MAX_MINUTES,
    CourierType,
    MAX_COURIER_INTERVAL,
    MIN_WAKE_SECONDS,
    POLL_JITTER,
)


def courier_interval(
    courier: str, count: int, base_minutes: int, batch_size: int = 1
) -> timedelta:
    """Return how often a courier with this many shipments is asked.

    One request per base interval: 1 shipment every 15 minutes, 2 every 30 and
    so on. Numbers that fit in one request (batch_size) count once. Numbers
    whose courier isn't known yet cost a request per courier, so they wait longer.
    """
    requests = max(1, math.ceil(count / max(1, batch_size)))
    minutes = min(base_minutes * requests, max(base_minutes, MAX_COURIER_INTERVAL))
    if courier == CourierType.AUTO:
        minutes = max(minutes, AUTO_DETECT_MIN_INTERVAL)
    return timedelta(minutes=minutes)


@dataclass
class CourierSchedule:
    """When each courier is due and which ones are backing off."""

    next_due: dict[str, datetime] = field(default_factory=dict)
    blocked_until: dict[str, datetime] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)

    def is_blocked(self, courier: str, now: datetime) -> bool:
        """Return whether a courier is being left alone."""
        until = self.blocked_until.get(courier)
        return until is not None and now < until

    def is_due(self, courier: str, now: datetime) -> bool:
        """Return whether a courier should be asked now."""
        if self.is_blocked(courier, now):
            return False
        due = self.next_due.get(courier)
        return due is None or now >= due

    def mark_polled(self, courier: str, interval: timedelta, now: datetime) -> None:
        """Schedule the next cycle, a little late so installations drift apart."""
        self.next_due[courier] = now + interval * (1 + random.uniform(0, POLL_JITTER))

    def record_success(self, courier: str) -> None:
        """Forget earlier refusals of a courier that answers again."""
        self.failures.pop(courier, None)
        self.blocked_until.pop(courier, None)

    def record_blocked(
        self, courier: str, now: datetime, retry_after: float | None = None
    ) -> timedelta:
        """Back off from a courier that refused a request; return for how long."""
        failures = self.failures.get(courier, 0)
        self.failures[courier] = failures + 1
        minutes = min(BACKOFF_BASE_MINUTES * 2**failures, BACKOFF_MAX_MINUTES)
        delay = max(timedelta(minutes=minutes), timedelta(seconds=retry_after or 0))
        self.blocked_until[courier] = now + delay
        return delay

    def reconcile(self, intervals: dict[str, timedelta], now: datetime) -> None:
        """Bring the schedule in line with the current couriers and intervals.

        Couriers that have just been asked (a number was added or detected) wait
        a full cycle, and a shorter interval takes effect without a restart.
        """
        for courier in list(self.next_due):
            if courier not in intervals:
                del self.next_due[courier]
        for courier, interval in intervals.items():
            due = self.next_due.get(courier)
            if due is None or due > now + interval * (1 + POLL_JITTER):
                self.mark_polled(courier, interval, now)

    def next_wake(self, couriers: list[str], now: datetime, fallback: timedelta) -> timedelta:
        """Return the time until the next courier is due."""
        times = [
            max(self.next_due.get(courier, now), self.blocked_until.get(courier, now))
            for courier in couriers
        ]
        if not times:
            return fallback
        return max(min(times) - now, timedelta(seconds=MIN_WAKE_SECONDS))

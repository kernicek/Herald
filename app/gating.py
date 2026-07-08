"""Work-hours / holiday / vacation gating for a GateProfile."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .holidays_provider import is_holiday


def is_working_day(day: date, profile, vac) -> bool:
    """Day-level: a working weekday that is not a holiday or vacation day."""
    if day.weekday() not in profile.days:
        return False
    if is_holiday(day, profile.holidays_country, profile.holidays_subdiv):
        return False
    if profile.vacation_calendar:
        if vac is not None and vac.available:
            if vac.is_vacation(day):
                return False
        elif profile.on_feed_failure == "fail-closed":
            # No feed data and policy says protect time off => treat as non-working.
            return False
        # fail-open (default): no data => assume not on vacation.
    return True


def is_working(dt: datetime, profile, vac, tz) -> bool:
    """Instant-level: on a working day AND inside the daily window."""
    local = dt.astimezone(tz)
    if not is_working_day(local.date(), profile, vac):
        return False
    t = local.time()
    return profile.window_start <= t < profile.window_end


def next_delivery(dt: datetime, profile, vac, tz) -> datetime:
    """Earliest working-day digest_time that is >= dt (when to deliver a deferral)."""
    local = dt.astimezone(tz)
    d = local.date()
    for _ in range(500):
        if is_working_day(d, profile, vac):
            candidate = datetime.combine(d, profile.digest_time, tzinfo=tz)
            if candidate >= dt:
                return candidate
        d += timedelta(days=1)
    return dt  # pathological fallback (e.g. no working days configured)

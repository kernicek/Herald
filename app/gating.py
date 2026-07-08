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


def _timed_vacation(dt: datetime, profile, vac) -> bool:
    """True if `dt` (tz-aware) falls inside a timed (e.g. half-day) vacation window."""
    return (profile.vacation_calendar and vac is not None and vac.available
            and vac.is_vacation_at(dt))


def is_working(dt: datetime, profile, vac, tz) -> bool:
    """Instant-level: on a working day, inside the daily window, and not inside a
    timed (half-day) vacation."""
    local = dt.astimezone(tz)
    if not is_working_day(local.date(), profile, vac):
        return False
    t = local.time()
    if not (profile.window_start <= t < profile.window_end):
        return False
    return not _timed_vacation(local, profile, vac)


def next_delivery(dt: datetime, profile, vac, tz) -> datetime:
    """Earliest working-day digest_time that is >= dt (when to deliver a deferral).
    Skips a day whose digest_time lands in a timed vacation window."""
    local = dt.astimezone(tz)
    d = local.date()
    for _ in range(500):
        if is_working_day(d, profile, vac):
            candidate = datetime.combine(d, profile.digest_time, tzinfo=tz)
            if candidate >= dt and not _timed_vacation(candidate, profile, vac):
                return candidate
        d += timedelta(days=1)
    return dt  # pathological fallback (e.g. no working days configured)

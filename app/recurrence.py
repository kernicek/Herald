"""Expand a ParsedStamp into concrete Occurrences within a time window.

Occurrences are computed in *naive local* wall-clock space and then localized, so a
09:00 daily repeater stays 09:00 across DST changes rather than drifting an hour.
The precise window filter is applied on the tz-aware datetimes.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from .models import Occurrence

_GUARD = 100_000  # hard cap on generated candidates per stamp (runaway backstop)


def expand(stamp, default_time, folder, tz, win_start, win_end) -> list:
    """Return Occurrences of `stamp` whose time falls in (win_start, win_end]."""
    base_time = stamp.base_time or default_time
    base = datetime.combine(stamp.base_date, base_time)  # naive local
    results: list = []

    def emit(naive_dt):
        aware = naive_dt.replace(tzinfo=tz)
        if win_start < aware <= win_end:
            results.append(Occurrence(
                folder=folder, when=aware, kind=stamp.kind,
                task_text=stamp.task_text, page=stamp.page, block_id=stamp.block_id,
            ))

    if not stamp.repeater:
        emit(base)
        return results

    sign, n, unit = stamp.repeater
    if n <= 0:
        emit(base)
        return results

    ws_n = win_start.replace(tzinfo=None)
    we_n = win_end.replace(tzinfo=None)

    if unit in ("h", "d", "w"):
        delta = {
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
            "w": timedelta(weeks=n),
        }[unit]
        # Jump straight to the first candidate at/just below the window start.
        k = math.floor((ws_n - base) / delta)
        cur = base + k * delta
        for _ in range(_GUARD):
            if cur > we_n + delta:
                break
            if cur >= base:
                emit(cur)
            cur += delta
    else:
        step = relativedelta(months=n) if unit == "m" else relativedelta(years=n)
        cur = base
        for _ in range(_GUARD):
            if cur > we_n:
                break
            emit(cur)
            cur += step

    return results

"""Public-holiday lookup, wrapping the `holidays` library with per-country caching."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import holidays

log = logging.getLogger("holidays")
_cache: dict = {}


def is_holiday(day: date, country: Optional[str], subdiv: Optional[str]) -> bool:
    if not country:
        return False
    key = (country, subdiv)
    obj = _cache.get(key)
    if obj is None:
        try:
            obj = holidays.country_holidays(country, subdiv=subdiv)
        except Exception as exc:  # unknown country/subdiv -> treat as no holidays
            log.warning("holidays init failed for %s/%s: %s", country, subdiv, exc)
            obj = {}
        _cache[key] = obj
    # `holidays` objects auto-populate the year on membership test.
    return day in obj

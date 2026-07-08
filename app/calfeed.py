"""Vacation calendar: fetch a secret iCal URL, cache it, expose covered dates.

Behavior (from SPEC):
  - Fetch over HTTPS on a refresh interval; cache the raw .ics to disk.
  - On fetch failure, use the cached copy.
  - If there is no cache at all and the fetch fails, `available` is False and the
    caller applies its `on_feed_failure` policy (default fail-open = treat as a
    working day).
Any all-day or timed event covering a date marks that whole date non-working;
multi-day DTSTART..DTEND ranges are supported.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from icalendar import Calendar
import recurring_ical_events

log = logging.getLogger("calfeed")

# How far around "today" to expand recurring events into concrete dates.
_LOOKBACK_DAYS = 60
_LOOKAHEAD_DAYS = 400


class VacationCalendar:
    def __init__(self, url: Optional[str], cache_file: str, refresh_seconds: int):
        self.url = url
        self.cache_file = cache_file
        self.refresh_seconds = refresh_seconds
        self._dates: set = set()
        self._last_refresh: Optional[datetime] = None
        self.available = False   # True once we have parsed data (fresh or cached)
        self.last_fetch_ok = True

    def maybe_refresh(self, now: datetime) -> None:
        if not self.url:
            self.available = False
            return
        if (self._last_refresh is not None
                and (now - self._last_refresh).total_seconds() < self.refresh_seconds):
            return
        self._last_refresh = now
        raw = self._fetch_or_cache()
        if raw is None:
            self.available = False
            return
        try:
            self._dates = self._parse(raw, now)
            self.available = True
        except Exception as exc:
            log.warning("failed to parse vacation ics: %s", exc)
            # Keep whatever we had before; only unavailable if we never parsed.

    def is_vacation(self, day: date) -> bool:
        return day in self._dates

    # --- internals ---
    def _fetch_or_cache(self) -> Optional[bytes]:
        try:
            resp = requests.get(self.url, timeout=15)
            resp.raise_for_status()
            raw = resp.content
            self._write_cache(raw)
            self.last_fetch_ok = True
            return raw
        except Exception as exc:
            self.last_fetch_ok = False
            log.warning("vacation feed fetch failed (%s); trying cache", exc)
            return self._read_cache()

    def _read_cache(self) -> Optional[bytes]:
        try:
            with open(self.cache_file, "rb") as fh:
                return fh.read()
        except OSError:
            return None

    def _write_cache(self, raw: bytes) -> None:
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            tmp = self.cache_file + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(raw)
            os.replace(tmp, self.cache_file)
        except OSError as exc:
            log.warning("could not write ics cache: %s", exc)

    @staticmethod
    def _parse(raw: bytes, now: datetime) -> set:
        cal = Calendar.from_ical(raw)
        start = (now - timedelta(days=_LOOKBACK_DAYS)).date()
        end = (now + timedelta(days=_LOOKAHEAD_DAYS)).date()
        covered: set = set()
        for ev in recurring_ical_events.of(cal).between(start, end):
            sd = ev.get("DTSTART").dt
            dt_end = ev.get("DTEND")
            ed = dt_end.dt if dt_end is not None else sd
            all_day = not isinstance(sd, datetime)  # date, not datetime => all-day
            sd_date = sd if all_day else sd.date()
            ed_date = ed if not isinstance(ed, datetime) else ed.date()
            # All-day DTEND is exclusive (last covered day = ed_date - 1). Timed and
            # single-day events cover [sd_date, ed_date] inclusive.
            last = ed_date - timedelta(days=1) if all_day and ed_date > sd_date else ed_date
            day = sd_date
            while day <= last:
                covered.add(day)
                day += timedelta(days=1)
        return covered

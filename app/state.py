"""Persistent state: last_scan watermark + deferred work queue + feed status.

Small JSON file, atomically written. No big "have-I-fired-this" set — once-only
firing comes from time-window matching (see SPEC).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("state")


class State:
    def __init__(self, path: str, tz: ZoneInfo):
        self.path = path
        self.tz = tz
        self.last_scan: Optional[datetime] = None
        self.deferred: list = []          # list of Delivery.to_json() dicts
        self.feed_ok: bool = True         # last-known vacation feed fetch status

    def load(self) -> "State":
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            return self  # first run / unreadable -> defaults
        ls = doc.get("last_scan")
        self.last_scan = datetime.fromisoformat(ls) if ls else None
        self.deferred = doc.get("deferred", [])
        self.feed_ok = doc.get("feed_ok", True)
        return self

    def save(self) -> None:
        doc = {
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "deferred": self.deferred,
            "feed_ok": self.feed_ok,
        }
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("could not persist state: %s", exc)

    def pop_due_deferred(self, now: datetime) -> list:
        """Remove and return deferred entries whose delivery_time <= now."""
        due, keep = [], []
        for entry in self.deferred:
            dt = datetime.fromisoformat(entry["delivery_time"])
            (due if dt <= now else keep).append(entry)
        self.deferred = keep
        return due

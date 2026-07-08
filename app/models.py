"""Dataclasses shared across the notifier."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional


@dataclass(frozen=True)
class GateProfile:
    """When a folder's reminders are allowed to fire.

    kind == "none":      fire at exact time, 24/7 (no gating).
    kind == "workhours": gate to a weekly window, excluding holidays and vacation.
    """
    name: str
    kind: str = "none"
    days: frozenset = frozenset()          # weekday ints, Mon=0 .. Sun=6
    window_start: Optional[time] = None
    window_end: Optional[time] = None      # exclusive
    digest_time: Optional[time] = None     # when the deferred backlog is delivered
    holidays_country: Optional[str] = None
    holidays_subdiv: Optional[str] = None
    vacation_calendar: bool = False
    on_feed_failure: str = "fail-open"     # fail-open | fail-closed


@dataclass(frozen=True)
class Folder:
    name: str
    path: str
    graph: str
    topic: str
    gate: GateProfile
    agenda_page: str
    default_time: time
    keywords: frozenset          # actionable markers, uppercased
    trigger_on: frozenset        # subset of {"SCHEDULED", "DEADLINE"}


@dataclass
class Occurrence:
    """One concrete firing candidate."""
    folder: Folder
    when: datetime               # tz-aware, the occurrence's own time
    kind: str                    # "SCHEDULED" | "DEADLINE"
    task_text: str
    page: str
    block_id: Optional[str] = None

    def deep_link(self) -> str:
        from .ntfy import build_deep_link
        return build_deep_link(self.folder.graph, self.page, self.block_id)


@dataclass
class Delivery:
    """An occurrence resolved to a delivery moment, ready to send or queue."""
    occurrence: Occurrence
    delivery_time: datetime      # tz-aware; == occurrence.when unless deferred
    deferred: bool = False

    # --- serialization for the persistent deferred queue ---
    def to_json(self) -> dict:
        o = self.occurrence
        return {
            "delivery_time": self.delivery_time.isoformat(),
            "deferred": self.deferred,
            "folder": o.folder.name,
            "when": o.when.isoformat(),
            "kind": o.kind,
            "task_text": o.task_text,
            "page": o.page,
            "block_id": o.block_id,
        }

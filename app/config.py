"""Load config.yaml + env secrets into typed objects."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from typing import Optional
from zoneinfo import ZoneInfo

import yaml

from .models import Folder, GateProfile

_DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


def _parse_time(value: str) -> time:
    hh, mm = str(value).strip().split(":")
    return time(int(hh), int(mm))


def _parse_days(values) -> frozenset:
    return frozenset(_DAY_MAP[str(v).strip().lower()[:3]] for v in values)


@dataclass(frozen=True)
class Secrets:
    ntfy_token: str
    vacation_ical_url: Optional[str]


@dataclass(frozen=True)
class Config:
    tz: ZoneInfo
    ntfy_url: str
    admin_topic: str
    poll_seconds: int
    state_file: str
    ics_cache_file: str
    feed_refresh_seconds: int
    folders: tuple
    secrets: Secrets


def _build_profile(name: str, raw: dict) -> GateProfile:
    raw = raw or {}
    # A profile with a window is a workhours gate; otherwise it's a no-op ("none").
    if "window_start" not in raw:
        return GateProfile(name=name, kind="none")
    return GateProfile(
        name=name,
        kind="workhours",
        days=_parse_days(raw.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])),
        window_start=_parse_time(raw["window_start"]),
        window_end=_parse_time(raw["window_end"]),
        digest_time=_parse_time(raw.get("digest_time", "09:00")),
        holidays_country=raw.get("holidays_country"),
        holidays_subdiv=raw.get("holidays_subdiv"),
        vacation_calendar=bool(raw.get("vacation_calendar", False)),
        on_feed_failure=raw.get("on_feed_failure", "fail-open"),
    )


def load(config_path: str = "/app/config.yaml") -> Config:
    with open(config_path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    g = doc["global"]
    defaults = g.get("defaults", {})
    def_keywords = frozenset(k.upper() for k in defaults.get(
        "keywords", ["TODO", "DOING", "NOW", "LATER"]))
    def_trigger = frozenset(t.upper() for t in defaults.get(
        "trigger_on", ["SCHEDULED", "DEADLINE"]))
    def_time = _parse_time(defaults.get("default_time", "09:00"))
    def_journal = defaults.get("journal_date_format")  # None => auto-read per graph

    profiles = {
        name: _build_profile(name, raw)
        for name, raw in (doc.get("gate_profiles") or {}).items()
    }
    profiles.setdefault("none", GateProfile(name="none", kind="none"))

    folders = []
    for f in doc["folders"]:
        prof = profiles[f["gate_profile"]]
        folders.append(Folder(
            name=f["name"],
            path=f["path"],
            graph=f["graph"],
            topic=f["topic"],
            gate=prof,
            agenda_page=f.get("agenda_page", "Agenda"),
            default_time=_parse_time(f["default_time"]) if "default_time" in f else def_time,
            keywords=frozenset(k.upper() for k in f["keywords"]) if "keywords" in f else def_keywords,
            trigger_on=frozenset(t.upper() for t in f["trigger_on"]) if "trigger_on" in f else def_trigger,
            journal_date_format=f.get("journal_date_format", def_journal),
        ))

    token = os.environ.get("NTFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError("NTFY_TOKEN env var is required (ntfy publisher token).")
    ical_url = os.environ.get("VACATION_ICAL_URL", "").strip() or None

    return Config(
        tz=ZoneInfo(g.get("timezone", "Europe/Prague")),
        ntfy_url=g["ntfy_url"].rstrip("/"),
        admin_topic=g.get("admin_topic", "logseq-admin"),
        poll_seconds=int(g.get("poll_seconds", 60)),
        state_file=g.get("state_file", "/data/state.json"),
        ics_cache_file=g.get("ics_cache_file", "/data/vacation.ics"),
        feed_refresh_seconds=int(g.get("feed_refresh_seconds", 1800)),
        folders=tuple(folders),
        secrets=Secrets(ntfy_token=token, vacation_ical_url=ical_url),
    )

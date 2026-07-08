"""ntfy publishing + Logseq deep-link construction + notification formatting."""
from __future__ import annotations

import logging
from urllib.parse import quote

import requests

log = logging.getLogger("ntfy")

# ntfy priorities: 5=max 4=high 3=default 2=low 1=min
_PRIORITY = {"SCHEDULED": 3, "DEADLINE": 4}
# SCHEDULED reminders carry no icon; only the urgent DEADLINE gets one.
_TAGS = {"SCHEDULED": [], "DEADLINE": ["alarm_clock"]}


def build_deep_link(graph: str, page: str, block_id: str | None = None) -> str:
    link = f"logseq://graph/{quote(graph, safe='')}?page={quote(page, safe='')}"
    if block_id:
        link += f"&block-id={quote(block_id, safe='')}"
    return link


class Publisher:
    def __init__(self, base_url: str, token: str, tz):
        self.base_url = base_url.rstrip("/")
        self.tz = tz
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self._fmt_cache: dict = {}   # folder.name -> resolved journal date format

    def _journal_format(self, folder) -> str:
        # Cached: resolve_journal_format may read the graph's config.edn from disk,
        # and the date format is static config (a restart picks up any change).
        fmt = self._fmt_cache.get(folder.name)
        if fmt is None:
            from . import parsing
            fmt = self._fmt_cache[folder.name] = parsing.resolve_journal_format(folder)
        return fmt

    def _post(self, payload: dict) -> bool:
        try:
            resp = self.session.post(self.base_url, json=payload, timeout=15)
            resp.raise_for_status()
            return True
        except Exception as exc:
            log.error("ntfy publish to '%s' failed: %s", payload.get("topic"), exc)
            return False

    def _fmt_time(self, dt) -> str:
        return dt.astimezone(self.tz).strftime("%a %d %b %H:%M")

    def send_occurrence(self, occ, now, on_time: bool) -> bool:
        from . import dateformat
        fmt = self._journal_format(occ.folder)
        # Drop the page when it's just the journal page for the occurrence's own
        # date — that date is already implied by arrival time (on time) or the
        # relative label (late). A task scheduled on a journal page but *for*
        # another day has a page title != its own date, so it survives.
        page = None if occ.page == dateformat.format_date(occ.when.date(), fmt) else occ.page

        if on_time:
            # Arrival == scheduled time, so the timestamp is redundant with
            # ntfy's own — show just the page (or nothing but the title).
            message = page or ""
        else:
            # Late: spell out when it was actually due, relative to now.
            rel = dateformat.humanize(occ.when.astimezone(self.tz),
                                      now.astimezone(self.tz), fmt)
            message = f"{page} · {rel}" if page else rel
        return self._post({
            "topic": occ.folder.topic,
            "title": occ.task_text,
            "message": message,
            "tags": _TAGS.get(occ.kind, []),
            "priority": _PRIORITY.get(occ.kind, 3),
            "click": occ.deep_link(),
        })

    def send_digest(self, folder, deliveries) -> bool:
        """One grouped notification for a batch (deferred backlog / downtime catch-up)."""
        occs = [d.occurrence for d in deliveries]
        lines = []
        for o in sorted(occs, key=lambda x: x.when):
            mark = "⏰" if o.kind == "DEADLINE" else "\U0001f4c5"
            lines.append(f"{mark} {o.task_text} ({self._fmt_time(o.when)})")
        priority = 4 if any(o.kind == "DEADLINE" for o in occs) else 3
        return self._post({
            "topic": folder.topic,
            "title": f"{len(occs)} {folder.name} tasks due",
            "message": "\n".join(lines),
            "tags": ["date"],
            "priority": priority,
            "click": build_deep_link(folder.graph, folder.agenda_page),
        })

    def send_admin(self, topic: str, title: str, message: str,
                   priority: int = 3, tags=None) -> bool:
        return self._post({
            "topic": topic,
            "title": title,
            "message": message,
            "tags": tags or ["gear"],
            "priority": priority,
        })

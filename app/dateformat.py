"""Render a date the way Logseq titles a journal page.

Logseq uses date-fns tokens for its "Preferred date format" (default
``MMM do, yyyy`` -> ``Jul 8th, 2026``). Journal *files* are named ``2026_07_08.md``
but the *page* is titled by that format, and the ``logseq://...?page=`` deep link
must use the title, not the ISO date. This renders the supported tokens.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

DEFAULT_FORMAT = "MMM do, yyyy"   # Logseq's default :journal/page-title-format

# Match an *uncommented* format key in logseq/config.edn. Newer key first.
_EDN_KEYS = (":journal/page-title-format", ":date-formatter")


def read_journal_format(graph_path: str) -> str | None:
    """Read :journal/page-title-format from a graph's logseq/config.edn, or None."""
    cfg = os.path.join(graph_path, "logseq", "config.edn")
    try:
        with open(cfg, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    for key in _EDN_KEYS:
        for m in re.finditer(re.escape(key) + r'\s+"([^"]*)"', text):
            # Skip commented lines (EDN comments start with ';').
            line_start = text.rfind("\n", 0, m.start()) + 1
            if ";" not in text[line_start:m.start()]:
                return m.group(1)
    return None

_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
_MONTHS_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                "Oct", "Nov", "Dec"]
# Python weekday(): Mon=0 .. Sun=6
_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
             "Sunday"]
_WEEKDAYS_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Longer tokens must precede their prefixes in this alternation.
_TOKEN_RE = re.compile(r"yyyy|yy|MMMM|MMM|MM|M|EEEE|EEE|EE|E|do|dd|d")


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def humanize(when: datetime, now: datetime, exact_fmt: str) -> str:
    """Human label for a past ``when`` delivered at ``now`` (both tz-aware, same tz).

    Only the calendar-day gap matters, not elapsed hours:
    ``Today 17:40`` -> ``Yesterday 17:40`` -> ``Sat 09:00`` (2-6 days) ->
    the exact Logseq-formatted date + time (>= 7 days).
    """
    hm = when.strftime("%H:%M")
    days = (now.date() - when.date()).days
    if days <= 0:
        return f"Today {hm}"
    if days == 1:
        return f"Yesterday {hm}"
    if days < 7:
        return f"{_WEEKDAYS_ABBR[when.weekday()]} {hm}"
    return f"{format_date(when.date(), exact_fmt)} {hm}"


def format_date(d: date, fmt: str) -> str:
    def repl(m: re.Match) -> str:
        t = m.group(0)
        return {
            "yyyy": f"{d.year:04d}",
            "yy": f"{d.year % 100:02d}",
            "MMMM": _MONTHS[d.month],
            "MMM": _MONTHS_ABBR[d.month],
            "MM": f"{d.month:02d}",
            "M": str(d.month),
            "EEEE": _WEEKDAYS[d.weekday()],
            "EEE": _WEEKDAYS_ABBR[d.weekday()],
            "EE": _WEEKDAYS_ABBR[d.weekday()],
            "E": _WEEKDAYS_ABBR[d.weekday()],
            "do": _ordinal(d.day),
            "dd": f"{d.day:02d}",
            "d": str(d.day),
        }[t]

    return _TOKEN_RE.sub(repl, fmt)

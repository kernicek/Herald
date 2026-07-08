"""Parse Logseq Markdown into task timestamps.

Logseq stores tasks as bullets whose SCHEDULED/DEADLINE (and id::) usually sit on
indented property lines beneath the bullet:

    - TODO Ship the release notes
      SCHEDULED: <2026-07-08 Wed 09:00 .+1d>
      id:: 66a1f0c2-...-...
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, time
from typing import Optional

from . import dateformat

# Match the date embedded in a journal filename (e.g. 2026_07_08 or 2026-07-08).
_JOURNAL_DATE_RE = re.compile(r"(\d{4})\D(\d{1,2})\D(\d{1,2})")

# Markers we recognize at all (so we can positively skip DONE/CANCELED).
KNOWN_MARKERS = {
    "TODO", "DOING", "NOW", "LATER", "DONE",
    "CANCELED", "CANCELLED", "WAITING", "IN-PROGRESS",
}

_BULLET_RE = re.compile(r"^(\s*)-\s+(.*)$")
_TS_RE = re.compile(
    r"(SCHEDULED|DEADLINE):\s*<"
    r"(\d{4})-(\d{2})-(\d{2})"          # date
    r"(?:\s+[A-Za-z]{1,3})?"            # optional day name (Wed)
    r"(?:\s+(\d{1,2}):(\d{2}))?"        # optional HH:MM
    r"(?:\s+([.+]{1,2})(\d+)([hdwmy]))?"  # optional repeater  .+1d / ++1w / +1m
    r"[^>]*>",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"id::\s*([0-9a-fA-F-]{36})")
_CLEAN_TS_RE = re.compile(r"(SCHEDULED|DEADLINE):\s*<[^>]*>", re.IGNORECASE)


@dataclass
class ParsedStamp:
    kind: str                      # "SCHEDULED" | "DEADLINE"
    base_date: date
    base_time: Optional[time]      # None => date-only
    repeater: Optional[tuple]      # (sign:str, n:int, unit:str) or None
    task_text: str
    page: str
    block_id: Optional[str]


def page_name(folder_path: str, file_path: str,
              journal_format: str = dateformat.DEFAULT_FORMAT) -> str:
    """Best-effort Logseq page name from a Markdown file path.

    Journal pages are titled by the graph's date format (e.g. `yyyy-MM-dd EEE` ->
    `2026-07-08 Wed`), NOT the ISO filename — the deep link must use that title.
    """
    rel = os.path.relpath(file_path, folder_path).replace(os.sep, "/")
    stem = rel[:-3] if rel.lower().endswith(".md") else rel
    if stem.startswith("journals/"):
        name = stem.split("/", 1)[1]
        m = _JOURNAL_DATE_RE.search(name)
        if m:
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                return dateformat.format_date(d, journal_format)
            except ValueError:
                pass
        return name.replace("_", "-")  # fallback if the date can't be parsed
    # Normal pages live in pages/; namespaces are encoded with triple underscores.
    if stem.startswith("pages/"):
        stem = stem.split("/", 1)[1]
    return stem.replace("___", "/")


def _clean_text(text: str) -> str:
    text = _CLEAN_TS_RE.sub("", text)
    text = _ID_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _finalize_block(first_line: str, body_lines: list, page: str,
                    keywords: frozenset, trigger_on: frozenset) -> list:
    tokens = first_line.split(maxsplit=1)
    if not tokens:
        return []
    marker = tokens[0].upper()
    if marker not in KNOWN_MARKERS or marker not in keywords:
        return []  # not a task, or not an actionable marker for this folder

    text_body = tokens[1] if len(tokens) > 1 else ""
    block_text = "\n".join([first_line] + body_lines)

    id_match = _ID_RE.search(block_text)
    block_id = id_match.group(1) if id_match else None
    task_text = _clean_text(text_body) or "(task)"

    stamps = []
    for m in _TS_RE.finditer(block_text):
        kind = m.group(1).upper()
        if kind not in trigger_on:
            continue
        base_date = date(int(m.group(2)), int(m.group(3)), int(m.group(4)))
        base_time = time(int(m.group(5)), int(m.group(6))) if m.group(5) else None
        repeater = None
        if m.group(7):
            repeater = (m.group(7), int(m.group(8)), m.group(9).lower())
        stamps.append(ParsedStamp(
            kind=kind, base_date=base_date, base_time=base_time,
            repeater=repeater, task_text=task_text, page=page, block_id=block_id,
        ))
    return stamps


def parse_text(text: str, page: str, keywords: frozenset,
               trigger_on: frozenset) -> list:
    """Parse one file's text into ParsedStamp records."""
    stamps = []
    first_line = None
    body_lines: list = []

    def flush():
        if first_line is not None:
            stamps.extend(_finalize_block(first_line, body_lines, page,
                                          keywords, trigger_on))

    for line in text.splitlines():
        m = _BULLET_RE.match(line)
        if m:
            flush()
            first_line = m.group(2)
            body_lines = []
        elif first_line is not None:
            body_lines.append(line)
    flush()
    return stamps


def resolve_journal_format(folder) -> str:
    """Journal title format: explicit config override, else the graph's
    logseq/config.edn, else Logseq's default."""
    if folder.journal_date_format:
        return folder.journal_date_format
    return dateformat.read_journal_format(folder.path) or dateformat.DEFAULT_FORMAT


def scan_folder(folder) -> list:
    """Walk a folder's Markdown files and return all ParsedStamp records."""
    stamps = []
    journal_format = resolve_journal_format(folder)
    for root, _dirs, files in os.walk(folder.path):
        for fn in files:
            if not fn.lower().endswith(".md"):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            page = page_name(folder.path, fp, journal_format)
            stamps.extend(parse_text(text, page, folder.keywords, folder.trigger_on))
    return stamps

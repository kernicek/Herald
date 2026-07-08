# Herald — Design Spec (Phase 1)

> **Status: original design snapshot — not maintained.** This captures the Phase 1
> plan as designed up front. It is intentionally frozen; the code and
> [README](README.md) are the living source of truth. Where they diverge from this
> document, they win. Kept for the "why it works this way" rationale.

Exact-time mobile push notifications for Logseq tasks with `SCHEDULED:`/`DEADLINE:`
timestamps, with a work/personal folder split and work-hours + Czech-holiday +
vacation gating for work reminders. Tapping a notification deep-links into the
Logseq Android app.

Phase 1 is **read-only and notify-only**. "Mark done" from the notification is
[Phase 2 (issue #1)](https://github.com/kernicek/herald/issues/1).

## Architecture

```
Logseq (phone) ──Syncthing──> NAS (Markdown files)
                                  │
                                  │  Python notifier daemon (Docker)
                                  │  scans files, matches occurrences, gates, fires
                                  ▼
                            self-hosted ntfy server (Docker, on NAS)
                                  │  push (persistent connection, TLS via Cloudflare tunnel)
                                  ▼
                            ntfy Android app ──tap──> logseq:// deep link
```

## Runtime & process

- **Python daemon**, its own container, `restart: unless-stopped`.
- Internal loop aligned to the top of each minute (**60s poll**).
- Key deps: `holidays` (CZ), `icalendar` + `recurring-ical-events`, an HTTP client,
  a YAML parser.

## Trigger model

Time-window matching — **no persistent "have-I-fired-this" dedup set**. Each poll
fires occurrences whose datetime falls in the interval `(last_scan, now]`. The
one-minute window itself guarantees once-only firing.

- **Actionable markers:** `TODO`, `DOING`, `NOW`, `LATER` (configurable). Skip
  `DONE`/`CANCELED`. Both `SCHEDULED` and `DEADLINE` trigger.
- **Date-only** timestamps (`<2026-07-08 Wed>`) → fire at the folder's
  `default_time`. Deduped once-per-day by the nature of the window.
- **Repeaters** (`.+1d`, `++1w`, `+1m`): enumerate occurrences from the base date;
  each matched once as its minute arrives. Period-based only — the `.+`/`++`/`+`
  distinction is irrelevant to a notify-only tool. Bounded modular check per scan,
  no projection cap needed.
- Marking a task `DONE` before its time silently cancels it — it stops matching on
  the next scan. (Emergent, free.)

## Gating (per-folder profiles)

Each folder has a `gate_profile`:

- **`none`** (personal default): fire at exact time, 24/7.
- **`workhours`** (work default): in-window =
  **Mon–Fri, [09:00, 16:00) Europe/Prague**, excluding:
  - **Public/bank holidays** via the `holidays` library (offline, includes moveable
    feasts like Easter). Country is **configurable** per profile (`holidays_country`,
    e.g. `CZ`), with optional `holidays_subdiv` for regional holidays; omit to disable.
  - **Vacation days** from a dedicated Google Calendar, read via its **secret iCal
    URL** over HTTPS. All-day or timed events covering a day mark the whole day
    non-working; multi-day `DTSTART..DTEND` supported. The `.ics` is **cached to
    disk**; on fetch failure use cache; if no cache, **fail-open** (treat as a
    working day — losing work reminders silently is worse than an extra buzz).

Off-window work occurrences **defer** and are delivered as **one digest** at the
next window open. Digest fires at **09:30** (window opens 09:00; 09:00–09:30 live
tasks still fire at their exact time). Digest tap → the folder's `agenda_page`.

**Delivery mode** (implementation rule): live on-time occurrences are sent
**individually**; batches (a deferred backlog flush, or downtime catch-up) are sent
as a **per-folder digest when more than one item is due**, and as a single
individual notification when exactly one is due (a one-item "digest" would only
lose the precise deep link). A digest of >1 links to `agenda_page`.

**Known limitation (Phase 1):** a deferred work item is delivered from the queue at
its digest time even if the task was completed during the deferral window — the
queue holds a snapshot and Phase 1 doesn't re-locate the block to re-validate it.
Acceptable for reminders; revisited alongside Mark-done (issue #1).

## State

Single **JSON file** (atomic write), tiny:

- `last_scan` watermark.
- Deferred work queue (occurrences awaiting the next window digest).
- Cached vacation `.ics` (may be a separate file alongside).

Behaviors:

- **First run** (no state): `last_scan = now`, **no backfill**. Past-due and
  earlier-today tasks are not announced on startup.
- **Downtime catch-up:** on restart, missed occurrences in `(last_scan, now]` are
  delivered as a **per-folder "while you were away" digest** — same code path as
  the work deferral digest. Nothing lost, no avalanche.

## Deep links

`logseq://graph/<graph>?page=<page>`

- `page` = Markdown filename stem, spaces `%20`-encoded (namespace `/` → `___` in
  filenames).
- Append `&block-id=<uuid>` **only if** the block already has an `id::` property;
  otherwise link page-level. **No file mutation** in Phase 1.
- Graph names: private folder → `Kernel`, work folder → `Logseq-AiP`.

## ntfy

- **Topics:** `logseq-personal`, `logseq-work`, `logseq-admin` (diagnostics:
  feed-stale warnings, crashes, startup ping).
- **Auth (least privilege):**
  - Publisher token — **write** on `logseq-*` (used by the notifier container).
  - Subscriber token — **read** on `logseq-*` (used by the phone).
  - Deny-all default for everyone else.
- **TLS** over the existing Cloudflare tunnel. Direct phone-to-NAS delivery, no
  Firebase, no third parties. No E2E by default; security rests on TLS + auth +
  owning the server.

## Notification format

- **Title:** task text (marker stripped).
- **Body:** page name · time.
- **Tag/emoji:** 📅 `SCHEDULED` / ⏰ `DEADLINE`.
- **Priority:** `DEADLINE` → `high`; `SCHEDULED` → `default`.
- **Click:** the deep link.

## Config

`config.yaml` (mounted) holds global + per-folder settings. **Secrets via env**
(ntfy publisher token, vacation iCal URL). See `config.example.yaml`.

Per-folder fields: `path` (container path), `graph`, `topic`, `gate_profile`,
`agenda_page`, `default_time`, `keywords`, `trigger_on`.

## Deployment

**Two independent Docker Compose stacks**, so ntfy stays a reusable push service:

- **ntfy** — the self-hosted ntfy server, its auth/ACL, and the Cloudflare tunnel
  wiring. General-purpose: other NAS services (backups, uptime monitors, ad-hoc
  scripts) can publish to it with their own tokens. Owns a named external Docker
  network **`ntfy-net`**. Lives in your homelab/infra collection; an illustrative
  example sits in [`ntfy/`](ntfy/).
- **Herald** (this repo's `docker-compose.yml`) — the Python daemon. Joins
  `ntfy-net` (declared `external: true`) and publishes to ntfy **by container name
  over the internal network** (`http://ntfy:80`) — no TLS/tunnel hairpin. The phone
  reaches the *same* server publicly via `https://ntfy.example.com` through the
  tunnel. So `ntfy_url` differs by consumer: internal for Herald, public for the
  phone.

The image is built by GitHub Actions on each `v*` tag and pushed to
`ghcr.io/kernicek/herald`; the target just pulls it. The dependency is one-way
(Herald → ntfy), so each stack deploys, upgrades, and tears down independently.
Create the shared network once: `docker network create ntfy-net`.

Herald volumes:

- The **parent directory holding all Logseq graphs** mounted **read-only** at
  `/graphs` (`GRAPHS_ROOT`). Each `folders[]` entry in `config.yaml` points at
  `/graphs/<graph-subfolder>`. **Adding a graph is config-only** — a new folder
  block plus a subfolder under the parent; no compose change. Name new topics
  `logseq-*` so the existing ntfy ACL/token already covers them. Read-only mount
  protects the notes from any accidental write. (Trade-off vs. per-graph mounts:
  the container sees every subfolder under the parent, which is fine read-only.)
- One writable volume for state + `.ics` cache (`/data`).

## Test path

1. Post one message with `Click: logseq://graph/Kernel?page=Test` and confirm the
   tap opens the page on the device.
2. Then wire up the file scanner and gating.

## Parked (Phase 2+)

- **Mark done** action button ([issue #1](https://github.com/kernicek/herald/issues/1)).
- `/today`-style on-demand summary.
- Half-day vacation granularity.
- Per-folder `SCHEDULED`-only vs `DEADLINE`-only toggle if desired.

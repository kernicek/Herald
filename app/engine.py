"""Per-poll scan/gate/deliver orchestration."""
from __future__ import annotations

import logging
from datetime import datetime

from . import gating, parsing, recurrence
from .models import Delivery, Occurrence

log = logging.getLogger("engine")


class Engine:
    def __init__(self, cfg, state, publisher, vac):
        self.cfg = cfg
        self.state = state
        self.pub = publisher
        self.vac = vac

    def run_once(self, now: datetime) -> None:
        st = self.state

        # First run: set the watermark and do NOT backfill past tasks.
        if st.last_scan is None:
            st.last_scan = now
            st.save()
            log.info("first run: watermark set to %s (no backfill)", now.isoformat())
            return

        win_start, win_end = st.last_scan, now
        if win_end <= win_start:
            return  # clock skew / no time elapsed

        # Downtime => deliver as per-folder digest rather than a burst of buzzes.
        is_catchup = (win_end - win_start).total_seconds() > self.cfg.poll_seconds * 2

        self.vac.maybe_refresh(now)
        self._maybe_alert_feed()

        folder_by_name = {f.name: f for f in self.cfg.folders}
        live_by_folder: dict = {}   # deliver now, individually (on-time)
        batch_by_folder: dict = {}  # deliver as digest (deferred flush / catch-up)

        # 1) Scan files, expand occurrences in the window, route each.
        for folder in self.cfg.folders:
            for stamp in parsing.scan_folder(folder, self.cfg.strip_wikilinks):
                occs = recurrence.expand(stamp, folder.default_time, folder,
                                         self.cfg.tz, win_start, win_end)
                for occ in occs:
                    self._route(occ, now, is_catchup, live_by_folder, batch_by_folder)

        # 2) Flush deferred-queue entries whose delivery moment has arrived.
        for entry in st.pop_due_deferred(now):
            folder = folder_by_name.get(entry["folder"])
            if folder is not None:
                batch_by_folder.setdefault(folder.name, []).append(
                    self._delivery_from_entry(entry, folder))

        # 3) Send.
        live_n = sum(len(v) for v in live_by_folder.values())
        batch_n = sum(len(v) for v in batch_by_folder.values())
        log.debug("scan window (%s, %s] catchup=%s -> live=%d batch=%d deferred_q=%d",
                  win_start.isoformat(), win_end.isoformat(), is_catchup,
                  live_n, batch_n, len(st.deferred))
        self._send(live_by_folder, batch_by_folder, folder_by_name, now)

        # 4) Advance watermark and persist (deferred queue may have changed).
        st.last_scan = now
        st.save()

    # --- routing ---
    def _route(self, occ: Occurrence, now, is_catchup, live, batch) -> None:
        profile = occ.folder.gate
        fires_on_time = (profile.kind == "none"
                         or gating.is_working(occ.when, profile, self.vac, self.cfg.tz))

        if fires_on_time:
            d = Delivery(occurrence=occ, delivery_time=occ.when, deferred=False)
            target = batch if is_catchup else live
            target.setdefault(occ.folder.name, []).append(d)
            return

        # Off-window work task -> defer to the next working-day digest.
        dtime = gating.next_delivery(occ.when, profile, self.vac, self.cfg.tz)
        d = Delivery(occurrence=occ, delivery_time=dtime, deferred=True)
        if dtime <= now:
            batch.setdefault(occ.folder.name, []).append(d)  # missed while down
        else:
            self.state.deferred.append(d.to_json())          # queue for later
            log.info("deferred [%s] %r due %s -> digest %s", occ.folder.topic,
                     occ.task_text,
                     occ.when.astimezone(self.cfg.tz).strftime("%Y-%m-%d %H:%M"),
                     dtime.astimezone(self.cfg.tz).strftime("%Y-%m-%d %H:%M"))

    def _delivery_from_entry(self, entry: dict, folder) -> Delivery:
        occ = Occurrence(
            folder=folder,
            when=datetime.fromisoformat(entry["when"]),
            kind=entry["kind"],
            task_text=entry["task_text"],
            page=entry["page"],
            block_id=entry.get("block_id"),
        )
        return Delivery(
            occurrence=occ,
            delivery_time=datetime.fromisoformat(entry["delivery_time"]),
            deferred=entry.get("deferred", True),
        )

    # --- sending ---
    def _send(self, live, batch, folder_by_name, now) -> None:
        for deliveries in live.values():
            for d in deliveries:
                ok = self.pub.send_occurrence(d.occurrence, now, on_time=True)
                self._log_fire("fired", d.occurrence, ok)

        for fname, deliveries in batch.items():
            if len(deliveries) == 1:
                # A lone item keeps its precise deep link rather than a 1-item digest.
                # It's a late delivery (deferred flush or downtime catch-up).
                ok = self.pub.send_occurrence(deliveries[0].occurrence, now, on_time=False)
                self._log_fire("delivered", deliveries[0].occurrence, ok)
            else:
                ok = self.pub.send_digest(folder_by_name[fname], deliveries)
                log.info("digest [%s] %d tasks%s", fname, len(deliveries),
                         "" if ok else " (SEND FAILED)")

    def _log_fire(self, verb: str, occ, ok: bool) -> None:
        log.info("%s [%s] %r @ %s -> %s%s", verb, occ.folder.topic, occ.task_text,
                 occ.when.astimezone(self.cfg.tz).strftime("%Y-%m-%d %H:%M"),
                 occ.deep_link(), "" if ok else " (SEND FAILED)")

    # --- diagnostics ---
    def _maybe_alert_feed(self) -> None:
        if not self.vac.url:
            return
        ok = self.vac.last_fetch_ok
        if ok == self.state.feed_ok:
            return
        if not ok:
            self.pub.send_admin(
                self.cfg.admin_topic, "Vacation feed degraded",
                "Could not refresh the vacation calendar; work gating is running on "
                "stale/no data (fail-open).", priority=4, tags=["warning"])
        else:
            self.pub.send_admin(
                self.cfg.admin_topic, "Vacation feed recovered",
                "Vacation calendar refresh is working again.",
                tags=["white_check_mark"])
        self.state.feed_ok = ok

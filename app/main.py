"""Entrypoint: build components and run the aligned poll loop."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from . import config as config_mod
from .calfeed import VacationCalendar
from .engine import Engine
from .ntfy import Publisher
from .state import State

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")


def _sleep_to_next_tick(poll_seconds: int) -> None:
    """Sleep so the next scan lands near the top of a poll interval."""
    now = time.time()
    remainder = now % poll_seconds
    time.sleep(max(1.0, poll_seconds - remainder))


def main() -> None:
    cfg = config_mod.load(os.environ.get("CONFIG_PATH", "/app/config.yaml"))
    state = State(cfg.state_file, cfg.tz).load()
    publisher = Publisher(cfg.ntfy_url, cfg.secrets.ntfy_token, cfg.tz)
    vac = VacationCalendar(cfg.secrets.vacation_ical_url, cfg.ics_cache_file,
                           cfg.feed_refresh_seconds, cfg.tz)
    engine = Engine(cfg, state, publisher, vac)

    folders = ", ".join(f"{f.name}->{f.topic}" for f in cfg.folders)
    log.info("notifier starting: tz=%s poll=%ss folders=[%s]",
             cfg.tz.key, cfg.poll_seconds, folders)
    publisher.send_admin(cfg.admin_topic, "Logseq notifier started",
                         f"Watching: {folders}", tags=["rocket"])

    while True:
        try:
            engine.run_once(datetime.now(cfg.tz))
        except Exception:
            log.exception("scan failed; will retry next tick")
            try:
                publisher.send_admin(cfg.admin_topic, "Notifier scan error",
                                     "A scan raised an exception; see container logs.",
                                     priority=4, tags=["warning"])
            except Exception:
                pass
        _sleep_to_next_tick(cfg.poll_seconds)


if __name__ == "__main__":
    main()

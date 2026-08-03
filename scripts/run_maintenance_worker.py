#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import signal
import time
from threading import Event

from splitter.config import APP_ENV
from splitter.jobs import cleanup_expired_jobs, dispatch_pending_jobs, reconcile_jobs
from splitter.observability import configure_error_reporting, configure_logging

LOGGER = logging.getLogger("stemsplitter.maintenance")
STOP = Event()


def _stop(_signum: int, _frame: object) -> None:
    STOP.set()


def main() -> None:
    configure_logging(APP_ENV)
    configure_error_reporting()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    interval = max(15, int(os.getenv("MAINTENANCE_INTERVAL_SECONDS", "60")))
    stale_seconds = max(30, int(os.getenv("JOB_RECONCILE_STALE_SECONDS", "300")))

    while not STOP.is_set():
        started = time.monotonic()
        try:
            dispatched = dispatch_pending_jobs(limit=100)
            reconciled = reconcile_jobs(stale_seconds)
            deleted = cleanup_expired_jobs(limit=100)
            LOGGER.info(
                "maintenance_cycle dispatched=%d reconciled=%d deleted=%d duration_seconds=%.3f",
                len(dispatched),
                len(reconciled),
                len(deleted),
                time.monotonic() - started,
            )
        except Exception:
            LOGGER.exception("maintenance_cycle_failed")
        STOP.wait(interval)


if __name__ == "__main__":
    main()

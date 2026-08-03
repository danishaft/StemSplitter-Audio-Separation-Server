#!/usr/bin/env python3
from __future__ import annotations

import argparse

from splitter.config import APP_ENV, JOB_QUEUE_NAME, REDIS_URL
from splitter.observability import configure_error_reporting, configure_logging


def main() -> None:
    configure_logging(APP_ENV)
    configure_error_reporting()
    parser = argparse.ArgumentParser(description="Run the durable StemSplitter worker")
    parser.add_argument(
        "--burst",
        action="store_true",
        help="process the current queue and exit",
    )
    args = parser.parse_args()

    if not REDIS_URL:
        raise SystemExit("REDIS_URL is required")
    from redis import Redis
    from rq import Queue, Worker

    connection = Redis.from_url(REDIS_URL)
    queue = Queue(JOB_QUEUE_NAME, connection=connection)
    Worker([queue], connection=connection).work(
        burst=args.burst,
        with_scheduler=not args.burst,
    )


if __name__ == "__main__":
    main()

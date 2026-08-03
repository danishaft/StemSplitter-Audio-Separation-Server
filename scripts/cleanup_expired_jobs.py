#!/usr/bin/env python3
from __future__ import annotations

import argparse

from splitter.config import JOB_RETENTION_SECONDS
from splitter.jobs import cleanup_expired_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete expired StemSplitter jobs and media.")
    parser.add_argument("--retention-seconds", type=int, default=JOB_RETENTION_SECONDS)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    deleted = cleanup_expired_jobs(args.retention_seconds, limit=args.limit)
    print(f"Deleted {len(deleted)} expired job(s)")


if __name__ == "__main__":
    main()

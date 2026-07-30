#!/usr/bin/env python3
from __future__ import annotations

import argparse

from splitter.jobs import reconcile_jobs


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile stale StemSplitter jobs.")
    parser.add_argument("--stale-seconds", type=int, default=300)
    args = parser.parse_args()
    reconciled = reconcile_jobs(max(1, args.stale_seconds))
    print(f"Reconciled {len(reconciled)} job(s)")


if __name__ == "__main__":
    main()

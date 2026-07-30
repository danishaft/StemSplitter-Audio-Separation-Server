#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
from pathlib import Path
import statistics
import time

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Load-test lightweight API control-plane routes.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--token")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}

    def request_once(_: int) -> tuple[float, int]:
        started = time.perf_counter()
        response = requests.get(
            f"{args.base_url.rstrip('/')}/capabilities",
            headers=headers,
            timeout=15,
        )
        return time.perf_counter() - started, response.status_code

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        results = list(executor.map(request_once, range(max(1, args.requests))))
    elapsed = time.perf_counter() - started
    latencies = sorted(item[0] for item in results)
    statuses: dict[int, int] = {}
    for _, status in results:
        statuses[status] = statuses.get(status, 0) + 1

    def percentile(fraction: float) -> float:
        index = min(len(latencies) - 1, round((len(latencies) - 1) * fraction))
        return latencies[index] * 1000

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "request_count": len(results),
        "concurrency": args.concurrency,
        "elapsed_seconds": round(elapsed, 4),
        "requests_per_second": round(len(results) / elapsed, 4),
        "mean_ms": round(statistics.fmean(latencies) * 1000, 4),
        "p50_ms": round(percentile(0.50), 4),
        "p95_ms": round(percentile(0.95), 4),
        "p99_ms": round(percentile(0.99), 4),
        "statuses": statuses,
    }
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"report_json={output}")
    print(f"requests={len(results)}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"requests_per_second={len(results) / elapsed:.3f}")
    print(f"mean_ms={report['mean_ms']:.3f}")
    print(f"p50_ms={percentile(0.50):.3f}")
    print(f"p95_ms={percentile(0.95):.3f}")
    print(f"p99_ms={percentile(0.99):.3f}")
    print(f"statuses={statuses}")
    if any(status >= 500 for status in statuses):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

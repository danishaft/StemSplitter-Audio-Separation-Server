#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import time
import uuid

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one API-to-object-storage golden-path job.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument(
        "--resume-job-id",
        help="resume polling an existing job without uploading or dispatching again",
    )
    parser.add_argument("--profile", default="quality_gpu_experimental")
    parser.add_argument("--token")
    parser.add_argument("--max-wait", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.input and not args.resume_job_id:
        parser.error("--input is required unless --resume-job-id is provided")
    source = args.input.expanduser().resolve() if args.input else None
    if source is not None and not source.is_file():
        raise SystemExit(f"Input not found: {source}")
    base_url = args.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    started = time.perf_counter()

    if args.resume_job_id:
        job_id = args.resume_job_id
    else:
        assert source is not None
        upload_response = requests.post(
            f"{base_url}/uploads",
            headers=headers,
            json={"filename": source.name, "content_type": "audio/wav"},
            timeout=30,
        )
        upload_response.raise_for_status()
        upload = upload_response.json()
        with source.open("rb") as handle:
            object_response = requests.put(
                upload["url"],
                headers=upload.get("headers", {}),
                data=handle,
                timeout=120,
            )
        object_response.raise_for_status()

        idempotency_key = f"golden-{source.stem}-{uuid.uuid4().hex}"
        create_response = requests.post(
            f"{base_url}/jobs",
            headers={**headers, "Idempotency-Key": idempotency_key},
            json={
                "profile": args.profile,
                "input": {"filename": source.name, "object": upload["object"]},
            },
            timeout=30,
        )
        create_response.raise_for_status()
        job_id = str(create_response.json()["job_id"])
    deadline = time.monotonic() + args.max_wait
    status: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = requests.get(f"{base_url}/jobs/{job_id}", headers=headers, timeout=30)
        response.raise_for_status()
        status = response.json()
        if status.get("status") in {"completed", "error", "failed", "cancelled"}:
            break
        time.sleep(2)
    else:
        requests.post(f"{base_url}/jobs/{job_id}/cancel", headers=headers, timeout=30)
        raise SystemExit("Golden-path job exceeded max wait and was cancelled")

    artifact_groups = {
        group: sorted(items)
        for group, items in dict(status.get("artifacts") or {}).items()
        if isinstance(items, dict)
    }
    report = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "job_id": job_id,
        "profile": args.profile,
        "input_name": source.name if source else status.get("input_name"),
        "input_size_bytes": source.stat().st_size if source else None,
        "resumed_existing_job": bool(args.resume_job_id),
        "status": status.get("status"),
        "stage": status.get("stage"),
        "error": status.get("error"),
        "gpu_worker_status": status.get("gpu_worker_status"),
        "gpu_worker_reason": status.get("gpu_worker_reason"),
        "stem_contract": status.get("stem_contract"),
        "artifact_groups": artifact_groups,
        "timings": status.get("timings"),
        "unit_economics": status.get("unit_economics"),
        "wall_seconds": round(time.perf_counter() - started, 3),
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"report_json={output}")
    print(f"job_id={job_id}")
    print(f"status={report['status']}")
    print(f"wall_seconds={report['wall_seconds']}")
    if report["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

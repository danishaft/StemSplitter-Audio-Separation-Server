from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROOF_ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "benchmarks" / "hatchet" / "contract-proof.json"


def main() -> int:
    suite = unittest.defaultTestLoader.discover(
        str(PROOF_ROOT),
        pattern="test_contract_*.py",
        top_level_dir=str(PROOF_ROOT),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    docker_available = shutil.which("docker") is not None
    sdk_available = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.util; "
                "raise SystemExit(importlib.util.find_spec('hatchet_sdk') is None)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hatchet_source": {
            "commit": "41b056313b43",
            "tag": "v0.98.7",
            "python_sdk_version": "1.37.0",
        },
        "environment": {
            "python": platform.python_version(),
            "docker_available": docker_available,
            "hatchet_sdk_available": sdk_available,
        },
        "executed_evidence": {
            "contract_tests": {
                "status": "passed" if result.wasSuccessful() else "failed",
                "tests_run": result.testsRun,
                "failures": len(result.failures),
                "errors": len(result.errors),
                "proves": [
                    "stable product job and attempt identifiers",
                    "idempotent product dispatch reservation",
                    "explicit priority and tenant-concurrency metadata",
                    "bounded retry accounting",
                    "cancellation winning over late completion",
                    "callback replay safety",
                    "one terminal effect per product job",
                    "one usage and artifact effect per successful attempt",
                ],
            }
        },
        "source_confirmed_not_executed": {
            "hatchet_primitives": {
                "status": "source_inspected",
                "capabilities": [
                    "status-based idempotency",
                    "runtime priority",
                    "keyed concurrency",
                    "bounded retries and backoff",
                    "run cancellation",
                    "worker task retry metadata",
                ],
            }
        },
        "blocked_evidence": {
            "real_hatchet_campaign": {
                "status": (
                    "not_run"
                    if docker_available and sdk_available
                    else "blocked"
                ),
                "reasons": [
                    reason
                    for reason, blocked in (
                        ("docker_not_installed", not docker_available),
                        ("hatchet_sdk_not_installed", not sdk_available),
                    )
                    if blocked
                ],
                "must_prove": [
                    "server-enforced idempotency collision behavior",
                    "priority scheduling order",
                    "tenant concurrency enforcement",
                    "in-flight cancellation propagation",
                    "worker-process crash reassignment",
                    "bounded server retry behavior",
                    "zero duplicate product effects with real callbacks",
                ],
            }
        },
        "recommendation": (
            "continue_timeboxed_adoption_proof"
            if result.wasSuccessful()
            else "reject_until_contract_failures_are_fixed"
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {REPORT_PATH}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

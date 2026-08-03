from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = (
    ROOT / "datasets/manifests/calibration/acmid-cleaner-v1.json"
)
DEFAULT_SCORES = (
    ROOT / "datasets/manifests/calibration/acmid-cleaner-v1.scores.json"
)
DEFAULT_OUTPUT = (
    ROOT / "datasets/manifests/calibration/acmid-cleaner-v1.report.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score the fixed-threshold ACMID cleaner benchmark."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def score_family(
    candidates: list[dict[str, Any]],
    family: str,
    minimum_precision: float,
    minimum_recall: float,
    minimum_chunks: int,
) -> dict[str, Any]:
    family_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("metadata", {}).get("benchmark_family") == family
    ]
    errors = [
        candidate
        for candidate in family_candidates
        if candidate.get("decision") == "error"
    ]
    rows = []
    for candidate in family_candidates:
        if candidate.get("decision") == "error":
            continue
        positive = candidate["metadata"]["label"] == "positive"
        for probability in candidate["classification"]["probabilities"]:
            rows.append(
                {
                    "positive": positive,
                    "accepted": float(probability) >= 0.995,
                    "song_id": candidate["metadata"]["song_id"],
                }
            )
    positive_count = sum(row["positive"] for row in rows)
    negative_count = len(rows) - positive_count
    accepted = [row for row in rows if row["accepted"]]
    true_positive = sum(row["positive"] for row in accepted)
    false_positive = len(accepted) - true_positive
    precision = true_positive / len(accepted) if accepted else 0.0
    recall = true_positive / positive_count if positive_count else 0.0
    passed = (
        not errors
        and positive_count >= minimum_chunks
        and negative_count >= minimum_chunks
        and precision >= minimum_precision
        and recall >= minimum_recall
    )
    return {
        "status": "passed" if passed else "failed",
        "candidate_count": len(family_candidates),
        "error_count": len(errors),
        "positive_chunk_count": positive_count,
        "negative_chunk_count": negative_count,
        "accepted_chunk_count": len(accepted),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "precision": precision,
        "recall": recall,
        "false_positive_songs": dict(
            Counter(
                row["song_id"]
                for row in accepted
                if not row["positive"]
            )
        ),
    }


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    scores = json.loads(args.scores.read_text(encoding="utf-8"))
    targets = manifest["targets"]
    families = sorted(
        {
            candidate["metadata"]["benchmark_family"]
            for candidate in manifest["candidates"]
        }
    )
    results = {
        family: score_family(
            scores["candidates"],
            family,
            float(targets["minimum_precision"]),
            float(targets["minimum_recall"]),
            int(targets["minimum_chunks_per_label"]),
        )
        for family in families
    }
    passed = all(result["status"] == "passed" for result in results.values())
    report = {
        "schema_version": "1.0",
        "benchmark_id": manifest["benchmark_id"],
        "status": "passed" if passed else "failed",
        "threshold": 0.995,
        "targets": targets,
        "families": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": report["status"],
                "families": {
                    family: {
                        "status": result["status"],
                        "precision": result["precision"],
                        "recall": result["recall"],
                    }
                    for family, result in results.items()
                },
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

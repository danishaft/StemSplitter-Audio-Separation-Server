from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "models/synth_cleaner.yaml"
DEFAULT_SCORES = (
    ROOT / "datasets/manifests/calibration/synth-cleaner-v1.scores.json"
)
DEFAULT_REPORT = (
    ROOT / "datasets/manifests/calibration/synth-cleaner-v1.report.json"
)
LABELS = {"positive", "confuser", "target_absent"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive and validate synth-cleaner decision thresholds."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def flatten_scores(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for candidate in payload.get("candidates", []):
        metadata = candidate.get("metadata", {})
        if candidate.get("decision") == "error":
            continue
        label = metadata.get("label")
        split_name = metadata.get("split")
        if label not in LABELS or split_name not in {
            "calibration",
            "validation",
        }:
            raise RuntimeError("synth_calibration_metadata_invalid")
        for window in candidate["scoring"]["windows"]:
            rows.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "song_id": metadata["song_id"],
                    "label": label,
                    "split": split_name,
                    "positive_score": float(window["positive_score"]),
                    "margin": float(window["margin"]),
                }
            )
    return rows


def accept_metrics(
    rows: list[dict[str, Any]],
    score_threshold: float,
    margin_threshold: float,
) -> dict[str, float | int]:
    accepted = [
        row
        for row in rows
        if row["positive_score"] >= score_threshold
        and row["margin"] >= margin_threshold
    ]
    true_positive = sum(row["label"] == "positive" for row in accepted)
    false_positive = len(accepted) - true_positive
    positive_count = sum(row["label"] == "positive" for row in rows)
    return {
        "accepted": len(accepted),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "precision": (
            true_positive / len(accepted) if accepted else 0.0
        ),
        "recall": true_positive / positive_count if positive_count else 0.0,
    }


def threshold_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    values = sorted({float(row[field]) for row in rows})
    if len(values) <= 201:
        return values
    return [
        values[round(index * (len(values) - 1) / 200)]
        for index in range(201)
    ]


def select_accept_thresholds(
    rows: list[dict[str, Any]],
    target_precision: float,
    minimum_recall: float,
) -> tuple[float, float, dict[str, float | int]]:
    best = None
    for score_threshold in threshold_values(rows, "positive_score"):
        for margin_threshold in threshold_values(rows, "margin"):
            metrics = accept_metrics(rows, score_threshold, margin_threshold)
            if (
                metrics["precision"] < target_precision
                or metrics["recall"] < minimum_recall
            ):
                continue
            rank = (
                metrics["recall"],
                metrics["precision"],
                metrics["accepted"],
                score_threshold,
                margin_threshold,
            )
            if best is None or rank > best[0]:
                best = (
                    rank,
                    score_threshold,
                    margin_threshold,
                    metrics,
                )
    if best is None:
        raise RuntimeError("synth_acceptance_target_unreachable")
    return best[1], best[2], best[3]


def select_reject_threshold(
    rows: list[dict[str, Any]],
    positive_retention: float,
) -> float:
    positive_scores = sorted(
        row["positive_score"]
        for row in rows
        if row["label"] == "positive"
    )
    allowed = math.floor(len(positive_scores) * (1.0 - positive_retention))
    if allowed <= 0:
        return math.nextafter(positive_scores[0], -math.inf)
    return math.nextafter(positive_scores[allowed], -math.inf)


def rejection_metrics(
    rows: list[dict[str, Any]],
    threshold: float,
) -> dict[str, float | int]:
    rejected = [row for row in rows if row["positive_score"] <= threshold]
    rejected_positive = sum(row["label"] == "positive" for row in rejected)
    positive_count = sum(row["label"] == "positive" for row in rows)
    return {
        "rejected": len(rejected),
        "rejected_positive": rejected_positive,
        "positive_false_reject_rate": (
            rejected_positive / positive_count if positive_count else 0.0
        ),
    }


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        f"{split_name}:{label}": sum(
            row["split"] == split_name and row["label"] == label
            for row in rows
        )
        for split_name in ("calibration", "validation")
        for label in sorted(LABELS)
    }


def main() -> int:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    payload = json.loads(args.scores.read_text(encoding="utf-8"))
    rows = flatten_scores(payload)
    row_counts = counts(rows)
    required = config["decision"]
    for label, field in (
        ("positive", "required_positive_examples"),
        ("target_absent", "required_target_absent_examples"),
        ("confuser", "required_confuser_examples"),
    ):
        if row_counts[f"calibration:{label}"] < int(required[field]):
            raise RuntimeError(f"synth_calibration_examples_missing:{label}")

    targets = required["targets"]
    calibration = [row for row in rows if row["split"] == "calibration"]
    validation = [row for row in rows if row["split"] == "validation"]
    accept_threshold, margin_threshold, calibration_accept = (
        select_accept_thresholds(
            calibration,
            float(targets["accept_precision"]),
            float(targets["minimum_accept_recall"]),
        )
    )
    reject_threshold = select_reject_threshold(
        calibration,
        float(targets["positive_retention_after_rejection"]),
    )
    validation_accept = accept_metrics(
        validation,
        accept_threshold,
        margin_threshold,
    )
    calibration_reject = rejection_metrics(calibration, reject_threshold)
    validation_reject = rejection_metrics(validation, reject_threshold)
    passed = (
        validation_accept["precision"] >= float(targets["accept_precision"])
        and validation_accept["recall"]
        >= float(targets["minimum_accept_recall"])
        and validation_reject["positive_false_reject_rate"]
        <= 1.0 - float(targets["positive_retention_after_rejection"])
    )
    report = {
        "schema_version": "1.0",
        "calibration_id": "synth-cleaner-v1",
        "status": "passed" if passed else "failed",
        "window_counts": row_counts,
        "targets": targets,
        "proposed_thresholds": {
            "automatic_accept_threshold": accept_threshold,
            "automatic_reject_threshold": reject_threshold,
            "minimum_margin": margin_threshold,
        },
        "calibration": {
            "acceptance": calibration_accept,
            "rejection": calibration_reject,
        },
        "validation": {
            "acceptance": validation_accept,
            "rejection": validation_reject,
        },
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
                "proposed_thresholds": report["proposed_thresholds"],
                "validation": report["validation"],
                "window_counts": row_counts,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

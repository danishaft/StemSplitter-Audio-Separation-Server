#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.benchmark_corpus import load_and_validate_corpus
from splitter.ground_truth import score_prediction_against_reference
from splitter.util import ensure_dir, file_sha256


RELEASE_STEMS = ("vocals", "instrumental", "drums", "bass", "guitar", "piano", "kick", "snare")
MIN_GROUND_TRUTH_TRACKS_PER_STEM = 10


def _candidate(value: str) -> tuple[str, Path]:
    name, separator, root = value.partition("=")
    if not separator or not name.strip() or not root.strip():
        raise argparse.ArgumentTypeError("Use NAME=/absolute/prediction/root")
    return name.strip(), Path(root).expanduser().resolve()


def _summarize(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "minimum": None}
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "minimum": round(min(values), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score release candidates on a frozen corpus.")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--candidate",
        action="append",
        type=_candidate,
        required=True,
        help="Candidate exports as NAME=/root containing <song-id>/<stem>.wav.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    corpus_path = args.corpus.expanduser().resolve()
    corpus, validation = load_and_validate_corpus(corpus_path, verify_files=True)
    reports: dict[str, object] = {}
    for candidate_name, prediction_root in args.candidate:
        measurements: dict[str, dict[str, list[float]]] = {
            stem: {"si_sdr": [], "sdr": [], "correlation": []}
            for stem in RELEASE_STEMS
        }
        missing: list[dict[str, str]] = []
        for song in corpus["songs"]:
            if song["evidence_level"] != "ground_truth":
                continue
            song_id = str(song["id"])
            reference_root = Path(str(song["reference_root"])).expanduser().resolve()
            for stem in RELEASE_STEMS:
                reference = reference_root / f"{stem}.wav"
                prediction = prediction_root / song_id / f"{stem}.wav"
                if not reference.is_file():
                    continue
                if not prediction.is_file():
                    missing.append({"song_id": song_id, "stem": stem})
                    continue
                score = score_prediction_against_reference(prediction, reference)
                measurements[stem]["si_sdr"].append(score.si_sdr)
                measurements[stem]["sdr"].append(score.sdr)
                measurements[stem]["correlation"].append(score.correlation)

        stem_scores = {
            stem: {metric: _summarize(values) for metric, values in metrics.items()}
            for stem, metrics in measurements.items()
        }
        coverage = {
            stem: int(stem_scores[stem]["si_sdr"]["count"] or 0)
            for stem in RELEASE_STEMS
        }
        reports[candidate_name] = {
            "prediction_root": str(prediction_root),
            "stem_scores": stem_scores,
            "coverage": coverage,
            "missing_predictions": missing,
            "objective_gate_eligible": all(
                count >= MIN_GROUND_TRUTH_TRACKS_PER_STEM for count in coverage.values()
            ),
        }

    payload = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "corpus": asdict(validation),
        "corpus_manifest": str(corpus_path),
        "corpus_sha256": file_sha256(corpus_path),
        "release_stems": list(RELEASE_STEMS),
        "minimum_ground_truth_tracks_per_stem": MIN_GROUND_TRUTH_TRACKS_PER_STEM,
        "candidates": reports,
        "release_claim_eligible": validation.release_claim_eligible
        and bool(reports)
        and all(bool(report["objective_gate_eligible"]) for report in reports.values()),
        "limitations": [
            "Objective metrics do not replace the required blind producer listening gate.",
            "Commercial comparisons require exports generated from the identical mixtures.",
        ],
    }
    output = args.output.expanduser().resolve()
    ensure_dir(output.parent)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"report_json={output}")
    print(f"release_claim_eligible={str(payload['release_claim_eligible']).lower()}")


if __name__ == "__main__":
    main()

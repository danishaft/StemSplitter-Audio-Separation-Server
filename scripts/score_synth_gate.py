from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import librosa
import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.ground_truth import (  # noqa: E402
    _correlation,
    _error_loudness_db,
    _sdr,
    _si_sdr,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score synth candidates on a concatenated BabySlakh gate."
    )
    parser.add_argument("--gate-root", type=Path, required=True)
    parser.add_argument("--prediction-root", type=Path, required=True)
    parser.add_argument(
        "--candidates",
        nargs="+",
        default=("synth", "synth_xlance_v1", "synth_xlance_v2"),
    )
    return parser.parse_args()


def read_aligned(path: Path, sample_rate: int, frames: int) -> np.ndarray:
    audio, current_rate = sf.read(path, always_2d=True, dtype="float32")
    if current_rate != sample_rate:
        audio = librosa.resample(
            audio.T,
            orig_sr=current_rate,
            target_sr=sample_rate,
        ).T.astype(np.float32)
    if len(audio) < frames:
        audio = np.pad(audio, ((0, frames - len(audio)), (0, 0)))
    return audio[:frames]


def score(prediction: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    return {
        "si_sdr": _si_sdr(prediction, reference),
        "sdr": _sdr(prediction, reference),
        "correlation": _correlation(prediction, reference),
        "error_loudness_db": _error_loudness_db(prediction, reference),
    }


def finite_mean(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    return float(np.mean(finite)) if finite else float("-inf")


def main() -> int:
    args = parse_args()
    gate_root = args.gate_root.expanduser().resolve()
    prediction_root = args.prediction_root.expanduser().resolve()
    gate = json.loads((gate_root / "gate.json").read_text(encoding="utf-8"))
    reference, sample_rate = sf.read(
        gate_root / "reference_synth.wav",
        always_2d=True,
        dtype="float32",
    )

    candidates: dict[str, dict[str, object]] = {}
    for candidate in args.candidates:
        prediction = read_aligned(
            prediction_root / f"{candidate}.wav",
            sample_rate,
            len(reference),
        )
        per_segment = []
        for segment in gate["segments"]:
            start = int(
                round(float(segment["gate_start_seconds"]) * sample_rate)
            )
            stop = start + int(
                round(float(segment["duration_seconds"]) * sample_rate)
            )
            per_segment.append(
                {
                    "track_id": segment["track_id"],
                    **score(prediction[start:stop], reference[start:stop]),
                }
            )
        si_sdr_values = [float(item["si_sdr"]) for item in per_segment]
        candidates[candidate] = {
            "aggregate": score(prediction, reference),
            "per_segment": per_segment,
            "mean_segment_si_sdr": finite_mean(si_sdr_values),
            "median_segment_si_sdr": float(np.median(si_sdr_values)),
        }

    wins = {candidate: 0 for candidate in args.candidates}
    for index in range(len(gate["segments"])):
        winner = max(
            args.candidates,
            key=lambda candidate: float(
                candidates[candidate]["per_segment"][index]["si_sdr"]
            ),
        )
        wins[winner] += 1

    winner = max(
        args.candidates,
        key=lambda candidate: float(
            candidates[candidate]["median_segment_si_sdr"]
        ),
    )
    report = {
        "schema_version": "1.0",
        "gate_id": gate["gate_id"],
        "segment_count": gate["segment_count"],
        "candidates": candidates,
        "segment_win_counts": wins,
        "winner_by_median_segment_si_sdr": winner,
        "qualification_scope": "independent_nine_track_positive_source_gate",
    }
    report_path = prediction_root / "qualification.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import librosa
import soundfile as sf
import yaml

from .util import ensure_dir


BABYSLAKH_GROUPS = {
    "bass": {"Bass"},
    "drums": {"Drums"},
    "piano": {"Piano"},
    "guitar": {"Guitar"},
}

BABYSLAKH_OTHER_EXCLUDED_CLASSES = {"Bass", "Drums"}


@dataclass
class GroundTruthStemScore:
    stem_name: str
    prediction_path: str
    reference_path: str
    si_sdr: float
    sdr: float
    correlation: float
    error_loudness_db: float


@dataclass
class GroundTruthSongReport:
    song_name: str
    dataset: str
    success: bool
    scores: dict[str, GroundTruthStemScore] = field(default_factory=dict)
    missing_predictions: list[str] = field(default_factory=list)
    missing_references: list[str] = field(default_factory=list)
    error_message: str | None = None


def _read_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True)
    return audio.astype(np.float32), int(sample_rate)


def _align_audio(prediction: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    length = min(len(prediction), len(reference))
    if length <= 0:
        raise ValueError("audio files are empty")
    return prediction[:length], reference[:length]


def _to_mono(audio: np.ndarray) -> np.ndarray:
    return audio.mean(axis=1) if audio.ndim == 2 else audio


def _power(audio: np.ndarray) -> float:
    return float(np.mean(np.square(audio)) + 1e-12)


def _si_sdr(prediction: np.ndarray, reference: np.ndarray) -> float:
    pred = _to_mono(prediction).astype(np.float64)
    ref = _to_mono(reference).astype(np.float64)
    pred = pred - float(np.mean(pred))
    ref = ref - float(np.mean(ref))
    ref_energy = float(np.sum(ref * ref)) + 1e-12
    target = (float(np.sum(pred * ref)) / ref_energy) * ref
    noise = pred - target
    ratio = (float(np.sum(target * target)) + 1e-12) / (float(np.sum(noise * noise)) + 1e-12)
    return float(10.0 * math.log10(ratio))


def _sdr(prediction: np.ndarray, reference: np.ndarray) -> float:
    pred = _to_mono(prediction).astype(np.float64)
    ref = _to_mono(reference).astype(np.float64)
    noise = ref - pred
    return float(10.0 * math.log10((float(np.sum(ref * ref)) + 1e-12) / (float(np.sum(noise * noise)) + 1e-12)))


def _correlation(prediction: np.ndarray, reference: np.ndarray) -> float:
    pred = _to_mono(prediction).astype(np.float64)
    ref = _to_mono(reference).astype(np.float64)
    pred_std = float(np.std(pred))
    ref_std = float(np.std(ref))
    if pred_std < 1e-12 or ref_std < 1e-12:
        return 0.0
    return float(np.corrcoef(pred, ref)[0, 1])


def _error_loudness_db(prediction: np.ndarray, reference: np.ndarray) -> float:
    error = _to_mono(reference) - _to_mono(prediction)
    return float(10.0 * math.log10(_power(error) / _power(_to_mono(reference))))


def score_prediction_against_reference(prediction_path: Path, reference_path: Path) -> GroundTruthStemScore:
    prediction, pred_sr = _read_audio(prediction_path)
    reference, ref_sr = _read_audio(reference_path)
    if pred_sr != ref_sr:
        prediction = librosa.resample(prediction.T, orig_sr=pred_sr, target_sr=ref_sr).T.astype(np.float32)
    prediction, reference = _align_audio(prediction, reference)
    stem_name = prediction_path.stem
    return GroundTruthStemScore(
        stem_name=stem_name,
        prediction_path=str(prediction_path.resolve()),
        reference_path=str(reference_path.resolve()),
        si_sdr=_si_sdr(prediction, reference),
        sdr=_sdr(prediction, reference),
        correlation=_correlation(prediction, reference),
        error_loudness_db=_error_loudness_db(prediction, reference),
    )


def build_babyslakh_references(track_dir: Path, output_dir: Path) -> dict[str, Path]:
    metadata_path = track_dir / "metadata.yaml"
    stems_dir = track_dir / "stems"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    grouped_sources: dict[str, list[Path]] = {name: [] for name in BABYSLAKH_GROUPS}
    for stem_id, stem_info in metadata.get("stems", {}).items():
        inst_class = str(stem_info.get("inst_class", ""))
        stem_path = stems_dir / f"{stem_id}.wav"
        if not stem_path.exists():
            continue
        for group_name, classes in BABYSLAKH_GROUPS.items():
            if inst_class in classes:
                grouped_sources[group_name].append(stem_path)
        if inst_class not in BABYSLAKH_OTHER_EXCLUDED_CLASSES:
            grouped_sources.setdefault("other", []).append(stem_path)

    references: dict[str, Path] = {}
    ref_dir = ensure_dir(output_dir)
    for group_name, source_paths in grouped_sources.items():
        if not source_paths:
            continue
        mixed: np.ndarray | None = None
        sample_rate: int | None = None
        for source_path in source_paths:
            audio, sr = _read_audio(source_path)
            if sample_rate is None:
                sample_rate = sr
            elif sample_rate != sr:
                raise RuntimeError(f"reference sample rate mismatch in {track_dir}")
            mixed = audio if mixed is None else mixed[: len(audio)] + audio[: len(mixed)]
        assert mixed is not None and sample_rate is not None
        target = ref_dir / f"{group_name}.wav"
        sf.write(target, mixed, sample_rate, subtype="PCM_16")
        references[group_name] = target
    return references


def evaluate_manifest_against_babyslakh(
    manifest: dict[str, Any],
    track_dir: Path,
    output_dir: Path,
) -> GroundTruthSongReport:
    report = GroundTruthSongReport(
        song_name=track_dir.name,
        dataset="babyslakh",
        success=False,
    )
    try:
        references = build_babyslakh_references(track_dir, ensure_dir(output_dir / "references"))
        predictions = dict(manifest.get("published_broad_stems", {}))
        predictions.update(manifest.get("published_derived_stems", {}))
        for stem_name, reference_path in references.items():
            payload = predictions.get(stem_name)
            if not payload:
                report.missing_predictions.append(stem_name)
                continue
            prediction_path = Path(str(payload["path"]))
            if not prediction_path.exists():
                report.missing_predictions.append(stem_name)
                continue
            score = score_prediction_against_reference(prediction_path, reference_path)
            score.stem_name = stem_name
            report.scores[stem_name] = score
        for stem_name in [*BABYSLAKH_GROUPS, "other"]:
            if stem_name not in references:
                report.missing_references.append(stem_name)
        report.success = bool(report.scores) and not report.error_message
    except Exception as exc:
        report.error_message = str(exc)
    return report


def ground_truth_report_to_dict(report: GroundTruthSongReport) -> dict[str, Any]:
    return {
        "song_name": report.song_name,
        "dataset": report.dataset,
        "success": report.success,
        "missing_predictions": report.missing_predictions,
        "missing_references": report.missing_references,
        "error_message": report.error_message,
        "scores": {
            stem_name: {
                "prediction_path": score.prediction_path,
                "reference_path": score.reference_path,
                "si_sdr": score.si_sdr,
                "sdr": score.sdr,
                "correlation": score.correlation,
                "error_loudness_db": score.error_loudness_db,
            }
            for stem_name, score in report.scores.items()
        },
    }


def write_ground_truth_report(report: GroundTruthSongReport, output_path: Path) -> Path:
    payload = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        **ground_truth_report_to_dict(report),
    }
    ensure_dir(output_path.parent)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path

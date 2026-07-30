from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from .ground_truth import score_prediction_against_reference
from .util import ensure_dir, file_sha256


EXPECTED_SPEECH_MUSIC_SFX = {
    "speech_dialog": ("speech_dialog.wav", "speech.wav", "dialog.wav"),
    "music": ("music.wav",),
    "sfx": ("sfx.wav", "effects.wav", "sound_effects.wav"),
}


@dataclass(frozen=True)
class ExternalStemBenchmarkConfig:
    benchmark_id: str
    system_name: str
    input_path: Path
    prediction_dir: Path
    output_dir: Path
    reference_dir: Path | None = None
    comparator_dirs: tuple[Path, ...] = ()


def _read_audio(path: Path, *, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True)
    audio = audio.astype(np.float32)
    if target_sr is not None and sample_rate != target_sr:
        audio = librosa.resample(audio.T, orig_sr=sample_rate, target_sr=target_sr).T.astype(np.float32)
        sample_rate = target_sr
    return audio, int(sample_rate)


def _to_mono(audio: np.ndarray) -> np.ndarray:
    return audio.mean(axis=1) if audio.ndim == 2 else audio.astype(np.float32)


def _align_length(items: list[np.ndarray]) -> list[np.ndarray]:
    length = min(len(item) for item in items)
    return [item[:length] for item in items]


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio))) + 1e-12)


def _power(audio: np.ndarray) -> float:
    return float(np.mean(np.square(audio)) + 1e-12)


def _db_ratio(numerator: float, denominator: float) -> float:
    return float(20.0 * math.log10(max(numerator, 1e-12) / max(denominator, 1e-12)))


def _sdr(prediction: np.ndarray, reference: np.ndarray) -> float:
    pred = _to_mono(prediction).astype(np.float64)
    ref = _to_mono(reference).astype(np.float64)
    pred, ref = _align_length([pred, ref])
    error = ref - pred
    return float(10.0 * math.log10((float(np.sum(ref * ref)) + 1e-12) / (float(np.sum(error * error)) + 1e-12)))


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    left_mono = _to_mono(left).astype(np.float64)
    right_mono = _to_mono(right).astype(np.float64)
    left_mono, right_mono = _align_length([left_mono, right_mono])
    if float(np.std(left_mono)) < 1e-12 or float(np.std(right_mono)) < 1e-12:
        return 0.0
    return float(np.corrcoef(left_mono, right_mono)[0, 1])


def _active_ratio(audio: np.ndarray, sample_rate: int) -> float:
    mono = _to_mono(audio)
    frame = max(1024, int(sample_rate * 0.046))
    hop = max(256, frame // 4)
    rms = librosa.feature.rms(y=mono, frame_length=frame, hop_length=hop)[0]
    if rms.size == 0:
        return 0.0
    threshold = max(float(np.max(rms)) * 0.08, 1e-6)
    return float(np.mean(rms >= threshold))


def _find_stem(directory: Path | None, stem_name: str) -> Path | None:
    if directory is None:
        return None
    for filename in EXPECTED_SPEECH_MUSIC_SFX[stem_name]:
        path = directory / filename
        if path.exists():
            return path
    return None


def _stem_file_metrics(path: Path, audio: np.ndarray, sample_rate: int, mixture: np.ndarray) -> dict[str, Any]:
    audio, mixture = _align_length([audio, mixture])
    rms = _rms(audio)
    mixture_rms = _rms(mixture)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    clipped_ratio = float(np.mean(np.abs(audio) >= 0.999)) if audio.size else 0.0
    finite = bool(np.all(np.isfinite(audio)))
    duration = float(len(audio) / sample_rate)
    return {
        "path": str(path.resolve()),
        "sha256": file_sha256(path),
        "duration_seconds": round(duration, 4),
        "sample_rate": sample_rate,
        "channels": int(audio.shape[1]) if audio.ndim == 2 else 1,
        "rms": round(rms, 8),
        "rms_db_vs_mixture": round(_db_ratio(rms, mixture_rms), 3),
        "peak": round(peak, 6),
        "clipped_sample_ratio": round(clipped_ratio, 8),
        "active_ratio": round(_active_ratio(audio, sample_rate), 4),
        "finite": finite,
    }


def _reference_scores(
    predictions: dict[str, Path],
    reference_dir: Path | None,
    mixture: np.ndarray,
    sample_rate: int,
) -> dict[str, Any]:
    if reference_dir is None:
        return {}
    scores: dict[str, Any] = {}
    for stem_name, prediction_path in predictions.items():
        reference_path = _find_stem(reference_dir, stem_name)
        if reference_path is None:
            continue
        reference, _ = _read_audio(reference_path, target_sr=sample_rate)
        prediction, _ = _read_audio(prediction_path, target_sr=sample_rate)
        if _rms(reference) < 1e-7:
            prediction, aligned_mix = _align_length([prediction, mixture])
            leakage_db = _db_ratio(_rms(prediction), _rms(aligned_mix))
            scores[stem_name] = {
                "reference_path": str(reference_path.resolve()),
                "silence_reference": True,
                "leakage_rms_db_vs_input": round(leakage_db, 3),
                "prediction_peak": round(float(np.max(np.abs(prediction))) if prediction.size else 0.0, 6),
                "silence_pass": leakage_db <= -35.0,
            }
        else:
            score = score_prediction_against_reference(prediction_path, reference_path)
            scores[stem_name] = {
                "reference_path": str(reference_path.resolve()),
                "silence_reference": False,
                "si_sdr": round(score.si_sdr, 4),
                "sdr": round(score.sdr, 4),
                "correlation": round(score.correlation, 4),
                "error_loudness_db": round(score.error_loudness_db, 4),
            }
    return scores


def _comparator_scores(predictions: dict[str, Path], comparator_dirs: tuple[Path, ...]) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    for comparator_dir in comparator_dirs:
        comparator_name = comparator_dir.name
        comparator_result: dict[str, Any] = {}
        for stem_name, prediction_path in predictions.items():
            comparator_path = _find_stem(comparator_dir, stem_name)
            if comparator_path is None:
                continue
            prediction, sr = _read_audio(prediction_path)
            comparator, _ = _read_audio(comparator_path, target_sr=sr)
            comparator_result[stem_name] = {
                "comparator_path": str(comparator_path.resolve()),
                "correlation_to_comparator": round(_correlation(prediction, comparator), 4),
                "sdr_to_comparator": round(_sdr(prediction, comparator), 4),
                "rms_db_vs_comparator": round(_db_ratio(_rms(prediction), _rms(comparator)), 3),
            }
        scores[comparator_name] = comparator_result
    return scores


def run_external_stem_benchmark(config: ExternalStemBenchmarkConfig) -> dict[str, Any]:
    input_path = config.input_path.expanduser().resolve()
    prediction_dir = config.prediction_dir.expanduser().resolve()
    output_dir = ensure_dir(config.output_dir.expanduser().resolve())
    mixture, sample_rate = _read_audio(input_path)

    predictions = {
        stem_name: path
        for stem_name in EXPECTED_SPEECH_MUSIC_SFX
        if (path := _find_stem(prediction_dir, stem_name)) is not None
    }
    missing_stems = [stem_name for stem_name in EXPECTED_SPEECH_MUSIC_SFX if stem_name not in predictions]
    stem_audio = {stem_name: _read_audio(path, target_sr=sample_rate)[0] for stem_name, path in predictions.items()}

    stem_metrics = {
        stem_name: _stem_file_metrics(predictions[stem_name], audio, sample_rate, mixture)
        for stem_name, audio in stem_audio.items()
    }

    pairwise_correlations: dict[str, float] = {}
    for left_name, left_audio in stem_audio.items():
        for right_name, right_audio in stem_audio.items():
            if left_name >= right_name:
                continue
            pairwise_correlations[f"{left_name}__{right_name}"] = round(_correlation(left_audio, right_audio), 4)

    reconstruction: dict[str, Any] = {}
    if len(stem_audio) == len(EXPECTED_SPEECH_MUSIC_SFX):
        aligned = _align_length([mixture, *stem_audio.values()])
        aligned_mix = aligned[0]
        aligned_stems = aligned[1:]
        stem_sum = np.sum(np.stack(aligned_stems, axis=0), axis=0)
        residual = aligned_mix - stem_sum
        reconstruction = {
            "stem_sum_sdr_to_input": round(_sdr(stem_sum, aligned_mix), 4),
            "residual_rms_db_vs_input": round(_db_ratio(_rms(residual), _rms(aligned_mix)), 3),
            "stem_sum_rms_db_vs_input": round(_db_ratio(_rms(stem_sum), _rms(aligned_mix)), 3),
        }

    reference_scores = _reference_scores(
        predictions,
        config.reference_dir.expanduser().resolve() if config.reference_dir else None,
        mixture,
        sample_rate,
    )
    comparator_scores = _comparator_scores(
        predictions,
        tuple(path.expanduser().resolve() for path in config.comparator_dirs),
    )

    warnings: list[str] = []
    warnings.extend(f"missing_{stem_name}" for stem_name in missing_stems)
    for stem_name, metrics in stem_metrics.items():
        if not metrics["finite"]:
            warnings.append(f"{stem_name}_contains_nan_or_inf")
        if float(metrics["rms"]) < 1e-5:
            warnings.append(f"{stem_name}_near_silent")
        if float(metrics["clipped_sample_ratio"]) > 0.001:
            warnings.append(f"{stem_name}_clipping_detected")
    for pair_name, corr in pairwise_correlations.items():
        if abs(corr) > 0.95:
            warnings.append(f"{pair_name}_possible_duplicate")

    evidence_level = "no_reference_sanity"
    if reference_scores:
        evidence_level = "ground_truth_reference"
    elif any(comparator_scores.values()):
        evidence_level = "comparator_similarity"

    payload: dict[str, Any] = {
        "benchmark_id": config.benchmark_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "system_name": config.system_name,
        "evidence_level": evidence_level,
        "quality_claim": (
            "ground_truth_scored" if evidence_level == "ground_truth_reference"
            else "not_quality_benchmark_without_ground_truth"
        ),
        "input": {
            "path": str(input_path),
            "sha256": file_sha256(input_path),
            "duration_seconds": round(float(len(mixture) / sample_rate), 4),
            "sample_rate": sample_rate,
            "channels": int(mixture.shape[1]) if mixture.ndim == 2 else 1,
        },
        "prediction_dir": str(prediction_dir),
        "reference_dir": str(config.reference_dir.expanduser().resolve()) if config.reference_dir else None,
        "comparator_dirs": [str(path.expanduser().resolve()) for path in config.comparator_dirs],
        "missing_stems": missing_stems,
        "stem_metrics": stem_metrics,
        "pairwise_correlations": pairwise_correlations,
        "reconstruction": reconstruction,
        "reference_scores": reference_scores,
        "comparator_scores": comparator_scores,
        "sanity_pass": not warnings,
        "warnings": warnings,
    }
    (output_dir / f"{config.benchmark_id}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / f"{config.benchmark_id}.md").write_text(
        external_benchmark_markdown(payload),
        encoding="utf-8",
    )
    return payload


def external_benchmark_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# External stem benchmark {payload['benchmark_id']}",
        "",
        "This report records evidence for a speech, music, and SFX external",
        "runner. It is not a production quality claim unless ground-truth",
        "reference scores are present.",
        "",
        f"- System: `{payload['system_name']}`",
        f"- Evidence level: `{payload['evidence_level']}`",
        f"- Quality claim: `{payload['quality_claim']}`",
        f"- Sanity pass: `{payload['sanity_pass']}`",
        f"- Missing stems: `{', '.join(payload['missing_stems']) or 'none'}`",
        f"- Warnings: `{', '.join(payload['warnings']) or 'none'}`",
        "",
        "## Stem metrics",
        "",
        "| Stem | Duration | RMS dB vs input | Peak | Active ratio | Clipped ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for stem_name, metrics in sorted(payload["stem_metrics"].items()):
        lines.append(
            f"| `{stem_name}` | {metrics['duration_seconds']:.3f} | "
            f"{metrics['rms_db_vs_mixture']:.3f} | {metrics['peak']:.6f} | "
            f"{metrics['active_ratio']:.4f} | {metrics['clipped_sample_ratio']:.8f} |"
        )
    lines.extend(["", "## Reconstruction", ""])
    if payload["reconstruction"]:
        for key, value in payload["reconstruction"].items():
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- Reconstruction was not computed because one or more stems are missing.")

    lines.extend(["", "## Pairwise correlations", ""])
    if payload["pairwise_correlations"]:
        for key, value in sorted(payload["pairwise_correlations"].items()):
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No pairwise correlations were computed.")

    lines.extend(["", "## Reference scores", ""])
    if payload["reference_scores"]:
        for stem_name, scores in sorted(payload["reference_scores"].items()):
            if scores.get("silence_reference"):
                lines.append(
                    f"- `{stem_name}`: silence target, leakage "
                    f"`{scores['leakage_rms_db_vs_input']}` dB vs input, "
                    f"pass `{scores['silence_pass']}`"
                )
            else:
                lines.append(
                    f"- `{stem_name}`: SI-SDR `{scores['si_sdr']}`, "
                    f"SDR `{scores['sdr']}`, correlation `{scores['correlation']}`"
                )
    else:
        lines.append("- No ground-truth reference directory was supplied.")

    lines.extend(["", "## Comparator scores", ""])
    if any(payload["comparator_scores"].values()):
        for comparator_name, stems in sorted(payload["comparator_scores"].items()):
            for stem_name, scores in sorted(stems.items()):
                lines.append(
                    f"- `{comparator_name}/{stem_name}`: correlation "
                    f"`{scores['correlation_to_comparator']}`, "
                    f"SDR-to-comparator `{scores['sdr_to_comparator']}`"
                )
    else:
        lines.append("- No comparator directory was supplied.")
    lines.append("")
    return "\n".join(lines)

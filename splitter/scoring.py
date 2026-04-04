from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from pretty_midi_fix import PrettyMIDI

from .config import AUDIO_SCORE_CONFIG


def _read_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True)
    return audio.astype(np.float32), sample_rate


def _to_mono(audio: np.ndarray) -> np.ndarray:
    return audio.mean(axis=1) if audio.ndim == 2 else audio.astype(np.float32)


def _rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio))) + 1e-12)


def _bounded_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    if value <= 0:
        return 0.0
    if low <= value <= high:
        return 1.0
    if value < low:
        return max(0.0, min(1.0, value / max(low, 1e-6)))
    overshoot = (value - high) / max(high, 1e-6)
    return max(0.0, min(1.0, 1.0 - overshoot))


def _band_focus(audio: np.ndarray, sample_rate: int, low: float | None, high: float | None) -> float:
    if len(audio) < 8:
        return 0.0
    spectrum = np.abs(np.fft.rfft(audio))
    freqs = np.fft.rfftfreq(len(audio), d=1.0 / sample_rate)
    if low is None:
        low = 0.0
    if high is None:
        high = float(freqs[-1])
    mask = (freqs >= low) & (freqs <= high)
    total = float(np.sum(spectrum)) + 1e-12
    focused = float(np.sum(spectrum[mask]))
    return max(0.0, min(1.0, focused / total))


def _active_ratio(audio: np.ndarray) -> float:
    if len(audio) < 1024:
        return 1.0 if np.max(np.abs(audio)) > 1e-4 else 0.0
    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
    threshold = max(float(np.max(rms)) * 0.12, 1e-5)
    active = float(np.mean(rms >= threshold))
    return max(0.0, min(1.0, active))


def _transient_density(audio: np.ndarray, sample_rate: int) -> float:
    onset_env = librosa.onset.onset_strength(y=audio, sr=sample_rate)
    if onset_env.size == 0:
        return 0.0
    peaks = onset_env > (float(np.mean(onset_env)) + float(np.std(onset_env)))
    duration = max(len(audio) / sample_rate, 1e-6)
    return float(np.sum(peaks) / duration)


def _spectral_stability(audio: np.ndarray, sample_rate: int) -> float:
    if len(audio) < 2048:
        return 1.0
    centroid = librosa.feature.spectral_centroid(y=audio, sr=sample_rate)[0]
    if centroid.size <= 1:
        return 1.0
    delta = float(np.mean(np.abs(np.diff(centroid))) / (np.mean(centroid) + 1e-6))
    return max(0.0, min(1.0, 1.0 - min(delta / 0.6, 1.0)))


def _spectral_bleed_score(
    candidate_audio: np.ndarray,
    parent_audio: np.ndarray,
    sample_rate: int,
    family: str,
) -> float:
    """Measure spectral bleed from non-target frequencies.
    
    Compares candidate spectrum to parent spectrum outside the family's
    target band. High energy outside the band indicates poor isolation.
    """
    if len(candidate_audio) < 2048 or len(parent_audio) < 2048:
        return 0.5  # Default score for short audio
    
    # Get target band for family
    config = AUDIO_SCORE_CONFIG.get(family, {})
    band_low = config.get("band_low", 0.0)
    band_high = config.get("band_high", None)
    
    # Compute spectra
    candidate_spec = np.abs(np.fft.rfft(candidate_audio))
    parent_spec = np.abs(np.fft.rfft(parent_audio))
    
    freqs = np.fft.rfftfreq(len(candidate_audio), d=1.0 / sample_rate)
    
    # Mask for out-of-band frequencies (where bleed would show)
    if band_low is None:
        band_low = 0.0
    if band_high is None:
        band_high = float(freqs[-1])
    
    out_of_band = (freqs < band_low) | (freqs > band_high)
    
    # Normalize spectra
    candidate_total = float(np.sum(candidate_spec)) + 1e-12
    parent_total = float(np.sum(parent_spec)) + 1e-12
    
    # Energy in out-of-band region
    candidate_ooo = float(np.sum(candidate_spec[out_of_band])) / candidate_total
    parent_ooo = float(np.sum(parent_spec[out_of_band])) / parent_total
    
    # Good isolation: candidate has LESS out-of-band energy than parent
    # Bad isolation (bleed): candidate has similar or more out-of-band energy
    if parent_ooo < 0.05:  # Parent is already very clean
        return 0.7
    
    bleed_ratio = candidate_ooo / max(parent_ooo, 1e-6)
    
    # Score: 1.0 = no bleed (bleed_ratio < 0.5), 0.0 = heavy bleed (bleed_ratio > 1.0)
    score = 1.0 - min(bleed_ratio, 1.0)
    return max(0.0, min(1.0, score))


def _residual_energy_ratio(
    candidate_audio: np.ndarray,
    parent_audio: np.ndarray,
    sample_rate: int,
    family: str,
) -> float:
    """Measure residual energy that should have been isolated.
    
    For a well-isolated stem, the candidate should capture most of the
    parent's energy in the target band.
    """
    if len(candidate_audio) < 1024 or len(parent_audio) < 1024:
        return 0.5
    
    config = AUDIO_SCORE_CONFIG.get(family, {})
    band_low = config.get("band_low", 0.0)
    band_high = config.get("band_high", None)
    
    if band_low is None:
        band_low = 0.0
    if band_high is None:
        band_high = float(np.fft.rfftfreq(len(candidate_audio), d=1.0 / sample_rate)[-1])
    
    # Compute spectra
    candidate_spec = np.abs(np.fft.rfft(candidate_audio))
    parent_spec = np.abs(np.fft.rfft(parent_audio))
    freqs = np.fft.rfftfreq(len(candidate_audio), d=1.0 / sample_rate)
    
    # Mask for target band
    in_band = (freqs >= band_low) & (freqs <= band_high)
    
    candidate_in_band = float(np.sum(candidate_spec[in_band]))
    parent_in_band = float(np.sum(parent_spec[in_band]))
    
    if parent_in_band < 1e-6:
        return 1.0  # No energy to capture
    
    # Ratio of captured energy
    ratio = candidate_in_band / max(parent_in_band, 1e-6)
    
    # Ideal: 0.3-0.8 (good capture without over-capture)
    if 0.3 <= ratio <= 0.8:
        return 1.0
    elif ratio < 0.3:
        return ratio / 0.3  # Under-capture
    else:
        return max(0.0, 1.0 - (ratio - 0.8) / 0.4)  # Over-capture penalty


def _reason_from_metrics(metrics: dict[str, float], warnings: list[str], threshold: float) -> str:
    if metrics.get("quality_score", 0.0) >= threshold:
        return "quality_score_pass"
    if warnings:
        return warnings[0]
    if metrics.get("band_focus_score", 0.0) < 0.45:
        return "weak_band_focus"
    if metrics.get("relative_energy_score", 0.0) < 0.45:
        return "too_quiet_relative_to_parent"
    if metrics.get("inverse_parent_leakage", 0.0) < 0.35:
        return "captures_too_much_parent_energy"
    if metrics.get("transient_consistency", 1.0) < 0.35:
        return "weak_transient_focus"
    if metrics.get("spectral_stability", 1.0) < 0.35:
        return "unstable_spectral_profile"
    if metrics.get("spectral_bleed", 0.5) < 0.4:
        return "high_spectral_bleed"
    if metrics.get("residual_capture", 0.5) < 0.35:
        return "poor_residual_capture"
    return "quality_score_below_threshold"


def score_audio_candidate(candidate: dict[str, object], threshold: float) -> dict[str, object]:
    path = Path(str(candidate["path"]))
    parent_path = Path(str(candidate["parent_path"]))
    family = str(candidate["family"])
    config = AUDIO_SCORE_CONFIG[family]

    child_audio, child_sample_rate = _read_audio(path)
    parent_audio, parent_sample_rate = _read_audio(parent_path)
    if child_sample_rate != parent_sample_rate:
        raise RuntimeError("Candidate and parent sample rates do not match")

    child_mono = _to_mono(child_audio)
    parent_mono = _to_mono(parent_audio)
    if len(child_mono) != len(parent_mono):
        length = min(len(child_mono), len(parent_mono))
        child_mono = child_mono[:length]
        parent_mono = parent_mono[:length]

    relative_energy_raw = _rms(child_mono) / max(_rms(parent_mono), 1e-6)
    relative_energy_score = _bounded_score(
        relative_energy_raw,
        float(config["energy_low"]),
        float(config["energy_high"]),
    )

    band_focus_raw = _band_focus(
        child_mono,
        child_sample_rate,
        float(config["band_low"]) if config["band_low"] is not None else None,
        float(config["band_high"]) if config["band_high"] is not None else None,
    )
    band_focus_score = _bounded_score(band_focus_raw, 0.35, 0.95)

    max_parent_share = float(config["max_parent_share"])
    parent_leakage_raw = max(
        0.0,
        min(1.0, (relative_energy_raw - max_parent_share) / max(1.0 - max_parent_share, 1e-6)),
    )
    inverse_parent_leakage = 1.0 - parent_leakage_raw

    coverage_raw = _active_ratio(child_mono)
    duration_coverage = _bounded_score(coverage_raw, float(config["coverage_low"]), 0.98)

    transient_consistency = 1.0
    spectral_stability = 1.0
    if bool(config["transient"]):
        peak_density = _transient_density(child_mono, child_sample_rate)
        transient_consistency = _bounded_score(
            peak_density,
            float(config["peak_density_low"]),
            float(config["peak_density_high"]),
        )
    else:
        spectral_stability = _spectral_stability(child_mono, child_sample_rate)

    # NEW: Residual/bleed analysis for Phase 2 completion
    spectral_bleed = _spectral_bleed_score(child_mono, parent_mono, child_sample_rate, family)
    residual_capture = _residual_energy_ratio(child_mono, parent_mono, child_sample_rate, family)

    quality_score = (
        0.20 * relative_energy_score
        + 0.15 * band_focus_score
        + 0.20 * inverse_parent_leakage
        + 0.15 * (transient_consistency if bool(config["transient"]) else spectral_stability)
        + 0.10 * duration_coverage
        + 0.10 * spectral_bleed
        + 0.10 * residual_capture
    )

    warnings: list[str] = []
    if relative_energy_raw < float(config["energy_low"]):
        warnings.append("too_quiet_relative_to_parent")
    if relative_energy_raw > max_parent_share:
        warnings.append("captures_too_much_parent_energy")
    if band_focus_raw < 0.35:
        warnings.append("weak_band_focus")
    if bool(config["transient"]) and transient_consistency < 0.4:
        warnings.append("weak_transient_focus")
    if not bool(config["transient"]) and spectral_stability < 0.4:
        warnings.append("unstable_spectral_profile")
    if coverage_raw < float(config["coverage_low"]):
        warnings.append("sparse_duration_coverage")
    if spectral_bleed < 0.4:
        warnings.append("high_spectral_bleed")
    if residual_capture < 0.35:
        warnings.append("poor_residual_capture")

    metrics = {
        "relative_energy": round(relative_energy_raw, 4),
        "relative_energy_score": round(relative_energy_score, 4),
        "band_focus": round(band_focus_raw, 4),
        "band_focus_score": round(band_focus_score, 4),
        "parent_leakage": round(parent_leakage_raw, 4),
        "inverse_parent_leakage": round(inverse_parent_leakage, 4),
        "duration_coverage": round(duration_coverage, 4),
        "duration_coverage_raw": round(coverage_raw, 4),
        "transient_consistency": round(transient_consistency, 4),
        "spectral_stability": round(spectral_stability, 4),
        "spectral_bleed": round(spectral_bleed, 4),
        "residual_capture": round(residual_capture, 4),
        "quality_score": round(quality_score, 4),
    }

    publish_status = "published" if quality_score >= threshold else "rejected"
    publish_reason = _reason_from_metrics(metrics, warnings, threshold)

    return {
        **candidate,
        "quality_score": round(quality_score, 3),
        "publish_status": publish_status,
        "publish_reason": publish_reason,
        "warnings": warnings,
        "metrics": metrics,
    }


def validate_midi_candidate(
    midi_path: Path,
    *,
    source_name: str,
    source_path: Path,
    audio_duration: float,
    threshold: float,
) -> dict[str, object]:
    warnings: list[str] = []
    metrics: dict[str, float] = {
        "note_count": 0.0,
        "note_density": 0.0,
        "median_note_duration": 0.0,
        "coverage_ratio": 0.0,
        "quality_score": 0.0,
    }
    try:
        midi = PrettyMIDI(str(midi_path))
    except Exception:
        return {
            "path": str(midi_path.resolve()),
            "source_name": source_name,
            "source_path": str(source_path.resolve()),
            "quality_score": 0.0,
            "publish_status": "rejected",
            "publish_reason": "invalid_midi_file",
            "warnings": ["invalid_midi_file"],
            "metrics": metrics,
        }

    notes = [
        note
        for instrument in midi.instruments
        for note in instrument.notes
        if note.end > note.start
    ]
    if not notes:
        return {
            "path": str(midi_path.resolve()),
            "source_name": source_name,
            "source_path": str(source_path.resolve()),
            "quality_score": 0.0,
            "publish_status": "rejected",
            "publish_reason": "empty_midi",
            "warnings": ["empty_midi"],
            "metrics": metrics,
        }

    durations = np.asarray([note.end - note.start for note in notes], dtype=np.float32)
    note_count = len(notes)
    note_density = note_count / max(audio_duration, 1e-6)
    median_note_duration = float(np.median(durations))

    events = sorted((float(note.start), float(note.end)) for note in notes)
    merged: list[list[float]] = []
    for start, end in events:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    coverage_ratio = sum(end - start for start, end in merged) / max(audio_duration, 1e-6)

    density_score = _bounded_score(note_density, 0.2, 12.0)
    duration_score = _bounded_score(median_note_duration, 0.04, 0.8)
    coverage_score = _bounded_score(coverage_ratio, 0.02, 0.85)
    note_count_score = _bounded_score(float(note_count), 1.0, 256.0)
    quality_score = 0.30 * density_score + 0.30 * duration_score + 0.25 * coverage_score + 0.15 * note_count_score

    if note_density > 24.0:
        warnings.append("pathological_note_density")
    if median_note_duration < 0.04:
        warnings.append("subframe_note_durations")
    if coverage_ratio < 0.02:
        warnings.append("low_note_coverage")

    metrics.update(
        {
            "note_count": float(note_count),
            "note_density": round(note_density, 4),
            "median_note_duration": round(median_note_duration, 4),
            "coverage_ratio": round(coverage_ratio, 4),
            "quality_score": round(quality_score, 4),
        }
    )
    publish_status = "published" if quality_score >= threshold and not warnings else "rejected"
    publish_reason = (
        "midi_validation_pass"
        if publish_status == "published"
        else warnings[0] if warnings else "midi_quality_below_threshold"
    )

    return {
        "path": str(midi_path.resolve()),
        "source_name": source_name,
        "source_path": str(source_path.resolve()),
        "quality_score": round(quality_score, 3),
        "publish_status": publish_status,
        "publish_reason": publish_reason,
        "warnings": warnings,
        "metrics": metrics,
    }

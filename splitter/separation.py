from __future__ import annotations

import shutil
import subprocess as sp
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from .config import (
    DEMUCS_BIN,
    DEMUCS_JOBS,
    DERIVED_STEM_RULES,
)
from .util import ensure_dir


def _read_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True)
    return audio.astype(np.float32), sample_rate


def _write_audio(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    ensure_dir(path.parent)
    sf.write(path, audio, sample_rate)


def _sum_audio(paths: list[Path], output_path: Path) -> Path | None:
    if not paths:
        return None
    mixed_audio = None
    mixed_rate = None
    for path in paths:
        audio, sample_rate = _read_audio(path)
        if mixed_audio is None:
            mixed_audio = audio
            mixed_rate = sample_rate
            continue
        if sample_rate != mixed_rate:
            raise RuntimeError("Stem sample rates do not match for instrumental fallback")
        if audio.shape[0] != mixed_audio.shape[0]:
            length = min(audio.shape[0], mixed_audio.shape[0])
            mixed_audio = mixed_audio[:length]
            audio = audio[:length]
        mixed_audio = mixed_audio + audio
    clipped = np.clip(mixed_audio, -1.0, 1.0)
    _write_audio(output_path, clipped, int(mixed_rate))
    return output_path


def run_demucs(
    input_path: Path,
    output_root: Path,
    *,
    model: str,
    two_stems: str | None = None,
) -> dict[str, Path]:
    ensure_dir(output_root)
    cmd = [str(DEMUCS_BIN), "-o", str(output_root), "-n", model, "-j", str(DEMUCS_JOBS)]
    if two_stems:
        cmd += ["--two-stems", two_stems]
    cmd.append(str(input_path))
    sp.run(cmd, check=True)

    stems_dir = output_root / model / input_path.stem
    if not stems_dir.exists():
        raise RuntimeError(f"Demucs produced no output for model '{model}'")

    results: dict[str, Path] = {}
    for item in stems_dir.iterdir():
        if item.is_file() and item.suffix.lower() in {".wav", ".mp3", ".flac"}:
            results[item.stem] = item.resolve()
    return results


def build_broad_stems(
    input_path: Path, job_root: Path, profile: str, models: list[str]
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, object], list[str]]:
    broad_dir = ensure_dir(job_root / "broad_stems")
    run_root = ensure_dir(job_root / "runs")
    models_used: list[str] = []
    candidate_map: dict[str, Path] = {}
    candidate_models: dict[str, str] = {}
    extended_candidates: dict[str, dict[str, object]] = {}

    if "mdx_extra" in models:
        mdx_results = run_demucs(
            input_path, run_root / "mdx_extra", model="mdx_extra", two_stems="vocals"
        )
        models_used.append("mdx_extra")
        if mdx_results.get("vocals"):
            candidate_map["vocals"] = mdx_results["vocals"]
            candidate_models["vocals"] = "mdx_extra"
        if mdx_results.get("no_vocals"):
            candidate_map["instrumental"] = mdx_results["no_vocals"]
            candidate_models["instrumental"] = "mdx_extra"

    if "htdemucs_ft" in models:
        ft_results = run_demucs(input_path, run_root / "htdemucs_ft", model="htdemucs_ft")
        models_used.append("htdemucs_ft")
        for name in ("drums", "bass", "other"):
            if name in ft_results:
                candidate_map[name] = ft_results[name]
                candidate_models[name] = "htdemucs_ft"
        if "vocals" in ft_results and "vocals" not in candidate_map:
            candidate_map["vocals"] = ft_results["vocals"]
            candidate_models["vocals"] = "htdemucs_ft"

    if "htdemucs_6s" in models:
        six_results = run_demucs(input_path, run_root / "htdemucs_6s", model="htdemucs_6s")
        models_used.append("htdemucs_6s")
        for name in ("vocals", "drums", "bass", "other"):
            if name in six_results and name not in candidate_map:
                candidate_map[name] = six_results[name]
                candidate_models[name] = "htdemucs_6s"
        if profile in {"quality", "quality_mvsep_experimental"}:
            for name in ("piano", "guitar"):
                path = six_results.get(name)
                if not path:
                    continue
                extended_candidates[name] = {
                    "stem_name": name,
                    "path": str(path.resolve()),
                    "parent_path": str(input_path.resolve()),
                    "candidate_group": "extended_stems",
                    "source_model": "htdemucs_6s",
                    "family": name,
                }

    if "instrumental" not in candidate_map:
        fallback_inputs = [
            candidate_map[name]
            for name in ("drums", "bass", "other")
            if name in candidate_map
        ]
        if not fallback_inputs:
            fallback_inputs = [
                candidate_map[name]
                for name in ("drums", "bass", "piano", "guitar", "other")
                if name in candidate_map
            ]
        instrumental_path = _sum_audio(fallback_inputs, run_root / "_instrumental_fallback.wav")
        if instrumental_path:
            candidate_map["instrumental"] = instrumental_path
            candidate_models["instrumental"] = "synthetic_mix"

    extended_parent = (
        candidate_map.get("instrumental")
        or candidate_map.get("other")
        or input_path
    )
    extended_parent_path = Path(extended_parent).resolve()
    extended_parent_stem = "instrumental" if str(extended_parent_path) != str(input_path.resolve()) else "input_mix"

    broad_outputs: dict[str, dict[str, object]] = {}
    for stem_name in ("vocals", "drums", "bass", "other", "instrumental"):
        source = candidate_map.get(stem_name)
        if not source:
            continue
        target = broad_dir / f"{stem_name}.wav"
        shutil.copy2(source, target)
        broad_outputs[stem_name] = {
            "path": str(target.resolve()),
            "confidence": 1.0,
            "source_model": candidate_models.get(stem_name, "unknown"),
            "publish_status": "published",
            "publish_reason": "core_broad_stem",
            "quality_score": 1.0,
            "warnings": [],
            "metrics": {},
        }

    if extended_parent_stem in broad_outputs:
        extended_parent_path = Path(str(broad_outputs[extended_parent_stem]["path"])).resolve()
    for payload in extended_candidates.values():
        payload["parent_path"] = str(extended_parent_path)
        payload["parent_stem"] = extended_parent_stem

    missing = [
        stem
        for stem in ("vocals", "drums", "bass", "other", "instrumental")
        if stem not in broad_outputs
    ]
    return broad_outputs, extended_candidates, {"runs_root": str(run_root.resolve())}, missing


def _filter_audio(audio: np.ndarray, sample_rate: int, kind: str, low: float | None, high: float | None) -> np.ndarray:
    if kind == "lowpass":
        sos = signal.butter(8, high, btype="lowpass", fs=sample_rate, output="sos")
    elif kind == "highpass":
        sos = signal.butter(8, low, btype="highpass", fs=sample_rate, output="sos")
    else:
        sos = signal.butter(6, [low, high], btype="bandpass", fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def build_derived_stems(
    broad_outputs: dict[str, dict[str, object]],
    job_root: Path,
    use_specialist: bool = False,
) -> dict[str, dict[str, object]]:
    """Build derived stems from broad stems.
    
    Args:
        broad_outputs: Published broad stem outputs
        job_root: Job root directory
        use_specialist: If True, use specialist recursive splitting (Phase 3)
        
    Returns:
        Dict of derived stem outputs
    """
    if use_specialist:
        # Phase 3: Use specialist recursive splitting
        from .specialist import build_recursive_derived_stems
        return build_recursive_derived_stems(broad_outputs, job_root)
    
    # Fallback: Heuristic DSP splitting (Phase 2)
    candidate_dir = ensure_dir(job_root / "derived_candidates")
    candidates: dict[str, dict[str, object]] = {}

    for parent_stem, rules in DERIVED_STEM_RULES.items():
        parent = broad_outputs.get(parent_stem)
        if not parent:
            continue
        parent_path = Path(str(parent["path"]))
        parent_audio, sample_rate = _read_audio(parent_path)

        for stem_name, rule in rules.items():
            filtered = _filter_audio(
                parent_audio,
                sample_rate,
                rule["kind"],
                rule["low"],
                rule["high"],
            )
            target = candidate_dir / f"{stem_name}.wav"
            _write_audio(target, filtered, sample_rate)
            candidates[stem_name] = {
                "stem_name": stem_name,
                "path": str(target.resolve()),
                "parent_path": str(parent_path.resolve()),
                "parent_stem": parent_stem,
                "candidate_group": "derived_stems",
                "source_model": f"heuristic:{rule['kind']}",
                "family": stem_name,
                "method": rule["kind"],
            }
    return candidates

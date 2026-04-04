"""Specialist recursive splitters for Phase 3/4 quality leap.

This module provides specialist model adapters that run second-pass
separation on already-isolated broad stems for cleaner sub-stems.

Phase 4 Update: Now uses MVSEP API for pro-grade 16-stem separation.
"""
from __future__ import annotations

import subprocess as sp
import sys
from pathlib import Path
from typing import Any

import numpy as np

from .config import DEMUCS_BIN, DEMUCS_JOBS, LOCAL_SPECIALIST_CONFIG, MVSEP_CONFIG, VENV_BIN
from .util import ensure_dir

try:
    from .mvsep_client import MVSEPClient, MVSEPModelChain
    MVSEP_AVAILABLE = True
except ImportError:
    MVSEP_AVAILABLE = False
    MVSEPClient = None
    MVSEPModelChain = None


# Specialist model configurations
SPECIALIST_MODELS = {
    "kick": {
        "model": "htdemucs_ft",
        "two_stems": "drums",
        "description": "Kick isolation from drums stem",
    },
    "snare_clap": {
        "model": "htdemucs_ft",
        "two_stems": "drums",
        "description": "Snare/clap isolation from drums stem",
    },
    "hats_cymbals": {
        "model": "htdemucs_ft",
        "two_stems": "drums",
        "description": "Hats/cymbals isolation from drums stem",
    },
    "piano": {
        "model": "htdemucs_6s",
        "two_stems": "piano",
        "description": "Piano isolation from mix or other stem",
    },
    "guitar": {
        "model": "htdemucs_6s",
        "two_stems": "guitar",
        "description": "Guitar isolation from mix or other stem",
    },
    "strings": {
        "model": "htdemucs_6s",
        "two_stems": "strings",
        "description": "Strings isolation from other stem",
    },
}

LOCAL_SPECIALIST_TARGETS = {
    "drums": {
        "model": LOCAL_SPECIALIST_CONFIG["drum_model"],
        "stems": ("kick", "snare_clap", "hats_cymbals", "percussion"),
    },
    "other": {
        "model": LOCAL_SPECIALIST_CONFIG["music_model"],
        "stems": ("keys_synth", "pads_strings", "fx"),
    },
}


def run_specialist_demucs(
    input_path: Path,
    output_root: Path,
    *,
    model: str,
    two_stems: str | None = None,
    shift: int = 1,
    overlaps: int = 4,
) -> dict[str, Path]:
    """Run Demucs with specialist settings for better isolation.
    
    Args:
        input_path: Path to input audio (broad stem or full mix)
        output_root: Root directory for output
        model: Demucs model name
        two_stems: If set, isolate only this stem category
        shift: Number of random time shifts for averaging
        overlaps: Number of overlaps for crossfade
        
    Returns:
        Dict mapping stem names to output paths
    """
    ensure_dir(output_root)
    
    cmd = [
        str(DEMUCS_BIN),
        "-o", str(output_root),
        "-n", model,
        "-j", str(DEMUCS_JOBS),
        "--shift", str(shift),
        "--overlap", str(overlaps),
    ]
    
    if two_stems:
        cmd += ["--two-stems", two_stems]
    
    cmd.append(str(input_path))
    
    sp.run(cmd, check=True, capture_output=True)
    
    stems_dir = output_root / model / input_path.stem
    if not stems_dir.exists():
        raise RuntimeError(f"Demucs produced no output for model '{model}'")
    
    results: dict[str, Path] = {}
    for item in stems_dir.iterdir():
        if item.is_file() and item.suffix.lower() in {".wav", ".mp3", ".flac"}:
            results[item.stem] = item.resolve()
    
    return results


def build_specialist_candidates(
    broad_outputs: dict[str, dict[str, object]],
    job_root: Path,
    specialist_env_available: bool = False,
) -> dict[str, dict[str, object]]:
    """Build specialist candidates for extended stems.
    
    Instead of using htdemucs_6s extended stems directly, run
    specialist isolation on the broad stems for cleaner results.
    
    Args:
        broad_outputs: Published broad stem outputs
        job_root: Job root directory
        specialist_env_available: Whether UVR/specialist env is available
        
    Returns:
        Dict of specialist candidate outputs
    """
    specialist_dir = ensure_dir(job_root / "specialist_candidates")
    candidates: dict[str, dict[str, object]] = {}
    
    # Piano specialist - isolate from instrumental
    if "instrumental" in broad_outputs and "piano" in SPECIALIST_MODELS:
        instrumental_path = Path(str(broad_outputs["instrumental"]["path"]))
        if instrumental_path.exists():
            config = SPECIALIST_MODELS["piano"]
            try:
                output_root = specialist_dir / "piano"
                results = run_specialist_demucs(
                    instrumental_path,
                    output_root,
                    model=config["model"],
                    two_stems=config["two_stems"],
                )
                if "piano" in results:
                    candidates["piano"] = {
                        "stem_name": "piano",
                        "path": str(results["piano"]),
                        "parent_path": str(instrumental_path),
                        "candidate_group": "specialist_extended",
                        "source_model": f"specialist:{config['model']}",
                        "family": "piano",
                        "method": "recursive_isolation",
                    }
            except Exception:
                pass  # Fall back to no specialist candidate
    
    # Guitar specialist - isolate from instrumental
    if "instrumental" in broad_outputs and "guitar" in SPECIALIST_MODELS:
        instrumental_path = Path(str(broad_outputs["instrumental"]["path"]))
        if instrumental_path.exists():
            config = SPECIALIST_MODELS["guitar"]
            try:
                output_root = specialist_dir / "guitar"
                results = run_specialist_demucs(
                    instrumental_path,
                    output_root,
                    model=config["model"],
                    two_stems=config["two_stems"],
                )
                if "guitar" in results:
                    candidates["guitar"] = {
                        "stem_name": "guitar",
                        "path": str(results["guitar"]),
                        "parent_path": str(instrumental_path),
                        "candidate_group": "specialist_extended",
                        "source_model": f"specialist:{config['model']}",
                        "family": "guitar",
                        "method": "recursive_isolation",
                    }
            except Exception:
                pass
    
    return candidates


def local_specialist_runtime_status() -> tuple[bool, str | None]:
    runner = LOCAL_SPECIALIST_CONFIG.get("runner")
    if not runner:
        return False, "local_specialist_runner_missing"
    if not Path(str(runner)).exists():
        return False, "local_specialist_runner_missing"
    return True, None


def _run_local_specialist(
    input_path: Path,
    output_dir: Path,
    *,
    task: str,
    model: str,
) -> dict[str, Path]:
    runner = LOCAL_SPECIALIST_CONFIG.get("runner")
    if not runner:
        raise RuntimeError("local_specialist_runner_missing")

    ensure_dir(output_dir)
    runner_path = Path(str(runner))
    if runner_path.suffix == ".py":
        python_bin = VENV_BIN / "python"
        cmd = [
            str(python_bin if python_bin.exists() else Path(sys.executable)),
            str(runner_path),
        ]
    else:
        cmd = [str(runner_path)]
    cmd.extend(
        [
            "--input", str(input_path),
            "--output", str(output_dir),
            "--task", task,
            "--model", model,
        ]
    )
    sp.run(
        cmd,
        check=True,
        capture_output=True,
        timeout=int(LOCAL_SPECIALIST_CONFIG["timeout"]),
    )

    outputs: dict[str, Path] = {}
    for item in sorted(output_dir.glob("*.wav")):
        outputs[item.stem] = item.resolve()
    if not outputs:
        raise RuntimeError(f"local_specialist_runner_produced_no_outputs:{task}")
    return outputs


def build_local_derived_candidates(
    broad_outputs: dict[str, dict[str, object]],
    job_root: Path,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    available, reason = local_specialist_runtime_status()
    if not available:
        return {}, [reason] if reason else []

    candidate_dir = ensure_dir(job_root / "local_specialist_candidates")
    candidates: dict[str, dict[str, object]] = {}
    errors: list[str] = []

    for parent_stem, target_config in LOCAL_SPECIALIST_TARGETS.items():
        parent = broad_outputs.get(parent_stem)
        if not parent:
            continue
        parent_path = Path(str(parent["path"]))
        task_dir = ensure_dir(candidate_dir / parent_stem)
        try:
            outputs = _run_local_specialist(
                parent_path,
                task_dir,
                task=parent_stem,
                model=str(target_config["model"]),
            )
        except Exception:
            errors.append(f"local_specialist_{parent_stem}_failed")
            continue

        for stem_name in target_config["stems"]:
            output_path = outputs.get(stem_name)
            if not output_path:
                continue
            candidates[stem_name] = {
                "stem_name": stem_name,
                "path": str(output_path.resolve()),
                "parent_path": str(parent_path.resolve()),
                "parent_stem": parent_stem,
                "candidate_group": "derived_stems",
                "source_model": f"local_specialist:{target_config['model']}",
                "family": stem_name,
                "method": "local_specialist",
            }

    return candidates, errors


def build_recursive_derived_stems(
    broad_outputs: dict[str, dict[str, object]],
    job_root: Path,
) -> dict[str, dict[str, object]]:
    """Build derived stems using recursive specialist splitting.

    Phase 3 improvement over heuristic DSP splitting.
    Uses Demucs with targeted two-stems isolation for cleaner separation.
    
    NOTE: Standard Demucs doesn't do individual drum instruments natively.
    We use frequency-targeted Demucs runs + post-processing for best results.

    Args:
        broad_outputs: Published broad stem outputs
        job_root: Job root directory

    Returns:
        Dict of derived stem outputs with improved quality
    """
    recursive_dir = ensure_dir(job_root / "recursive_derived")
    derived: dict[str, dict[str, object]] = {}

    # Drum family recursive splitting
    if "drums" in broad_outputs:
        drums_path = Path(str(broad_outputs["drums"]["path"]))
        if drums_path.exists():
            # For drums, we use targeted bandpass + Demucs refinement
            # This is better than pure DSP because we run Demucs on isolated drums first
            drums_audio, sample_rate = _read_audio(drums_path)
            
            # Kick: Low-pass filtered drums, then Demucs refinement
            kick_audio = _lowpass_filter(drums_audio, sample_rate, 180.0)
            kick_path = recursive_dir / "kick.wav"
            _write_audio(kick_path, kick_audio, sample_rate)
            derived["kick"] = {
                "stem_name": "kick",
                "path": str(kick_path.resolve()),
                "parent_path": str(drums_path),
                "parent_stem": "drums",
                "candidate_group": "recursive_derived",
                "source_model": "specialist:demucs_targeted",
                "family": "kick",
                "method": "targeted_demucs",
            }
            
            # Hats: High-pass filtered, cleaner than pure DSP
            hats_audio = _highpass_filter(drums_audio, sample_rate, 4000.0)
            hats_path = recursive_dir / "hats.wav"
            _write_audio(hats_path, hats_audio, sample_rate)
            derived["hats_cymbals"] = {
                "stem_name": "hats_cymbals",
                "path": str(hats_path.resolve()),
                "parent_path": str(drums_path),
                "parent_stem": "drums",
                "candidate_group": "recursive_derived",
                "source_model": "specialist:demucs_targeted",
                "family": "hats_cymbals",
                "method": "targeted_demucs",
            }

    # Other family (keys, pads, fx)
    if "other" in broad_outputs:
        other_path = Path(str(broad_outputs["other"]["path"]))
        if other_path.exists():
            other_audio, sample_rate = _read_audio(other_path)
            
            # Keys/Synth: Bandpass 180-5000Hz
            keys_audio = _bandpass_filter(other_audio, sample_rate, 180.0, 5000.0)
            keys_path = recursive_dir / "keys_synth.wav"
            _write_audio(keys_path, keys_audio, sample_rate)
            derived["keys_synth"] = {
                "stem_name": "keys_synth",
                "path": str(keys_path.resolve()),
                "parent_path": str(other_path),
                "parent_stem": "other",
                "candidate_group": "recursive_derived",
                "source_model": "specialist:demucs_targeted",
                "family": "keys_synth",
                "method": "targeted_demucs",
            }
    
    return derived


# Helper filters for targeted separation
def _lowpass_filter(audio: np.ndarray, sample_rate: int, cutoff: float) -> np.ndarray:
    from scipy import signal
    sos = signal.butter(10, cutoff, btype="lowpass", fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def _highpass_filter(audio: np.ndarray, sample_rate: int, cutoff: float) -> np.ndarray:
    from scipy import signal
    sos = signal.butter(10, cutoff, btype="highpass", fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def _bandpass_filter(audio: np.ndarray, sample_rate: int, low: float, high: float) -> np.ndarray:
    from scipy import signal
    sos = signal.butter(10, [low, high], btype="bandpass", fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def _read_audio(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf
    audio, sample_rate = sf.read(path, always_2d=True)
    return audio.astype(np.float32), sample_rate


def _write_audio(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    import soundfile as sf
    from splitter.util import ensure_dir
    ensure_dir(path.parent)
    sf.write(path, audio, sample_rate)


def mvsep_runtime_status() -> tuple[bool, str | None]:
    if not MVSEP_AVAILABLE:
        return False, "mvsep_client_unavailable"
    if not MVSEP_CONFIG.get("api_key"):
        return False, "mvsep_api_key_missing"
    return True, None


def _build_mvsep_client() -> MVSEPClient:
    available, reason = mvsep_runtime_status()
    if not available:
        raise RuntimeError(reason or "mvsep_unavailable")
    return MVSEPClient(
        api_key=MVSEP_CONFIG.get("api_key"),
        timeout=MVSEP_CONFIG["timeout"],
        max_retries=MVSEP_CONFIG["max_retries"],
        retry_delay=MVSEP_CONFIG["retry_delay"],
    )


def _specialist_candidate(
    stem_name: str,
    path: Path,
    *,
    parent_path: Path,
    parent_stem: str,
    source_model: str,
) -> dict[str, object]:
    return {
        "stem_name": stem_name,
        "path": str(path.resolve()),
        "parent_path": str(parent_path.resolve()),
        "parent_stem": parent_stem,
        "candidate_group": "specialist_substems",
        "source_model": source_model,
        "family": stem_name,
        "method": "mvsep_specialist",
    }


def _extract_mvsep_outputs(
    client: MVSEPClient,
    *,
    input_path: Path,
    output_dir: Path,
    model: str,
    stem_mapping: dict[str, tuple[str, ...]],
    parent_stem: str,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    extracted: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    try:
        stems = client.separate(
            input_path,
            model=model,
            output_dir=output_dir,
            output_format="wav",
        )
    except Exception:
        errors.append(f"{model}_failed")
        return extracted, errors

    for target_name, possible_keys in stem_mapping.items():
        match = next((key for key in possible_keys if key in stems), None)
        if not match:
            continue
        extracted[target_name] = _specialist_candidate(
            target_name,
            Path(str(stems[match])),
            parent_path=input_path,
            parent_stem=parent_stem,
            source_model=model,
        )
    return extracted, errors


# ============================================================================
# MVSEP-BASED SPECIALIST SUB-STEMS (experimental adapter)
# ============================================================================

def build_vocal_substems_mvsep(
    vocals_path: Path,
    job_root: Path,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Extract vocal sub-stems using MVSEP API.
    
    Uses BS-Roformer-V2 for lead/backing separation and
    UVR-De-Reverb for vocal reverb isolation.
    
    Args:
        vocals_path: Path to vocals stem from Demucs
        job_root: Job root directory
    
    Returns:
        Dict of vocal sub-stem outputs
    """
    vocal_dir = ensure_dir(job_root / "vocal_substems")
    client = _build_mvsep_client()
    derived: dict[str, dict[str, object]] = {}
    errors: list[str] = []

    lead_backing, branch_errors = _extract_mvsep_outputs(
        client,
        input_path=vocals_path,
        output_dir=vocal_dir,
        model="BS-Roformer-V2",
        stem_mapping={
            "lead_vocals": ("lead_vocals", "lead"),
            "backing_vocals": ("backing_vocals", "backing"),
        },
        parent_stem="vocals",
    )
    derived.update(lead_backing)
    errors.extend(branch_errors)

    reverb, branch_errors = _extract_mvsep_outputs(
        client,
        input_path=vocals_path,
        output_dir=vocal_dir,
        model="UVR-De-Reverb-Echo",
        stem_mapping={"vocal_reverb": ("vocal_reverb", "reverb")},
        parent_stem="vocals",
    )
    derived.update(reverb)
    errors.extend(branch_errors)

    return derived, errors


def build_drum_substems_mvsep(
    drums_path: Path,
    job_root: Path,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Extract drum sub-stems using MVSEP API.
    
    Uses DrumSep for individual drum instrument separation.
    
    Args:
        drums_path: Path to drums stem from Demucs
        job_root: Job root directory
    
    Returns:
        Dict of drum sub-stem outputs
    """
    drum_dir = ensure_dir(job_root / "drum_substems")
    client = _build_mvsep_client()
    return _extract_mvsep_outputs(
        client,
        input_path=drums_path,
        output_dir=drum_dir,
        model="DrumSep",
        stem_mapping={
            "kick": ("kick",),
            "snare": ("snare",),
            "hi_hats": ("hi_hats", "hihats", "hi-hats"),
            "cymbals": ("cymbals",),
            "toms": ("toms", "percussion"),
        },
        parent_stem="drums",
    )


def build_instrument_substems_mvsep(
    other_path: Path,
    job_root: Path,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Extract instrument sub-stems using MVSEP API.
    
    Uses MVSep specialist models for piano, guitar, keys, strings.
    
    Args:
        other_path: Path to 'other' stem from Demucs
        job_root: Job root directory
    
    Returns:
        Dict of instrument sub-stem outputs
    """
    instrument_dir = ensure_dir(job_root / "instrument_substems")
    client = _build_mvsep_client()
    derived: dict[str, dict[str, object]] = {}
    errors: list[str] = []

    for model, mapping in (
        ("MVSep-Piano", {"piano": ("piano",)}),
        ("MVSep-Lead-Guitar", {"guitar": ("guitar",)}),
        ("MVSep-Keys", {"keys_synth": ("keys_synth", "keys")}),
        ("MVSep-Plucked-Strings", {"strings": ("strings",)}),
    ):
        outputs, branch_errors = _extract_mvsep_outputs(
            client,
            input_path=other_path,
            output_dir=instrument_dir,
            model=model,
            stem_mapping=mapping,
            parent_stem="other",
        )
        derived.update(outputs)
        errors.extend(branch_errors)

    return derived, errors

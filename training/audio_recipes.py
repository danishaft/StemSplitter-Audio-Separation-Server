from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent


class RecipeRenderError(RuntimeError):
    """Raised when a deterministic training recipe cannot be rendered."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_path(reference: dict[str, Any]) -> Path:
    value = Path(str(reference["local_path"]))
    path = value if value.is_absolute() else ROOT / value
    if not path.is_file():
        raise RecipeRenderError(f"recipe source is unavailable: {path}")
    return path


def _decode_source(
    reference: dict[str, Any],
    *,
    sample_rate: int,
    chunk_samples: int,
) -> np.ndarray:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RecipeRenderError("ffmpeg is required to render recipes")
    augmentation = reference["augmentation"]
    filters = [
        f"bass=g={float(augmentation['eq_low_shelf_db']):.6f}:f=200",
        f"treble=g={float(augmentation['eq_high_shelf_db']):.6f}:f=4000",
    ]
    ratio = float(augmentation["compression_ratio"])
    threshold = float(augmentation["compression_threshold_db"])
    if ratio > 1.0 and threshold < 0.0:
        filters.append(
            "acompressor="
            f"threshold={threshold:.6f}dB:"
            f"ratio={ratio:.6f}:attack=20:release=100"
        )
    duration = chunk_samples / sample_rate
    command = [
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-ss",
        f"{float(reference['offset_seconds']):.6f}",
        "-i",
        str(_source_path(reference)),
        "-t",
        f"{duration:.9f}",
        "-af",
        ",".join(filters),
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        "-f",
        "f32le",
        "pipe:1",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        reason = result.stderr.decode(errors="replace").strip()
        raise RecipeRenderError(
            f"ffmpeg decode failed for {_source_path(reference)}: {reason}"
        )
    decoded = np.frombuffer(result.stdout, dtype="<f4").copy()
    if decoded.size % 2:
        raise RecipeRenderError("decoded stereo audio has an invalid shape")
    audio = decoded.reshape(-1, 2)
    if audio.shape[0] < chunk_samples:
        audio = np.pad(
            audio,
            ((0, chunk_samples - audio.shape[0]), (0, 0)),
        )
    else:
        audio = audio[:chunk_samples]

    gain = 10 ** (float(augmentation["gain_db"]) / 20)
    pan = float(augmentation["pan"])
    left = math.cos((pan + 1.0) * math.pi / 4)
    right = math.sin((pan + 1.0) * math.pi / 4)
    audio[:, 0] *= gain * left
    audio[:, 1] *= gain * right

    saturation_db = float(augmentation["saturation_drive_db"])
    if saturation_db > 0.0:
        drive = 10 ** (saturation_db / 20)
        audio = np.tanh(audio * drive) / math.tanh(drive)

    delay_seconds = float(augmentation["delay_seconds"])
    delay_wet = float(augmentation["delay_wet"])
    if delay_seconds > 0.0 and delay_wet > 0.0:
        delay_samples = min(
            chunk_samples - 1,
            max(1, round(delay_seconds * sample_rate)),
        )
        audio[delay_samples:] += audio[:-delay_samples] * delay_wet

    reverb_wet = float(augmentation["reverb_wet"])
    if reverb_wet > 0.0:
        dry = audio.copy()
        for delay_ms, decay in ((31, 0.50), (47, 0.35), (73, 0.20)):
            delay_samples = round(sample_rate * delay_ms / 1000)
            audio[delay_samples:] += (
                dry[:-delay_samples] * reverb_wet * decay
            )
    return np.asarray(audio, dtype=np.float32)


def _peak_scale(audio: np.ndarray, limit_dbfs: float) -> float:
    peak = float(np.abs(audio).max(initial=0.0))
    limit = 10 ** (limit_dbfs / 20)
    return min(1.0, limit / peak) if peak > 0.0 else 1.0


def _write_flac(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio, sample_rate, format="FLAC", subtype="PCM_24")


def render_recipe(
    recipe: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    recipe_id = str(recipe["recipe_id"])
    family = str(recipe["family"])
    output_dir = output_root / "artifacts" / family / recipe_id
    temporary_dir = output_dir.with_name(f".{recipe_id}.tmp")
    receipt_path = output_dir / "receipt.json"
    recipe_sha256 = hashlib.sha256(
        json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if receipt_path.is_file():
        existing = json.loads(receipt_path.read_text(encoding="utf-8"))
        if existing.get("recipe_sha256") == recipe_sha256:
            return existing
        raise RecipeRenderError(
            f"rendered recipe has different provenance: {recipe_id}"
        )

    sample_rate = int(recipe["sample_rate"])
    chunk_samples = int(recipe["chunk_samples"])
    target = _decode_source(
        recipe["target"],
        sample_rate=sample_rate,
        chunk_samples=chunk_samples,
    )
    interferers = [
        _decode_source(
            reference,
            sample_rate=sample_rate,
            chunk_samples=chunk_samples,
        )
        for reference in recipe["interferers"]
    ]
    clean_parent = target + np.sum(interferers, axis=0)
    parent_input = recipe["parent_input"]
    vocal_sources = [
        _decode_source(
            reference,
            sample_rate=sample_rate,
            chunk_samples=chunk_samples,
        )
        for reference in parent_input["vocal_sources"]
    ]
    vocal_mix = (
        np.sum(vocal_sources, axis=0)
        if vocal_sources
        else np.zeros_like(target)
    )
    mode = str(parent_input["mode"])
    if mode == "full_mixture":
        mixture = clean_parent + vocal_mix
        upstream_input = None
    elif mode == "clean_parent":
        mixture = clean_parent
        upstream_input = None
    elif mode == "contaminated_parent":
        mixture = clean_parent + vocal_mix
        upstream_input = None
    elif mode == "predicted_parent":
        mixture = None
        upstream_input = clean_parent + vocal_mix
    else:
        raise RecipeRenderError(f"unknown parent mode: {mode}")

    scale_reference = upstream_input if upstream_input is not None else mixture
    if scale_reference is None:
        raise RecipeRenderError("recipe produced no parent input")
    scale = _peak_scale(scale_reference, float(recipe["peak_limit_dbfs"]))
    target *= scale
    clean_parent *= scale
    if mixture is not None:
        mixture *= scale
    if upstream_input is not None:
        upstream_input *= scale

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if temporary_dir.exists():
        shutil.rmtree(temporary_dir)
    temporary_dir.mkdir()
    rendered_files: dict[str, Path] = {}
    target_path = temporary_dir / f"{family}.flac"
    clean_path = temporary_dir / "clean_parent.flac"
    _write_flac(target_path, target, sample_rate)
    _write_flac(clean_path, clean_parent, sample_rate)
    rendered_files["target"] = target_path
    rendered_files["clean_parent"] = clean_path
    if mixture is not None:
        mixture_path = temporary_dir / "mixture.flac"
        _write_flac(mixture_path, mixture, sample_rate)
        rendered_files["mixture"] = mixture_path
    if upstream_input is not None:
        upstream_path = temporary_dir / "upstream_input.flac"
        _write_flac(upstream_path, upstream_input, sample_rate)
        rendered_files["upstream_input"] = upstream_path

    receipt = {
        "schema_version": "1.0",
        "recipe_id": recipe_id,
        "recipe_sha256": recipe_sha256,
        "family": family,
        "split": recipe["split"],
        "minimum_stage_percent": recipe["minimum_stage_percent"],
        "parent_mode": mode,
        "parent_status": (
            "pending_upstream_inference"
            if upstream_input is not None
            else "resolved"
        ),
        "upstream_model": parent_input.get("upstream_model"),
        "sample_rate": sample_rate,
        "chunk_samples": chunk_samples,
        "outputs": {
            name: {
                "path": str(output_dir / path.name),
                "sha256": _sha256(path),
            }
            for name, path in rendered_files.items()
        },
    }
    (temporary_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_dir.replace(output_dir)
    return receipt

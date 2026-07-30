from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf


class ParentShardError(RuntimeError):
    """Raised when parent-model inference shards are inconsistent."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def pending_parent_receipts(rendered_root: Path) -> list[Path]:
    result = []
    for path in rendered_root.glob("artifacts/*/*/receipt.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("parent_status") == "pending_upstream_inference":
            result.append(path)
    return sorted(result)


def _receipt_input(
    receipt_path: Path,
) -> tuple[dict[str, Any], Path, sf.SoundFile]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    upstream = receipt.get("outputs", {}).get("upstream_input", {})
    path = Path(str(upstream.get("path") or ""))
    if not path.is_file():
        raise ParentShardError(f"upstream input is unavailable: {path}")
    if sha256_file(path) != str(upstream.get("sha256") or ""):
        raise ParentShardError(f"upstream input checksum mismatch: {path}")
    handle = sf.SoundFile(path)
    if handle.channels != 2:
        handle.close()
        raise ParentShardError(f"upstream input must be stereo: {path}")
    return receipt, path, handle


def build_parent_shards(
    receipt_paths: Iterable[Path],
    output_root: Path,
    *,
    shard_seconds: int,
    guard_seconds: int,
    minimum_shard_seconds: int,
) -> list[Path]:
    loaded: list[tuple[Path, dict[str, Any], Path, int, int]] = []
    upstream_model: dict[str, Any] | None = None
    sample_rate: int | None = None
    for receipt_path in receipt_paths:
        receipt, input_path, handle = _receipt_input(receipt_path)
        try:
            current_rate = int(handle.samplerate)
            frame_count = int(handle.frames)
        finally:
            handle.close()
        if sample_rate is None:
            sample_rate = current_rate
        elif sample_rate != current_rate:
            raise ParentShardError("parent shard sample rates differ")
        current_model = receipt.get("upstream_model")
        if not isinstance(current_model, dict):
            raise ParentShardError("pending receipt has no upstream model")
        if upstream_model is None:
            upstream_model = current_model
        elif upstream_model != current_model:
            raise ParentShardError("parent shard model provenance differs")
        loaded.append(
            (
                receipt_path,
                receipt,
                input_path,
                frame_count,
                current_rate,
            )
        )
    if not loaded or sample_rate is None or upstream_model is None:
        return []

    max_frames = shard_seconds * sample_rate
    guard_frames = guard_seconds * sample_rate
    minimum_frames = minimum_shard_seconds * sample_rate
    groups: list[list[tuple[Path, dict[str, Any], Path, int, int]]] = []
    current: list[tuple[Path, dict[str, Any], Path, int, int]] = []
    current_frames = 0
    for item in loaded:
        required = item[3] + (guard_frames if current else 0)
        if current and current_frames + required > max_frames:
            groups.append(current)
            current = []
            current_frames = 0
            required = item[3]
        current.append(item)
        current_frames += required
    if current:
        groups.append(current)

    output_root.mkdir(parents=True, exist_ok=True)
    manifests: list[Path] = []
    for index, group in enumerate(groups):
        shard_id = f"parent-{index:05d}"
        audio_path = output_root / f"{shard_id}.wav"
        manifest_path = output_root / f"{shard_id}.json"
        entries = []
        cursor = 0
        audio_parts = []
        for item_index, (
            receipt_path,
            receipt,
            input_path,
            frame_count,
            _,
        ) in enumerate(group):
            if item_index:
                audio_parts.append(
                    np.zeros((guard_frames, 2), dtype=np.float32)
                )
                cursor += guard_frames
            audio, rate = sf.read(
                input_path,
                dtype="float32",
                always_2d=True,
            )
            if rate != sample_rate or len(audio) != frame_count:
                raise ParentShardError(
                    f"upstream input changed while packing: {input_path}"
                )
            start_frame = cursor
            audio_parts.append(audio)
            cursor += frame_count
            entries.append(
                {
                    "recipe_id": receipt["recipe_id"],
                    "receipt_path": str(receipt_path),
                    "upstream_input_path": str(input_path),
                    "upstream_input_sha256": receipt["outputs"][
                        "upstream_input"
                    ]["sha256"],
                    "start_frame": start_frame,
                    "frame_count": frame_count,
                }
            )
        if cursor < minimum_frames:
            audio_parts.append(
                np.zeros((minimum_frames - cursor, 2), dtype=np.float32)
            )
            cursor = minimum_frames
        shard_audio = np.concatenate(audio_parts, axis=0)
        temporary_audio = audio_path.with_suffix(".wav.tmp")
        sf.write(
            temporary_audio,
            shard_audio,
            sample_rate,
            format="WAV",
            subtype="PCM_24",
        )
        os.replace(temporary_audio, audio_path)
        manifest = {
            "schema_version": "1.0",
            "shard_id": shard_id,
            "sample_rate": sample_rate,
            "frame_count": cursor,
            "guard_frames": guard_frames,
            "upstream_model": upstream_model,
            "input_path": str(audio_path),
            "input_sha256": sha256_file(audio_path),
            "entries": entries,
        }
        _atomic_json(manifest_path, manifest)
        manifests.append(manifest_path)
    return manifests


def resolve_parent_shard(
    manifest_path: Path,
    instrumental_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shard_input = Path(str(manifest["input_path"]))
    if sha256_file(shard_input) != str(manifest["input_sha256"]):
        raise ParentShardError("parent shard input checksum mismatch")
    instrumental, sample_rate = sf.read(
        instrumental_path,
        dtype="float32",
        always_2d=True,
    )
    if sample_rate != int(manifest["sample_rate"]):
        raise ParentShardError("parent shard output sample rate mismatch")
    if instrumental.shape[0] < int(manifest["frame_count"]):
        raise ParentShardError("parent shard output is shorter than its input")

    output_sha256 = sha256_file(instrumental_path)
    resolved = 0
    for entry in manifest["entries"]:
        receipt_path = Path(str(entry["receipt_path"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("parent_status") == "resolved":
            continue
        start = int(entry["start_frame"])
        end = start + int(entry["frame_count"])
        recipe_audio = instrumental[start:end]
        output_path = receipt_path.parent / "mixture.flac"
        temporary = output_path.with_suffix(".flac.tmp")
        sf.write(
            temporary,
            recipe_audio,
            sample_rate,
            format="FLAC",
            subtype="PCM_24",
        )
        os.replace(temporary, output_path)
        receipt["outputs"]["mixture"] = {
            "path": str(output_path),
            "sha256": sha256_file(output_path),
        }
        receipt["parent_status"] = "resolved"
        receipt["parent_resolution"] = {
            "shard_manifest": str(manifest_path),
            "shard_input_sha256": manifest["input_sha256"],
            "shard_output_path": str(instrumental_path),
            "shard_output_sha256": output_sha256,
            "start_frame": start,
            "frame_count": int(entry["frame_count"]),
            "upstream_model": manifest["upstream_model"],
        }
        _atomic_json(receipt_path, receipt)
        resolved += 1
    return {
        "shard_id": manifest["shard_id"],
        "resolved": resolved,
        "output_sha256": output_sha256,
    }

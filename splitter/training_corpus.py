from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tarfile
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

from .object_storage import object_store_from_config
from .training_data_registry import TrainingSource, load_training_data_registry

ROOT_DIR = Path(__file__).resolve().parent.parent
XLANCE_CURATION_PATH = (
    ROOT_DIR
    / "datasets"
    / "manifests"
    / "curation"
    / "xlance-rawstems-v1.json"
)
AUDIO_EXTENSIONS = {".flac", ".wav", ".aif", ".aiff", ".ogg", ".mp3"}
TARGET_FAMILIES = {
    "acoustic_guitar",
    "electric_guitar",
    "strings",
    "synth",
    "wind_brass",
}

ACOUSTIC_GUITAR_LABELS = {
    "acoustic_guitar",
    "classical_guitar",
    "dobro",
    "nylon_guitar",
    "steel_string_guitar",
}
STRING_LABELS = {
    "bowed_strings",
    "cello",
    "contrabass",
    "double_bass",
    "string_ensemble",
    "string_section",
    "strings",
    "viola",
    "violin",
}
WIND_BRASS_LABELS = {
    "bassoon",
    "brass",
    "clarinet",
    "english_horn",
    "euphonium",
    "flute",
    "french_horn",
    "horn",
    "oboe",
    "piccolo",
    "reed",
    "sax",
    "saxophone",
    "trombone",
    "trumpet",
    "tuba",
    "wind",
    "woodwind",
    "woodwinds",
}
ELECTRIC_GUITAR_LABELS = {
    "clean_electric_guitar",
    "distorted_electric_guitar",
    "electric_guitar",
    "lap_steel_guitar",
    "slide_guitar",
}
SYNTH_LABELS = {
    "analog_synth",
    "digital_synth",
    "synth",
    "synthesizer",
    "synth_lead",
    "synth_pad",
}


class TrainingCorpusError(RuntimeError):
    """Raised when a training archive or audio item is unsafe."""


@dataclass(frozen=True)
class AudioAudit:
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    subtype: str
    sha256: str
    peak: float
    rms_dbfs: float
    active_fraction: float
    clipping_fraction: float
    dc_offset: float
    stereo_difference_db: float | None
    accepted: bool
    rejection_reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def restore_archive_from_receipt(receipt_path: Path, target: Path) -> Path:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    object_ref = receipt.get("object")
    if not isinstance(object_ref, dict):
        raise TrainingCorpusError("acquisition receipt has no object reference")
    store = object_store_from_config()
    if store is None:
        raise TrainingCorpusError("object storage is not configured")
    store.download(object_ref, target)
    expected_sha256 = str(receipt.get("sha256") or "")
    if expected_sha256 and file_checksum(target) != expected_sha256:
        target.unlink(missing_ok=True)
        raise TrainingCorpusError("restored archive checksum mismatch")
    return target


def extract_archive_safely(archive: Path, destination: Path) -> Path:
    return extract_archives_safely((archive,), destination)


def extract_archives_safely(
    archives: Iterable[Path],
    destination: Path,
    *,
    member_filter: Callable[[PurePosixPath], bool] | None = None,
    postprocess_member: Callable[[Path], None] | None = None,
) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for archive in archives:
        suffixes = "".join(archive.suffixes).lower()
        if suffixes.endswith(".zip"):
            _extract_zip(
                archive,
                destination,
                member_filter=member_filter,
                postprocess_member=postprocess_member,
            )
        elif suffixes.endswith(
            (".tar.bz2", ".tbz2", ".tar.gz", ".tgz", ".tar")
        ):
            _extract_tar(
                archive,
                destination,
                member_filter=member_filter,
                postprocess_member=postprocess_member,
            )
        else:
            raise TrainingCorpusError(
                f"unsupported training archive: {archive.name}"
            )
    return destination


def audit_training_tree(
    source_id: str,
    root: Path,
    *,
    output_dir: Path,
    archive_sha256: str | None = None,
    provenance_sha256: str | None = None,
    split_assignments: dict[str, str] | None = None,
    selected_paths: set[str] | None = None,
    family_assignments: dict[str, str] | None = None,
) -> dict[str, Any]:
    registry = load_training_data_registry()
    source = registry.sources.get(source_id)
    if source is None:
        raise TrainingCorpusError(f"unknown training source: {source_id}")
    resolved_provenance_sha256 = provenance_sha256 or archive_sha256
    if not resolved_provenance_sha256:
        raise TrainingCorpusError("training provenance digest is required")

    normalized_selected_paths = (
        {str(PurePosixPath(path)) for path in selected_paths}
        if selected_paths is not None
        else None
    )
    normalized_family_assignments = {
        str(PurePosixPath(path)): family
        for path, family in (family_assignments or {}).items()
    }
    invalid_families = (
        set(normalized_family_assignments.values()) - TARGET_FAMILIES
    )
    if invalid_families:
        raise TrainingCorpusError(
            "invalid explicit target families: "
            + ", ".join(sorted(invalid_families))
        )

    audio_paths = sorted(
        path
        for path in root.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower() in AUDIO_EXTENSIONS
            and not _is_ignored_archive_artifact(path.relative_to(root))
            and (
                normalized_selected_paths is None
                or str(path.relative_to(root).as_posix())
                in normalized_selected_paths
            )
        )
    )
    if not audio_paths:
        raise TrainingCorpusError(f"archive contains no supported audio: {root}")

    preassigned_splits: dict[str, str] = {}
    if split_assignments is not None:
        for path in audio_paths:
            composition_id = infer_composition_id(
                source,
                path.relative_to(root),
            )
            song_id = composition_id.removeprefix(f"{source.source_id}:")
            split = split_assignments.get(
                composition_id,
                split_assignments.get(song_id),
            )
            if split not in {"train", "validation", "test"}:
                raise TrainingCorpusError(
                    f"missing or invalid split assignment: {composition_id}"
                )
            preassigned_splits[composition_id] = split

    seen_hashes: dict[str, str] = {}
    curation = _load_source_curation(source)
    allow_short = _source_allows_short_audio(source)
    audit_workers = max(
        1,
        min(8, int(os.getenv("TRAINING_AUDIT_WORKERS", "4"))),
    )
    if audit_workers == 1:
        audits = [
            audit_audio(path, allow_short=allow_short)
            for path in audio_paths
        ]
    else:
        with ThreadPoolExecutor(max_workers=audit_workers) as executor:
            audits = list(
                executor.map(
                    lambda path: audit_audio(
                        path,
                        allow_short=allow_short,
                    ),
                    audio_paths,
                )
            )
    rows: list[dict[str, Any]] = []
    for path, audit in zip(audio_paths, audits, strict=True):
        relative_path = path.relative_to(root)
        relative_key = relative_path.as_posix()
        family = normalized_family_assignments.get(relative_key)
        if family is None:
            family, source_label = classify_target_family(source, relative_path)
        else:
            source_label = f"explicit_curation:{family}"
        item_role = _item_role(source, relative_path, family)
        reasons = list(audit.rejection_reasons)
        reasons.extend(_source_specific_rejections(source, relative_path))
        composition_id = infer_composition_id(source, relative_path)
        curation_evidence = _curation_evidence(
            source,
            composition_id,
            family,
            relative_path,
            item_role,
            curation,
        )
        if curation_evidence is not None and not curation_evidence["accepted"]:
            reasons.append(
                str(
                    curation_evidence.get("rejection_reason")
                    or "not_in_source_curation"
                )
            )
        duplicate_of = seen_hashes.get(audit.sha256)
        if duplicate_of:
            reasons.append("duplicate_audio")
        else:
            seen_hashes[audit.sha256] = str(relative_path)

        is_hard_negative = item_role == "hard_negative"
        if family is None and item_role not in {"hard_negative", "mixture"}:
            reasons.append("target_family_unresolved")
        accepted = (
            not reasons
            and (
                family is not None
                or item_role in {"hard_negative", "mixture"}
            )
            and (
                curation_evidence is None
                or bool(curation_evidence["accepted"])
            )
        )
        rows.append(
            {
                "schema_version": "1.0",
                "source_id": source.source_id,
                "source_version": source.version,
                "archive_sha256": archive_sha256,
                "provenance_sha256": resolved_provenance_sha256,
                "relative_path": str(relative_path),
                "local_path": _repository_path(path),
                "composition_id": composition_id,
                "split": None,
                "family": family,
                "item_role": item_role,
                "source_label": source_label,
                "curation": curation_evidence,
                "roles": list(source.roles),
                "rights_status": source.rights_status,
                "release_use": source.release_use,
                "accepted": accepted,
                "rejection_reasons": sorted(set(reasons)),
                "duplicate_of": duplicate_of,
                "audio": asdict(audit),
            }
        )

    acquisition = source.raw.get("acquisition") or {}
    if split_assignments is not None:
        for row in rows:
            composition_id = str(row["composition_id"])
            row["split"] = preassigned_splits[composition_id]
    elif acquisition.get("split_policy") == "train_only":
        for row in rows:
            row["split"] = "train"
    else:
        assign_grouped_splits(rows, source.source_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "items.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    accepted_rows = [row for row in rows if row["accepted"]]
    try:
        manifest_reference = str(manifest_path.relative_to(ROOT_DIR))
    except ValueError:
        manifest_reference = str(manifest_path)
    report = {
        "schema_version": "1.0",
        "source_id": source.source_id,
        "source_version": source.version,
        "archive_sha256": archive_sha256,
        "provenance_sha256": resolved_provenance_sha256,
        "manifest": manifest_reference,
        "audio_file_count": len(rows),
        "accepted_file_count": len(accepted_rows),
        "rejected_file_count": len(rows) - len(accepted_rows),
        "accepted_duration_seconds": sum(
            float(row["audio"]["duration_seconds"]) for row in accepted_rows
        ),
        "accepted_active_seconds": sum(
            float(row["audio"]["duration_seconds"])
            * float(row["audio"]["active_fraction"])
            for row in accepted_rows
        ),
        "accepted_target_active_seconds": sum(
            float(row["audio"]["duration_seconds"])
            * float(row["audio"]["active_fraction"])
            for row in accepted_rows
            if row["item_role"] == "target"
        ),
        "accepted_composition_count": len(
            {row["composition_id"] for row in accepted_rows}
        ),
        "family_counts": dict(
            Counter(
                row["family"]
                for row in accepted_rows
                if row["family"] is not None
            )
        ),
        "hard_negative_count": sum(
            row["item_role"] == "hard_negative" for row in accepted_rows
        ),
        "split_counts": dict(Counter(row["split"] for row in accepted_rows)),
        "composition_split_counts": dict(
            Counter(
                {
                    row["composition_id"]: row["split"]
                    for row in accepted_rows
                }.values()
            )
        ),
        "rejection_counts": dict(
            Counter(
                reason
                for row in rows
                for reason in row["rejection_reasons"]
            )
        ),
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _repository_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT_DIR.resolve()))
    except ValueError:
        return str(resolved)


def audit_audio(path: Path, *, allow_short: bool = False) -> AudioAudit:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise TrainingCorpusError("training audio dependencies are not installed") from exc

    try:
        info = sf.info(path)
    except Exception as exc:
        return _rejected_audio_audit(path, "audio_decode_failed")

    sum_squares = 0.0
    sample_count = 0
    active_samples = 0
    clipping_samples = 0
    peak = 0.0
    channel_sum = None
    stereo_difference_squares = 0.0
    stereo_reference_squares = 0.0
    try:
        for block in sf.blocks(
            path,
            blocksize=max(info.samplerate, 1),
            dtype="float32",
            always_2d=True,
        ):
            if not np.isfinite(block).all():
                return _rejected_audio_audit(path, "non_finite_audio")
            absolute = np.abs(block)
            peak = max(peak, float(absolute.max(initial=0.0)))
            sum_squares += float(np.square(block, dtype=np.float64).sum())
            sample_count += int(block.size)
            active_samples += int((absolute >= 10 ** (-60 / 20)).sum())
            clipping_samples += int((absolute >= 0.999).sum())
            block_sum = block.sum(axis=0, dtype=np.float64)
            channel_sum = block_sum if channel_sum is None else channel_sum + block_sum
            if block.shape[1] == 2:
                difference = block[:, 0] - block[:, 1]
                stereo_difference_squares += float(
                    np.square(difference, dtype=np.float64).sum()
                )
                stereo_reference_squares += float(
                    np.square(block, dtype=np.float64).sum()
                )
    except Exception:
        return _rejected_audio_audit(path, "audio_decode_failed")

    rms = math.sqrt(sum_squares / max(sample_count, 1))
    rms_dbfs = 20 * math.log10(max(rms, 1e-12))
    active_fraction = active_samples / max(sample_count, 1)
    clipping_fraction = clipping_samples / max(sample_count, 1)
    dc_offset = (
        float(abs(channel_sum).max(initial=0.0)) / max(int(info.frames), 1)
        if channel_sum is not None
        else 0.0
    )
    stereo_difference_db = None
    if info.channels == 2:
        ratio = stereo_difference_squares / max(stereo_reference_squares, 1e-12)
        stereo_difference_db = 10 * math.log10(max(ratio, 1e-12))

    reasons: list[str] = []
    warnings: list[str] = []
    minimum_duration = 0.08 if allow_short else 1.0
    if info.duration < minimum_duration:
        reasons.append("audio_too_short")
    if info.samplerate < 16000:
        reasons.append("sample_rate_too_low")
    if info.channels < 1 or info.channels > 2:
        reasons.append("unsupported_channel_count")
    if rms_dbfs < -60 or active_fraction < 0.01:
        reasons.append("insufficient_active_audio")
    if clipping_fraction > 0.05:
        reasons.append("severe_clipping")
    elif clipping_fraction > 0.001:
        warnings.append("possible_clipping")
    if dc_offset > 0.05:
        warnings.append("large_dc_offset")
    if stereo_difference_db is not None and stereo_difference_db < -80:
        warnings.append("dual_mono")

    return AudioAudit(
        sample_rate=int(info.samplerate),
        channels=int(info.channels),
        frames=int(info.frames),
        duration_seconds=float(info.duration),
        subtype=str(info.subtype),
        sha256=file_checksum(path),
        peak=peak,
        rms_dbfs=rms_dbfs,
        active_fraction=active_fraction,
        clipping_fraction=clipping_fraction,
        dc_offset=dc_offset,
        stereo_difference_db=stereo_difference_db,
        accepted=not reasons,
        rejection_reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def classify_target_family(
    source: TrainingSource,
    relative_path: Path,
) -> tuple[str | None, str]:
    acquisition = source.raw.get("acquisition") or {}
    default_family = str(acquisition.get("default_family") or "")
    normalized_parts = [_normalize_label(part) for part in relative_path.parts]
    normalized_path = "/".join(normalized_parts)
    source_label = _normalize_label(relative_path.parent.name)

    if default_family in TARGET_FAMILIES:
        return default_family, source_label
    if source.source_id == "cocochorales" and relative_path.parts:
        for part in relative_path.parts:
            track_name = _normalize_label(part)
            if track_name.startswith("string_track"):
                return "strings", source_label
            if track_name.startswith(("brass_track", "woodwind_track")):
                return "wind_brass", source_label
    if source.source_id == "urmp":
        filename_tokens = set(
            _normalize_label(relative_path.stem).split("_")
        )
        if filename_tokens & {"db", "va", "vc", "vn"}:
            return "strings", source_label
        if filename_tokens & {
            "bn",
            "cl",
            "fl",
            "hn",
            "ob",
            "sax",
            "tba",
            "tbn",
            "tpt",
        }:
            return "wind_brass", source_label
    if source.source_id == "spheres":
        stem_label = _normalize_label(relative_path.stem)
        if stem_label == "bass":
            return "strings", source_label
        if stem_label == "coranglais":
            return "wind_brass", source_label
    if source.source_id == "medleydb_sample":
        curation = _load_source_curation(source) or {}
        song_id = _medleydb_song_id(relative_path)
        stem_id = _medleydb_stem_id(relative_path)
        song = (curation.get("songs") or {}).get(song_id, {})
        stem = (song.get("stems") or {}).get(stem_id, {})
        family = str(stem.get("family") or "")
        label = _normalize_label(str(stem.get("label") or source_label))
        if family in TARGET_FAMILIES:
            return family, label
    if source.source_id == "rawstems":
        if "/gtr/ag/" in f"/{normalized_path}/":
            return "acoustic_guitar", "gtr_ag"
        if "/gtr/eg/" in f"/{normalized_path}/":
            return "electric_guitar", "gtr_eg"
        if "/synth/" in f"/{normalized_path}/":
            return "synth", "synth"
        if "/orch/str/" in f"/{normalized_path}/":
            return "strings", "orch_str"
        if (
            "/orch/ww/" in f"/{normalized_path}/"
            or "/orch/br/" in f"/{normalized_path}/"
        ):
            return "wind_brass", "orch_ww_br"
    if "guitar_electric" in normalized_path:
        return "electric_guitar", source_label

    labels = set(normalized_parts)
    if labels & ACOUSTIC_GUITAR_LABELS:
        return "acoustic_guitar", source_label
    if labels & ELECTRIC_GUITAR_LABELS:
        return "electric_guitar", source_label
    if labels & SYNTH_LABELS:
        return "synth", source_label
    if labels & STRING_LABELS:
        return "strings", source_label
    if labels & WIND_BRASS_LABELS:
        return "wind_brass", source_label

    tokens = set(normalized_path.replace("/", "_").split("_"))
    if tokens & ACOUSTIC_GUITAR_LABELS:
        return "acoustic_guitar", source_label
    if tokens & STRING_LABELS:
        return "strings", source_label
    if tokens & SYNTH_LABELS:
        return "synth", source_label
    if tokens & WIND_BRASS_LABELS:
        return "wind_brass", source_label
    return None, source_label


def infer_composition_id(source: TrainingSource, relative_path: Path) -> str:
    if source.source_id == "chorale_bricks":
        parts = list(relative_path.parts)
        for index, part in enumerate(parts):
            if part in {"tracks", "tracks_normalized"} and index > 0:
                return f"{source.source_id}:{parts[index - 1]}"
    if source.source_id == "guitar_techs":
        archive = relative_path.parts[0] if relative_path.parts else "unknown"
        canonical_stem = re.sub(
            r"^(directinput|micamp|ego|exo)_",
            "",
            relative_path.stem,
        )
        return f"{source.source_id}:{archive}:{canonical_stem}"
    if source.source_id == "eg_ipt":
        parts = relative_path.parts
        if len(parts) >= 5:
            pickup = parts[-4]
            technique = parts[-2]
            canonical_stem = re.sub(
                r"_(rib|DI|room|dyn|cond|bucket)$",
                "",
                relative_path.stem,
            )
            return (
                f"{source.source_id}:{pickup}:{technique}:"
                f"{canonical_stem}"
            )
    if source.source_id == "quartset":
        composition = relative_path.stem.split("-", 1)[0]
        return f"{source.source_id}:{composition}"
    if source.source_id == "rawstems":
        parts = list(relative_path.parts)
        if len(parts) >= 2:
            return f"{source.source_id}:{parts[0]}"
    if source.source_id == "cocochorales" and relative_path.parts:
        for part in relative_path.parts:
            track_name = _normalize_label(part)
            if re.fullmatch(
                r"(string|brass|woodwind|random)_track\d+",
                track_name,
            ):
                return f"{source.source_id}:{track_name}"
    if source.source_id == "urmp" and relative_path.parts:
        for part in relative_path.parts:
            normalized_part = _normalize_label(part)
            if re.match(r"^\d{2}_", normalized_part):
                return f"{source.source_id}:{normalized_part}"
    if source.source_id == "medleydb_sample":
        return f"{source.source_id}:{_medleydb_song_id(relative_path)}"
    parts = [
        part
        for part in relative_path.parts[:-1]
        if not part.startswith(".") and _normalize_label(part) not in {"audio", "stems"}
    ]
    if not parts:
        return f"{source.source_id}:{relative_path.stem}"
    meaningful = parts[-2:] if len(parts) >= 2 else parts
    return f"{source.source_id}:{'/'.join(meaningful)}"


def _item_role(
    source: TrainingSource,
    relative_path: Path,
    family: str | None,
) -> str:
    if (
        source.source_id == "medleydb_sample"
        and relative_path.stem.upper().endswith("_MIX")
    ):
        return "mixture"
    if (
        "mixture" in source.roles
        and (
            _normalize_label(relative_path.stem) in {"mix", "mixture"}
            or (
                source.source_id == "urmp"
                and _normalize_label(relative_path.stem).startswith("aumix_")
            )
        )
    ):
        return "mixture"
    if family is None and "hard_negative" in source.roles:
        return "hard_negative"
    return "target"


def assign_grouped_splits(rows: list[dict[str, Any]], source_id: str) -> None:
    composition_ids = sorted(
        {str(row["composition_id"]) for row in rows},
        key=lambda value: hashlib.sha256(
            f"split-ranked-v1:{source_id}:{value}".encode()
        ).digest(),
    )
    count = len(composition_ids)
    if count == 1:
        split_by_composition = {composition_ids[0]: "train"}
    elif count == 2:
        split_by_composition = {
            composition_ids[0]: "validation",
            composition_ids[1]: "train",
        }
    else:
        test_count = max(1, round(count * 0.10))
        validation_count = max(1, round(count * 0.10))
        if test_count + validation_count >= count:
            test_count = 1
            validation_count = 1
        split_by_composition = {}
        for index, composition_id in enumerate(composition_ids):
            if index < test_count:
                split = "test"
            elif index < test_count + validation_count:
                split = "validation"
            else:
                split = "train"
            split_by_composition[composition_id] = split

    for row in rows:
        row["split"] = split_by_composition[str(row["composition_id"])]


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_zip(
    archive: Path,
    destination: Path,
    *,
    member_filter: Callable[[PurePosixPath], bool] | None = None,
    postprocess_member: Callable[[Path], None] | None = None,
) -> None:
    with zipfile.ZipFile(archive) as handle:
        for entry in handle.infolist():
            member = PurePosixPath(entry.filename)
            if _is_archive_metadata(member):
                continue
            if member_filter is not None and not member_filter(member):
                continue
            target = _safe_archive_target(destination, entry.filename)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                raise TrainingCorpusError(
                    f"duplicate archive member: {entry.filename}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
            if postprocess_member is not None:
                postprocess_member(target)


def _extract_tar(
    archive: Path,
    destination: Path,
    *,
    member_filter: Callable[[PurePosixPath], bool] | None = None,
    postprocess_member: Callable[[Path], None] | None = None,
) -> None:
    with tarfile.open(archive) as handle:
        for entry in handle:
            if entry.issym() or entry.islnk() or entry.isdev():
                raise TrainingCorpusError(f"unsafe tar member: {entry.name}")
            member = PurePosixPath(entry.name)
            if _is_archive_metadata(member):
                continue
            if member_filter is not None and not member_filter(member):
                continue
            target = _safe_archive_target(destination, entry.name)
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                raise TrainingCorpusError(
                    f"duplicate archive member: {entry.name}"
                )
            extracted = handle.extractfile(entry)
            if extracted is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with extracted, target.open("wb") as output:
                shutil.copyfileobj(extracted, output, length=8 * 1024 * 1024)
            if postprocess_member is not None:
                postprocess_member(target)


def _is_archive_metadata(member: PurePosixPath) -> bool:
    return any(
        part == "__MACOSX" or part.startswith("._")
        for part in member.parts
    )


def _safe_archive_target(destination: Path, member_name: str) -> Path:
    member = PurePosixPath(member_name)
    if member.is_absolute() or ".." in member.parts:
        raise TrainingCorpusError(f"unsafe archive member: {member_name}")
    target = destination.joinpath(*member.parts)
    try:
        target.resolve().relative_to(destination.resolve())
    except ValueError as exc:
        raise TrainingCorpusError(f"unsafe archive member: {member_name}") from exc
    return target


def _source_allows_short_audio(source: TrainingSource) -> bool:
    return bool({"articulation", "timbre", "rendering_source"} & set(source.roles))


def _load_source_curation(source: TrainingSource) -> dict[str, Any] | None:
    acquisition = source.raw.get("acquisition") or {}
    configured_path = acquisition.get("curation_manifest")
    if configured_path:
        path = (ROOT_DIR / str(configured_path)).resolve()
        try:
            path.relative_to(ROOT_DIR.resolve())
        except ValueError as exc:
            raise TrainingCorpusError(
                f"curation manifest escapes repository: {configured_path}"
            ) from exc
        if not path.exists():
            raise TrainingCorpusError(f"curation manifest missing: {path}")
        return _load_json(path)
    if source.source_id == "rawstems" and XLANCE_CURATION_PATH.exists():
        return _load_json(XLANCE_CURATION_PATH)
    return None


@lru_cache(maxsize=32)
def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _curation_evidence(
    source: TrainingSource,
    composition_id: str,
    family: str | None,
    relative_path: Path,
    item_role: str,
    curation: dict[str, Any] | None,
) -> dict[str, object] | None:
    if curation is None:
        return None
    if source.source_id == "rawstems":
        song_id = composition_id.removeprefix("rawstems:")
        song = (curation.get("songs") or {}).get(song_id)
        families = (
            list(song.get("families") or [])
            if isinstance(song, dict)
            else []
        )
        return {
            "manifest": str(XLANCE_CURATION_PATH.relative_to(ROOT_DIR)),
            "xlance_commit": str(curation.get("xlance_commit") or ""),
            "song_id": song_id,
            "families": families,
            "accepted": bool(song and (family is None or family in families)),
            "rejection_reason": "not_in_xlance_curation",
        }
    if source.source_id == "medleydb_sample":
        manifest_path = str(
            (source.raw.get("acquisition") or {}).get("curation_manifest") or ""
        )
        song_id = composition_id.removeprefix("medleydb_sample:")
        song = (curation.get("songs") or {}).get(song_id)
        stem_id = _medleydb_stem_id(relative_path)
        stem = (
            (song.get("stems") or {}).get(stem_id)
            if isinstance(song, dict)
            else None
        )
        accepted = bool(
            song
            and (
                item_role == "mixture"
                or (
                    isinstance(stem, dict)
                    and stem.get("family") == family
                )
            )
        )
        return {
            "manifest": manifest_path,
            "metadata_commit": str(curation.get("metadata_commit") or ""),
            "song_id": song_id,
            "stem_id": stem_id,
            "accepted": accepted,
            "rejection_reason": "not_in_medleydb_specialist_curation",
        }
    return None


def _medleydb_song_id(relative_path: Path) -> str:
    parts = list(relative_path.parts)
    for index, part in enumerate(parts[:-1]):
        if _normalize_label(part) == "audio" and index + 1 < len(parts):
            return parts[index + 1]
    return relative_path.parts[0] if relative_path.parts else relative_path.stem


def _medleydb_stem_id(relative_path: Path) -> str:
    match = re.search(r"_STEM_(\d+)$", relative_path.stem, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _normalize_label(value: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else "_"
        for character in value
    )
    return "_".join(part for part in normalized.split("_") if part)


def _is_ignored_archive_artifact(relative_path: Path) -> bool:
    return (
        "__MACOSX" in relative_path.parts
        or relative_path.name.startswith("._")
        or relative_path.name in {".DS_Store", "Thumbs.db"}
    )


def _source_specific_rejections(
    source: TrainingSource,
    relative_path: Path,
) -> list[str]:
    if (
        source.source_id == "chorale_bricks"
        and "tracks_normalized" in relative_path.parts
    ):
        return ["derived_normalized_copy"]
    if source.source_id == "guitar_techs" and "video" in relative_path.parts:
        return ["reference_video_audio"]
    if source.source_id == "medleydb_sample":
        normalized_parts = {_normalize_label(part) for part in relative_path.parts}
        if any(part.endswith("_raw") for part in normalized_parts):
            return ["duplicate_raw_view"]
        if (
            "_STEM_" in relative_path.stem.upper()
            and _medleydb_stem_id(relative_path)
            and classify_target_family(source, relative_path)[0] is None
        ):
            return ["non_specialist_stem"]
    return []


def _rejected_audio_audit(path: Path, reason: str) -> AudioAudit:
    sha256 = file_checksum(path) if path.exists() else ""
    return AudioAudit(
        sample_rate=0,
        channels=0,
        frames=0,
        duration_seconds=0.0,
        subtype="",
        sha256=sha256,
        peak=0.0,
        rms_dbfs=-240.0,
        active_fraction=0.0,
        clipping_fraction=0.0,
        dc_offset=0.0,
        stereo_difference_db=None,
        accepted=False,
        rejection_reasons=(reason,),
        warnings=(),
    )

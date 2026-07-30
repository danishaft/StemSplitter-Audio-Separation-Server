from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
import mimetypes
import os
import shutil
import struct
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import quote

from .object_storage import ObjectRef, object_store_from_config
from .training_data_registry import TrainingSource, load_training_data_registry

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STAGING_ROOT = ROOT_DIR / "datasets" / "staging"
DEFAULT_INVENTORY_ROOT = ROOT_DIR / "datasets" / "inventories"
DEFAULT_RECEIPT_ROOT = ROOT_DIR / "datasets" / "manifests" / "acquisition"
MAX_REMOTE_CENTRAL_DIRECTORY_BYTES = 256 * 1024 * 1024
REMOTE_ZIP_SELECTION_MAX_GAP_BYTES = 1024 * 1024


class TrainingDataAcquisitionError(RuntimeError):
    """Raised when a source cannot be acquired or verified safely."""


def _path_reference(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT_DIR))
    except ValueError:
        return str(resolved)


@dataclass(frozen=True)
class ProviderFile:
    path: str
    size_bytes: int
    download_url: str | None
    checksum_algorithm: str | None
    checksum: str | None
    provider_revision: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "download_url": self.download_url,
            "checksum_algorithm": self.checksum_algorithm,
            "checksum": self.checksum,
            "provider_revision": self.provider_revision,
        }


def list_source_files(source_id: str) -> tuple[TrainingSource, list[ProviderFile]]:
    source = load_training_data_registry().sources.get(source_id)
    if source is None:
        raise TrainingDataAcquisitionError(f"unknown training source: {source_id}")
    acquisition = source.raw.get("acquisition")
    if not isinstance(acquisition, dict):
        raise TrainingDataAcquisitionError(
            f"source has no acquisition configuration: {source_id}"
        )

    provider = str(acquisition.get("provider") or "")
    if provider == "huggingface":
        return source, _list_huggingface_files(acquisition)
    if provider == "gcs_public":
        return source, _list_gcs_public_files(acquisition)
    if provider == "static_http":
        return source, _list_static_http_files(acquisition)
    if provider == "dryad":
        return source, _list_dryad_files(acquisition)
    if provider == "zenodo":
        return source, _list_zenodo_files(acquisition)
    reason = str(acquisition.get("reason") or "manual acquisition required")
    raise TrainingDataAcquisitionError(f"{source_id}: {reason}")


def snapshot_source_inventory(
    source_id: str,
    *,
    output_root: Path = DEFAULT_INVENTORY_ROOT,
) -> tuple[Path, dict[str, Any]]:
    source, files = list_source_files(source_id)
    payload = {
        "schema_version": "1.0",
        "source_id": source.source_id,
        "source_version": source.version,
        "source_url": source.source_url,
        "license": source.license,
        "rights_status": source.rights_status,
        "file_count": len(files),
        "total_size_bytes": sum(item.size_bytes for item in files),
        "files": [item.as_dict() for item in files],
    }
    output_path = output_root / source.source_id / source.version / "inventory.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path, payload


def snapshot_remote_zip_inventory(
    source_id: str,
    file_path: str,
    *,
    output_root: Path = DEFAULT_INVENTORY_ROOT,
) -> tuple[Path, dict[str, Any]]:
    source, files = list_source_files(source_id)
    provider_file = _find_file(files, file_path)
    if not provider_file.download_url:
        raise TrainingDataAcquisitionError(
            f"provider file has no remote ZIP URL: {provider_file.path}"
        )
    entries = _list_remote_zip_entries(provider_file)
    payload = {
        "schema_version": "1.0",
        "source_id": source.source_id,
        "source_version": source.version,
        "provider_path": provider_file.path,
        "provider_size_bytes": provider_file.size_bytes,
        "provider_checksum_algorithm": provider_file.checksum_algorithm,
        "provider_checksum": provider_file.checksum,
        "provider_revision": provider_file.provider_revision,
        "entry_count": len(entries),
        "compressed_size_bytes": sum(
            int(entry["compressed_size_bytes"]) for entry in entries
        ),
        "uncompressed_size_bytes": sum(
            int(entry["uncompressed_size_bytes"]) for entry in entries
        ),
        "entries": entries,
    }
    safe_name = str(_safe_relative_path(provider_file.path)).replace("/", "__")
    output_path = (
        output_root
        / source.source_id
        / source.version
        / f"{safe_name}.entries.json.gz"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output_path, payload


def acquire_source_file(
    source_id: str,
    file_path: str,
    *,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
    upload: bool = False,
    delete_after_upload: bool = False,
) -> tuple[Path | None, dict[str, Any]]:
    source, files = list_source_files(source_id)
    provider_file = _find_file(files, file_path)
    safe_relative = _safe_relative_path(provider_file.path)
    target = staging_root / source.source_id / source.version / safe_relative
    receipt_path = (
        receipt_root
        / source.source_id
        / source.version
        / safe_relative.with_suffix(f"{safe_relative.suffix}.receipt.json")
    )
    prior_receipt = _read_receipt(receipt_path)
    existing_receipt = _verified_existing_receipt(
        receipt_path,
        upload=upload,
        target=target,
    )
    if existing_receipt is not None:
        return target if target.exists() else None, existing_receipt

    target.parent.mkdir(parents=True, exist_ok=True)

    acquisition = source.raw["acquisition"]
    provider = str(acquisition["provider"])
    if provider == "huggingface":
        _download_huggingface_file(acquisition, provider_file, target)
    elif provider in {"dryad", "gcs_public", "static_http", "zenodo"}:
        _download_http_file(provider_file, target)
    else:  # pragma: no cover - list_source_files rejects this first
        raise TrainingDataAcquisitionError(f"unsupported provider: {provider}")

    actual_size = target.stat().st_size
    if provider_file.size_bytes and actual_size != provider_file.size_bytes:
        raise TrainingDataAcquisitionError(
            f"download size mismatch for {provider_file.path}: "
            f"expected {provider_file.size_bytes}, got {actual_size}"
        )

    sha256 = _file_checksum(target, "sha256")
    _verify_provider_checksum(target, provider_file)
    object_ref: ObjectRef | None = None
    prior_object = prior_receipt.get("object")
    object_payload = prior_object if isinstance(prior_object, dict) else None
    remote_readback_verified = (
        prior_receipt.get("remote_readback_verified") is True
    )
    if upload:
        object_ref = _upload_training_file(source, provider_file, target)
        _verify_remote_readback(object_ref, target)
        object_payload = object_ref.as_dict()
        remote_readback_verified = True

    if delete_after_upload:
        if object_ref is None:
            raise TrainingDataAcquisitionError(
                "delete_after_upload requires a successful object-store upload"
            )
        if not remote_readback_verified:
            raise TrainingDataAcquisitionError(
                "delete_after_upload requires verified remote read access"
            )
        target.unlink()

    receipt = {
        "schema_version": "1.0",
        "source_id": source.source_id,
        "source_version": source.version,
        "provider_path": provider_file.path,
        "size_bytes": actual_size,
        "sha256": sha256,
        "provider_checksum_algorithm": provider_file.checksum_algorithm,
        "provider_checksum": provider_file.checksum,
        "provider_revision": provider_file.provider_revision,
        "rights_status": source.rights_status,
        "release_use": source.release_use,
        "local_path": _path_reference(target) if target.exists() else None,
        "local_retained": target.exists(),
        "object": object_payload,
        "remote_readback_verified": remote_readback_verified,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return target if target.exists() else None, receipt


def acquire_remote_zip_selection(
    source_id: str,
    file_path: str,
    selection_name: str,
    *,
    include_components: tuple[str, ...],
    suffixes: tuple[str, ...] = (".wav",),
    staging_root: Path = DEFAULT_STAGING_ROOT,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
) -> tuple[Path, dict[str, Any]]:
    source, files = list_source_files(source_id)
    provider_file = _find_file(files, file_path)
    if not provider_file.download_url:
        raise TrainingDataAcquisitionError(
            f"provider file has no remote ZIP URL: {provider_file.path}"
        )
    safe_selection = _safe_selection_name(selection_name)
    target_root = (
        staging_root
        / source.source_id
        / source.version
        / "selections"
        / safe_selection
    )
    receipt_path = (
        receipt_root
        / source.source_id
        / source.version
        / f"{safe_selection}.selection.json"
    )
    prior_receipt = _read_receipt(receipt_path)
    if (
        prior_receipt.get("provider_path") == provider_file.path
        and prior_receipt.get("selection_name") == safe_selection
        and tuple(prior_receipt.get("include_components") or ())
        == include_components
        and tuple(prior_receipt.get("suffixes") or ()) == suffixes
    ):
        prior_entries = list(prior_receipt.get("entries") or [])
        if prior_entries and all(
            (target_root / str(entry["path"])).is_file()
            for entry in prior_entries
        ):
            return target_root, prior_receipt

    inventory_path = (
        DEFAULT_INVENTORY_ROOT
        / source.source_id
        / source.version
        / f"{provider_file.path.replace('/', '__')}.entries.json.gz"
    )
    if not inventory_path.exists():
        legacy_inventory = inventory_path.with_suffix("")
        if legacy_inventory.exists():
            inventory_path = legacy_inventory
        else:
            inventory_path, _ = snapshot_remote_zip_inventory(
                source_id,
                file_path,
            )
    inventory = _read_json_document(inventory_path)
    entries = list(inventory.get("entries") or [])
    selected = [
        entry
        for entry in entries
        if _remote_zip_entry_selected(
            entry,
            include_components=include_components,
            suffixes=suffixes,
        )
    ]
    if not selected:
        raise TrainingDataAcquisitionError(
            f"remote ZIP selection is empty: {selection_name}"
        )

    block_root = target_root.parent / f".{safe_selection}.blocks"
    target_root.mkdir(parents=True, exist_ok=True)
    block_root.mkdir(parents=True, exist_ok=True)
    runs = _remote_zip_selection_runs(
        entries,
        selected_paths={str(entry["path"]) for entry in selected},
        archive_size=provider_file.size_bytes,
    )
    extracted_count = 0
    for run_index, run in enumerate(runs):
        start = int(run["start"])
        end = int(run["end"])
        block_path = block_root / f"block-{run_index:04d}.bin"
        _download_http_block_parallel(
            provider_file.download_url,
            block_path,
            start,
            end,
        )
        with block_path.open("rb") as block:
            for entry in run["entries"]:
                _extract_remote_zip_entry(
                    block,
                    block_start=start,
                    entry=entry,
                    target_root=target_root,
                )
                extracted_count += 1
        block_path.unlink()
    block_root.rmdir()

    selection_entries = [
        {
            "path": str(entry["path"]),
            "compressed_size_bytes": int(entry["compressed_size_bytes"]),
            "uncompressed_size_bytes": int(entry["uncompressed_size_bytes"]),
            "crc32": str(entry["crc32"]),
        }
        for entry in selected
    ]
    receipt = {
        "schema_version": "1.0",
        "source_id": source.source_id,
        "source_version": source.version,
        "provider_path": provider_file.path,
        "provider_size_bytes": provider_file.size_bytes,
        "provider_checksum_algorithm": provider_file.checksum_algorithm,
        "provider_checksum": provider_file.checksum,
        "provider_revision": provider_file.provider_revision,
        "selection_name": safe_selection,
        "include_components": list(include_components),
        "suffixes": list(suffixes),
        "entry_count": len(selection_entries),
        "extracted_count": extracted_count,
        "compressed_size_bytes": sum(
            int(entry["compressed_size_bytes"]) for entry in selected
        ),
        "uncompressed_size_bytes": sum(
            int(entry["uncompressed_size_bytes"]) for entry in selected
        ),
        "local_path": _path_reference(target_root),
        "local_retained": True,
        "remote_inventory": str(inventory_path.relative_to(ROOT_DIR)),
        "rights_status": source.rights_status,
        "release_use": source.release_use,
        "entries": selection_entries,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target_root, receipt


def acquire_remote_zip_manifest(
    manifest_path: Path,
    *,
    staging_root: Path = DEFAULT_STAGING_ROOT,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
    validate_only: bool = False,
) -> tuple[Path, dict[str, Any]]:
    resolved_manifest = manifest_path.expanduser().resolve()
    manifest = _read_json_document(resolved_manifest)
    source_id = str(manifest.get("source_id") or "")
    selection_name = _safe_selection_name(
        str(manifest.get("selection_name") or "")
    )
    source, files = list_source_files(source_id)
    if str(manifest.get("source_version") or "") != source.version:
        raise TrainingDataAcquisitionError(
            "selection manifest source version does not match registry"
        )
    archives = manifest.get("archives")
    if not isinstance(archives, list) or not archives:
        raise TrainingDataAcquisitionError(
            "selection manifest contains no archives"
        )

    target_root = (
        staging_root
        / source.source_id
        / source.version
        / "selections"
        / selection_name
    )
    block_root = target_root.parent / f".{selection_name}.blocks"
    target_root.mkdir(parents=True, exist_ok=True)
    block_root.mkdir(parents=True, exist_ok=True)
    seen_paths: set[str] = set()
    archive_receipts: list[dict[str, object]] = []
    selected_entries: list[dict[str, object]] = []
    prepared_archives: list[
        tuple[
            int,
            ProviderFile,
            list[dict[str, object]],
            list[dict[str, object]],
            list[dict[str, object]],
        ]
    ] = []

    for archive_index, archive in enumerate(archives):
        if not isinstance(archive, dict):
            raise TrainingDataAcquisitionError(
                "selection manifest archive is not an object"
            )
        provider_path = str(archive.get("provider_path") or "")
        provider_file = _find_file(files, provider_path)
        if not provider_file.download_url:
            raise TrainingDataAcquisitionError(
                f"provider file has no remote ZIP URL: {provider_path}"
            )
        _verify_manifest_archive_provider(archive, provider_file)
        inventory_path = ROOT_DIR / _safe_relative_path(
            str(archive.get("remote_inventory") or "")
        )
        expected_inventory_sha256 = str(
            archive.get("remote_inventory_sha256") or ""
        )
        if (
            not inventory_path.is_file()
            or _file_checksum(inventory_path, "sha256")
            != expected_inventory_sha256
        ):
            raise TrainingDataAcquisitionError(
                f"remote ZIP inventory provenance mismatch: {provider_path}"
            )
        inventory = _read_json_document(inventory_path)
        inventory_entries = {
            str(entry["path"]): entry
            for entry in list(inventory.get("entries") or [])
        }
        paths = archive.get("paths")
        if not isinstance(paths, list) or not paths:
            raise TrainingDataAcquisitionError(
                f"selection manifest has no paths for {provider_path}"
            )
        selected: list[dict[str, object]] = []
        for raw_path in paths:
            path = str(_safe_relative_path(str(raw_path)))
            if path in seen_paths:
                raise TrainingDataAcquisitionError(
                    f"duplicate selected path across archives: {path}"
                )
            entry = inventory_entries.get(path)
            if entry is None:
                raise TrainingDataAcquisitionError(
                    f"selected path missing from ZIP inventory: {path}"
                )
            seen_paths.add(path)
            selected.append(entry)
        _verify_manifest_archive_selection(archive, selected)

        runs = _remote_zip_selection_runs(
            list(inventory_entries.values()),
            selected_paths={str(entry["path"]) for entry in selected},
            archive_size=provider_file.size_bytes,
        )
        prepared_archives.append(
            (
                archive_index,
                provider_file,
                selected,
                runs,
                list(inventory_entries.values()),
            )
        )
        selected_entries.extend(selected)
        archive_receipts.append(
            {
                "provider_path": provider_path,
                "provider_size_bytes": provider_file.size_bytes,
                "provider_checksum_algorithm": (
                    provider_file.checksum_algorithm
                ),
                "provider_checksum": provider_file.checksum,
                "provider_revision": provider_file.provider_revision,
                "remote_inventory": str(inventory_path.relative_to(ROOT_DIR)),
                "remote_inventory_sha256": expected_inventory_sha256,
                "entry_count": len(selected),
                "range_run_count": len(runs),
                "compressed_size_bytes": sum(
                    int(entry["compressed_size_bytes"])
                    for entry in selected
                ),
                "uncompressed_size_bytes": sum(
                    int(entry["uncompressed_size_bytes"])
                    for entry in selected
                ),
            }
        )

    expected_entry_count = int(manifest.get("entry_count") or 0)
    if len(selected_entries) != expected_entry_count:
        raise TrainingDataAcquisitionError(
            "selection manifest aggregate entry count mismatch"
        )
    expected_compressed_size = int(
        manifest.get("compressed_size_bytes") or 0
    )
    actual_compressed_size = sum(
        int(entry["compressed_size_bytes"]) for entry in selected_entries
    )
    if actual_compressed_size != expected_compressed_size:
        raise TrainingDataAcquisitionError(
            "selection manifest aggregate compressed size mismatch"
        )
    expected_uncompressed_size = int(
        manifest.get("uncompressed_size_bytes") or 0
    )
    actual_uncompressed_size = sum(
        int(entry["uncompressed_size_bytes"]) for entry in selected_entries
    )
    if actual_uncompressed_size != expected_uncompressed_size:
        raise TrainingDataAcquisitionError(
            "selection manifest aggregate uncompressed size mismatch"
        )
    if validate_only:
        block_root.rmdir()
        return target_root, {
            "schema_version": "1.0",
            "source_id": source.source_id,
            "source_version": source.version,
            "selection_name": selection_name,
            "entry_count": len(selected_entries),
            "compressed_size_bytes": actual_compressed_size,
            "uncompressed_size_bytes": actual_uncompressed_size,
            "archive_count": len(prepared_archives),
            "validated": True,
        }

    for (
        archive_index,
        provider_file,
        selected,
        _planned_runs,
        inventory_entries,
    ) in prepared_archives:
        assert provider_file.download_url is not None
        missing_paths = {
            str(entry["path"])
            for entry in selected
            if not _remote_zip_entry_verified(target_root, entry)
        }
        runs = (
            _remote_zip_selection_runs(
                inventory_entries,
                selected_paths=missing_paths,
                archive_size=provider_file.size_bytes,
            )
            if missing_paths
            else []
        )
        for run in runs:
            run_entries = list(run["entries"])
            if all(
                _remote_zip_entry_verified(target_root, entry)
                for entry in run_entries
            ):
                continue
            start = int(run["start"])
            end = int(run["end"])
            block_path = block_root / (
                f"archive-{archive_index:02d}-range-{start}-{end}.bin"
            )
            _download_http_block_parallel(
                provider_file.download_url,
                block_path,
                start,
                end,
            )
            with block_path.open("rb") as block:
                for entry in run_entries:
                    _extract_remote_zip_entry(
                        block,
                        block_start=start,
                        entry=entry,
                        target_root=target_root,
                    )
            block_path.unlink()
        for entry in selected:
            if not _remote_zip_entry_verified(target_root, entry):
                raise TrainingDataAcquisitionError(
                    f"selected ZIP entry failed final verification: "
                    f"{entry['path']}"
                )
    pruned_file_count, pruned_bytes = _prune_selection_root(
        target_root,
        selected_paths=seen_paths,
    )
    for stale_block in block_root.iterdir():
        if stale_block.is_file():
            stale_block.unlink()
    block_root.rmdir()
    try:
        manifest_reference = str(resolved_manifest.relative_to(ROOT_DIR))
    except ValueError:
        manifest_reference = str(resolved_manifest)
    receipt = {
        "schema_version": "1.0",
        "source_id": source.source_id,
        "source_version": source.version,
        "selection_name": selection_name,
        "selection_manifest": manifest_reference,
        "selection_manifest_sha256": _file_checksum(
            resolved_manifest,
            "sha256",
        ),
        "curation_manifest": manifest.get("curation_manifest"),
        "curation_manifest_sha256": manifest.get(
            "curation_manifest_sha256"
        ),
        "xlance_commit": manifest.get("xlance_commit"),
        "split_policy": manifest.get("split_policy"),
        "song_split_assignments": manifest.get("song_split_assignments"),
        "family_split_song_counts": manifest.get(
            "family_split_song_counts"
        ),
        "entry_count": len(selected_entries),
        "extracted_count": len(selected_entries),
        "pruned_file_count": pruned_file_count,
        "pruned_bytes": pruned_bytes,
        "compressed_size_bytes": sum(
            int(entry["compressed_size_bytes"])
            for entry in selected_entries
        ),
        "uncompressed_size_bytes": sum(
            int(entry["uncompressed_size_bytes"])
            for entry in selected_entries
        ),
        "local_path": _path_reference(target_root),
        "local_retained": True,
        "rights_status": source.rights_status,
        "release_use": source.release_use,
        "archives": archive_receipts,
    }
    receipt_path = (
        receipt_root
        / source.source_id
        / source.version
        / f"{selection_name}.selection.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target_root, receipt


def _prune_selection_root(
    target_root: Path,
    *,
    selected_paths: set[str],
) -> tuple[int, int]:
    pruned_file_count = 0
    pruned_bytes = 0
    for path in target_root.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(target_root).as_posix()
        if relative_path in selected_paths:
            continue
        pruned_bytes += path.stat().st_size
        path.unlink()
        pruned_file_count += 1
    for path in sorted(
        (path for path in target_root.rglob("*") if path.is_dir()),
        key=lambda candidate: len(candidate.parts),
        reverse=True,
    ):
        try:
            path.rmdir()
        except OSError:
            pass
    return pruned_file_count, pruned_bytes


def _list_huggingface_files(acquisition: dict[str, Any]) -> list[ProviderFile]:
    try:
        from huggingface_hub import HfApi, hf_hub_url
    except ImportError as exc:
        raise TrainingDataAcquisitionError("huggingface_hub_not_installed") from exc

    repo_id = str(acquisition["repo_id"])
    repo_type = str(acquisition.get("repo_type") or "dataset")
    api = HfApi(token=os.getenv("HF_TOKEN") or None)
    repo_info = api.repo_info(repo_id=repo_id, repo_type=repo_type)
    revision = str(repo_info.sha)
    entries = api.list_repo_tree(
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        recursive=True,
        expand=True,
    )
    files: list[ProviderFile] = []
    for entry in entries:
        entry_type = entry.__class__.__name__.lower()
        if "file" not in entry_type:
            continue
        lfs = getattr(entry, "lfs", None)
        checksum = _nested_value(lfs, "sha256")
        size = int(
            _nested_value(lfs, "size")
            or getattr(entry, "size", 0)
            or 0
        )
        files.append(
            ProviderFile(
                path=str(getattr(entry, "path")),
                size_bytes=size,
                download_url=hf_hub_url(
                    repo_id=repo_id,
                    filename=str(getattr(entry, "path")),
                    repo_type=repo_type,
                    revision=revision,
                ),
                checksum_algorithm="sha256" if checksum else None,
                checksum=str(checksum) if checksum else None,
                provider_revision=revision,
            )
        )
    return sorted(files, key=lambda item: item.path)


def _list_zenodo_files(acquisition: dict[str, Any]) -> list[ProviderFile]:
    try:
        import requests
    except ImportError as exc:
        raise TrainingDataAcquisitionError("requests_not_installed") from exc

    record_id = str(acquisition["record_id"])
    response = requests.get(
        f"https://zenodo.org/api/records/{record_id}",
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    files: list[ProviderFile] = []
    for entry in payload.get("files") or []:
        checksum_algorithm, checksum = _split_checksum(entry.get("checksum"))
        links = entry.get("links") or {}
        files.append(
            ProviderFile(
                path=str(entry["key"]),
                size_bytes=int(entry.get("size") or 0),
                download_url=str(links.get("content") or links.get("self") or ""),
                checksum_algorithm=checksum_algorithm,
                checksum=checksum,
            )
        )
    return sorted(files, key=lambda item: item.path)


def _list_gcs_public_files(acquisition: dict[str, Any]) -> list[ProviderFile]:
    try:
        import requests
    except ImportError as exc:
        raise TrainingDataAcquisitionError("requests_not_installed") from exc

    bucket = str(acquisition["bucket"])
    object_paths = acquisition.get("object_paths")
    if not isinstance(object_paths, list) or not object_paths:
        raise TrainingDataAcquisitionError(
            "gcs_public acquisition requires object_paths"
        )

    files: list[ProviderFile] = []
    for value in object_paths:
        object_path = str(_safe_relative_path(str(value)))
        encoded_path = quote(object_path, safe="")
        metadata_url = (
            f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}"
            f"/o/{encoded_path}"
        )
        response = requests.get(metadata_url, timeout=60)
        response.raise_for_status()
        payload = response.json()
        generation = str(payload["generation"])
        md5_base64 = payload.get("md5Hash")
        checksum = (
            base64.b64decode(str(md5_base64), validate=True).hex()
            if md5_base64
            else None
        )
        download_url = (
            f"https://storage.googleapis.com/download/storage/v1/b/"
            f"{quote(bucket, safe='')}/o/{encoded_path}"
            f"?alt=media&generation={quote(generation, safe='')}"
        )
        files.append(
            ProviderFile(
                path=object_path,
                size_bytes=int(payload["size"]),
                download_url=download_url,
                checksum_algorithm="md5" if checksum else None,
                checksum=checksum,
                provider_revision=generation,
            )
        )
    return sorted(files, key=lambda item: item.path)


def _list_static_http_files(acquisition: dict[str, Any]) -> list[ProviderFile]:
    entries = acquisition.get("files")
    if not isinstance(entries, list) or not entries:
        raise TrainingDataAcquisitionError(
            "static_http acquisition requires files"
        )

    files: list[ProviderFile] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TrainingDataAcquisitionError(
                "static_http file entries must be mappings"
            )
        path = str(_safe_relative_path(str(entry["path"])))
        download_url = str(entry["url"])
        if not download_url.startswith("https://"):
            raise TrainingDataAcquisitionError(
                f"static_http URL must use HTTPS: {path}"
            )
        checksum = str(entry.get("sha256") or "")
        if not checksum or len(checksum) != 64:
            raise TrainingDataAcquisitionError(
                f"static_http file requires a SHA-256 checksum: {path}"
            )
        files.append(
            ProviderFile(
                path=path,
                size_bytes=int(entry["size_bytes"]),
                download_url=download_url,
                checksum_algorithm="sha256",
                checksum=checksum,
                provider_revision=str(
                    entry.get("provider_revision") or ""
                ) or None,
            )
        )
    return sorted(files, key=lambda item: item.path)


def _list_dryad_files(acquisition: dict[str, Any]) -> list[ProviderFile]:
    try:
        import requests
    except ImportError as exc:
        raise TrainingDataAcquisitionError("requests_not_installed") from exc

    file_ids = acquisition.get("file_ids")
    if not isinstance(file_ids, list) or not file_ids:
        raise TrainingDataAcquisitionError(
            "dryad acquisition requires file_ids"
        )

    files: list[ProviderFile] = []
    for value in file_ids:
        file_id = int(value)
        metadata_url = f"https://datadryad.org/api/v2/files/{file_id}"
        response = requests.get(metadata_url, timeout=60)
        response.raise_for_status()
        payload = response.json()
        path = str(
            payload.get("path")
            or payload.get("fileName")
            or payload.get("name")
            or ""
        )
        if not path:
            raise TrainingDataAcquisitionError(
                f"Dryad file metadata has no path: {file_id}"
            )
        size = int(payload.get("size") or payload.get("sizeBytes") or 0)
        if size <= 0:
            raise TrainingDataAcquisitionError(
                f"Dryad file metadata has no size: {file_id}"
            )
        checksum_value = (
            payload.get("digest")
            or payload.get("checksum")
            or payload.get("sha256")
        )
        checksum_algorithm, checksum = _split_checksum(checksum_value)
        if checksum and checksum_algorithm is None:
            if len(checksum) == 32:
                checksum_algorithm = "md5"
            elif len(checksum) == 64:
                checksum_algorithm = "sha256"
        if checksum and checksum_algorithm in {"sha-256", "sha_256"}:
            checksum_algorithm = "sha256"
        files.append(
            ProviderFile(
                path=path,
                size_bytes=size,
                download_url=(
                    "https://datadryad.org/stash/downloads/"
                    f"file_stream/{file_id}"
                ),
                checksum_algorithm=checksum_algorithm,
                checksum=checksum,
                provider_revision=str(file_id),
            )
        )
    return sorted(files, key=lambda item: item.path)


def _download_huggingface_file(
    acquisition: dict[str, Any],
    provider_file: ProviderFile,
    target: Path,
) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise TrainingDataAcquisitionError("huggingface_hub_not_installed") from exc

    downloaded = Path(
        hf_hub_download(
            repo_id=str(acquisition["repo_id"]),
            filename=provider_file.path,
            repo_type=str(acquisition.get("repo_type") or "dataset"),
            revision=provider_file.provider_revision,
            token=os.getenv("HF_TOKEN") or None,
            local_dir=target.parent,
        )
    )
    if downloaded.resolve() != target.resolve():
        downloaded.replace(target)


def _download_http_file(provider_file: ProviderFile, target: Path) -> None:
    if not provider_file.download_url:
        raise TrainingDataAcquisitionError(
            f"provider file has no download URL: {provider_file.path}"
        )
    try:
        import requests
    except ImportError as exc:
        raise TrainingDataAcquisitionError("requests_not_installed") from exc

    if provider_file.size_bytes >= 64 * 1024 * 1024:
        try:
            _download_http_ranges(provider_file, target)
            return
        except _RangeDownloadUnsupported:
            pass

    _download_http_single(provider_file, target)


def _download_http_single(provider_file: ProviderFile, target: Path) -> None:
    import requests

    partial = target.with_name(f".{target.name}.part")
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {"Accept-Encoding": "identity"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    with requests.get(
        provider_file.download_url,
        headers=headers,
        stream=True,
        timeout=(30, 300),
    ) as response:
        if existing and response.status_code == 200:
            existing = 0
            partial.unlink(missing_ok=True)
        response.raise_for_status()
        mode = "ab" if existing else "wb"
        with partial.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    handle.write(chunk)
    partial.replace(target)


def _download_http_ranges(provider_file: ProviderFile, target: Path) -> None:
    total_size = provider_file.size_bytes
    configured_workers = max(
        1,
        min(8, int(os.getenv("TRAINING_DOWNLOAD_WORKERS", "4"))),
    )
    workers = min(
        configured_workers,
        max(1, math_ceil_div(total_size, 64 * 1024 * 1024)),
    )
    if workers <= 1:
        raise _RangeDownloadUnsupported

    partial = target.with_name(f".{target.name}.part")
    chunk_size = math_ceil_div(total_size, workers)
    part_paths = [
        target.with_name(f".{target.name}.part.{index:03d}")
        for index in range(workers)
    ]
    if partial.exists() and not part_paths[0].exists():
        if partial.stat().st_size <= chunk_size:
            partial.replace(part_paths[0])
        else:
            partial.unlink()

    ranges = []
    for index, part_path in enumerate(part_paths):
        start = index * chunk_size
        end = min(total_size - 1, start + chunk_size - 1)
        if start <= end:
            ranges.append((part_path, start, end))

    incomplete = []
    for part_path, start, end in ranges:
        expected_size = end - start + 1
        existing_size = part_path.stat().st_size if part_path.exists() else 0
        if existing_size > expected_size:
            part_path.unlink()
            existing_size = 0
        if existing_size < expected_size:
            incomplete.append(
                {
                    "part_path": part_path,
                    "start": start,
                    "end": end,
                    "existing_size": existing_size,
                    "remaining_size": expected_size - existing_size,
                    "workers": 1,
                }
            )
    for _ in range(max(0, workers - len(incomplete))):
        if not incomplete:
            break
        selected = max(
            incomplete,
            key=lambda item: (
                int(item["remaining_size"]) / int(item["workers"]),
                -int(item["start"]),
            ),
        )
        selected["workers"] = int(selected["workers"]) + 1

    download_jobs: list[tuple[Path, int, int]] = []
    resume_groups: dict[Path, list[tuple[Path, int, int]]] = {}
    for item in incomplete:
        part_path = item["part_path"]
        start = int(item["start"])
        end = int(item["end"])
        existing_size = int(item["existing_size"])
        assigned_workers = int(item["workers"])
        if assigned_workers == 1:
            download_jobs.append((part_path, start, end))
            continue
        remaining_start = start + existing_size
        remaining_size = end - remaining_start + 1
        resume_chunk_size = math_ceil_div(
            remaining_size,
            assigned_workers,
        )
        group = []
        for worker_index in range(assigned_workers):
            sub_start = remaining_start + worker_index * resume_chunk_size
            if sub_start > end:
                break
            sub_end = min(end, sub_start + resume_chunk_size - 1)
            sub_path = part_path.with_name(
                f"{part_path.name}.resume.{worker_index:03d}"
            )
            group.append((sub_path, sub_start, sub_end))
            download_jobs.append((sub_path, sub_start, sub_end))
        resume_groups[part_path] = group

    try:
        if download_jobs:
            with ThreadPoolExecutor(
                max_workers=min(workers, len(download_jobs))
            ) as executor:
                futures = {
                    executor.submit(
                        _download_http_range,
                        str(provider_file.download_url),
                        part_path,
                        start,
                        end,
                    ): (part_path, start, end)
                    for part_path, start, end in download_jobs
                }
                for future in as_completed(futures):
                    future.result()
    except _RangeDownloadUnsupported:
        for part_path in part_paths:
            for resume_path in part_path.parent.glob(
                f"{part_path.name}.resume.*"
            ):
                resume_path.unlink(missing_ok=True)
        for part_path in part_paths[1:]:
            part_path.unlink(missing_ok=True)
        if part_paths[0].exists():
            part_paths[0].replace(partial)
        raise

    for part_path, group in resume_groups.items():
        with part_path.open("ab") as output:
            for sub_path, sub_start, sub_end in group:
                expected = sub_end - sub_start + 1
                if sub_path.stat().st_size != expected:
                    raise TrainingDataAcquisitionError(
                        f"incomplete resumed range: {sub_start}-{sub_end}"
                    )
                with sub_path.open("rb") as handle:
                    shutil.copyfileobj(
                        handle,
                        output,
                        length=8 * 1024 * 1024,
                    )
                sub_path.unlink()

    with partial.open("wb") as output:
        for part_path, start, end in ranges:
            expected = end - start + 1
            if part_path.stat().st_size != expected:
                raise TrainingDataAcquisitionError(
                    f"incomplete range for {provider_file.path}: "
                    f"{start}-{end}"
                )
            with part_path.open("rb") as handle:
                shutil.copyfileobj(handle, output, length=8 * 1024 * 1024)
    if partial.stat().st_size != total_size:
        raise TrainingDataAcquisitionError(
            f"combined download size mismatch for {provider_file.path}"
        )
    for part_path in part_paths:
        for resume_path in part_path.parent.glob(
            f"{part_path.name}.resume.*"
        ):
            resume_path.unlink(missing_ok=True)
        part_path.unlink(missing_ok=True)
    partial.replace(target)


def _download_http_range(
    url: str,
    part_path: Path,
    start: int,
    end: int,
) -> None:
    import requests

    expected_size = end - start + 1
    existing = part_path.stat().st_size if part_path.exists() else 0
    if existing == expected_size:
        return
    if existing > expected_size:
        part_path.unlink()
        existing = 0

    for attempt in range(3):
        range_start = start + existing
        headers = {
            "Accept-Encoding": "identity",
            "Range": f"bytes={range_start}-{end}",
        }
        try:
            with requests.get(
                url,
                headers=headers,
                stream=True,
                timeout=(30, 300),
            ) as response:
                if response.status_code != 206:
                    raise _RangeDownloadUnsupported
                content_range = str(response.headers.get("Content-Range") or "")
                if not content_range.startswith(f"bytes {range_start}-{end}/"):
                    raise TrainingDataAcquisitionError(
                        f"unexpected Content-Range: {content_range}"
                    )
                with part_path.open("ab" if existing else "wb") as handle:
                    for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            actual_size = part_path.stat().st_size
            if actual_size != expected_size:
                raise TrainingDataAcquisitionError(
                    f"range size mismatch: expected {expected_size}, got {actual_size}"
                )
            return
        except _RangeDownloadUnsupported:
            raise
        except Exception as exc:
            existing = part_path.stat().st_size if part_path.exists() else 0
            if attempt == 2:
                raise TrainingDataAcquisitionError(
                    f"range download failed after retries: {start}-{end}"
                ) from exc
            time.sleep(2**attempt)


def _download_http_block_parallel(
    url: str,
    target: Path,
    start: int,
    end: int,
) -> None:
    expected_size = end - start + 1
    if target.exists() and target.stat().st_size == expected_size:
        return
    workers = max(
        1,
        min(8, int(os.getenv("TRAINING_DOWNLOAD_WORKERS", "4"))),
    )
    chunk_size = math_ceil_div(expected_size, workers)
    parts: list[tuple[Path, int, int]] = []
    for index in range(workers):
        part_start = start + index * chunk_size
        if part_start > end:
            continue
        part_end = min(end, part_start + chunk_size - 1)
        parts.append(
            (
                target.with_name(f".{target.name}.part.{index:03d}"),
                part_start,
                part_end,
            )
        )
    if target.exists() and parts and not parts[0][0].exists():
        first_expected = parts[0][2] - parts[0][1] + 1
        if target.stat().st_size <= first_expected:
            target.replace(parts[0][0])
        else:
            target.unlink()

    with ThreadPoolExecutor(max_workers=len(parts)) as executor:
        futures = [
            executor.submit(
                _download_http_range,
                url,
                part_path,
                part_start,
                part_end,
            )
            for part_path, part_start, part_end in parts
        ]
        for future in as_completed(futures):
            future.result()

    assembled = target.with_name(f".{target.name}.assembling")
    with assembled.open("wb") as output:
        for part_path, part_start, part_end in parts:
            part_size = part_end - part_start + 1
            if part_path.stat().st_size != part_size:
                raise TrainingDataAcquisitionError(
                    f"incomplete remote ZIP block part: {part_path.name}"
                )
            with part_path.open("rb") as handle:
                shutil.copyfileobj(handle, output, length=8 * 1024 * 1024)
    if assembled.stat().st_size != expected_size:
        assembled.unlink(missing_ok=True)
        raise TrainingDataAcquisitionError(
            f"remote ZIP block size mismatch: {target.name}"
        )
    assembled.replace(target)
    for part_path, _, _ in parts:
        part_path.unlink(missing_ok=True)


def _list_remote_zip_entries(
    provider_file: ProviderFile,
) -> list[dict[str, object]]:
    if not provider_file.download_url or provider_file.size_bytes <= 0:
        raise TrainingDataAcquisitionError("remote ZIP metadata is incomplete")
    tail_size = min(provider_file.size_bytes, 1024 * 1024)
    tail_start = provider_file.size_bytes - tail_size
    tail = _read_remote_range(
        provider_file.download_url,
        start=tail_start,
        length=tail_size,
        total_size=provider_file.size_bytes,
    )
    eocd_index = tail.rfind(b"PK\x05\x06")
    if eocd_index < 0 or eocd_index + 22 > len(tail):
        raise TrainingDataAcquisitionError("remote ZIP end record not found")
    eocd = struct.unpack_from("<4s4H2IH", tail, eocd_index)
    entry_count = int(eocd[4])
    central_size = int(eocd[5])
    central_offset = int(eocd[6])
    if (
        entry_count == 0xFFFF
        or central_size == 0xFFFFFFFF
        or central_offset == 0xFFFFFFFF
    ):
        locator_index = tail.rfind(b"PK\x06\x07", 0, eocd_index)
        if locator_index < 0 or locator_index + 20 > len(tail):
            raise TrainingDataAcquisitionError(
                "remote ZIP64 locator not found"
            )
        _, _, zip64_offset, _ = struct.unpack_from(
            "<4sIQI",
            tail,
            locator_index,
        )
        zip64_record = _read_remote_range(
            provider_file.download_url,
            start=int(zip64_offset),
            length=56,
            total_size=provider_file.size_bytes,
        )
        zip64 = struct.unpack_from("<4sQ2H2I4Q", zip64_record)
        if zip64[0] != b"PK\x06\x06":
            raise TrainingDataAcquisitionError(
                "invalid remote ZIP64 end record"
            )
        entry_count = int(zip64[7])
        central_size = int(zip64[8])
        central_offset = int(zip64[9])
    if central_size > MAX_REMOTE_CENTRAL_DIRECTORY_BYTES:
        raise TrainingDataAcquisitionError(
            "remote ZIP central directory exceeds safety limit"
        )
    central = _read_remote_range(
        provider_file.download_url,
        start=central_offset,
        length=central_size,
        total_size=provider_file.size_bytes,
    )
    entries = _parse_zip_central_directory(central)
    if len(entries) != entry_count:
        raise TrainingDataAcquisitionError(
            f"remote ZIP entry count mismatch: {len(entries)} != {entry_count}"
        )
    return entries


def _parse_zip_central_directory(
    payload: bytes,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    offset = 0
    while offset < len(payload):
        if offset + 46 > len(payload):
            raise TrainingDataAcquisitionError(
                "truncated remote ZIP central directory"
            )
        header = struct.unpack_from("<4s6H3I5H2I", payload, offset)
        if header[0] != b"PK\x01\x02":
            raise TrainingDataAcquisitionError(
                "invalid remote ZIP central-directory entry"
            )
        flags = int(header[3])
        compressed_size = int(header[8])
        uncompressed_size = int(header[9])
        filename_length = int(header[10])
        extra_length = int(header[11])
        comment_length = int(header[12])
        local_offset = int(header[16])
        variable_start = offset + 46
        filename_bytes = payload[
            variable_start : variable_start + filename_length
        ]
        extra_start = variable_start + filename_length
        extra = payload[extra_start : extra_start + extra_length]
        filename = filename_bytes.decode(
            "utf-8" if flags & 0x800 else "cp437",
            errors="replace",
        )
        (
            uncompressed_size,
            compressed_size,
            local_offset,
        ) = _resolve_zip64_entry_values(
            extra,
            uncompressed_size=uncompressed_size,
            compressed_size=compressed_size,
            local_offset=local_offset,
        )
        entries.append(
            {
                "path": filename,
                "is_directory": filename.endswith("/"),
                "compressed_size_bytes": compressed_size,
                "uncompressed_size_bytes": uncompressed_size,
                "compression_method": int(header[4]),
                "crc32": f"{int(header[7]):08x}",
                "local_header_offset": local_offset,
            }
        )
        offset = (
            extra_start
            + extra_length
            + comment_length
        )
    return entries


def _resolve_zip64_entry_values(
    extra: bytes,
    *,
    uncompressed_size: int,
    compressed_size: int,
    local_offset: int,
) -> tuple[int, int, int]:
    cursor = 0
    while cursor + 4 <= len(extra):
        field_id, field_size = struct.unpack_from("<HH", extra, cursor)
        field = extra[cursor + 4 : cursor + 4 + field_size]
        cursor += 4 + field_size
        if field_id != 0x0001:
            continue
        values: list[int] = []
        value_offset = 0
        for current in (uncompressed_size, compressed_size, local_offset):
            if current == 0xFFFFFFFF:
                if value_offset + 8 > len(field):
                    raise TrainingDataAcquisitionError(
                        "truncated ZIP64 entry metadata"
                    )
                values.append(
                    int(struct.unpack_from("<Q", field, value_offset)[0])
                )
                value_offset += 8
            else:
                values.append(current)
        return values[0], values[1], values[2]
    if 0xFFFFFFFF in (uncompressed_size, compressed_size, local_offset):
        raise TrainingDataAcquisitionError("ZIP64 entry metadata missing")
    return uncompressed_size, compressed_size, local_offset


def _read_remote_range(
    url: str,
    *,
    start: int,
    length: int,
    total_size: int,
) -> bytes:
    import requests

    if start < 0 or length <= 0 or start + length > total_size:
        raise TrainingDataAcquisitionError("invalid remote byte range")
    end = start + length - 1
    response = requests.get(
        url,
        headers={
            "Accept-Encoding": "identity",
            "Range": f"bytes={start}-{end}",
        },
        timeout=(30, 300),
    )
    if response.status_code != 206:
        raise TrainingDataAcquisitionError(
            f"provider did not honor remote range: {response.status_code}"
        )
    content_range = str(response.headers.get("Content-Range") or "")
    if not content_range.startswith(f"bytes {start}-{end}/"):
        raise TrainingDataAcquisitionError(
            f"unexpected remote Content-Range: {content_range}"
        )
    if len(response.content) != length:
        raise TrainingDataAcquisitionError(
            f"remote range size mismatch: {len(response.content)} != {length}"
        )
    return response.content


def _remote_zip_entry_selected(
    entry: dict[str, object],
    *,
    include_components: tuple[str, ...],
    suffixes: tuple[str, ...],
) -> bool:
    path = PurePosixPath(str(entry.get("path") or ""))
    if entry.get("is_directory") is True or not path.parts:
        return False
    if "__MACOSX" in path.parts or path.name.startswith("._"):
        return False
    normalized_suffixes = {suffix.lower() for suffix in suffixes}
    if path.suffix.lower() not in normalized_suffixes:
        return False
    return (
        not include_components
        or any(component in path.parts for component in include_components)
    )


def _remote_zip_selection_runs(
    entries: list[dict[str, object]],
    *,
    selected_paths: set[str],
    archive_size: int,
) -> list[dict[str, object]]:
    ordered = sorted(
        (
            entry
            for entry in entries
            if entry.get("local_header_offset") is not None
            and int(entry["local_header_offset"]) >= 0
        ),
        key=lambda entry: int(entry["local_header_offset"]),
    )
    selected_positions = [
        index
        for index, entry in enumerate(ordered)
        if str(entry.get("path") or "") in selected_paths
    ]
    runs: list[dict[str, object]] = []
    for position in selected_positions:
        entry = ordered[position]
        start = int(entry["local_header_offset"])
        record_end = (
            int(ordered[position + 1]["local_header_offset"])
            if position + 1 < len(ordered)
            else archive_size
        )
        if (
            runs
            and start - int(runs[-1]["end"]) <= REMOTE_ZIP_SELECTION_MAX_GAP_BYTES
        ):
            runs[-1]["end"] = record_end
            run_entries = runs[-1]["entries"]
            assert isinstance(run_entries, list)
            run_entries.append(entry)
        else:
            runs.append(
                {
                    "start": start,
                    "end": record_end,
                    "entries": [entry],
                }
            )
    for run in runs:
        run["end"] = int(run["end"]) - 1
    planned_paths = {
        str(entry["path"])
        for run in runs
        for entry in list(run["entries"])
    }
    if planned_paths != selected_paths:
        missing = sorted(selected_paths - planned_paths)
        extra = sorted(planned_paths - selected_paths)
        raise TrainingDataAcquisitionError(
            "remote ZIP run coverage mismatch: "
            f"missing={missing[:3]} extra={extra[:3]}"
        )
    return runs


def _extract_remote_zip_entry(
    block: Any,
    *,
    block_start: int,
    entry: dict[str, object],
    target_root: Path,
) -> None:
    relative_path = _safe_relative_path(str(entry["path"]))
    target = target_root / relative_path
    expected_size = int(entry["uncompressed_size_bytes"])
    expected_crc32 = int(str(entry["crc32"]), 16)
    if (
        target.exists()
        and target.stat().st_size == expected_size
        and _file_crc32(target) == expected_crc32
    ):
        return

    block.seek(int(entry["local_header_offset"]) - block_start)
    header_bytes = block.read(30)
    if len(header_bytes) != 30:
        raise TrainingDataAcquisitionError("truncated ZIP local header")
    header = struct.unpack("<4s5H3I2H", header_bytes)
    if header[0] != b"PK\x03\x04":
        raise TrainingDataAcquisitionError("invalid ZIP local header")
    flags = int(header[2])
    method = int(header[3])
    if flags & 0x1:
        raise TrainingDataAcquisitionError("encrypted ZIP entry is unsupported")
    if method not in {0, 8}:
        raise TrainingDataAcquisitionError(
            f"unsupported ZIP compression method: {method}"
        )
    filename_length = int(header[9])
    extra_length = int(header[10])
    filename_bytes = block.read(filename_length)
    block.seek(extra_length, 1)
    filename = filename_bytes.decode(
        "utf-8" if flags & 0x800 else "cp437",
        errors="replace",
    )
    if filename != str(entry["path"]):
        raise TrainingDataAcquisitionError(
            f"ZIP local path mismatch: {filename}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.part")
    remaining = int(entry["compressed_size_bytes"])
    decompressor = zlib.decompressobj(-15) if method == 8 else None
    crc32 = 0
    written = 0
    with temp_path.open("wb") as output:
        while remaining:
            chunk = block.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                temp_path.unlink(missing_ok=True)
                raise TrainingDataAcquisitionError(
                    f"truncated ZIP entry payload: {entry['path']}"
                )
            remaining -= len(chunk)
            decoded = decompressor.decompress(chunk) if decompressor else chunk
            if decoded:
                output.write(decoded)
                written += len(decoded)
                crc32 = binascii.crc32(decoded, crc32)
        if decompressor is not None:
            decoded = decompressor.flush()
            if decoded:
                output.write(decoded)
                written += len(decoded)
                crc32 = binascii.crc32(decoded, crc32)
    crc32 &= 0xFFFFFFFF
    if written != expected_size or crc32 != expected_crc32:
        temp_path.unlink(missing_ok=True)
        raise TrainingDataAcquisitionError(
            f"ZIP entry verification failed: {entry['path']}"
        )
    temp_path.replace(target)


def _file_crc32(path: Path) -> int:
    checksum = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            checksum = binascii.crc32(chunk, checksum)
    return checksum & 0xFFFFFFFF


def _remote_zip_entry_verified(
    target_root: Path,
    entry: dict[str, object],
) -> bool:
    target = target_root / _safe_relative_path(str(entry["path"]))
    return (
        target.is_file()
        and target.stat().st_size == int(entry["uncompressed_size_bytes"])
        and _file_crc32(target) == int(str(entry["crc32"]), 16)
    )


def _verify_manifest_archive_provider(
    archive: dict[str, Any],
    provider_file: ProviderFile,
) -> None:
    expected = {
        "provider_size_bytes": provider_file.size_bytes,
        "provider_checksum_algorithm": provider_file.checksum_algorithm,
        "provider_checksum": provider_file.checksum,
        "provider_revision": provider_file.provider_revision,
    }
    for key, actual in expected.items():
        if archive.get(key) != actual:
            raise TrainingDataAcquisitionError(
                f"selection manifest provider mismatch for "
                f"{provider_file.path}: {key}"
            )


def _verify_manifest_archive_selection(
    archive: dict[str, Any],
    entries: list[dict[str, object]],
) -> None:
    expected = {
        "entry_count": len(entries),
        "compressed_size_bytes": sum(
            int(entry["compressed_size_bytes"]) for entry in entries
        ),
        "uncompressed_size_bytes": sum(
            int(entry["uncompressed_size_bytes"]) for entry in entries
        ),
    }
    for key, actual in expected.items():
        if int(archive.get(key) or -1) != actual:
            raise TrainingDataAcquisitionError(
                f"selection manifest archive aggregate mismatch: {key}"
            )


def _safe_selection_name(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in value
    ).strip("-_")
    if not normalized:
        raise TrainingDataAcquisitionError("selection name is empty")
    return normalized


def _read_json_document(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TrainingDataAcquisitionError(
            f"JSON document is not an object: {path}"
        )
    return payload


def math_ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def _upload_training_file(
    source: TrainingSource,
    provider_file: ProviderFile,
    target: Path,
) -> ObjectRef:
    store = object_store_from_config()
    if store is None:
        raise TrainingDataAcquisitionError("object_storage_not_configured")
    try:
        from boto3.s3.transfer import TransferConfig
    except ImportError as exc:
        raise TrainingDataAcquisitionError("boto3_not_installed") from exc
    key = (
        f"{store.prefix}/training-data/raw/{source.source_id}/"
        f"{source.version}/{provider_file.path}"
    )
    content_type = (
        mimetypes.guess_type(provider_file.path)[0] or "application/octet-stream"
    )
    transfer_config = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=max(
            1,
            min(8, int(os.getenv("TRAINING_UPLOAD_WORKERS", "4"))),
        ),
        use_threads=True,
    )
    return store.upload(
        target,
        key,
        content_type,
        transfer_config=transfer_config,
    )


def _verify_remote_readback(object_ref: ObjectRef, target: Path) -> None:
    store = object_store_from_config()
    if store is None:
        raise TrainingDataAcquisitionError("object_storage_not_configured")
    sample_size = min(64 * 1024, target.stat().st_size)
    offsets = {0, max(0, target.stat().st_size - sample_size)}
    try:
        with target.open("rb") as handle:
            for offset in sorted(offsets):
                handle.seek(offset)
                expected = handle.read(sample_size)
                actual = store.read_range(
                    object_ref.as_dict(),
                    start=offset,
                    length=sample_size,
                )
                if actual != expected:
                    raise TrainingDataAcquisitionError(
                        "object-store read-back content mismatch"
                    )
    except TrainingDataAcquisitionError:
        raise
    except Exception as exc:
        raise TrainingDataAcquisitionError(
            "object-store upload is not remotely readable"
        ) from exc


def _verified_existing_receipt(
    receipt_path: Path,
    *,
    upload: bool,
    target: Path,
) -> dict[str, Any] | None:
    if not receipt_path.exists():
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if target.exists():
        expected_sha256 = str(receipt.get("sha256") or "")
        if expected_sha256 and _file_checksum(target, "sha256") == expected_sha256:
            return receipt
        return None

    object_payload = receipt.get("object")
    if not upload or not isinstance(object_payload, dict):
        return None
    if receipt.get("remote_readback_verified") is not True:
        return None
    store = object_store_from_config()
    if store is None:
        return None
    try:
        stored = store.stat(object_payload)
    except Exception:
        return None
    if stored.size_bytes != int(receipt.get("size_bytes") or -1):
        return None

    if receipt.get("local_path") is not None or receipt.get("local_retained") is not False:
        receipt["local_path"] = None
        receipt["local_retained"] = False
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return receipt


def _read_receipt(receipt_path: Path) -> dict[str, Any]:
    if not receipt_path.exists():
        return {}
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _verify_provider_checksum(target: Path, provider_file: ProviderFile) -> None:
    if not provider_file.checksum_algorithm or not provider_file.checksum:
        return
    actual = _file_checksum(target, provider_file.checksum_algorithm)
    if actual.lower() != provider_file.checksum.lower():
        raise TrainingDataAcquisitionError(
            f"checksum mismatch for {provider_file.path}: "
            f"expected {provider_file.checksum}, got {actual}"
        )


def _file_checksum(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise TrainingDataAcquisitionError(
            f"unsupported checksum algorithm: {algorithm}"
        ) from exc
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_file(files: Iterable[ProviderFile], file_path: str) -> ProviderFile:
    normalized = str(_safe_relative_path(file_path))
    for item in files:
        if item.path == normalized:
            return item
    raise TrainingDataAcquisitionError(f"provider file not found: {file_path}")


def _safe_relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise TrainingDataAcquisitionError(f"unsafe provider path: {value}")
    return Path(*path.parts)


def _split_checksum(value: object) -> tuple[str | None, str | None]:
    text = str(value or "")
    if ":" not in text:
        return None, text or None
    algorithm, checksum = text.split(":", 1)
    return algorithm.lower(), checksum


def _nested_value(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


class _RangeDownloadUnsupported(RuntimeError):
    pass

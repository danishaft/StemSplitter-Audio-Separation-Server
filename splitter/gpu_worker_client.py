from __future__ import annotations

import mimetypes
import os
import shutil
import subprocess as sp
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .config import GPU_WORKER_CONFIG
from .util import ensure_dir


class GPUWorkerError(RuntimeError):
    """Raised when the optional GPU worker cannot complete a job."""


@dataclass(frozen=True)
class GPUWorkerClient:
    base_url: str
    api_key: str | None = None
    timeout: int = 30

    @classmethod
    def from_config(cls) -> GPUWorkerClient | None:
        base_url = GPU_WORKER_CONFIG.get("base_url")
        if not base_url:
            return None
        return cls(
            base_url=str(base_url).rstrip("/") + "/",
            api_key=GPU_WORKER_CONFIG.get("api_key") or None,
            timeout=int(GPU_WORKER_CONFIG["timeout"]),
        )

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    def submit(
        self,
        input_path: Path,
        *,
        profile: str,
        local_job_id: str,
        max_worker_seconds: float | None = None,
    ) -> dict[str, Any]:
        content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
        form: dict[str, object] = {"profile": profile, "local_job_id": local_job_id}
        if max_worker_seconds is not None:
            form["max_worker_seconds"] = max_worker_seconds
        with input_path.open("rb") as handle:
            response = requests.post(
                urljoin(self.base_url, "separate"),
                headers=self._headers(),
                data=form,
                files={"file": (input_path.name, handle, content_type)},
                timeout=self.timeout,
            )
        if response.status_code >= 400:
            raise GPUWorkerError(f"gpu_worker_submit_failed:{response.status_code}:{response.text[:300]}")
        return _json_response(response)

    def submit_object(
        self,
        object_reference: dict[str, object],
        *,
        input_name: str,
        profile: str,
        local_job_id: str,
        max_worker_seconds: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {
            "profile": profile,
            "local_job_id": local_job_id,
            "input_name": input_name,
            "object": object_reference,
        }
        if max_worker_seconds is not None:
            payload["max_worker_seconds"] = max_worker_seconds
        response = requests.post(
            urljoin(self.base_url, "separate-reference"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise GPUWorkerError(
                f"gpu_worker_object_submit_failed:{response.status_code}:{response.text[:300]}"
            )
        return _json_response(response)

    def status(self, worker_job_id: str) -> dict[str, Any]:
        response = requests.get(
            urljoin(self.base_url, f"jobs/{worker_job_id}"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise GPUWorkerError(f"gpu_worker_status_failed:{response.status_code}:{response.text[:300]}")
        return _json_response(response)

    def cancel(self, worker_job_id: str) -> dict[str, Any]:
        response = requests.post(
            urljoin(self.base_url, f"jobs/{worker_job_id}/cancel"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise GPUWorkerError(f"gpu_worker_cancel_failed:{response.status_code}:{response.text[:300]}")
        return _json_response(response)

    def download_artifact(self, artifact_url: str, target_path: Path) -> Path:
        url = (
            artifact_url
            if _is_absolute_url(artifact_url)
            else urljoin(self.base_url, artifact_url.lstrip("/"))
        )
        if _url_origin(url) != _url_origin(self.base_url):
            raise GPUWorkerError("gpu_worker_artifact_origin_not_allowed")
        ensure_dir(target_path.parent)
        attempts = max(1, int(GPU_WORKER_CONFIG.get("artifact_download_retries") or 1))
        retry_delay = float(GPU_WORKER_CONFIG.get("artifact_download_retry_delay") or 0.0)
        last_error: str | None = None
        temp_path = target_path.with_name(f".{target_path.name}.part")
        for attempt in range(1, attempts + 1):
            try:
                with requests.get(url, headers=self._headers(), timeout=self.timeout, stream=True) as response:
                    if response.status_code >= 400:
                        last_error = f"gpu_worker_artifact_failed:{response.status_code}:{artifact_url}"
                        if attempt < attempts:
                            time.sleep(retry_delay * attempt)
                            continue
                        raise GPUWorkerError(last_error)
                    with temp_path.open("wb") as handle:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                handle.write(chunk)
                    temp_path.replace(target_path)
                    return target_path.resolve()
            except requests.RequestException as exc:
                last_error = f"gpu_worker_artifact_request_failed:{artifact_url}:{exc}"
                if attempt >= attempts:
                    raise GPUWorkerError(last_error) from exc
                time.sleep(retry_delay * attempt)
        raise GPUWorkerError(last_error or f"gpu_worker_artifact_failed:{artifact_url}")


def wait_for_worker_job(
    client: GPUWorkerClient,
    worker_job_id: str,
    *,
    on_update,
) -> dict[str, Any]:
    start = time.time()
    poll_interval = float(GPU_WORKER_CONFIG["poll_interval"])
    max_wait = int(GPU_WORKER_CONFIG["max_wait"])

    while True:
        payload = client.status(worker_job_id)
        on_update(payload)
        status = str(payload.get("status", "unknown"))
        if status in {"completed", "error", "failed", "cancelled"}:
            return payload
        if time.time() - start > max_wait:
            raise GPUWorkerError("gpu_worker_timeout")
        time.sleep(poll_interval)


def copy_worker_artifacts(
    client: GPUWorkerClient,
    worker_payload: dict[str, Any],
    job_root: Path,
    *,
    seen: set[str],
    artifact_allowlist: dict[str, set[str] | None] | None = None,
) -> dict[str, dict[str, dict[str, object]]]:
    copied: dict[str, dict[str, dict[str, object]]] = {
        "broad_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
        "analysis": {},
        "midi": {},
    }
    artifacts = worker_payload.get("artifacts", {})
    object_artifacts = worker_payload.get("object_artifacts")
    if isinstance(object_artifacts, dict) and object_artifacts:
        return _reference_worker_artifacts(
            worker_payload,
            object_artifacts,
            seen=seen,
            artifact_allowlist=artifact_allowlist,
        )
    if not isinstance(artifacts, dict):
        return copied
    artifact_sources = worker_payload.get("artifact_sources", {})
    if not isinstance(artifact_sources, dict):
        artifact_sources = {}
    import_mode = str(GPU_WORKER_CONFIG.get("artifact_import_mode") or "direct").lower()
    bundle_downloaded = False
    if import_mode == "parallel_direct":
        try:
            return _download_worker_artifacts_parallel(
                client,
                worker_payload,
                job_root,
                seen=seen,
                artifact_allowlist=artifact_allowlist,
            )
        except GPUWorkerError:
            bundle_downloaded = _download_worker_bundle(client, worker_payload, job_root)
    else:
        volume_imported = import_mode == "volume" and _import_worker_job_from_volume(worker_payload, job_root)
        bundle_downloaded = volume_imported or (import_mode == "bundle" and _download_worker_bundle(client, worker_payload, job_root))

    group_dirs = {
        "broad_stems": "broad_stems",
        "derived_stems": "derived_stems",
        "specialist_substems": "specialist_substems",
        "analysis": "analysis",
        "midi": "midi",
    }
    for group_name, relative_dir in group_dirs.items():
        group = artifacts.get(group_name, {})
        if not isinstance(group, dict):
            continue
        if artifact_allowlist is not None and group_name not in artifact_allowlist:
            continue
        allowed_artifacts = artifact_allowlist.get(group_name) if artifact_allowlist is not None else None
        source_group = artifact_sources.get(group_name, {})
        if not isinstance(source_group, dict):
            source_group = {}
        for artifact_name, url in group.items():
            if allowed_artifacts is not None and artifact_name not in allowed_artifacts:
                continue
            if not isinstance(url, str) or not url:
                continue
            key = f"{group_name}:{artifact_name}:{url}"
            if key in seen:
                continue
            target_path = _local_artifact_path_from_url(url, job_root)
            if target_path is None or not bundle_downloaded or not target_path.exists():
                suffix = _suffix_from_url(url) or _default_suffix(group_name)
                target_path = job_root / relative_dir / f"{artifact_name}{suffix}"
                copied_path = client.download_artifact(url, target_path)
            else:
                copied_path = target_path.resolve()
            seen.add(key)
            copied[group_name][artifact_name] = {
                "path": str(copied_path),
                "source_model": source_group.get(artifact_name) or worker_payload.get("current_model") or "gpu_worker",
                "publish_status": "published",
                "publish_reason": "gpu_worker_progressive_artifact",
                "quality_score": None,
                "warnings": [],
                "metrics": {},
            }
    return copied


def _reference_worker_artifacts(
    worker_payload: dict[str, Any],
    object_artifacts: dict[str, Any],
    *,
    seen: set[str],
    artifact_allowlist: dict[str, set[str] | None] | None,
) -> dict[str, dict[str, dict[str, object]]]:
    referenced: dict[str, dict[str, dict[str, object]]] = {
        "broad_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
        "analysis": {},
        "midi": {},
    }
    sources = worker_payload.get("artifact_sources")
    artifact_sources = sources if isinstance(sources, dict) else {}
    for group_name in referenced:
        if artifact_allowlist is not None and group_name not in artifact_allowlist:
            continue
        group = object_artifacts.get(group_name)
        if not isinstance(group, dict):
            continue
        allowed = artifact_allowlist.get(group_name) if artifact_allowlist is not None else None
        source_group = artifact_sources.get(group_name)
        source_group = source_group if isinstance(source_group, dict) else {}
        for artifact_name, storage_ref in group.items():
            if allowed is not None and artifact_name not in allowed:
                continue
            if not isinstance(storage_ref, dict):
                continue
            key = f"{group_name}:{artifact_name}:{storage_ref.get('bucket')}:{storage_ref.get('key')}"
            if key in seen:
                continue
            seen.add(key)
            referenced[group_name][artifact_name] = {
                "storage_ref": storage_ref,
                "source_model": source_group.get(artifact_name) or "gpu_worker",
                "publish_status": "published",
                "publish_reason": "gpu_worker_object_artifact",
                "quality_score": None,
                "warnings": [],
                "metrics": {},
            }
    return referenced


def _download_worker_artifacts_parallel(
    client: GPUWorkerClient,
    worker_payload: dict[str, Any],
    job_root: Path,
    *,
    seen: set[str],
    artifact_allowlist: dict[str, set[str] | None] | None,
) -> dict[str, dict[str, dict[str, object]]]:
    copied: dict[str, dict[str, dict[str, object]]] = {
        "broad_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
        "analysis": {},
        "midi": {},
    }
    artifacts = worker_payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return copied
    artifact_sources = worker_payload.get("artifact_sources", {})
    if not isinstance(artifact_sources, dict):
        artifact_sources = {}

    group_dirs = {
        "broad_stems": "broad_stems",
        "derived_stems": "derived_stems",
        "specialist_substems": "specialist_substems",
        "analysis": "analysis",
        "midi": "midi",
    }
    entries: list[tuple[str, str, str, str, str, str]] = []
    for group_name, relative_dir in group_dirs.items():
        group = artifacts.get(group_name, {})
        if not isinstance(group, dict):
            continue
        if artifact_allowlist is not None and group_name not in artifact_allowlist:
            continue
        allowed_artifacts = artifact_allowlist.get(group_name) if artifact_allowlist is not None else None
        source_group = artifact_sources.get(group_name, {})
        if not isinstance(source_group, dict):
            source_group = {}
        for artifact_name, url in group.items():
            if allowed_artifacts is not None and artifact_name not in allowed_artifacts:
                continue
            if not isinstance(url, str) or not url:
                continue
            key = f"{group_name}:{artifact_name}:{url}"
            if key in seen:
                continue
            source_model = str(source_group.get(artifact_name) or worker_payload.get("current_model") or "gpu_worker")
            entries.append((group_name, relative_dir, artifact_name, url, source_model, key))

    if not entries:
        return copied

    worker_count = max(1, int(GPU_WORKER_CONFIG.get("artifact_download_workers") or 1))
    worker_count = min(worker_count, len(entries))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _download_one_worker_artifact,
                client,
                job_root,
                group_name,
                relative_dir,
                artifact_name,
                url,
                source_model,
            ): (group_name, artifact_name, key)
            for group_name, relative_dir, artifact_name, url, source_model, key in entries
        }
        for future in as_completed(futures):
            group_name, artifact_name, key = futures[future]
            copied[group_name][artifact_name] = future.result()
            seen.add(key)
    return copied


def _download_one_worker_artifact(
    client: GPUWorkerClient,
    job_root: Path,
    group_name: str,
    relative_dir: str,
    artifact_name: str,
    url: str,
    source_model: str,
) -> dict[str, object]:
    suffix = _suffix_from_url(url) or _default_suffix(group_name)
    target_path = job_root / relative_dir / f"{artifact_name}{suffix}"
    copied_path = client.download_artifact(url, target_path)
    return {
        "path": str(copied_path),
        "source_model": source_model,
        "publish_status": "published",
        "publish_reason": "gpu_worker_progressive_artifact",
        "quality_score": None,
        "warnings": [],
        "metrics": {},
    }


def _download_worker_bundle(
    client: GPUWorkerClient,
    worker_payload: dict[str, Any],
    job_root: Path,
) -> bool:
    bundle_url = worker_payload.get("bundle_artifact")
    if not isinstance(bundle_url, str) or not bundle_url:
        return False
    bundle_path = job_root / "package" / "worker_artifacts.zip"
    if not bundle_path.exists():
        client.download_artifact(bundle_url, bundle_path)
    _safe_extract_zip(bundle_path, job_root)
    return True


def _import_worker_job_from_volume(worker_payload: dict[str, Any], job_root: Path) -> bool:
    if not GPU_WORKER_CONFIG.get("prefer_volume_import"):
        return False
    if str(worker_payload.get("status")) != "completed":
        return False
    worker_job_id = str(worker_payload.get("job_id") or worker_payload.get("worker_job_id") or "")
    if not worker_job_id:
        return False
    modal_bin = _resolve_modal_bin(str(GPU_WORKER_CONFIG.get("modal_bin") or "modal"))
    if modal_bin is None:
        return False
    volume_name = str(GPU_WORKER_CONFIG.get("volume_name") or "stemsplitter-gpu-worker-jobs")
    timeout = int(GPU_WORKER_CONFIG.get("volume_import_timeout") or 1800)
    env = os.environ.copy()
    modal_profile = GPU_WORKER_CONFIG.get("modal_profile")
    if modal_profile:
        env["MODAL_PROFILE"] = str(modal_profile)

    with tempfile.TemporaryDirectory(prefix="gpu-worker-volume-") as temp_dir:
        command = [
            modal_bin,
            "volume",
            "get",
            volume_name,
            f"/{worker_job_id}",
            temp_dir,
        ]
        try:
            result = sp.run(command, check=False, capture_output=True, text=True, timeout=timeout, env=env)
        except (OSError, sp.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False

        recovered_root = Path(temp_dir) / worker_job_id
        if not recovered_root.exists():
            recovered_root = Path(temp_dir)
        _copy_recovered_worker_dirs(recovered_root, job_root)
    return True


def _resolve_modal_bin(modal_bin: str) -> str | None:
    candidate = Path(modal_bin)
    if candidate.exists():
        return str(candidate)
    resolved = shutil.which(modal_bin)
    if resolved:
        return resolved
    return None


def _copy_recovered_worker_dirs(recovered_root: Path, job_root: Path) -> None:
    for relative_dir in ("broad_stems", "derived_stems", "specialist_substems", "analysis", "midi", "package"):
        source_root = recovered_root / relative_dir
        if not source_root.exists():
            continue
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            target = job_root / relative_dir / source.relative_to(source_root)
            ensure_dir(target.parent)
            shutil.copy2(source, target)


def _safe_extract_zip(bundle_path: Path, target_root: Path) -> None:
    root = target_root.resolve()
    with zipfile.ZipFile(bundle_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = (root / member.filename).resolve()
            if not str(target).startswith(str(root)):
                raise GPUWorkerError(f"gpu_worker_bundle_unsafe_path:{member.filename}")
            ensure_dir(target.parent)
            with archive.open(member) as source, target.open("wb") as dest:
                dest.write(source.read())


def _local_artifact_path_from_url(url: str, job_root: Path) -> Path | None:
    parsed = urlparse(url)
    parts = [part for part in Path(parsed.path).parts if part not in {"/", ""}]
    try:
        artifact_index = parts.index("artifacts")
    except ValueError:
        return None
    relative_parts = parts[artifact_index + 2 :]
    if not relative_parts:
        return None
    if any(part in {"..", "."} for part in relative_parts):
        return None
    return (job_root / Path(*relative_parts)).resolve()


def _json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GPUWorkerError("gpu_worker_invalid_json") from exc
    if not isinstance(payload, dict):
        raise GPUWorkerError("gpu_worker_invalid_payload")
    return payload


def _is_absolute_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _url_origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    port = parsed.port
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, (parsed.hostname or "").lower(), port


def _suffix_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = Path(parsed.path)
    suffix = path.suffix.lower()
    if suffix in {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".mid", ".json"}:
        return suffix
    return ""


def _default_suffix(group_name: str) -> str:
    if group_name == "midi":
        return ".mid"
    if group_name == "analysis":
        return ".json"
    return ".wav"

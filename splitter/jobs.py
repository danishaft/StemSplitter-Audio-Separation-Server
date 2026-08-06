from __future__ import annotations

import shutil
import subprocess as sp
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread
from typing import Any

from .analysis import (
    create_tempo_locked_copy,
    detect_sections,
    detect_tempo_and_beats,
    estimate_key,
    write_chord_guide_midi,
    write_sections_analysis,
    write_tempo_key_analysis,
)
from .bootstrap import runtime_services
from .config import (
    DEFAULT_PROFILE,
    GPU_WORKER_CONFIG,
    INSTANCE_ID,
    JOB_DISPATCH_BACKEND,
    JOB_LEASE_RENEW_INTERVAL,
    JOB_LEASE_SECONDS,
    JOB_MAX_ACTIVE,
    JOB_MAX_ACTIVE_PER_OWNER,
    JOB_MAX_ATTEMPTS,
    JOB_RETENTION_SECONDS,
    JOBS_DIR,
    PROFILE_CONFIG,
    PUBLISH_THRESHOLDS,
    QUALITY_8_STEM_PROFILE,
)
from .gpu_worker_client import (
    GPUWorkerClient,
    GPUWorkerError,
    copy_worker_artifacts,
    wait_for_worker_job,
)
from .infrastructure.job_store import (
    TERMINAL_JOB_STATES,
    JobStoreError,
)
from .infrastructure.object_storage import (
    ObjectStorageError,
    object_store_from_config,
)
from .packaging import package_directories, write_manifest
from .path_safety import resolve_job_root
from .scoring import score_audio_candidate, validate_midi_candidate
from .separation import build_broad_stems, build_derived_stems
from .specialist import (
    build_drum_substems_mvsep,
    build_instrument_substems_mvsep,
    build_local_derived_candidates,
    build_vocal_substems_mvsep,
    local_specialist_runtime_status,
    mvsep_runtime_status,
)
from .stem_contract import apply_quality_8_contract
from .unit_economics import build_unit_economics
from .util import dump_json, ensure_dir, file_sha256, load_json, now_iso, sanitize_filename
from .waveform import write_waveform_peaks

# These imports remain part of the historical monkeypatch surface used by the
# isolation tests while specialist execution is being decomposed from this module.
_COMPATIBILITY_EXPORTS = (
    build_drum_substems_mvsep,
    build_vocal_substems_mvsep,
    dump_json,
)

try:
    from audio2midi.librosa_pitch_detector import Normal_Pitch_Det
except Exception:  # pragma: no cover - dependency can be absent during import
    Normal_Pitch_Det = None


def _resolve_profile(profile: str | None) -> str:
    resolved = str(profile or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    if resolved not in PROFILE_CONFIG:
        raise ValueError(f"unsupported_profile:{resolved}")
    return resolved


def _job_store():
    return runtime_services().job_store(jobs_dir=JOBS_DIR)


def _dispatcher():
    return runtime_services().dispatcher(run_job)


def control_plane_health() -> dict[str, bool]:
    store_ready = _job_store().ping()
    dispatcher_ready = _dispatcher().ping()
    object_store = object_store_from_config()
    object_storage_ready = object_store.ping() if object_store is not None else False
    return {
        "job_store": store_ready,
        "dispatcher": dispatcher_ready,
        "object_storage": object_storage_ready,
    }


def _job_root(job_id: str) -> Path:
    return resolve_job_root(JOBS_DIR, job_id)


def _status_path(job_root: Path) -> Path:
    return job_root / "status.json"


def _update_status(job_root: Path, **fields: Any) -> dict[str, Any]:
    return _job_store().update(job_root.name, fields)


def _run_audio2midi(input_path: Path, output_path: Path) -> bool:
    if Normal_Pitch_Det is None:
        return False
    ensure_dir(output_path.parent)
    try:
        detector = Normal_Pitch_Det()
        detector.predict(str(input_path), output_file=str(output_path))
    except Exception:
        return False
    return output_path.exists()


def create_job(
    upload_name: str,
    file_bytes: bytes,
    *,
    profile: str | None = None,
    input_source: dict[str, object] | None = None,
    owner_id: str = "local-development",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return _create_local_job(
        upload_name,
        lambda upload_path: upload_path.write_bytes(file_bytes),
        profile=profile,
        input_source=input_source,
        owner_id=owner_id,
        idempotency_key=idempotency_key,
    )


def create_job_from_path(
    upload_name: str,
    source_path: Path,
    *,
    profile: str | None = None,
    input_source: dict[str, object] | None = None,
    owner_id: str = "local-development",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return _create_local_job(
        upload_name,
        lambda upload_path: shutil.copy2(source_path, upload_path),
        profile=profile,
        input_source=input_source,
        owner_id=owner_id,
        idempotency_key=idempotency_key,
    )


def _create_local_job(
    upload_name: str,
    write_upload: Callable[[Path], object],
    *,
    profile: str | None,
    input_source: dict[str, object] | None,
    owner_id: str,
    idempotency_key: str | None,
) -> dict[str, Any]:
    resolved_profile = _resolve_profile(profile)
    job_id = uuid.uuid4().hex
    ensure_dir(JOBS_DIR)
    job_root = ensure_dir(_job_root(job_id))
    input_dir = ensure_dir(job_root / "input")
    safe_name = sanitize_filename(upload_name) or "input.wav"
    upload_path = input_dir / safe_name
    write_upload(upload_path)

    status = {
        "job_id": job_id,
        "profile": resolved_profile,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "input_name": safe_name,
        "input_path": str(upload_path.resolve()),
        "input_source": input_source or {"type": "upload", "provider": "local"},
    }
    try:
        persisted, created = _job_store().create(
            status,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            max_active=JOB_MAX_ACTIVE,
            max_active_per_owner=JOB_MAX_ACTIVE_PER_OWNER,
        )
    except Exception:
        shutil.rmtree(job_root, ignore_errors=True)
        raise
    if not created:
        shutil.rmtree(job_root, ignore_errors=True)
    return {**persisted, "idempotency_replayed": not created}


def create_job_from_object(
    upload_name: str,
    object_reference: dict[str, object],
    *,
    profile: str | None = None,
    input_source: dict[str, object] | None = None,
    owner_id: str = "local-development",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    store = object_store_from_config()
    if store is None:
        raise ObjectStorageError("object_storage_not_configured")
    verified = store.stat(object_reference)
    resolved_profile = _resolve_profile(profile)
    job_id = uuid.uuid4().hex
    ensure_dir(JOBS_DIR)
    job_root = ensure_dir(_job_root(job_id))
    safe_name = sanitize_filename(upload_name) or "input.wav"
    expected_path = job_root / "input" / safe_name
    status = {
        "job_id": job_id,
        "profile": resolved_profile,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "input_name": safe_name,
        "input_path": str(expected_path.resolve()),
        "input_object": verified.as_dict(),
        "input_source": input_source or {"type": "upload", "provider": "object_storage"},
    }
    try:
        persisted, created = _job_store().create(
            status,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            max_active=JOB_MAX_ACTIVE,
            max_active_per_owner=JOB_MAX_ACTIVE_PER_OWNER,
        )
    except Exception:
        shutil.rmtree(job_root, ignore_errors=True)
        raise
    if not created:
        shutil.rmtree(job_root, ignore_errors=True)
    return {**persisted, "idempotency_replayed": not created}


def submit_job(job_id: str, *, recovery_attempt: int | None = None) -> str:
    dispatcher = _dispatcher()
    dispatch_id = (
        dispatcher.recover(job_id, recovery_attempt)
        if recovery_attempt is not None
        else dispatcher.enqueue(job_id)
    )
    _job_store().mark_dispatched(job_id, dispatch_id)
    _update_status(_job_root(job_id), dispatch_id=dispatch_id)
    return dispatch_id


def record_dispatch_failure(job_id: str, error: Exception) -> dict[str, Any]:
    error_code = f"{type(error).__name__}:{error}"
    _job_store().mark_dispatch_failed(job_id, error_code)
    return _update_status(
        _job_root(job_id),
        status="queued",
        stage="dispatch_pending",
        error=error_code,
    )


def dispatch_pending_jobs(limit: int = 100) -> list[str]:
    """Drain committed outbox rows after API crashes or transient Redis failures."""

    dispatched: list[str] = []
    records = _job_store().claim_dispatches(
        INSTANCE_ID,
        limit=max(1, min(limit, 500)),
    )
    for record in records:
        job_id = str(record["job_id"])
        try:
            submit_job(job_id)
        except Exception as exc:
            _job_store().mark_dispatch_failed(
                job_id,
                f"{type(exc).__name__}:{exc}",
            )
            continue
        dispatched.append(job_id)
    return dispatched


def cancel_job(job_id: str) -> dict[str, Any] | None:
    status = _job_store().request_cancel(job_id)
    if status is None:
        return None
    if status.get("status") in TERMINAL_JOB_STATES:
        if status.get("status") == "cancelled":
            _dispatcher().cancel(job_id)
        return status
    worker_job_id = str(status.get("gpu_worker_job_id") or "")
    if worker_job_id:
        client = GPUWorkerClient.from_config()
        if client is not None:
            try:
                remote = client.cancel(worker_job_id)
                if str(remote.get("status")) == "cancelled":
                    cancelled = _update_status(
                        _job_root(job_id),
                        status="cancelled",
                        stage="cancelled",
                        cancellation_status="cancelled",
                    )
                    _dispatcher().cancel(job_id)
                    return cancelled
            except GPUWorkerError:
                return _update_status(
                    _job_root(job_id),
                    cancellation_status="remote_cancel_failed",
                )
    return _update_status(
        _job_root(job_id),
        cancellation_status="awaiting_execution_ack",
    )


def reconcile_jobs(stale_seconds: int = 300) -> list[dict[str, Any]]:
    reconciled: list[dict[str, Any]] = []
    for status in _job_store().list_reconcilable(stale_seconds):
        job_id = str(status["job_id"])
        if status.get("cancel_requested"):
            updated = cancel_job(job_id)
            if updated:
                reconciled.append(updated)
            continue
        attempt = int(status.get("attempt") or 0)
        if attempt >= JOB_MAX_ATTEMPTS:
            reconciled.append(
                _update_status(
                    _job_root(job_id),
                    status="error",
                    stage="retry_exhausted",
                    error="job_retry_exhausted",
                )
            )
            continue
        submit_job(job_id, recovery_attempt=attempt + 1)
        updated = get_job_status(job_id)
        if updated:
            reconciled.append(updated)
    return reconciled


def resume_remote_job(job_id: str) -> dict[str, Any] | None:
    status = get_job_status(job_id)
    if not status or status.get("status") != "error" or not status.get("gpu_worker_job_id"):
        return None
    _update_status(
        _job_root(job_id),
        status="queued",
        stage="remote_recovery_queued",
        error=None,
        gpu_worker_reason=None,
    )
    submit_job(job_id)
    return get_job_status(job_id)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    return _job_store().get(job_id)


def get_job_events(job_id: str, *, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    return _job_store().list_events(
        job_id,
        after_id=max(0, after_id),
        limit=max(1, min(limit, 500)),
    )


def _storage_references(payload: object) -> list[dict[str, object]]:
    references: dict[tuple[str, str], dict[str, object]] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("provider") == "s3" and value.get("bucket") and value.get("key"):
                identity = (str(value["bucket"]), str(value["key"]))
                references[identity] = value
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return list(references.values())


def delete_job(job_id: str) -> bool:
    store = _job_store()
    status = store.get(job_id)
    if status is None:
        return False
    if status.get("status") not in TERMINAL_JOB_STATES:
        raise JobStoreError("job_not_terminal")
    object_store = object_store_from_config()
    if object_store is not None:
        for reference in _storage_references(status):
            object_store.delete(reference)
    deleted = store.delete(job_id)
    shutil.rmtree(_job_root(job_id), ignore_errors=True)
    return deleted


def cleanup_expired_jobs(
    retention_seconds: int = JOB_RETENTION_SECONDS,
    *,
    limit: int = 100,
) -> list[str]:
    deleted: list[str] = []
    for status in _job_store().list_expired(max(1, retention_seconds), max(1, limit)):
        job_id = str(status["job_id"])
        if delete_job(job_id):
            deleted.append(job_id)
    return deleted


def get_manifest(job_id: str) -> dict[str, Any] | None:
    status = get_job_status(job_id)
    durable_manifest = status.get("manifest") if status else None
    if isinstance(durable_manifest, dict):
        return durable_manifest
    manifest_path = _job_root(job_id) / "analysis" / "manifest.json"
    if not manifest_path.exists():
        return None
    return load_json(manifest_path)


def _collect_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for item in sorted(root.glob("**/*")):
            if item.is_file():
                files.append(item)
    return files


def _audio_duration(audio_path: Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(audio_path))
        return float(info.frames / max(info.samplerate, 1))
    except Exception:
        return 0.0


def _elapsed_seconds(start: float) -> float:
    return round(time.perf_counter() - start, 3)


def _materialize_job_input(status: dict[str, Any], job_root: Path) -> Path:
    input_path = Path(str(status["input_path"]))
    if input_path.exists():
        return input_path
    reference = status.get("input_object")
    if not isinstance(reference, dict):
        raise ObjectStorageError("job_input_missing")
    store = object_store_from_config()
    if store is None:
        raise ObjectStorageError("object_storage_not_configured")
    _update_status(job_root, stage="materializing_input")
    return store.download(reference, input_path)


def _merged_gpu_timings(worker_payload: dict[str, Any], local_timings: dict[str, object] | None = None) -> dict[str, object]:
    worker_timings = worker_payload.get("timings")
    timings: dict[str, object] = dict(worker_timings) if isinstance(worker_timings, dict) else {}
    if local_timings:
        timings.update(local_timings)
    timings["updated_at"] = now_iso()
    return timings


def _gpu_artifact_allowlist_for_profile(profile: str) -> dict[str, set[str] | None] | None:
    if profile != QUALITY_8_STEM_PROFILE:
        return None
    return {
        "broad_stems": None,
        "specialist_substems": {
            "kick",
            "snare",
            "electric_guitar",
            "synth",
            "strings",
        },
    }


def _publish_audio_candidates(
    candidates: dict[str, dict[str, object]],
    *,
    threshold: float,
    publish_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    published: dict[str, dict[str, object]] = {}
    rejected: dict[str, dict[str, object]] = {}
    if not candidates:
        return published, rejected

    ensure_dir(publish_dir)
    for stem_name, candidate in candidates.items():
        scored = score_audio_candidate(candidate, threshold)
        if scored["publish_status"] == "published":
            target = publish_dir / f"{stem_name}.wav"
            shutil.copy2(Path(str(scored["path"])), target)
            published[stem_name] = {
                **scored,
                "path": str(target.resolve()),
                "confidence": scored["quality_score"],
            }
        else:
            rejected[stem_name] = scored
    return published, rejected


def _publish_midi_candidate(
    candidate_path: Path,
    *,
    name: str,
    source_name: str,
    source_path: Path,
    audio_duration: float,
    publish_dir: Path,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    scored = validate_midi_candidate(
        candidate_path,
        source_name=source_name,
        source_path=source_path,
        audio_duration=audio_duration,
        threshold=PUBLISH_THRESHOLDS["midi"],
    )
    if scored["publish_status"] != "published":
        return None, scored

    ensure_dir(publish_dir)
    target = publish_dir / f"{name}.mid"
    shutil.copy2(candidate_path, target)
    return {**scored, "path": str(target.resolve())}, None


def _candidate_winner_entry(
    payload: dict[str, object],
    *,
    published_group: str,
    fallback_used: bool = False,
) -> dict[str, object]:
    return {
        "published_group": published_group,
        "winning_source": payload.get("source_model", "unknown"),
        "quality_score": payload.get("quality_score"),
        "fallback_used": fallback_used,
    }


def _collect_specialist_candidates(
    broad_outputs: dict[str, dict[str, object]],
    job_root: Path,
) -> tuple[dict[str, dict[str, object]], list[str], str, str | None]:
    available, reason = mvsep_runtime_status()
    if not available:
        return {}, [reason] if reason else [], "skipped", reason

    candidates: dict[str, dict[str, object]] = {}
    errors: list[str] = []

    # The hosted lane is currently restricted to the six unresolved
    # instrument families. Vocal and drum specialist models are not part of
    # this qualification pass and must not consume remote credits here.
    if "other" in broad_outputs:
        outputs, branch_errors = build_instrument_substems_mvsep(
            Path(str(broad_outputs["other"]["path"])),
            job_root,
        )
        candidates.update(outputs)
        errors.extend(branch_errors)

    if candidates and errors:
        return candidates, errors, "partial", ";".join(errors)
    if candidates:
        return candidates, [], "used", None
    if errors:
        return {}, errors, "failed", ";".join(errors)
    return {}, [], "skipped", "mvsep_no_outputs"


def _merge_worker_groups(
    target: dict[str, dict[str, object]],
    source: dict[str, dict[str, object]],
) -> None:
    for stem_name, payload in source.items():
        target[stem_name] = payload


def _write_gpu_progress_manifest(
    job_id: str,
    job_root: Path,
    status: dict[str, Any],
    input_path: Path,
    *,
    input_hash: str,
    worker_payload: dict[str, Any],
    broad_outputs: dict[str, dict[str, object]],
    derived_outputs: dict[str, dict[str, object]],
    specialist_outputs: dict[str, dict[str, object]],
    analysis_exports: dict[str, dict[str, object]],
    midi_exports: dict[str, dict[str, object]],
    main_outputs: dict[str, dict[str, object]] | None = None,
    stem_contract: dict[str, object] | None = None,
    candidate_winners: dict[str, dict[str, object]] | None = None,
    rejected_candidates: dict[str, dict[str, dict[str, object]]] | None = None,
    bundles: dict[str, str] | None = None,
    local_timings: dict[str, object] | None = None,
) -> Path:
    manifest = {
        "job_id": job_id,
        "profile": status["profile"],
        "status": worker_payload.get("status", "running"),
        "input_name": status["input_name"],
        "input_path": str(input_path.resolve()),
        "input_hash": input_hash,
        "input_source": status.get("input_source", {"type": "upload", "provider": "local"}),
        "runtime_env": {
            "engine": "gpu-worker",
            "worker_job_id": worker_payload.get("job_id"),
            "created_at": status["created_at"],
        },
        "models_used": worker_payload.get("models_used", []),
        "quarantined_models": worker_payload.get("quarantined_models", {}),
        "runs_root": str(job_root.resolve()),
        "published_broad_stems": broad_outputs,
        "published_derived_stems": derived_outputs,
        "published_specialist_substems": specialist_outputs,
        "published_main_stems": main_outputs or {},
        "stem_contract": stem_contract or {},
        "tempo_locked_exports": {},
        "midi_exports": midi_exports,
        "analysis": worker_payload.get("analysis", {}),
        "analysis_exports": analysis_exports,
        "pipeline_mode": "gpu_worker_progressive",
        "candidate_winners": candidate_winners or {},
        "rejected_candidates": rejected_candidates or {
            "extended_stems": {},
            "derived_stems": {},
            "specialist_substems": {},
            "midi": {},
        },
        "missing_features": worker_payload.get("missing_features", []),
        "remote_adapter_status": "not_requested",
        "remote_adapter_reason": None,
        "worker_status": worker_payload,
        "bundle_exports": bundles or {},
        "timings": _merged_gpu_timings(worker_payload, local_timings),
        "unit_economics": build_unit_economics(worker_payload),
    }
    return write_manifest(job_root, manifest)


def _run_gpu_worker_job(
    job_id: str,
    job_root: Path,
    status: dict[str, Any],
    input_path: Path,
) -> bool:
    local_started = time.perf_counter()
    input_exists = input_path.exists()
    input_duration_seconds = round(_audio_duration(input_path), 3) if input_exists else 0.0
    local_timings: dict[str, object] = {
        "local_started_at": now_iso(),
        "input_duration_seconds": input_duration_seconds,
    }
    client = GPUWorkerClient.from_config()
    if client is None:
        local_timings["local_total_seconds"] = _elapsed_seconds(local_started)
        _update_status(
            job_root,
            stage="gpu_worker_unavailable",
            gpu_worker_status="skipped",
            gpu_worker_reason="gpu_worker_url_missing",
            timings=local_timings,
        )
        return False

    broad_outputs: dict[str, dict[str, object]] = {}
    derived_outputs: dict[str, dict[str, object]] = {}
    specialist_outputs: dict[str, dict[str, object]] = {}
    analysis_exports: dict[str, dict[str, object]] = {}
    midi_exports: dict[str, dict[str, object]] = {}
    main_outputs: dict[str, dict[str, object]] = {}
    stem_contract: dict[str, object] = {}
    candidate_winners: dict[str, dict[str, object]] = {}
    rejected_candidates: dict[str, dict[str, dict[str, object]]] = {
        "extended_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
        "midi": {},
    }
    seen_artifacts: set[str] = set()
    input_reference = status.get("input_object")
    input_hash = (
        file_sha256(input_path)
        if input_exists
        else str(input_reference.get("etag") or "object_etag_unavailable")
        if isinstance(input_reference, dict)
        else "input_hash_unavailable"
    )
    artifact_allowlist = _gpu_artifact_allowlist_for_profile(str(status["profile"]))

    try:
        latest_before_submit = get_job_status(job_id)
        if latest_before_submit and latest_before_submit.get("cancel_requested"):
            _update_status(
                job_root,
                status="cancelled",
                stage="cancelled",
                cancellation_status="cancelled_before_remote_submit",
            )
            return True
        submit_started = time.perf_counter()
        existing_worker_job_id = str(status.get("gpu_worker_job_id") or "")
        submitted: dict[str, Any] | None = None
        if existing_worker_job_id:
            recovered = client.status(existing_worker_job_id)
            if str(recovered.get("status")) in {"queued", "running", "completed"}:
                submitted = recovered
                local_timings["remote_job_reused"] = True
                local_timings["recovered_worker_job_id"] = existing_worker_job_id
        if submitted is None and isinstance(input_reference, dict):
            execution_budget = float(GPU_WORKER_CONFIG.get("max_execution_seconds") or 0.0)
            submit_kwargs: dict[str, object] = {
                "input_name": str(status["input_name"]),
                "profile": str(status["profile"]),
                "local_job_id": job_id,
            }
            if execution_budget > 0:
                submit_kwargs["max_worker_seconds"] = execution_budget
            submitted = client.submit_object(input_reference, **submit_kwargs)
        elif submitted is None:
            submitted = client.submit(
                input_path,
                profile=str(status["profile"]),
                local_job_id=job_id,
            )
        local_timings["submit_request_seconds"] = _elapsed_seconds(submit_started)
        worker_job_id = str(submitted.get("job_id") or submitted.get("worker_job_id") or "")
        if not worker_job_id:
            raise GPUWorkerError("gpu_worker_missing_job_id")
        local_timings["worker_job_id"] = worker_job_id

        _update_status(
            job_root,
            status="running",
            stage="gpu_worker_submitted",
            gpu_worker_status="submitted",
            gpu_worker_job_id=worker_job_id,
            timings=_merged_gpu_timings(submitted, local_timings),
        )

        def on_update(worker_payload: dict[str, Any]) -> None:
            current_status = get_job_status(job_id)
            if current_status and current_status.get("cancel_requested"):
                raise GPUWorkerError("job_cancelled")
            worker_status = str(worker_payload.get("status", "unknown"))
            copied: dict[str, dict[str, dict[str, object]]] = {
                "broad_stems": {},
                "derived_stems": {},
                "specialist_substems": {},
                "analysis": {},
                "midi": {},
            }
            if not isinstance(input_reference, dict) or worker_status == "completed":
                copy_started = time.perf_counter()
                copied = copy_worker_artifacts(
                    client,
                    worker_payload,
                    job_root,
                    seen=seen_artifacts,
                    artifact_allowlist=artifact_allowlist,
                )
                copy_seconds = _elapsed_seconds(copy_started)
                local_timings["last_artifact_sync_seconds"] = copy_seconds
                local_timings["artifact_sync_seconds"] = round(
                    float(local_timings.get("artifact_sync_seconds", 0.0)) + copy_seconds,
                    3,
                )
            else:
                # Object-reference jobs publish a final storage manifest. Importing
                # progressive volume artifacts would reintroduce the local relay.
                local_timings["artifact_sync_deferred"] = True
            local_timings["local_elapsed_seconds"] = _elapsed_seconds(local_started)
            _merge_worker_groups(broad_outputs, copied["broad_stems"])
            _merge_worker_groups(derived_outputs, copied["derived_stems"])
            _merge_worker_groups(specialist_outputs, copied["specialist_substems"])
            _merge_worker_groups(analysis_exports, copied["analysis"])
            _merge_worker_groups(midi_exports, copied["midi"])
            manifest_path = _write_gpu_progress_manifest(
                job_id,
                job_root,
                status,
                input_path,
                input_hash=input_hash,
                worker_payload=worker_payload,
                broad_outputs=broad_outputs,
                derived_outputs=derived_outputs,
                specialist_outputs=specialist_outputs,
                analysis_exports=analysis_exports,
                midi_exports=midi_exports,
                local_timings=local_timings,
            )
            _update_status(
                job_root,
                status="running" if worker_status != "completed" else "finalizing",
                stage=str(worker_payload.get("stage", "gpu_worker_running")),
                manifest_path=str(manifest_path.resolve()),
                gpu_worker_status=worker_status,
                gpu_worker_job_id=worker_job_id,
                timings=_merged_gpu_timings(worker_payload, local_timings),
                artifacts_ready={
                    "broad_stems": sorted(broad_outputs),
                    "derived_stems": sorted(derived_outputs),
                    "specialist_substems": sorted(specialist_outputs),
                    "midi": sorted(midi_exports),
                    "analysis": sorted(analysis_exports),
                },
            )

        if str(submitted.get("status")) in {"completed", "error", "failed"}:
            on_update(submitted)
            local_timings["poll_wait_seconds"] = 0.0
            final_payload = submitted
        else:
            poll_started = time.perf_counter()
            final_payload = wait_for_worker_job(client, worker_job_id, on_update=on_update)
            local_timings["poll_wait_seconds"] = _elapsed_seconds(poll_started)
        if final_payload.get("status") != "completed":
            raise GPUWorkerError(str(final_payload.get("error") or "gpu_worker_failed"))

        object_transport = final_payload.get("artifact_transport") == "object_storage"
        worker_contract = final_payload.get("stem_contract")
        worker_finalized_contract = (
            isinstance(worker_contract, dict)
            and worker_contract.get("name") in {"quality_8_stems", "product_11_stems"}
        )
        if str(status["profile"]) == QUALITY_8_STEM_PROFILE and worker_finalized_contract:
            rejected_payload = final_payload.get("rejected_candidates")
            if isinstance(rejected_payload, dict):
                rejected_candidates = rejected_payload
            stem_contract = worker_contract
            for stem_name in stem_contract.get("published_stems", []):
                if stem_name in broad_outputs:
                    main_outputs[stem_name] = {
                        **broad_outputs[stem_name],
                        "artifact_group": "broad_stems",
                    }
                elif stem_name in specialist_outputs:
                    main_outputs[stem_name] = {
                        **specialist_outputs[stem_name],
                        "artifact_group": "specialist_substems",
                    }
            candidate_winners = {
                stem_name: _candidate_winner_entry(
                    payload,
                    published_group=str(payload.get("artifact_group") or "unknown"),
                    fallback_used=False,
                )
                for stem_name, payload in main_outputs.items()
            }
        elif str(status["profile"]) == QUALITY_8_STEM_PROFILE:
            missing_features = list(final_payload.get("missing_features") or [])
            contract_payload = apply_quality_8_contract(
                job_root,
                broad_outputs=broad_outputs,
                derived_outputs=derived_outputs,
                specialist_outputs=specialist_outputs,
                rejected_candidates=rejected_candidates,
                missing_features=missing_features,
            )
            broad_outputs = contract_payload["published_broad_stems"]  # type: ignore[assignment]
            derived_outputs = contract_payload["published_derived_stems"]  # type: ignore[assignment]
            specialist_outputs = contract_payload["published_specialist_substems"]  # type: ignore[assignment]
            main_outputs = contract_payload["published_main_stems"]  # type: ignore[assignment]
            stem_contract = contract_payload["stem_contract"]  # type: ignore[assignment]
            final_payload = {**final_payload, "missing_features": missing_features}
            candidate_winners = {
                stem_name: _candidate_winner_entry(
                    payload,
                    published_group=str(payload.get("artifact_group") or payload.get("candidate_group") or "unknown"),
                    fallback_used=str(payload.get("source_model")) == "synthetic_sum",
                )
                for stem_name, payload in main_outputs.items()
            }

        if object_transport:
            object_bundle = final_payload.get("object_bundle")
            bundles = (
                {"stems": {"storage_ref": object_bundle}}
                if isinstance(object_bundle, dict)
                else {}
            )
            local_timings["local_package_seconds"] = 0.0
            local_timings["artifact_sync_skipped"] = True
            local_timings["package_skipped"] = True
        else:
            package_started = time.perf_counter()
            package_groups = {
                "stems": _collect_files(job_root / "broad_stems", job_root / "derived_stems", job_root / "specialist_substems"),
                "midi": _collect_files(job_root / "midi"),
                "wav_plus_midi": _collect_files(
                    job_root / "broad_stems",
                    job_root / "derived_stems",
                    job_root / "specialist_substems",
                    job_root / "midi",
                ),
            }
            bundles = package_directories(job_root, package_groups)
            local_timings["local_package_seconds"] = _elapsed_seconds(package_started)
        local_timings["local_total_seconds"] = _elapsed_seconds(local_started)
        if input_duration_seconds > 0:
            local_timings["local_realtime_factor"] = round(
                float(local_timings["local_total_seconds"]) / input_duration_seconds,
                3,
            )
        manifest_path = _write_gpu_progress_manifest(
            job_id,
            job_root,
            status,
            input_path,
            input_hash=input_hash,
            worker_payload=final_payload,
            broad_outputs=broad_outputs,
            derived_outputs=derived_outputs,
            specialist_outputs=specialist_outputs,
            analysis_exports=analysis_exports,
            midi_exports=midi_exports,
            main_outputs=main_outputs,
            stem_contract=stem_contract,
            candidate_winners=candidate_winners,
            rejected_candidates=rejected_candidates,
            bundles=bundles,
            local_timings=local_timings,
        )
        _update_status(
            job_root,
            status="completed",
            stage="done",
            manifest_path=str(manifest_path.resolve()),
            bundles=bundles,
            gpu_worker_status="completed",
            gpu_worker_job_id=worker_job_id,
            timings=_merged_gpu_timings(final_payload, local_timings),
            manifest=load_json(manifest_path),
        )
        return True
    except Exception as exc:
        local_timings["local_total_seconds"] = _elapsed_seconds(local_started)
        if input_duration_seconds > 0:
            local_timings["local_realtime_factor"] = round(
                float(local_timings["local_total_seconds"]) / input_duration_seconds,
                3,
            )
        latest = get_job_status(job_id)
        if str(exc) == "job_cancelled" or (latest and latest.get("cancel_requested")):
            cancellation_status = "cancelled"
            if worker_job_id:
                try:
                    cancelled = client.cancel(worker_job_id)
                    if str(cancelled.get("status")) != "cancelled":
                        cancellation_status = "remote_cancel_unconfirmed"
                except GPUWorkerError:
                    cancellation_status = "remote_cancel_failed"
            if cancellation_status != "cancelled":
                _update_status(
                    job_root,
                    status="cancelling",
                    stage="cancelling",
                    gpu_worker_status="cancelling",
                    cancellation_status=cancellation_status,
                    timings=local_timings,
                )
                return True
            _update_status(
                job_root,
                status="cancelled",
                stage="cancelled",
                gpu_worker_status="cancelled",
                cancellation_status="cancelled",
                timings=local_timings,
            )
            return True
        _update_status(
            job_root,
            stage="gpu_worker_failed_fallback",
            gpu_worker_status="failed",
            gpu_worker_reason=str(exc),
            timings=local_timings,
        )
        return False


def _run_job_pipeline(job_id: str) -> None:
    job_root = _job_root(job_id)
    status = get_job_status(job_id)
    if not status:
        return

    input_path = Path(str(status["input_path"]))
    profile = str(status["profile"])
    profile_cfg = PROFILE_CONFIG[profile]
    models_used = list(profile_cfg["run_models"])

    try:
        if profile_cfg.get("use_gpu_worker"):
            handled_by_worker = _run_gpu_worker_job(job_id, job_root, status, input_path)
            if handled_by_worker:
                return
            if not profile_cfg.get("allow_local_fallback", True):
                raise GPUWorkerError("gpu_worker_failed")

        input_path = _materialize_job_input(status, job_root)

        _update_status(job_root, status="running", stage="broad_split")
        broad_outputs, extended_candidates, run_info, missing = build_broad_stems(
            input_path, job_root, profile, profile_cfg["run_models"]
        )
        rejected_candidates: dict[str, dict[str, dict[str, object]]] = {
            "extended_stems": {},
            "derived_stems": {},
            "specialist_substems": {},
            "midi": {},
        }
        missing_features = list(missing)
        candidate_winners: dict[str, dict[str, object]] = {}
        remote_adapter_status = "not_requested"
        remote_adapter_reason: str | None = None
        pipeline_mode = "local_standard" if profile == "preview" else "local_fallback"

        if profile_cfg["publish_extended"]:
            published_extended, rejected_extended = _publish_audio_candidates(
                extended_candidates,
                threshold=PUBLISH_THRESHOLDS["extended_stems"],
                publish_dir=job_root / "broad_stems",
            )
            broad_outputs.update(published_extended)
            rejected_candidates["extended_stems"] = rejected_extended
            for stem_name, payload in published_extended.items():
                candidate_winners[stem_name] = _candidate_winner_entry(
                    payload,
                    published_group="broad_stems",
                    fallback_used=False,
                )

        derived_outputs: dict[str, dict[str, object]] = {}
        if profile_cfg["publish_derived"]:
            _update_status(job_root, stage="derived_split")
            heuristic_candidates = build_derived_stems(
                broad_outputs,
                job_root,
                use_specialist=False,
            )
            derived_candidates = dict(heuristic_candidates)
            local_specialist_available, local_specialist_reason = local_specialist_runtime_status()
            if profile_cfg.get("prefer_local_specialists") and local_specialist_available:
                local_candidates, local_errors = build_local_derived_candidates(broad_outputs, job_root)
                derived_candidates.update(local_candidates)
                pipeline_mode = "local_specialist"
                for error in local_errors:
                    if error not in missing_features:
                        missing_features.append(error)
            elif profile_cfg.get("prefer_local_specialists") and local_specialist_reason:
                if local_specialist_reason not in missing_features:
                    missing_features.append(local_specialist_reason)
            derived_outputs, rejected_derived = _publish_audio_candidates(
                derived_candidates,
                threshold=PUBLISH_THRESHOLDS["derived_stems"],
                publish_dir=job_root / "derived_stems",
            )
            rejected_candidates["derived_stems"] = rejected_derived
            for stem_name, payload in derived_outputs.items():
                candidate_winners[stem_name] = _candidate_winner_entry(
                    payload,
                    published_group="derived_stems",
                    fallback_used=str(payload.get("source_model", "")).startswith("heuristic:"),
                )
                source_model = str(payload.get("source_model", ""))
                if source_model.startswith("local_specialist:"):
                    model_name = source_model.split(":", 1)[1]
                    if model_name not in models_used:
                        models_used.append(model_name)

        specialist_outputs: dict[str, dict[str, object]] = {}
        if profile_cfg.get("use_mvsep"):
            _update_status(job_root, stage="specialist_substems")
            specialist_candidates, specialist_errors, remote_adapter_status, remote_adapter_reason = _collect_specialist_candidates(
                broad_outputs,
                job_root,
            )
            specialist_outputs, rejected_specialist = _publish_audio_candidates(
                specialist_candidates,
                threshold=PUBLISH_THRESHOLDS["specialist_substems"],
                publish_dir=job_root / "specialist_substems",
            )
            rejected_candidates["specialist_substems"] = rejected_specialist
            if specialist_outputs:
                pipeline_mode = "local_plus_mvsep_experimental"
            for stem_name, payload in specialist_outputs.items():
                candidate_winners[stem_name] = _candidate_winner_entry(
                    payload,
                    published_group="specialist_substems",
                    fallback_used=False,
                )
            if specialist_errors:
                for error in specialist_errors:
                    if error not in missing_features:
                        missing_features.append(error)
            if remote_adapter_status in {"skipped", "failed"} and remote_adapter_reason and remote_adapter_reason not in missing_features:
                missing_features.append(remote_adapter_reason)
        else:
            specialist_outputs = {}

        analysis: dict[str, Any] = {}
        tempo_locked: dict[str, str] = {}
        analysis_exports: dict[str, str] = {}
        waveform_sources = {
            stem_name: Path(str(payload["path"]))
            for stem_name, payload in {
                **broad_outputs,
                **derived_outputs,
                **specialist_outputs,
            }.items()
            if isinstance(payload, dict) and payload.get("path")
        }
        if waveform_sources:
            waveform_path = write_waveform_peaks(
                waveform_sources,
                job_root / "analysis" / "waveform_peaks.json",
            )
            analysis_exports["waveform_peaks"] = str(waveform_path.resolve())
        if profile_cfg["tempo_lock"] and broad_outputs:
            analysis = detect_tempo_and_beats(Path(str(broad_outputs["instrumental"]["path"])))
            analysis.update(estimate_key(Path(str(broad_outputs["instrumental"]["path"]))))
            analysis_dir = ensure_dir(job_root / "analysis")
            tempo_key_path = write_tempo_key_analysis(analysis_dir / "tempo_key.json", analysis)
            analysis_exports["tempo_key"] = str(tempo_key_path.resolve())
            sections = detect_sections(
                Path(str(broad_outputs["instrumental"]["path"])),
                analysis.get("beat_times"),
            )
            sections_path = write_sections_analysis(analysis_dir / "sections.json", sections)
            analysis_exports["sections"] = str(sections_path.resolve())
            tempo_dir = ensure_dir(job_root / "tempo_locked_wavs")
            for stem_name, payload in {**broad_outputs, **derived_outputs, **specialist_outputs}.items():
                source = Path(str(payload["path"]))
                target = tempo_dir / f"{stem_name}.wav"
                create_tempo_locked_copy(
                    source,
                    target,
                    float(analysis.get("first_beat_seconds", 0.0)),
                )
                tempo_locked[stem_name] = str(target.resolve())

        midi_exports: dict[str, dict[str, object]] = {}
        if profile_cfg["generate_midi"]:
            _update_status(job_root, stage="midi")
            midi_dir = ensure_dir(job_root / "midi")
            midi_candidate_dir = ensure_dir(job_root / "midi_candidates")
            melody_sources = []
            if profile_cfg.get("use_mvsep"):
                melody_sources.append(("lead_vocals", specialist_outputs.get("lead_vocals")))
            melody_sources.extend(
                [
                    ("vocals", broad_outputs.get("vocals")),
                    ("keys_synth", specialist_outputs.get("keys_synth") or derived_outputs.get("keys_synth")),
                    ("piano", specialist_outputs.get("piano") or broad_outputs.get("piano")),
                ]
            )
            for source_name, payload in melody_sources:
                if not payload:
                    continue
                candidate_target = midi_candidate_dir / "melody.mid"
                if not _run_audio2midi(Path(str(payload["path"])), candidate_target):
                    continue
                published_midi, rejected_midi = _publish_midi_candidate(
                    candidate_target,
                    name="melody",
                    source_name=source_name,
                    source_path=Path(str(payload["path"])),
                    audio_duration=_audio_duration(Path(str(payload["path"]))),
                    publish_dir=midi_dir,
                )
                if published_midi:
                    midi_exports["melody"] = published_midi
                    candidate_winners["midi:melody"] = {
                        "published_group": "midi",
                        "winning_source": source_name,
                        "quality_score": published_midi.get("quality_score"),
                        "fallback_used": False,
                    }
                    break
                if rejected_midi:
                    rejected_candidates["midi"][f"melody_from_{source_name}"] = rejected_midi

            bass_source = broad_outputs.get("bass")
            if bass_source:
                bass_candidate = midi_candidate_dir / "bass.mid"
                if _run_audio2midi(Path(str(bass_source["path"])), bass_candidate):
                    published_midi, rejected_midi = _publish_midi_candidate(
                        bass_candidate,
                        name="bass",
                        source_name="bass",
                        source_path=Path(str(bass_source["path"])),
                        audio_duration=_audio_duration(Path(str(bass_source["path"]))),
                        publish_dir=midi_dir,
                    )
                    if published_midi:
                        midi_exports["bass"] = published_midi
                        candidate_winners["midi:bass"] = {
                            "published_group": "midi",
                            "winning_source": "bass",
                            "quality_score": published_midi.get("quality_score"),
                            "fallback_used": False,
                        }
                    elif rejected_midi:
                        rejected_candidates["midi"]["bass"] = rejected_midi

            chord_source = specialist_outputs.get("keys_synth") or derived_outputs.get("keys_synth") or broad_outputs.get("other")
            if chord_source:
                chord_target = midi_candidate_dir / "chords_guide.mid"
                try:
                    write_chord_guide_midi(
                        Path(str(chord_source["path"])),
                        chord_target,
                        analysis.get("beat_times"),
                    )
                except Exception:
                    pass
                else:
                    chord_source_name = (
                        "keys_synth"
                        if specialist_outputs.get("keys_synth") or derived_outputs.get("keys_synth")
                        else "other"
                    )
                    published_midi, rejected_midi = _publish_midi_candidate(
                        chord_target,
                        name="chords_guide",
                        source_name=chord_source_name,
                        source_path=Path(str(chord_source["path"])),
                        audio_duration=_audio_duration(Path(str(chord_source["path"]))),
                        publish_dir=midi_dir,
                    )
                    if published_midi:
                        midi_exports["chords_guide"] = published_midi
                        candidate_winners["midi:chords_guide"] = {
                            "published_group": "midi",
                            "winning_source": chord_source_name,
                            "quality_score": published_midi.get("quality_score"),
                            "fallback_used": False,
                        }
                    elif rejected_midi:
                        rejected_candidates["midi"]["chords_guide"] = rejected_midi

        _update_status(job_root, stage="package")
        manifest = {
            "job_id": job_id,
            "profile": profile,
            "status": "completed",
            "input_name": status["input_name"],
            "input_path": str(input_path.resolve()),
            "input_hash": file_sha256(input_path),
            "input_source": status.get("input_source", {"type": "upload", "provider": "local"}),
            "runtime_env": {
                "engine": "local-cpu",
                "created_at": status["created_at"],
            },
            "models_used": models_used + (["mvsep"] if specialist_outputs else []),
            "runs_root": run_info["runs_root"],
            "published_broad_stems": broad_outputs,
            "published_derived_stems": derived_outputs,
            "published_specialist_substems": specialist_outputs,
            "tempo_locked_exports": tempo_locked,
            "midi_exports": midi_exports,
            "analysis": analysis,
            "analysis_exports": analysis_exports,
            "pipeline_mode": pipeline_mode,
            "candidate_winners": candidate_winners,
            "rejected_candidates": rejected_candidates,
            "missing_features": missing_features,
            "remote_adapter_status": remote_adapter_status,
            "remote_adapter_reason": remote_adapter_reason,
            "timings": {"completed_at": now_iso()},
        }
        manifest_path = write_manifest(job_root, manifest)

        package_groups = {
            "stems": _collect_files(job_root / "broad_stems", job_root / "derived_stems", job_root / "specialist_substems"),
            "midi": _collect_files(job_root / "midi"),
            "wav_plus_midi": _collect_files(
                job_root / "broad_stems",
                job_root / "derived_stems",
                job_root / "specialist_substems",
                job_root / "midi",
                job_root / "tempo_locked_wavs",
                job_root / "analysis",
            ),
        }
        bundles = package_directories(job_root, package_groups)
        manifest["bundle_exports"] = bundles
        write_manifest(job_root, manifest)
        _update_status(
            job_root,
            status="completed",
            stage="done",
            manifest_path=str(manifest_path.resolve()),
            bundles=bundles,
            manifest=manifest,
        )
    except sp.CalledProcessError as exc:
        _update_status(job_root, status="error", stage="failed", error=str(exc))
        raise
    except Exception as exc:  # pragma: no cover - integration path
        _update_status(job_root, status="error", stage="failed", error=str(exc))
        raise


def run_job(job_id: str) -> None:
    store = _job_store()
    lease_owner = f"{INSTANCE_ID}:{uuid.uuid4().hex}"
    if not store.acquire_lease(job_id, lease_owner, JOB_LEASE_SECONDS):
        return
    heartbeat_stop = Event()
    lease_lost = Event()

    def renew_lease() -> None:
        while not heartbeat_stop.wait(JOB_LEASE_RENEW_INTERVAL):
            try:
                renewed = store.renew_lease(job_id, lease_owner, JOB_LEASE_SECONDS)
            except Exception:
                lease_lost.set()
                return
            if not renewed:
                lease_lost.set()
                return

    heartbeat = Thread(target=renew_lease, name=f"lease-{job_id[:8]}", daemon=True)
    heartbeat.start()
    try:
        status = store.get(job_id)
        if status is None:
            return
        if status.get("cancel_requested"):
            _update_status(_job_root(job_id), status="cancelled", stage="cancelled")
            return
        if int(status.get("attempt") or 0) > JOB_MAX_ATTEMPTS:
            _update_status(
                _job_root(job_id),
                status="error",
                stage="retry_exhausted",
                error="job_retry_exhausted",
            )
            return
        _run_job_pipeline(job_id)
        if lease_lost.is_set():
            latest = store.get(job_id)
            if latest and latest.get("status") not in TERMINAL_JOB_STATES:
                raise RuntimeError("job_execution_lease_lost")
    except Exception as exc:
        if JOB_DISPATCH_BACKEND != "rq":
            latest = store.get(job_id)
            if latest and latest.get("status") not in TERMINAL_JOB_STATES:
                _update_status(
                    _job_root(job_id),
                    status="error",
                    stage="failed",
                    error=str(exc),
                )
            raise
        latest = store.get(job_id)
        attempt = int((latest or {}).get("attempt") or 0)
        if latest and not latest.get("cancel_requested") and attempt < JOB_MAX_ATTEMPTS:
            _update_status(
                _job_root(job_id),
                status="queued",
                stage="retry_scheduled",
                error=str(exc),
            )
        else:
            _update_status(
                _job_root(job_id),
                status="error",
                stage="retry_exhausted",
                error=str(exc),
            )
        raise
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=2)
        store.release_lease(job_id, lease_owner)

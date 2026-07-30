from __future__ import annotations

import hmac
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess as sp
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.responses import FileResponse

from splitter.object_storage import ObjectStorageError, materialize_object, object_store_from_config
from splitter.stem_contract import apply_product_11_contract

WORKER_ROOT = Path(os.getenv("GPU_WORKER_ROOT", "/tmp/stemsplitter-gpu-worker"))
JOBS_DIR = Path(os.getenv("GPU_WORKER_JOBS_DIR", str(WORKER_ROOT / "jobs")))
MODEL_DIR = Path(os.getenv("AUDIO_SEPARATOR_MODEL_DIR", str(WORKER_ROOT / "models")))
LOCAL_RUNS_DIR = Path(os.getenv("GPU_WORKER_LOCAL_RUNS_DIR", "/tmp/stemsplitter-local-runs"))
AUDIO_SEPARATOR_BIN = os.getenv("AUDIO_SEPARATOR_BIN") or shutil.which("audio-separator") or "audio-separator"
API_KEY = os.getenv("GPU_WORKER_API_KEY") or os.getenv("WORKER_API_KEY")
MAX_WORKERS = int(os.getenv("GPU_WORKER_MAX_CONCURRENCY", "1"))
AUDIO_SEPARATOR_ENGINE = os.getenv("AUDIO_SEPARATOR_ENGINE", "python").lower()
AUDIO_SEPARATOR_MODEL_CACHE = os.getenv("AUDIO_SEPARATOR_MODEL_CACHE", "1").lower() not in {"0", "false", "no"}
MAX_UPLOAD_BYTES = int(os.getenv("GPU_WORKER_MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
GPU_TYPE = os.getenv("STEMSPLITTER_GPU_TYPE") or os.getenv("MODAL_GPU", "T4")
EXECUTION_MODE = os.getenv("GPU_WORKER_EXECUTION_MODE", "sequential").lower()
BROAD_GPU_TYPE = os.getenv("MODAL_BROAD_GPU", "L4")
VOCAL_GPU_TYPE = os.getenv("MODAL_VOCAL_GPU", "L4")
DRUM_GPU_TYPE = os.getenv("MODAL_DRUM_GPU", "L4")
OPEN_SPECIALIST_APP_NAME = os.getenv(
    "OPEN_SPECIALIST_MODAL_APP_NAME",
    "stemsplitter-open-specialists",
)
OPEN_SPECIALIST_GPU_TYPE = os.getenv("OPEN_SPECIALIST_MODAL_GPU", "L4")
BRANCH_CPU = float(os.getenv("GPU_WORKER_BRANCH_CPU", "4"))
BRANCH_KEEP_WARM = int(os.getenv("GPU_WORKER_BRANCH_KEEP_WARM", "0"))
OBJECT_PUBLISH_WORKERS = max(1, int(os.getenv("GPU_WORKER_OBJECT_PUBLISH_WORKERS", "4")))
ENABLE_RESOURCE_PROFILING = os.getenv("GPU_WORKER_ENABLE_PROFILING", "0").lower() in {
    "1",
    "true",
    "yes",
}
GPU_PROFILE_INTERVAL_SECONDS = 0.25

EXECUTOR = ThreadPoolExecutor(max_workers=MAX_WORKERS)
LOCK = Lock()
SEPARATOR_CACHE_LOCK = Lock()
FUTURES: dict[str, object] = {}
SEPARATOR_CACHE: dict[str, object] = {}
REPLAYABLE_JOB_STATES = {
    "queued",
    "running",
    "finalizing",
    "cancelling",
    "completed",
    "cancelled",
}

api_app = FastAPI(title="StemSplitter GPU Worker")

JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}
ARTIFACT_GROUP_DIRS = ("broad_stems", "derived_stems", "specialist_substems", "analysis", "midi")
LOCAL_MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "bs_roformer_sw": {
        "stage": "broad_bs_roformer_sw",
        "group": "broad_stems",
        "model": "BS-Roformer-SW.ckpt",
        "stem_map": {
            "vocals": "bs_aux_voice",
            "instrumental": "bs_aux_accompaniment",
        },
    },
    "melband_kim_vocals": {
        "stage": "vocal_instrumental_melband_kim",
        "group": "broad_stems",
        "model": "vocals_mel_band_roformer.ckpt",
    },
    "mdx23c_drumsep_jarredou_aufr33": {
        "stage": "drum_substems",
        "group": "specialist_substems",
        "model": "MDX23C-DrumSep-aufr33-jarredou.ckpt",
    },
    "open_specialist_product_pack": {
        "stage": "product_specialist_stems",
        "group": "specialist_substems",
        "model": "open_specialist_product_pack",
        "members": {
            "bs_roformer_sw_electric_guitar_head": "electric_guitar_bsroformer_base.ckpt",
            "oulianov_bs_roformer_bowed_strings": "gilliaan_bowedstrings_bs_v1.ckpt",
            "xlance_bs_roformer_synth_v2": "bs_syn2_xlancer.ckpt",
        },
    },
}

PROFILE_MODEL_PLANS = {
    "preview_gpu_experimental": ["bs_roformer_sw"],
    "quality_gpu_experimental": [
        "melband_kim_vocals",
        "bs_roformer_sw",
        "mdx23c_drumsep_jarredou_aufr33",
        "open_specialist_product_pack",
    ],
}

QUARANTINED_MODELS: dict[str, str] = {}

PARALLEL_BRANCHES = (
    {"role": "vocals", "model_key": "melband_kim_vocals", "gpu_type": VOCAL_GPU_TYPE},
    {"role": "broad", "model_key": "bs_roformer_sw", "gpu_type": BROAD_GPU_TYPE},
    {
        "role": "drums",
        "model_key": "mdx23c_drumsep_jarredou_aufr33",  # gitleaks:allow
        "gpu_type": DRUM_GPU_TYPE,
    },
    {
        "role": "specialists",
        "model_key": "open_specialist_product_pack",
        "gpu_type": OPEN_SPECIALIST_GPU_TYPE,
    },
)

QUALITY_PARALLEL_PROFILE = "quality_gpu_experimental"
PRODUCT_SPECIALIST_OUTPUTS = {
    "electric_guitar": "electric_guitar",
    "strings": "strings",
    "synth_xlance_v2": "synth",
}

STEM_ALIASES = {
    "vocals": ("vocals", "vocal"),
    "instrumental": ("instrumental", "no_vocals", "no vocals", "inst"),
    "drums": ("drums", "drum"),
    "bass": ("bass",),
    "other": ("other",),
    "kick": ("kick",),
    "snare": ("snare",),
    "toms": ("toms", "tom"),
    "hi_hats": ("hi_hat", "hi-hat", "hihat", "hh"),
    "ride": ("ride",),
    "crash": ("crash",),
    "cymbals": ("cymbal",),
    "wind": ("wind", "winds", "woodwind", "woodwinds"),
    "no_crowd": ("no_crowd", "no crowd", "nocrowd"),
    "crowd": ("crowd",),
    "noreverb": ("noreverb", "no_reverb", "no reverb"),
    "reverb": ("reverb",),
    "dry": ("dry",),
    "no_dry": ("no_dry", "no dry", "nodry"),
    "no_echo": ("no_echo", "no echo"),
    "echo": ("echo",),
    "no_noise": ("no_noise", "no noise"),
    "noise": ("noise",),
}


def _authorize(authorization: str | None) -> None:
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GPU worker authentication is not configured.",
        )
    expected = f"Bearer {API_KEY}"
    if not hmac.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _elapsed_seconds(start: float) -> float:
    return round(time.perf_counter() - start, 3)


def _audio_duration_seconds(path: Path) -> float | None:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return round(float(info.frames / max(info.samplerate, 1)), 3)
    except Exception:
        try:
            completed = sp.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                check=True,
                text=True,
            )
            return round(float(completed.stdout.strip()), 3)
        except (OSError, ValueError, sp.SubprocessError):
            return None


def _status_timings(status: dict[str, Any]) -> dict[str, Any]:
    timings = status.get("timings")
    return dict(timings) if isinstance(timings, dict) else {}


def _job_root(job_id: str) -> Path:
    if not JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job id")
    return JOBS_DIR / job_id


def _status_path(job_id: str) -> Path:
    return _job_root(job_id) / "status.json"


def _load_status(job_id: str) -> dict[str, Any]:
    path = _status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_status(job_id: str, payload: dict[str, Any]) -> None:
    path = _status_path(job_id)
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _reserve_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Atomically reserve a worker job or replay its durable active result."""
    _reload_jobs_volume()
    with LOCK:
        path = _status_path(job_id)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if str(existing.get("status")) in REPLAYABLE_JOB_STATES:
                return {**existing, "idempotency_replayed": True}
        _write_status(job_id, payload)
    return None


def _update_status(job_id: str, **updates: Any) -> dict[str, Any]:
    status = _load_status(job_id)
    status.update(updates)
    _write_status(job_id, status)
    return status


def _tasks_for_profile(profile: str) -> list[dict[str, Any]]:
    model_keys = PROFILE_MODEL_PLANS.get(profile) or PROFILE_MODEL_PLANS["quality_gpu_experimental"]
    tasks: list[dict[str, Any]] = []
    for model_key in model_keys:
        task = dict(LOCAL_MODEL_REGISTRY[model_key])
        task["model_key"] = model_key
        tasks.append(task)
    return tasks


def _quarantined_models_for_profile(profile: str) -> dict[str, str]:
    if profile == "quality_gpu_experimental":
        return dict(QUARANTINED_MODELS)
    return {}


def _run_audio_separator(input_path: Path, output_dir: Path, model: str) -> dict[str, Any]:
    if AUDIO_SEPARATOR_ENGINE == "python":
        try:
            return _run_audio_separator_python(input_path, output_dir, model)
        except ModuleNotFoundError:
            return _run_audio_separator_cli(input_path, output_dir, model, fallback_reason="python_api_missing")
    return _run_audio_separator_cli(input_path, output_dir, model)


def _run_audio_separator_cli(
    input_path: Path,
    output_dir: Path,
    model: str,
    *,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    _ensure_dir(output_dir)
    _ensure_dir(MODEL_DIR)
    cmd = [
        AUDIO_SEPARATOR_BIN,
        str(input_path),
        "--model_filename",
        model,
        "--model_file_dir",
        str(MODEL_DIR),
        "--output_dir",
        str(output_dir),
        "--output_format",
        "WAV",
        "--log_level",
        "warning",
    ]
    started = time.perf_counter()
    sp.run(cmd, check=True, capture_output=True, text=True)
    details: dict[str, Any] = {
        "engine": "cli",
        "separate_seconds": _elapsed_seconds(started),
        "cache_hit": False,
    }
    if fallback_reason:
        details["fallback_reason"] = fallback_reason
    return details


def _run_audio_separator_python(input_path: Path, output_dir: Path, model: str) -> dict[str, Any]:
    _ensure_dir(output_dir)
    _ensure_dir(MODEL_DIR)
    started = time.perf_counter()
    load_cpu_started = time.process_time()
    separator, cache_hit, load_seconds = _get_python_separator(model, output_dir)
    load_cpu_seconds = round(time.process_time() - load_cpu_started, 3)
    _set_separator_output_dir(separator, output_dir)
    separate_started = time.perf_counter()
    separate_cpu_started = time.process_time()
    gpu_sampler = _start_gpu_sampler(output_dir)
    try:
        separator.separate(str(input_path))
    finally:
        gpu_profile = _stop_gpu_sampler(gpu_sampler)
    separate_seconds = _elapsed_seconds(separate_started)
    separate_cpu_seconds = round(time.process_time() - separate_cpu_started, 3)
    return {
        "engine": "python",
        "cache_hit": cache_hit,
        "load_seconds": load_seconds,
        "load_cpu_seconds": load_cpu_seconds,
        "separate_seconds": separate_seconds,
        "separate_cpu_seconds": separate_cpu_seconds,
        "separate_cpu_to_wall_ratio": (
            round(separate_cpu_seconds / separate_seconds, 4) if separate_seconds > 0 else None
        ),
        "cpu_capacity_count": _cpu_capacity_count(),
        "gpu_profile": gpu_profile,
        "total_seconds": _elapsed_seconds(started),
    }


def _cpu_capacity_count() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return int(os.cpu_count() or 1)


def _start_gpu_sampler(output_dir: Path) -> tuple[sp.Popen[str], object, Path] | None:
    if not ENABLE_RESOURCE_PROFILING or shutil.which("nvidia-smi") is None:
        return None
    profile_path = output_dir / "gpu-profile.csv"
    handle = profile_path.open("w", encoding="utf-8")
    try:
        process = sp.Popen(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.memory,memory.used,power.draw",
                "--format=csv,noheader,nounits",
                f"--loop-ms={int(GPU_PROFILE_INTERVAL_SECONDS * 1000)}",
            ],
            stdout=handle,
            stderr=sp.DEVNULL,
            text=True,
        )
    except Exception:
        handle.close()
        return None
    return process, handle, profile_path


def _stop_gpu_sampler(
    sampler: tuple[sp.Popen[str], object, Path] | None,
) -> dict[str, object]:
    if sampler is None:
        return {"status": "disabled" if not ENABLE_RESOURCE_PROFILING else "unavailable"}
    process, handle, profile_path = sampler
    process.terminate()
    try:
        process.wait(timeout=2)
    except sp.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
    handle.close()  # type: ignore[union-attr]

    samples: list[tuple[float, float, float, float]] = []
    for line in profile_path.read_text(encoding="utf-8").splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 4:
            continue
        try:
            samples.append(tuple(float(field) for field in fields))  # type: ignore[arg-type]
        except ValueError:
            continue
    if not samples:
        return {"status": "no_samples", "sample_interval_seconds": GPU_PROFILE_INTERVAL_SECONDS}

    gpu_utilization = [sample[0] for sample in samples]
    memory_utilization = [sample[1] for sample in samples]
    memory_used = [sample[2] for sample in samples]
    power_draw = [sample[3] for sample in samples]
    active_indexes = [index for index, value in enumerate(gpu_utilization) if value >= 10]
    return {
        "status": "sampled",
        "sample_count": len(samples),
        "sample_interval_seconds": GPU_PROFILE_INTERVAL_SECONDS,
        "gpu_utilization_avg_percent": round(sum(gpu_utilization) / len(samples), 3),
        "gpu_utilization_max_percent": round(max(gpu_utilization), 3),
        "gpu_active_sample_ratio": round(len(active_indexes) / len(samples), 4),
        "time_to_first_gpu_active_seconds": (
            round(active_indexes[0] * GPU_PROFILE_INTERVAL_SECONDS, 3) if active_indexes else None
        ),
        "memory_utilization_avg_percent": round(sum(memory_utilization) / len(samples), 3),
        "memory_used_max_mib": round(max(memory_used), 3),
        "power_draw_avg_watts": round(sum(power_draw) / len(samples), 3),
    }


def _get_python_separator(model: str, output_dir: Path) -> tuple[object, bool, float]:
    if AUDIO_SEPARATOR_MODEL_CACHE:
        with SEPARATOR_CACHE_LOCK:
            cached = SEPARATOR_CACHE.get(model)
            if cached is not None:
                return cached, True, 0.0
            separator, load_seconds = _load_python_separator(model, output_dir)
            SEPARATOR_CACHE[model] = separator
            return separator, False, load_seconds
    separator, load_seconds = _load_python_separator(model, output_dir)
    return separator, False, load_seconds


def _load_python_separator(model: str, output_dir: Path) -> tuple[object, float]:
    from audio_separator.separator import Separator

    load_started = time.perf_counter()
    separator = Separator(
        log_level=logging.WARNING,
        model_file_dir=str(MODEL_DIR),
        output_dir=str(output_dir),
        output_format="WAV",
    )
    separator.load_model(model_filename=model)
    return separator, _elapsed_seconds(load_started)


def _set_separator_output_dir(separator: object, output_dir: Path) -> None:
    output = str(output_dir)
    separator.output_dir = output
    model_instance = getattr(separator, "model_instance", None)
    if model_instance is not None:
        model_instance.output_dir = output


def _alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _stem_name_from_label(label: str) -> str | None:
    normalized_label = _alias_key(label)
    if not normalized_label:
        return None
    for stem_name, aliases in STEM_ALIASES.items():
        if normalized_label == _alias_key(stem_name):
            return stem_name
        for alias in aliases:
            if normalized_label == _alias_key(alias):
                return stem_name
    return None


def _normalize_stem_name(path: Path) -> str:
    name = path.stem.lower()
    for label in re.findall(r"\(([^)]+)\)", name):
        stem_name = _stem_name_from_label(label)
        if stem_name:
            return stem_name
    normalized = _alias_key(name)
    for stem_name, aliases in STEM_ALIASES.items():
        for alias in aliases:
            alias_key = _alias_key(alias)
            if alias_key and alias_key in normalized:
                return stem_name
    return normalized or "stem"


def _safe_artifact_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "stem"


def _artifact_name(source: Path, task: dict[str, Any]) -> str:
    stem_name = _normalize_stem_name(source)
    stem_map = task.get("stem_map", {})
    if isinstance(stem_map, dict):
        stem_name = str(stem_map.get(stem_name, stem_name))
    prefix = task.get("output_prefix")
    if prefix:
        stem_name = f"{prefix}_{stem_name}"
    return _safe_artifact_name(stem_name)


def _unique_artifact_path(artifact_dir: Path, base_name: str, stage: str) -> tuple[str, Path]:
    artifact_name = _safe_artifact_name(base_name)
    target = artifact_dir / f"{artifact_name}.wav"
    if not target.exists():
        return artifact_name, target

    stage_name = _safe_artifact_name(stage)
    candidate_name = f"{artifact_name}_{stage_name}"
    target = artifact_dir / f"{candidate_name}.wav"
    counter = 2
    while target.exists():
        candidate_name = f"{artifact_name}_{stage_name}_{counter}"
        target = artifact_dir / f"{candidate_name}.wav"
        counter += 1
    return candidate_name, target


def _collect_outputs(job_id: str, task: dict[str, Any], run_dir: Path) -> dict[str, str]:
    group = task["group"]
    artifact_dir = _ensure_dir(_job_root(job_id) / group)
    artifacts: dict[str, str] = {}
    for source in sorted(run_dir.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        stem_name = _artifact_name(source, task)
        artifact_name, target = _unique_artifact_path(artifact_dir, stem_name, str(task["stage"]))
        shutil.copy2(source, target)
        artifacts[artifact_name] = f"/artifacts/{job_id}/{group}/{target.name}"
    return artifacts


def _merge_artifacts(
    status: dict[str, Any],
    group: str,
    artifacts: dict[str, str],
    *,
    source_model: str,
) -> dict[str, Any]:
    current = status.setdefault("artifacts", {})
    group_payload = current.setdefault(group, {})
    group_payload.update(artifacts)
    artifact_sources = status.setdefault("artifact_sources", {})
    source_group = artifact_sources.setdefault(group, {})
    for artifact_name in artifacts:
        source_group[artifact_name] = source_model
    return status


def _artifact_local_path(job_id: str, artifact_url: str) -> Path:
    prefix = f"/artifacts/{job_id}/"
    if not artifact_url.startswith(prefix):
        raise RuntimeError("invalid_worker_artifact_url")
    target = (_job_root(job_id) / artifact_url[len(prefix) :]).resolve()
    root = _job_root(job_id).resolve()
    if not str(target).startswith(str(root)):
        raise RuntimeError("worker_artifact_outside_job")
    return target


def _finalize_quality_contract(job_id: str, status: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, dict[str, dict[str, object]]] = {
        "broad_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
    }
    artifacts = status.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    sources = status.get("artifact_sources")
    sources = sources if isinstance(sources, dict) else {}
    for group_name in groups:
        artifact_group = artifacts.get(group_name)
        artifact_group = artifact_group if isinstance(artifact_group, dict) else {}
        source_group = sources.get(group_name)
        source_group = source_group if isinstance(source_group, dict) else {}
        for artifact_name, artifact_url in artifact_group.items():
            if not isinstance(artifact_url, str):
                continue
            groups[group_name][artifact_name] = {
                "path": str(_artifact_local_path(job_id, artifact_url)),
                "source_model": source_group.get(artifact_name) or "gpu_worker",
                "publish_status": "candidate",
                "publish_reason": "gpu_worker_candidate",
                "quality_score": None,
                "warnings": [],
                "metrics": {},
            }

    rejected = {
        "extended_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
        "midi": {},
    }
    missing = list(status.get("missing_features") or [])
    contract = apply_product_11_contract(
        _job_root(job_id),
        broad_outputs=groups["broad_stems"],
        derived_outputs=groups["derived_stems"],
        specialist_outputs=groups["specialist_substems"],
        rejected_candidates=rejected,
        missing_features=missing,
    )
    canonical_artifacts: dict[str, dict[str, str]] = {}
    canonical_sources: dict[str, dict[str, str]] = {}
    for output_key, group_name in (
        ("published_broad_stems", "broad_stems"),
        ("published_derived_stems", "derived_stems"),
        ("published_specialist_substems", "specialist_substems"),
    ):
        output_group = contract[output_key]
        if not isinstance(output_group, dict):
            continue
        canonical_artifacts[group_name] = {}
        canonical_sources[group_name] = {}
        for artifact_name, metadata in output_group.items():
            if not isinstance(metadata, dict):
                continue
            path = Path(str(metadata["path"]))
            relative = path.resolve().relative_to(_job_root(job_id).resolve())
            canonical_artifacts[group_name][artifact_name] = f"/artifacts/{job_id}/{relative.as_posix()}"
            canonical_sources[group_name][artifact_name] = str(metadata.get("source_model") or "gpu_worker")

    status.update(
        {
            "artifacts": canonical_artifacts,
            "artifact_sources": canonical_sources,
            "stem_contract": contract["stem_contract"],
            "rejected_candidates": rejected,
            "missing_features": missing,
        }
    )
    _write_status(job_id, status)
    return status


def _publish_worker_objects(
    job_id: str,
    status: dict[str, Any],
) -> dict[str, object]:
    try:
        store = object_store_from_config()
    except ObjectStorageError as exc:
        return {"artifact_transport": "local_worker", "object_storage_reason": str(exc)}
    if store is None:
        return {"artifact_transport": "local_worker"}

    object_artifacts: dict[str, dict[str, dict[str, object]]] = {}
    uploads: list[tuple[str, str, Path, str, str]] = []
    artifacts = status.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    for group_name, artifact_group in artifacts.items():
        if not isinstance(artifact_group, dict):
            continue
        object_artifacts[group_name] = {}
        for artifact_name, artifact_url in artifact_group.items():
            if not isinstance(artifact_url, str):
                continue
            source = _artifact_local_path(job_id, artifact_url)
            content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            key = store.artifact_key(job_id, group_name, source.name)
            uploads.append((group_name, artifact_name, source, key, content_type))

    def upload_one(item: tuple[str, str, Path, str, str]):
        group_name, artifact_name, source, key, content_type = item
        return group_name, artifact_name, store.upload(source, key, content_type).as_dict()

    with ThreadPoolExecutor(max_workers=min(OBJECT_PUBLISH_WORKERS, len(uploads) or 1)) as executor:
        for group_name, artifact_name, reference in executor.map(upload_one, uploads):
            object_artifacts[group_name][artifact_name] = reference

    result: dict[str, object] = {
        "artifact_transport": "object_storage",
        "object_artifacts": object_artifacts,
    }
    bundle = _build_worker_bundle(job_id, status)
    if bundle is not None:
        bundle_key = store.artifact_key(job_id, "package", bundle.name)
        result["object_bundle"] = store.upload(
            bundle,
            bundle_key,
            "application/zip",
        ).as_dict()
    return result


def _build_worker_bundle(job_id: str, status: dict[str, Any]) -> Path | None:
    artifacts = status.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    members: list[tuple[str, Path]] = []
    for group_name in ("broad_stems", "specialist_substems"):
        group = artifacts.get(group_name)
        if not isinstance(group, dict):
            continue
        for artifact_name, artifact_url in group.items():
            source = _artifact_local_path(job_id, str(artifact_url))
            if source.is_file():
                members.append((f"{group_name}/{artifact_name}{source.suffix}", source))
    if not members:
        return None
    bundle = _job_root(job_id) / "package" / "stems.zip"
    _ensure_dir(bundle.parent)
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as archive:
        for archive_name, source in members:
            archive.write(source, archive_name)
    return bundle


def _execute_model_task(
    job_id: str,
    input_path: Path,
    task: dict[str, Any],
    *,
    index: int,
    total: int,
    run_namespace: str | None = None,
) -> dict[str, Any]:
    model = str(task["model"])
    task_started = time.perf_counter()
    task_started_at = _now_iso()
    run_name = run_namespace or f"{index:02d}_{task['stage']}"
    run_dir = LOCAL_RUNS_DIR / job_id / run_name
    shutil.rmtree(run_dir, ignore_errors=True)
    print(
        f"[worker] job={job_id} {index}/{total} stage={task['stage']} model={model} start",
        flush=True,
    )
    try:
        inference_started = time.perf_counter()
        run_details = _run_audio_separator(input_path, run_dir, model)
        inference_seconds = _elapsed_seconds(inference_started)
        collect_started = time.perf_counter()
        artifacts = _collect_outputs(job_id, task, run_dir)
        artifact_collection_seconds = _elapsed_seconds(collect_started)
        task_total_seconds = _elapsed_seconds(task_started)
        model_run = {
            "index": index,
            "total": total,
            "stage": task["stage"],
            "model_key": task["model_key"],
            "model": model,
            "status": "completed",
            "started_at": task_started_at,
            "ended_at": _now_iso(),
            "duration_seconds": task_total_seconds,
            "inference_seconds": inference_seconds,
            **run_details,
            "artifact_collection_seconds": artifact_collection_seconds,
            "artifact_count": len(artifacts),
        }
        print(
            f"[worker] job={job_id} stage={task['stage']} model={model} artifacts={sorted(artifacts)}",
            flush=True,
        )
        return {
            "status": "completed",
            "group": task["group"],
            "model": model,
            "model_run": model_run,
            "artifacts": artifacts,
        }
    except Exception as exc:
        tail = (getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or repr(exc))[-500:]
        task_total_seconds = _elapsed_seconds(task_started)
        model_run = {
            "index": index,
            "total": total,
            "stage": task["stage"],
            "model_key": task["model_key"],
            "model": model,
            "status": "failed",
            "started_at": task_started_at,
            "ended_at": _now_iso(),
            "duration_seconds": task_total_seconds,
            "error_tail": tail,
        }
        print(
            f"[worker] job={job_id} stage={task['stage']} model={model} failed tail={tail!r}",
            flush=True,
        )
        return {
            "status": "failed",
            "group": task["group"],
            "model": model,
            "model_run": model_run,
            "artifacts": {},
            "missing_feature": f"{model}:failed",
            "error_tail": tail,
        }
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def _materialize_worker_input(status: dict[str, Any], timings: dict[str, Any]) -> Path:
    input_path = Path(str(status["input_path"]))
    if not input_path.exists():
        input_reference = status.get("input_object")
        if not isinstance(input_reference, dict):
            raise RuntimeError("worker_input_missing")
        materialize_started = time.perf_counter()
        materialize_object(input_reference, input_path)
        timings["input_materialize_seconds"] = _elapsed_seconds(materialize_started)
        timings["input_bytes"] = input_path.stat().st_size
    timings["input_duration_seconds"] = _audio_duration_seconds(input_path)
    return input_path


def _run_job(job_id: str) -> None:
    job_started = time.perf_counter()
    status = _load_status(job_id)
    input_path = Path(str(status["input_path"]))
    profile = str(status["profile"])
    tasks = _tasks_for_profile(profile)
    quarantined_models = _quarantined_models_for_profile(profile)
    models_used: list[str] = []
    missing_features: list[str] = []
    model_runs: list[dict[str, Any]] = []
    timings = _status_timings(status)
    timings.update(
        {
            "worker_started_at": _now_iso(),
            "worker_model_plan_count": len(tasks),
            "model_runs": model_runs,
            "gpu_type": GPU_TYPE,
        }
    )
    print(f"[worker] job={job_id} profile={profile} tasks={len(tasks)} start", flush=True)

    try:
        input_path = _materialize_worker_input(status, timings)

        for index, task in enumerate(tasks, start=1):
            model = task["model"]
            models_used.append(model)
            task_started_at = _now_iso()
            timings.update(
                {
                    "active_stage": task["stage"],
                    "active_model": model,
                    "active_model_key": task["model_key"],
                    "active_model_started_at": task_started_at,
                    "worker_elapsed_seconds": _elapsed_seconds(job_started),
                }
            )
            _update_status(
                job_id,
                status="running",
                stage=task["stage"],
                current_model=model,
                progress={"completed": index - 1, "total": len(tasks)},
                model_plan=[task["model_key"] for task in tasks],
                quarantined_models=quarantined_models,
                models_used=models_used,
                timings=timings,
            )
            result = _execute_model_task(
                job_id,
                input_path,
                task,
                index=index,
                total=len(tasks),
            )
            model_run = result["model_run"]
            model_runs.append(model_run)
            task_total_seconds = float(model_run["duration_seconds"])
            if result["status"] != "completed":
                missing_features.append(str(result["missing_feature"]))
                timings.update(
                    {
                        "model_runs": model_runs,
                        "completed_model_count": index,
                        "last_model_duration_seconds": task_total_seconds,
                        "worker_elapsed_seconds": _elapsed_seconds(job_started),
                    }
                )
                _update_status(
                    job_id,
                    status="running",
                    stage=f"{task['stage']}_failed",
                    current_model=model,
                    missing_features=missing_features,
                    error_tail=result.get("error_tail"),
                    timings=timings,
                )
                continue

            timings.update(
                {
                    "model_runs": model_runs,
                    "completed_model_count": index,
                    "last_model_duration_seconds": task_total_seconds,
                    "worker_elapsed_seconds": _elapsed_seconds(job_started),
                }
            )
            updated = _update_status(
                job_id,
                status="running",
                stage=task["stage"],
                current_model=model,
                progress={"completed": index, "total": len(tasks)},
                model_plan=[task["model_key"] for task in tasks],
                quarantined_models=quarantined_models,
                models_used=models_used,
                missing_features=missing_features,
                timings=timings,
            )
            updated = _merge_artifacts(
                updated,
                str(result["group"]),
                result["artifacts"],
                source_model=str(result["model"]),
            )
            _write_status(job_id, updated)

        current_status = _load_status(job_id)
        if profile == "quality_gpu_experimental":
            current_status = _finalize_quality_contract(job_id, current_status)
            missing_features = list(current_status.get("missing_features") or [])

        object_publish_started = time.perf_counter()
        object_publish = _publish_worker_objects(job_id, current_status)
        object_publish_seconds = _elapsed_seconds(object_publish_started)
        timings.update(
            {
                "active_stage": None,
                "active_model": None,
                "active_model_key": None,
                "worker_completed_at": _now_iso(),
                "worker_total_seconds": _elapsed_seconds(job_started),
                "worker_bundle_deferred": True,
                "worker_bundle_seconds": 0.0,
                "object_publish_seconds": object_publish_seconds,
                "model_runs": model_runs,
            }
        )
        print(f"[worker] job={job_id} completed missing={len(missing_features)} bundle=deferred", flush=True)
        _update_status(
            job_id,
            status="completed",
            stage="done",
            current_model=None,
            progress={"completed": len(tasks), "total": len(tasks)},
            model_plan=[task["model_key"] for task in tasks],
            quarantined_models=quarantined_models,
            models_used=models_used,
            missing_features=missing_features,
            stem_contract=current_status.get("stem_contract", {}),
            rejected_candidates=current_status.get("rejected_candidates", {}),
            **object_publish,
            timings=timings,
        )
    except Exception as exc:
        timings = _status_timings(_load_status(job_id))
        timings.update(
            {
                "worker_failed_at": _now_iso(),
                "worker_total_seconds": _elapsed_seconds(job_started),
            }
        )
        print(f"[worker] job={job_id} fatal={exc!r}", flush=True)
        _update_status(job_id, status="error", stage="failed", error=str(exc), timings=timings)


def _run_parallel_branch(
    job_id: str,
    *,
    input_path: Path,
    role: str,
    model_key: str,
    gpu_type: str,
) -> dict[str, Any]:
    if not input_path.exists():
        raise RuntimeError("parallel_worker_input_not_materialized")
    task = dict(LOCAL_MODEL_REGISTRY[model_key])
    task["model_key"] = model_key
    result = _execute_model_task(
        job_id,
        input_path,
        task,
        index=1,
        total=1,
        run_namespace=f"parallel_{role}_{model_key}",
    )
    result.update(
        {
            "role": role,
            "model_key": model_key,
            "gpu_type": gpu_type,
            "gpu_seconds": float(result["model_run"]["duration_seconds"]),
        }
    )
    result["model_run"]["gpu_type"] = gpu_type
    result["model_run"]["parallel_role"] = role
    return result


def _execute_parallel_branch_container(
    request: dict[str, Any],
    *,
    role: str,
    model_key: str,
    gpu_type: str,
    shared_volume: bool = False,
) -> dict[str, Any]:
    branch_started = time.perf_counter()
    branch_started_epoch = time.time()
    job_id = str(request.get("job_id") or "")
    input_reference = request.get("input_object")
    if not JOB_ID_RE.match(job_id) or (
        not shared_volume and not isinstance(input_reference, dict)
    ):
        raise RuntimeError("parallel_branch_requires_scoped_object_input")
    input_name = Path(str(request.get("input_name") or "input.wav")).name
    branch_root = _job_root(job_id)
    input_path = branch_root / "input" / input_name
    try:
        materialize_started = time.perf_counter()
        if shared_volume:
            if not input_path.is_file():
                raise RuntimeError("parallel_shared_input_missing")
        else:
            materialize_object(input_reference, input_path)
        object_input_seconds = _elapsed_seconds(materialize_started)
        input_duration_seconds = _audio_duration_seconds(input_path)
        result = _run_parallel_branch(
            job_id,
            input_path=input_path,
            role=role,
            model_key=model_key,
            gpu_type=gpu_type,
        )
        publish_started = time.perf_counter()
        if shared_volume:
            result["branch_transport"] = "modal_volume"
        else:
            result["branch_object_artifacts"] = _publish_parallel_branch_objects(
                job_id,
                role,
                result,
            )
            result["artifacts"] = {}
        object_publish_seconds = _elapsed_seconds(publish_started)
        branch_total_seconds = _elapsed_seconds(branch_started)
        result.update(
            {
                "gpu_seconds": branch_total_seconds,
                "branch_started_epoch_seconds": branch_started_epoch,
                "branch_total_seconds": branch_total_seconds,
                "object_input_seconds": object_input_seconds,
                "input_duration_seconds": input_duration_seconds,
                "object_publish_seconds": object_publish_seconds,
                "volume_reload_seconds": 0.0,
                "volume_commit_seconds": 0.0,
            }
        )
        result["model_run"].update(
            {
                "gpu_seconds": branch_total_seconds,
                "branch_total_seconds": branch_total_seconds,
                "object_input_seconds": object_input_seconds,
                "input_duration_seconds": input_duration_seconds,
                "object_publish_seconds": object_publish_seconds,
                "volume_reload_seconds": 0.0,
                "volume_commit_seconds": 0.0,
            }
        )
        return result
    finally:
        if not shared_volume:
            shutil.rmtree(branch_root, ignore_errors=True)


def _publish_parallel_branch_objects(
    job_id: str,
    role: str,
    result: dict[str, Any],
) -> dict[str, dict[str, object]]:
    store = object_store_from_config()
    if store is None:
        raise RuntimeError("parallel_branch_object_storage_required")
    references: dict[str, dict[str, object]] = {}
    for artifact_name, artifact_url in dict(result.get("artifacts") or {}).items():
        source = _artifact_local_path(job_id, str(artifact_url))
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        key = store.artifact_key(job_id, f"branch_{role}", source.name)
        references[str(artifact_name)] = store.upload(source, key, content_type).as_dict()
    return references


def _materialize_parallel_branch_objects(job_id: str, result: dict[str, Any]) -> None:
    references = result.get("branch_object_artifacts")
    if not isinstance(references, dict):
        raise RuntimeError("parallel_branch_outputs_missing")
    group = str(result["group"])
    artifacts: dict[str, str] = {}
    for artifact_name, reference in references.items():
        if not isinstance(reference, dict):
            continue
        filename = Path(str(reference.get("key") or f"{artifact_name}.wav")).name
        target = _job_root(job_id) / group / filename
        materialize_object(reference, target)
        artifacts[str(artifact_name)] = f"/artifacts/{job_id}/{group}/{filename}"
    result["artifacts"] = artifacts


def _validate_parallel_branch_volume_artifacts(job_id: str, result: dict[str, Any]) -> None:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        if result.get("status") == "completed":
            raise RuntimeError("parallel_branch_outputs_missing")
        return
    for artifact_url in artifacts.values():
        if not isinstance(artifact_url, str) or not _artifact_local_path(job_id, artifact_url).is_file():
            raise RuntimeError("parallel_branch_volume_artifact_missing")


def _delete_parallel_branch_objects(branch_results: list[dict[str, Any]]) -> int:
    store = object_store_from_config()
    if store is None:
        return 0
    deleted = 0
    for result in branch_results:
        references = result.get("branch_object_artifacts")
        if not isinstance(references, dict):
            continue
        for reference in references.values():
            if isinstance(reference, dict):
                store.delete(reference)
                deleted += 1
    return deleted


def _parallel_failure_reason(
    branch_results: list[dict[str, Any]],
    stem_contract: dict[str, Any],
) -> str | None:
    failed_roles = sorted(
        str(result.get("role") or "unknown")
        for result in branch_results
        if result.get("status") != "completed"
    )
    if failed_roles:
        return f"parallel_branches_failed:{','.join(failed_roles)}"
    if stem_contract.get("status") != "complete":
        missing = stem_contract.get("missing_stems")
        missing_names = ",".join(str(name) for name in missing) if isinstance(missing, list) else "unknown"
        return f"product_11_contract_incomplete:{missing_names}"
    return None


def _parallel_branch_failure(branch: dict[str, str], exc: Exception) -> dict[str, Any]:
    error_tail = repr(exc)[-500:]
    model_key = branch["model_key"]
    model = str(LOCAL_MODEL_REGISTRY[model_key]["model"])
    return {
        "status": "failed",
        "group": LOCAL_MODEL_REGISTRY[model_key]["group"],
        "model": model,
        "model_key": model_key,
        "role": branch["role"],
        "gpu_type": branch["gpu_type"],
        "gpu_seconds": 0.0,
        "artifacts": {},
        "missing_feature": f"{model}:failed",
        "error_tail": error_tail,
        "model_run": {
            "stage": LOCAL_MODEL_REGISTRY[model_key]["stage"],
            "model_key": model_key,
            "model": model,
            "status": "failed",
            "gpu_type": branch["gpu_type"],
            "parallel_role": branch["role"],
            "duration_seconds": 0.0,
            "error_tail": error_tail,
        },
    }


def _product_specialist_input_object(
    job_id: str,
    status: dict[str, Any],
) -> dict[str, object]:
    existing = status.get("input_object")
    if isinstance(existing, dict):
        return existing
    store = object_store_from_config()
    if store is None:
        raise RuntimeError("product_specialist_object_storage_required")
    input_path = Path(str(status["input_path"]))
    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
    key = store.artifact_key(job_id, "specialist_input", input_path.name)
    reference = store.upload(input_path, key, content_type).as_dict()
    _update_status(job_id, input_object=reference)
    return reference


def _spawn_product_specialist_branch(
    job_id: str,
    input_object: dict[str, object],
):
    modal_module = globals().get("modal")
    if modal_module is None:
        raise RuntimeError("modal_runtime_unavailable")
    remote_cls = modal_module.Cls.from_name(
        OPEN_SPECIALIST_APP_NAME,
        "OpenSpecialist",
    )
    return remote_cls().separate.spawn(
        {
            "job_id": job_id,
            "input_object": input_object,
            "targets": list(PRODUCT_SPECIALIST_OUTPUTS),
        }
    )


def _normalize_product_specialist_result(
    report: dict[str, Any],
) -> dict[str, Any]:
    outputs = report.get("outputs")
    outputs = outputs if isinstance(outputs, dict) else {}
    references: dict[str, dict[str, object]] = {}
    source_models: list[str] = []
    inference_seconds = 0.0
    input_duration_seconds: float | None = None
    for source_name, target_name in PRODUCT_SPECIALIST_OUTPUTS.items():
        payload = outputs.get(source_name)
        if not isinstance(payload, dict) or not isinstance(payload.get("object"), dict):
            continue
        references[target_name] = dict(payload["object"])
        source_models.append(str(payload.get("model_id") or source_name))
        inference_seconds += float(payload.get("inference_seconds") or 0.0)
        duration = payload.get("duration_seconds")
        if input_duration_seconds is None and isinstance(duration, (int, float)):
            input_duration_seconds = float(duration)

    missing = sorted(set(PRODUCT_SPECIALIST_OUTPUTS.values()) - set(references))
    completed = not missing and report.get("status") == "completed"
    model_name = "+".join(source_models) or "open_specialist_product_pack"
    model_run = {
        "stage": "product_specialist_stems",
        "model_key": "open_specialist_product_pack",
        "model": model_name,
        "status": "completed" if completed else "failed",
        "gpu_type": OPEN_SPECIALIST_GPU_TYPE,
        "parallel_role": "specialists",
        "duration_seconds": round(inference_seconds, 3),
        "remote_report_status": str(report.get("status") or "unknown"),
        "remote_failures": dict(report.get("failures") or {}),
    }
    return {
        "status": "completed" if completed else "failed",
        "group": "specialist_substems",
        "model": model_name,
        "model_key": "open_specialist_product_pack",
        "role": "specialists",
        "gpu_type": OPEN_SPECIALIST_GPU_TYPE,
        "gpu_seconds": round(inference_seconds, 3),
        "artifacts": {},
        "branch_object_artifacts": references,
        "missing_feature": (
            "product_specialists_missing:" + ",".join(missing)
            if missing
            else "product_specialists_failed"
        ),
        "input_duration_seconds": input_duration_seconds,
        "model_run": model_run,
    }


def _finalize_parallel_job(
    job_id: str,
    branch_results: list[dict[str, Any]],
    *,
    job_started: float,
    parallel_wait_seconds: float,
) -> None:
    status = _load_status(job_id)
    timings = _status_timings(status)
    missing_features = list(status.get("missing_features") or [])
    model_runs: list[dict[str, Any]] = []
    models_used: list[str] = []
    gpu_allocations: list[dict[str, Any]] = []

    for result in branch_results:
        model = str(result["model"])
        models_used.append(model)
        model_runs.append(dict(result["model_run"]))
        gpu_allocations.append(
            {
                "role": str(result["role"]),
                "model_key": str(result["model_key"]),
                "gpu_type": str(result["gpu_type"]),
                "gpu_seconds": float(result.get("gpu_seconds") or 0.0),
            }
        )
        if result["status"] == "completed":
            status = _merge_artifacts(
                status,
                str(result["group"]),
                result["artifacts"],
                source_model=model,
            )
        else:
            missing_features.append(str(result["missing_feature"]))

    timings.update(
        {
            "execution_mode": "heterogeneous_parallel",
            "gpu_type": "heterogeneous",
            "gpu_allocations": gpu_allocations,
            "model_runs": model_runs,
            "parallel_wait_seconds": parallel_wait_seconds,
            "parallel_branch_sum_seconds": round(
                sum(float(allocation["gpu_seconds"]) for allocation in gpu_allocations), 3
            ),
            "input_duration_seconds": next(
                (
                    float(result["input_duration_seconds"])
                    for result in branch_results
                    if result.get("input_duration_seconds") is not None
                ),
                None,
            ),
        }
    )
    status.update(
        {
            "artifacts": status.get("artifacts", {}),
            "artifact_sources": status.get("artifact_sources", {}),
            "models_used": models_used,
            "missing_features": missing_features,
            "timings": timings,
        }
    )
    _write_status(job_id, status)

    contract_started = time.perf_counter()
    status = _finalize_quality_contract(job_id, status)
    timings["quality_contract_seconds"] = _elapsed_seconds(contract_started)
    missing_features = list(status.get("missing_features") or [])
    stem_contract = status.get("stem_contract")
    stem_contract = stem_contract if isinstance(stem_contract, dict) else {}
    failure_reason = _parallel_failure_reason(branch_results, stem_contract)

    if failure_reason is not None:
        timings.update(
            {
                "active_stage": None,
                "active_model": None,
                "active_model_key": None,
                "worker_failed_at": _now_iso(),
                "worker_total_seconds": _elapsed_seconds(job_started),
                "worker_bundle_deferred": True,
                "worker_bundle_seconds": 0.0,
            }
        )
        _update_status(
            job_id,
            status="error",
            stage="parallel_failed",
            error=failure_reason,
            current_model=None,
            progress={"completed": len(branch_results), "total": len(PARALLEL_BRANCHES)},
            model_plan=[branch["model_key"] for branch in PARALLEL_BRANCHES],
            quarantined_models=_quarantined_models_for_profile("quality_gpu_experimental"),
            models_used=models_used,
            missing_features=missing_features,
            stem_contract=stem_contract,
            rejected_candidates=status.get("rejected_candidates", {}),
            artifact_transport="local_worker",
            timings=timings,
        )
        return

    object_publish_started = time.perf_counter()
    object_publish = _publish_worker_objects(job_id, status)
    cleanup_started = time.perf_counter()
    deleted_branch_objects = 0
    if object_publish.get("artifact_transport") == "object_storage":
        deleted_branch_objects = _delete_parallel_branch_objects(branch_results)
    timings.update(
        {
            "active_stage": None,
            "active_model": None,
            "active_model_key": None,
            "worker_completed_at": _now_iso(),
            "worker_total_seconds": _elapsed_seconds(job_started),
            "worker_bundle_deferred": True,
            "worker_bundle_seconds": 0.0,
            "object_publish_seconds": _elapsed_seconds(object_publish_started),
            "branch_cleanup_seconds": _elapsed_seconds(cleanup_started),
            "deleted_branch_object_count": deleted_branch_objects,
        }
    )
    _update_status(
        job_id,
        status="completed",
        stage="done",
        current_model=None,
        progress={"completed": len(branch_results), "total": len(PARALLEL_BRANCHES)},
        model_plan=[branch["model_key"] for branch in PARALLEL_BRANCHES],
        quarantined_models=_quarantined_models_for_profile("quality_gpu_experimental"),
        models_used=models_used,
        missing_features=missing_features,
        stem_contract=stem_contract,
        rejected_candidates=status.get("rejected_candidates", {}),
        **object_publish,
        timings=timings,
    )


def _run_parallel_job(job_id: str) -> None:
    job_started = time.perf_counter()
    try:
        status = _load_status(job_id)
        if status.get("profile") != "quality_gpu_experimental":
            raise RuntimeError("parallel_execution_requires_quality_gpu_experimental")
        timings = _status_timings(status)
        max_worker_seconds_raw = status.get("max_worker_seconds")
        max_worker_seconds = (
            float(max_worker_seconds_raw) if max_worker_seconds_raw is not None else None
        )
        timings.update(
            {
                "worker_started_at": _now_iso(),
                "worker_model_plan_count": len(PARALLEL_BRANCHES),
                "execution_mode": "heterogeneous_parallel",
                "gpu_type": "heterogeneous",
                "worker_budget_seconds": max_worker_seconds,
            }
        )
        _materialize_worker_input(status, timings)
        specialist_input_object = _product_specialist_input_object(job_id, status)
        branch_request = {
            "job_id": job_id,
            "input_name": status.get("input_name"),
            "branch_transport": "modal_volume",
        }
        _update_status(
            job_id,
            status="running",
            stage="parallel_dispatch",
            progress={"completed": 0, "total": len(PARALLEL_BRANCHES)},
            model_plan=[branch["model_key"] for branch in PARALLEL_BRANCHES],
            timings=timings,
        )
        _commit_jobs_volume()

        runners = {
            "vocals": globals().get("process_vocal_branch"),
            "broad": globals().get("process_broad_branch"),
            "drums": globals().get("process_drum_branch"),
        }
        calls: list[tuple[dict[str, str], object, float]] = []
        branch_results: list[dict[str, Any]] = []
        parallel_started = time.perf_counter()
        for branch in PARALLEL_BRANCHES:
            if branch["role"] == "specialists":
                try:
                    dispatch_epoch = time.time()
                    calls.append(
                        (
                            branch,
                            _spawn_product_specialist_branch(
                                job_id,
                                specialist_input_object,
                            ),
                            dispatch_epoch,
                        )
                    )
                except Exception as exc:
                    branch_results.append(_parallel_branch_failure(branch, exc))
                continue
            runner = runners.get(branch["role"])
            if runner is None or not hasattr(runner, "spawn"):
                branch_results.append(
                    _parallel_branch_failure(branch, RuntimeError("parallel_branch_runner_unavailable"))
                )
                continue
            try:
                dispatch_epoch = time.time()
                calls.append((branch, runner.spawn(branch_request), dispatch_epoch))
            except Exception as exc:
                branch_results.append(_parallel_branch_failure(branch, exc))

        budget_exceeded = False
        for branch, call, dispatch_epoch in calls:
            try:
                remaining_seconds = (
                    max_worker_seconds - (time.perf_counter() - job_started)
                    if max_worker_seconds is not None
                    else None
                )
                if remaining_seconds is not None and remaining_seconds <= 0:
                    budget_exceeded = True
                    break
                raw_result = call.get(timeout=remaining_seconds)
                result = (
                    _normalize_product_specialist_result(raw_result)
                    if branch["role"] == "specialists"
                    else raw_result
                )
                materialize_started = time.perf_counter()
                if result.get("branch_object_artifacts"):
                    _materialize_parallel_branch_objects(job_id, result)
                else:
                    _reload_jobs_volume()
                    _validate_parallel_branch_volume_artifacts(job_id, result)
                result["orchestrator_materialize_seconds"] = _elapsed_seconds(materialize_started)
                result["model_run"]["orchestrator_materialize_seconds"] = result[
                    "orchestrator_materialize_seconds"
                ]
                branch_started_epoch = result.get("branch_started_epoch_seconds")
                if isinstance(branch_started_epoch, (int, float)):
                    result["dispatch_to_branch_start_seconds"] = round(
                        max(0.0, float(branch_started_epoch) - dispatch_epoch), 3
                    )
                    result["model_run"]["dispatch_to_branch_start_seconds"] = result[
                        "dispatch_to_branch_start_seconds"
                    ]
                branch_results.append(result)
            except Exception as exc:
                if (
                    max_worker_seconds is not None
                    and time.perf_counter() - job_started >= max_worker_seconds
                ):
                    budget_exceeded = True
                    break
                branch_results.append(_parallel_branch_failure(branch, exc))
        if budget_exceeded:
            cancelled_count = 0
            for _, call, _ in calls:
                try:
                    call.cancel(terminate_containers=True)
                    cancelled_count += 1
                except Exception:
                    continue
            timings.update(
                {
                    "worker_failed_at": _now_iso(),
                    "worker_total_seconds": _elapsed_seconds(job_started),
                    "budget_exceeded": True,
                    "cancelled_branch_count": cancelled_count,
                }
            )
            _update_status(
                job_id,
                status="error",
                stage="budget_exceeded",
                error="worker_budget_exceeded",
                timings=timings,
            )
            return
        parallel_wait_seconds = _elapsed_seconds(parallel_started)
        _reload_jobs_volume()
        _finalize_parallel_job(
            job_id,
            branch_results,
            job_started=job_started,
            parallel_wait_seconds=parallel_wait_seconds,
        )
    except Exception as exc:
        timings = _status_timings(_load_status(job_id))
        timings.update(
            {
                "worker_failed_at": _now_iso(),
                "worker_total_seconds": _elapsed_seconds(job_started),
                "execution_mode": "heterogeneous_parallel",
            }
        )
        print(f"[worker] parallel job={job_id} fatal={exc!r}", flush=True)
        _update_status(job_id, status="error", stage="failed", error=str(exc), timings=timings)


def _mounted_jobs_volume() -> object | None:
    modal_module = globals().get("modal")
    if modal_module is not None and modal_module.is_local():
        return None
    return globals().get("jobs_volume")


def _commit_jobs_volume() -> None:
    volume = _mounted_jobs_volume()
    if volume is not None:
        volume.commit()


async def _commit_jobs_volume_async() -> None:
    volume = _mounted_jobs_volume()
    if volume is not None:
        await volume.commit.aio()


def _reload_jobs_volume() -> None:
    volume = _mounted_jobs_volume()
    if volume is not None:
        volume.reload()


def _dispatch_job(job_id: str) -> dict[str, str]:
    status = _load_status(job_id)
    use_parallel = status.get("profile") == QUALITY_PARALLEL_PROFILE
    modal_runner = globals().get("process_parallel_job" if use_parallel else "process_gpu_job")
    if modal_runner is not None and hasattr(modal_runner, "spawn"):
        call = modal_runner.spawn(job_id)
        return {
            "execution_backend": "modal_spawn",
            "execution_call_id": str(getattr(call, "object_id", "")),
        }

    with LOCK:
        FUTURES[job_id] = EXECUTOR.submit(_run_job, job_id)
    return {"execution_backend": "local_thread", "execution_call_id": ""}


async def _dispatch_job_async(job_id: str) -> dict[str, str]:
    status = _load_status(job_id)
    use_parallel = status.get("profile") == QUALITY_PARALLEL_PROFILE
    modal_runner = globals().get("process_parallel_job" if use_parallel else "process_gpu_job")
    if modal_runner is not None and hasattr(modal_runner, "spawn"):
        spawn = modal_runner.spawn
        call = await spawn.aio(job_id) if hasattr(spawn, "aio") else spawn(job_id)
        return {
            "execution_backend": "modal_spawn",
            "execution_call_id": str(getattr(call, "object_id", "")),
        }

    with LOCK:
        FUTURES[job_id] = EXECUTOR.submit(_run_job, job_id)
    return {"execution_backend": "local_thread", "execution_call_id": ""}


@api_app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "configured_execution_mode": EXECUTION_MODE,
        "quality_topology": "heterogeneous_parallel",
        "quality_profile": QUALITY_PARALLEL_PROFILE,
        "parallel_branches": [
            {
                "role": branch["role"],
                "model_key": branch["model_key"],
                "gpu_type": branch["gpu_type"],
            }
            for branch in PARALLEL_BRANCHES
        ],
        "branch_keep_warm": BRANCH_KEEP_WARM,
    }


@api_app.post("/separate", status_code=http_status.HTTP_202_ACCEPTED)
async def separate(
    file: Annotated[UploadFile, File()],
    profile: str = Form("quality_gpu_experimental"),
    local_job_id: str = Form(""),
    max_worker_seconds: float | None = Form(None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    request_started = time.perf_counter()
    request_received_at = _now_iso()
    _authorize(authorization)
    job_id = local_job_id if local_job_id and JOB_ID_RE.match(local_job_id) else uuid.uuid4().hex
    job_root = _ensure_dir(_job_root(job_id))
    input_dir = _ensure_dir(job_root / "input")
    safe_name = Path(file.filename or "input.wav").name
    input_path = input_dir / safe_name
    payload = {
        "job_id": job_id,
        "profile": profile,
        "status": "queued",
        "stage": "receiving_input",
        "input_name": safe_name,
        "input_path": str(input_path),
        "max_worker_seconds": max_worker_seconds,
        "artifacts": {},
        "artifact_sources": {},
        "models_used": [],
        "missing_features": [],
        "quarantined_models": _quarantined_models_for_profile(profile),
        "timings": {"request_received_at": request_received_at},
    }
    replay = _reserve_job(job_id, payload)
    if replay is not None:
        return replay
    upload_save_started = time.perf_counter()
    input_bytes = 0
    with input_path.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            input_bytes += len(chunk)
            if input_bytes > MAX_UPLOAD_BYTES:
                handle.close()
                input_path.unlink(missing_ok=True)
                _update_status(
                    job_id,
                    status="error",
                    stage="input_rejected",
                    error="upload_limit_exceeded",
                )
                raise HTTPException(status_code=413, detail="Uploaded audio exceeds the worker limit")
            handle.write(chunk)
    upload_save_seconds = _elapsed_seconds(upload_save_started)
    payload = _update_status(
        job_id,
        stage="queued",
        timings={
            "request_received_at": request_received_at,
            "input_upload_save_seconds": upload_save_seconds,
            "input_bytes": input_bytes,
        },
    )
    print(f"[worker] received job={job_id} profile={profile} input={safe_name}", flush=True)
    await _commit_jobs_volume_async()
    dispatch = await _dispatch_job_async(job_id)
    timings = _status_timings(payload)
    timings["request_total_seconds"] = _elapsed_seconds(request_started)
    _update_status(job_id, timings=timings, **dispatch)
    await _commit_jobs_volume_async()
    return _load_status(job_id)


@api_app.post("/separate-reference", status_code=http_status.HTTP_202_ACCEPTED)
async def separate_reference(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    request_started = time.perf_counter()
    _authorize(authorization)
    local_job_id = str(payload.get("local_job_id") or "")
    job_id = local_job_id if local_job_id and JOB_ID_RE.match(local_job_id) else uuid.uuid4().hex
    object_reference = payload.get("object")
    if not isinstance(object_reference, dict):
        raise HTTPException(status_code=400, detail="A valid object reference is required")
    input_name = Path(str(payload.get("input_name") or "input.wav")).name
    if Path(input_name).suffix.lower() not in AUDIO_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported audio filename")

    job_root = _ensure_dir(_job_root(job_id))
    input_path = job_root / "input" / input_name
    object_size = object_reference.get("size_bytes")
    if object_size is not None and int(object_size) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Referenced audio exceeds the worker limit")
    max_worker_seconds_raw = payload.get("max_worker_seconds")
    max_worker_seconds: float | None = None
    if max_worker_seconds_raw is not None:
        try:
            max_worker_seconds = float(max_worker_seconds_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid worker budget") from exc
        if max_worker_seconds <= 0:
            raise HTTPException(status_code=400, detail="Worker budget must be positive")
    status_payload = {
        "job_id": job_id,
        "profile": str(payload.get("profile") or "quality_gpu_experimental"),
        "status": "queued",
        "stage": "queued",
        "input_name": input_name,
        "input_path": str(input_path),
        "input_object": object_reference,
        "max_worker_seconds": max_worker_seconds,
        "artifacts": {},
        "artifact_sources": {},
        "models_used": [],
        "missing_features": [],
        "quarantined_models": _quarantined_models_for_profile(
            str(payload.get("profile") or "quality_gpu_experimental")
        ),
        "timings": {
            "request_received_at": _now_iso(),
            "input_reference_bytes": int(object_size) if object_size is not None else None,
            "input_transport": "object_reference",
        },
    }
    replay = _reserve_job(job_id, status_payload)
    if replay is not None:
        return replay
    await _commit_jobs_volume_async()
    dispatch = await _dispatch_job_async(job_id)
    timings = _status_timings(status_payload)
    timings["request_total_seconds"] = _elapsed_seconds(request_started)
    _update_status(job_id, timings=timings, **dispatch)
    await _commit_jobs_volume_async()
    return _load_status(job_id)


@api_app.get("/jobs/{job_id}")
def job_status(job_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    _reload_jobs_volume()
    return _load_status(job_id)


@api_app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    _reload_jobs_volume()
    status = _load_status(job_id)
    if status.get("status") in {"completed", "error", "failed", "cancelled"}:
        return status

    call_id = str(status.get("execution_call_id") or "")
    if call_id:
        try:
            function_call = modal.FunctionCall.from_id(call_id)
            cancel = function_call.cancel
            if hasattr(cancel, "aio"):
                await cancel.aio(terminate_containers=True)
            else:
                cancel(terminate_containers=True)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Modal cancellation failed") from exc
    else:
        with LOCK:
            future = FUTURES.get(job_id)
            if future is not None:
                future.cancel()

    updated = _update_status(
        job_id,
        status="cancelled",
        stage="cancelled",
        cancel_requested=True,
        cancelled_at=_now_iso(),
    )
    await _commit_jobs_volume_async()
    return updated


@api_app.get("/artifacts/{job_id}/{artifact_path:path}")
def artifact(job_id: str, artifact_path: str, authorization: str | None = Header(default=None)) -> FileResponse:
    _authorize(authorization)
    _reload_jobs_volume()
    root = _job_root(job_id).resolve()
    target = (root / artifact_path).resolve()
    if not str(target).startswith(str(root)) or not target.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(target)


try:
    import modal
except Exception:  # pragma: no cover - modal is optional for local dev
    modal_app = None
    app = api_app
else:
    app = modal.App(os.getenv("MODAL_APP_NAME", "stemsplitter-audio-separator-gpu"))
    modal_app = app
    model_volume = modal.Volume.from_name("stemsplitter-audio-separator-models", create_if_missing=True)
    jobs_volume = modal.Volume.from_name("stemsplitter-gpu-worker-jobs", create_if_missing=True)
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg")
        .pip_install(
            "fastapi[standard]",
            "python-multipart",
            "audio-separator==0.44.3",
            "onnxruntime",
            "boto3>=1.35.0",
        )
        .env(
            {
                "STEMSPLITTER_GPU_TYPE": GPU_TYPE,
                "GPU_WORKER_EXECUTION_MODE": EXECUTION_MODE,
                "MODAL_VOCAL_GPU": VOCAL_GPU_TYPE,
                "MODAL_BROAD_GPU": BROAD_GPU_TYPE,
                "MODAL_DRUM_GPU": DRUM_GPU_TYPE,
                "OPEN_SPECIALIST_MODAL_APP_NAME": OPEN_SPECIALIST_APP_NAME,
                "OPEN_SPECIALIST_MODAL_GPU": OPEN_SPECIALIST_GPU_TYPE,
                "GPU_WORKER_BRANCH_CPU": str(BRANCH_CPU),
                "GPU_WORKER_OBJECT_PUBLISH_WORKERS": str(OBJECT_PUBLISH_WORKERS),
                "GPU_WORKER_ENABLE_PROFILING": "1" if ENABLE_RESOURCE_PROFILING else "0",
            }
        )
        .add_local_python_source("splitter")
        .add_local_file(
            "models/stem_qualification.yaml",
            "/root/models/stem_qualification.yaml",
        )
        .add_local_file(
            "models/product_12_stem_contract.yaml",
            "/root/models/product_12_stem_contract.yaml",
        )
    )

    # Modal re-imports this module in the container, so dependency shape cannot
    # depend on environment variables that only exist during local deployment.
    object_storage_secrets = [
        modal.Secret.from_name(os.getenv("OBJECT_STORAGE_MODAL_SECRET", "stemsplitter-b2"))
    ]

    @app.function(
        image=image,
        gpu=VOCAL_GPU_TYPE,
        cpu=BRANCH_CPU,
        timeout=int(os.getenv("GPU_WORKER_MODAL_TIMEOUT", "3600")),
        min_containers=BRANCH_KEEP_WARM,
        max_containers=int(os.getenv("GPU_WORKER_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("GPU_WORKER_SCALEDOWN_WINDOW", "600")),
        volumes={
            "/tmp/stemsplitter-gpu-worker/models": model_volume,
            "/tmp/stemsplitter-gpu-worker/jobs": jobs_volume,
        },
        secrets=object_storage_secrets,
    )
    def process_vocal_branch(request: dict[str, Any]) -> dict[str, Any]:
        jobs_volume.reload()
        try:
            return _execute_parallel_branch_container(
                request,
                role="vocals",
                model_key="melband_kim_vocals",
                gpu_type=VOCAL_GPU_TYPE,
                shared_volume=True,
            )
        finally:
            jobs_volume.commit()

    @app.function(
        image=image,
        gpu=BROAD_GPU_TYPE,
        cpu=BRANCH_CPU,
        timeout=int(os.getenv("GPU_WORKER_MODAL_TIMEOUT", "3600")),
        min_containers=BRANCH_KEEP_WARM,
        max_containers=int(os.getenv("GPU_WORKER_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("GPU_WORKER_SCALEDOWN_WINDOW", "600")),
        volumes={
            "/tmp/stemsplitter-gpu-worker/models": model_volume,
            "/tmp/stemsplitter-gpu-worker/jobs": jobs_volume,
        },
        secrets=object_storage_secrets,
    )
    def process_broad_branch(request: dict[str, Any]) -> dict[str, Any]:
        jobs_volume.reload()
        try:
            return _execute_parallel_branch_container(
                request,
                role="broad",
                model_key="bs_roformer_sw",
                gpu_type=BROAD_GPU_TYPE,
                shared_volume=True,
            )
        finally:
            jobs_volume.commit()

    @app.function(
        image=image,
        gpu=DRUM_GPU_TYPE,
        cpu=BRANCH_CPU,
        timeout=int(os.getenv("GPU_WORKER_MODAL_TIMEOUT", "3600")),
        min_containers=BRANCH_KEEP_WARM,
        max_containers=int(os.getenv("GPU_WORKER_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("GPU_WORKER_SCALEDOWN_WINDOW", "600")),
        volumes={
            "/tmp/stemsplitter-gpu-worker/models": model_volume,
            "/tmp/stemsplitter-gpu-worker/jobs": jobs_volume,
        },
        secrets=object_storage_secrets,
    )
    def process_drum_branch(request: dict[str, Any]) -> dict[str, Any]:
        jobs_volume.reload()
        try:
            return _execute_parallel_branch_container(
                request,
                role="drums",
                model_key="mdx23c_drumsep_jarredou_aufr33",  # gitleaks:allow
                gpu_type=DRUM_GPU_TYPE,
                shared_volume=True,
            )
        finally:
            jobs_volume.commit()

    @app.function(
        image=image,
        gpu=os.getenv("MODAL_GPU", "T4"),
        timeout=int(os.getenv("GPU_WORKER_MODAL_TIMEOUT", "3600")),
        max_containers=int(os.getenv("GPU_WORKER_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("GPU_WORKER_SCALEDOWN_WINDOW", "600")),
        volumes={
            "/tmp/stemsplitter-gpu-worker/models": model_volume,
            "/tmp/stemsplitter-gpu-worker/jobs": jobs_volume,
        },
        secrets=object_storage_secrets,
    )
    def process_gpu_job(job_id: str) -> None:
        jobs_volume.reload()
        try:
            _run_job(job_id)
        finally:
            jobs_volume.commit()

    @app.function(
        image=image,
        timeout=int(os.getenv("GPU_WORKER_MODAL_TIMEOUT", "3600")),
        max_containers=int(os.getenv("GPU_WORKER_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("GPU_WORKER_SCALEDOWN_WINDOW", "600")),
        volumes={"/tmp/stemsplitter-gpu-worker/jobs": jobs_volume},
        secrets=object_storage_secrets,
    )
    def process_parallel_job(job_id: str) -> None:
        jobs_volume.reload()
        try:
            _run_parallel_job(job_id)
        finally:
            jobs_volume.commit()

    @app.function(
        image=image,
        timeout=int(os.getenv("GPU_WORKER_MODAL_TIMEOUT", "3600")),
        min_containers=int(os.getenv("GPU_WORKER_KEEP_WARM", "0")),
        max_containers=int(os.getenv("GPU_WORKER_API_MAX_CONTAINERS", "2")),
        scaledown_window=int(os.getenv("GPU_WORKER_SCALEDOWN_WINDOW", "600")),
        volumes={"/tmp/stemsplitter-gpu-worker/jobs": jobs_volume},
        secrets=object_storage_secrets,
    )
    @modal.asgi_app()
    def fastapi_app():
        return api_app

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from splitter import jobs
from splitter.config import (
    ALLOW_EVALUATION_PROFILES,
    ALLOW_MULTIPART_UPLOADS,
    ALLOWED_EXTENSIONS,
    APP_ENV,
    BASE_6_STEMS,
    DEFAULT_PROFILE,
    JOBS_DIR,
    OBJECT_STORAGE_CONFIG,
    PRODUCT_12_STEM_HIERARCHY,
    PRODUCT_12_STEMS,
    PROFILE_CAPABILITIES,
    PROFILE_CONFIG,
    QUALITY_8_EXCLUDED_STEMS,
    QUALITY_8_STEM_PROFILE,
    QUALITY_8_STEMS,
    SAM_SPECIALIST_STEMS,
)
from splitter.infrastructure.object_storage import object_store_from_config
from splitter.path_safety import resolve_job_root
from splitter.qualification import load_stem_qualification


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def job_root(job_id: str) -> Path:
    return resolve_job_root(JOBS_DIR, job_id)


def owned_job(job_id: str, owner_id: str) -> dict[str, Any] | None:
    try:
        status = jobs.get_job_status(job_id)
    except ValueError:
        return None
    recorded_owner = status.get("owner_id", "local-development") if status else None
    if status is None or recorded_owner != owner_id:
        return None
    return status


def requested_profile(value: object) -> str:
    profile = str(value or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    if profile not in PROFILE_CONFIG:
        raise ValueError("unsupported_profile")
    tier = str(PROFILE_CAPABILITIES.get(profile, {}).get("tier") or "internal")
    if APP_ENV == "production" and tier in {"legacy", "diagnostic", "internal"}:
        raise ValueError("profile_disabled_in_production")
    if (
        APP_ENV == "production"
        and tier in {"evaluation", "experimental"}
        and not ALLOW_EVALUATION_PROFILES
    ):
        raise ValueError("evaluation_profile_disabled")
    return profile


def artifact_payload(
    job_id: str,
    manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    manifest = manifest or jobs.get_manifest(job_id) or {}
    bundles = manifest.get("bundle_exports", {})
    main = manifest.get("published_main_stems", {})
    broad = manifest.get("published_broad_stems", {})
    derived = manifest.get("published_derived_stems", {})
    specialist = manifest.get("published_specialist_substems", {})
    tempo_locked = manifest.get("tempo_locked_exports", {})
    midi = manifest.get("midi_exports", {})
    analysis = manifest.get("analysis_exports", {})
    if not any((bundles, main, broad, derived, specialist, tempo_locked, midi, analysis)):
        return artifact_payload_from_dirs(job_id)

    def make_urls(payload: object) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        urls: dict[str, str] = {}
        for name, meta in payload.items():
            if isinstance(meta, dict) and isinstance(meta.get("storage_ref"), dict):
                store = object_store_from_config()
                if store is not None:
                    object_key = str(meta["storage_ref"].get("key") or "")
                    download_name = Path(object_key).name or str(name)
                    urls[str(name)] = store.signed_download_url(
                        meta["storage_ref"],
                        download_name,
                    )
                continue
            path = meta["path"] if isinstance(meta, dict) else meta
            rel = Path(str(path)).resolve().relative_to(job_root(job_id))
            urls[str(name)] = f"/artifacts/{job_id}/{rel.as_posix()}"
        return urls

    def bundle_urls(payload: object) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        urls: dict[str, str] = {}
        for name, path in payload.items():
            if isinstance(path, dict) and isinstance(path.get("storage_ref"), dict):
                store = object_store_from_config()
                if store is not None:
                    urls[str(name)] = store.signed_download_url(
                        path["storage_ref"],
                        f"{name}.zip",
                    )
                continue
            rel = Path(str(path)).resolve().relative_to(job_root(job_id))
            urls[str(name)] = f"/artifacts/{job_id}/{rel.as_posix()}"
        return urls

    return {
        "main_stems": make_urls(main),
        "broad_stems": make_urls(broad),
        "derived_stems": make_urls(derived),
        "specialist_substems": make_urls(specialist),
        "tempo_locked_wavs": make_urls(tempo_locked),
        "midi": make_urls(midi),
        "analysis": make_urls(analysis),
        "bundles": bundle_urls(bundles),
    }


def artifact_payload_from_dirs(job_id: str) -> dict[str, object]:
    root = job_root(job_id)

    def scan(relative_dir: str, suffixes: set[str]) -> dict[str, str]:
        directory = root / relative_dir
        if not directory.exists():
            return {}
        return {
            path.stem: f"/artifacts/{job_id}/{relative_dir}/{path.name}"
            for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.lower() in suffixes
        }

    audio = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}
    return {
        "main_stems": {},
        "broad_stems": scan("broad_stems", audio),
        "derived_stems": scan("derived_stems", audio),
        "specialist_substems": scan("specialist_substems", audio),
        "tempo_locked_wavs": scan("tempo_locked_wavs", audio),
        "midi": scan("midi", {".mid", ".midi"}),
        "analysis": scan("analysis", {".json"}),
        "bundles": scan("package", {".zip"}),
    }


def capabilities_payload() -> dict[str, object]:
    qualification = load_stem_qualification(QUALITY_8_STEMS)
    profiles = {}
    for profile_name, profile_config in PROFILE_CONFIG.items():
        metadata = PROFILE_CAPABILITIES.get(profile_name, {})
        profiles[profile_name] = {
            "label": metadata.get("label", profile_name),
            "public": metadata.get("public") is True,
            "tier": metadata.get("tier", "internal"),
            "engine": metadata.get("engine", "unknown"),
            "contract": metadata.get("contract"),
            "target_stems": list(metadata.get("target_stems", [])),
            "fallback_policy": metadata.get("fallback_policy", "unspecified"),
            "warnings": list(metadata.get("warnings", [])),
            "uses_gpu_worker": bool(profile_config.get("use_gpu_worker")),
            "uses_local_demucs": "demucs" in str(metadata.get("engine", "")),
            "uses_remote_mvsep": bool(profile_config.get("use_mvsep")),
        }

    return {
        "default_profile": DEFAULT_PROFILE,
        "recommended_profile": QUALITY_8_STEM_PROFILE,
        "production_profile": (
            QUALITY_8_STEM_PROFILE
            if qualification["production_release_eligible"]
            else None
        ),
        "evaluation_profile": QUALITY_8_STEM_PROFILE,
        "product_contract": {
            "name": "hierarchical_12_stems",
            "target_stems": list(PRODUCT_12_STEMS),
            "hierarchy": PRODUCT_12_STEM_HIERARCHY,
            "model_supported_stems": list(BASE_6_STEMS),
            "specialist_candidate_stems": list(SAM_SPECIALIST_STEMS),
            "specialist_model": None,
            "specialist_status": "wind_unavailable",
            "production_release_eligible": False,
        },
        "quality_qualification": qualification,
        "stem_contracts": {
            "product_11_stems": {
                "target_stems": list(QUALITY_8_STEMS),
                "excluded_stems": list(QUALITY_8_EXCLUDED_STEMS),
                "required_artifact_group": "main_stems",
            }
        },
        "artifact_groups": [
            "main_stems",
            "broad_stems",
            "derived_stems",
            "specialist_substems",
            "tempo_locked_wavs",
            "midi",
            "analysis",
            "bundles",
        ],
        "input_sources": {
            "upload": {
                "enabled": True,
                "job_content_type": "multipart/form-data",
                "multipart_enabled": ALLOW_MULTIPART_UPLOADS,
                "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
                "direct_upload_route": "/uploads",
                "direct_upload_enabled": (
                    OBJECT_STORAGE_CONFIG["backend"] == "s3"
                    and bool(OBJECT_STORAGE_CONFIG["bucket"])
                ),
            },
            "audius": {
                "enabled": True,
                "requires_api_key": False,
                "search_route": "/sources/audius/search",
                "track_route": "/sources/audius/tracks/{track_id}",
                "job_content_type": "application/json",
                "license_policy": "commercial_derivatives_only",
                "accepted_licenses": ["CC0", "CC BY", "CC BY-SA"],
            },
        },
        "profiles": profiles,
    }


def content_type_for(filename: str, requested: str | None) -> str:
    return str(
        requested
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )

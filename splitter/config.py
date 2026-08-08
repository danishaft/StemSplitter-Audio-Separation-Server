from __future__ import annotations

import os
from pathlib import Path

from .product_contract import load_product_contract

ROOT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT_DIR.parent
VENV_BIN = PROJECT_ROOT / "venv" / "bin"
DEMUCS_BIN = VENV_BIN / "demucs"
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
APP_VERSION = os.getenv("APP_VERSION") or os.getenv("GIT_SHA") or "development"
INSTANCE_ID = os.getenv("INSTANCE_ID") or f"api-{os.getpid()}"
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:5000").rstrip("/")
TRUSTED_HOSTS = tuple(
    host.strip()
    for host in os.getenv(
        "TRUSTED_HOSTS",
        "*" if APP_ENV != "production" else "",
    ).split(",")
    if host.strip()
)
EDGE_MODE = os.getenv(
    "EDGE_MODE",
    "disabled" if APP_ENV != "production" else "cloudflare",
).strip().lower()
EDGE_VERIFY_HEADER = os.getenv(
    "EDGE_VERIFY_HEADER",
    "X-StemSplitter-Origin-Verify",
).strip()
EDGE_VERIFY_SECRET = os.getenv("EDGE_VERIFY_SECRET", "")
RATE_LIMIT_ENABLED = os.getenv(
    "RATE_LIMIT_ENABLED",
    "0" if APP_ENV == "test" else "1",
).strip().lower() in {"1", "true", "yes"}
RATE_LIMIT_REQUESTS_PER_MINUTE = max(
    1,
    int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "120")),
)
RATE_LIMIT_MUTATIONS_PER_MINUTE = max(
    1,
    int(os.getenv("RATE_LIMIT_MUTATIONS_PER_MINUTE", "20")),
)
RATE_LIMIT_NAMESPACE = os.getenv("RATE_LIMIT_NAMESPACE", "stemsplitter:rate")
METRICS_BEARER_TOKEN = os.getenv("METRICS_BEARER_TOKEN", "")
SENTRY_DSN = os.getenv("SENTRY_DSN")
SENTRY_TRACES_SAMPLE_RATE = min(
    1.0,
    max(0.0, float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))),
)
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "stemsplitter-api")
APPLICATIONINSIGHTS_CONNECTION_STRING = os.getenv(
    "APPLICATIONINSIGHTS_CONNECTION_STRING"
)
CORS_ALLOWED_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "*" if APP_ENV != "production" else "",
    ).split(",")
    if origin.strip()
)
ALLOW_EVALUATION_PROFILES = os.getenv(
    "ALLOW_EVALUATION_PROFILES",
    "1" if APP_ENV != "production" else "0",
).strip().lower() in {"1", "true", "yes"}
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_POOL_MIN_SIZE = max(1, int(os.getenv("DATABASE_POOL_MIN_SIZE", "1")))
DATABASE_POOL_MAX_SIZE = max(
    DATABASE_POOL_MIN_SIZE,
    int(os.getenv("DATABASE_POOL_MAX_SIZE", "10")),
)
DATABASE_POOL_TIMEOUT = max(1.0, float(os.getenv("DATABASE_POOL_TIMEOUT", "10")))
REDIS_URL = os.getenv("REDIS_URL")
JOB_STORE_BACKEND = os.getenv(
    "JOB_STORE_BACKEND", "postgres" if DATABASE_URL else "json"
).strip().lower()
JOB_DISPATCH_BACKEND = os.getenv(
    "JOB_DISPATCH_BACKEND", "rq" if REDIS_URL else "thread"
).strip().lower()
JOB_QUEUE_NAME = os.getenv("JOB_QUEUE_NAME", "stemsplitter")
JOB_LEASE_SECONDS = int(os.getenv("JOB_LEASE_SECONDS", "3900"))
JOB_LEASE_RENEW_INTERVAL = min(
    max(1, int(os.getenv("JOB_LEASE_RENEW_INTERVAL", str(max(1, JOB_LEASE_SECONDS // 3))))),
    max(1, JOB_LEASE_SECONDS - 1),
)
JOB_MAX_ATTEMPTS = int(os.getenv("JOB_MAX_ATTEMPTS", "3"))
JOB_RETRY_INTERVALS = tuple(
    max(0, int(value.strip()))
    for value in os.getenv("JOB_RETRY_INTERVALS", "10,30").split(",")
    if value.strip()
)
JOB_MAX_ACTIVE = int(os.getenv("JOB_MAX_ACTIVE", "100"))
JOB_MAX_ACTIVE_PER_OWNER = int(os.getenv("JOB_MAX_ACTIVE_PER_OWNER", "5"))
JOB_EXECUTION_TIMEOUT = int(os.getenv("JOB_EXECUTION_TIMEOUT", "3900"))
JOB_RESULT_TTL = int(os.getenv("JOB_RESULT_TTL", "86400"))
JOB_FAILURE_TTL = int(os.getenv("JOB_FAILURE_TTL", "604800"))
JOB_RETENTION_SECONDS = int(os.getenv("JOB_RETENTION_SECONDS", "604800"))
AUTH_MODE = os.getenv("AUTH_MODE", "disabled").strip().lower()
AUTH_JWKS_URL = os.getenv("AUTH_JWKS_URL")
AUTH_ISSUER = os.getenv("AUTH_ISSUER")
_AUTH_AUDIENCE = os.getenv("AUTH_AUDIENCE", "").strip()
AUTH_AUDIENCE = (
    _AUTH_AUDIENCE
    if _AUTH_AUDIENCE and _AUTH_AUDIENCE.lower() not in {"none", "disabled"}
    else None
)
AUTH_AUTHORIZED_PARTIES = tuple(
    item.strip()
    for item in os.getenv("AUTH_AUTHORIZED_PARTIES", "").split(",")
    if item.strip()
)
AUTH_ALGORITHMS = tuple(
    item.strip()
    for item in os.getenv("AUTH_ALGORITHMS", "RS256").split(",")
    if item.strip()
)
DEMUCS_JOBS = int(os.getenv("DEMUCS_JOBS", "1"))
BUNDLED_LOCAL_SPECIALIST_RUNNER = ROOT_DIR / "tools" / "local_specialist_runner.py"
BUNDLED_SOTA_INSTRUMENT_RUNNER = ROOT_DIR / "tools" / "audio_separator_sota_runner.py"

UPLOAD_DIR = ROOT_DIR / "uploads"
JOBS_DIR = ROOT_DIR / "jobs"

ALLOWED_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "m4a"}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024
ALLOW_MULTIPART_UPLOADS = os.getenv(
    "ALLOW_MULTIPART_UPLOADS",
    "1" if APP_ENV != "production" else "0",
).strip().lower() in {"1", "true", "yes"}

CORE_BROAD_STEMS = ["vocals", "drums", "bass", "other", "instrumental"]
EXTENDED_BROAD_STEMS = ["piano", "guitar"]

# This is a hierarchy, not a set of tracks that should be summed together.
PRODUCT_CONTRACT = load_product_contract()
PRODUCT_12_STEMS = list(PRODUCT_CONTRACT.target_stems)
PRODUCT_12_STEM_HIERARCHY = {
    parent: list(children)
    for parent, children in PRODUCT_CONTRACT.hierarchy.items()
}
PRODUCT_STEM_PROFILE = "quality_gpu_experimental"
PRODUCT_DISABLED_STEMS = ["wind"]
PRODUCT_11_STEMS = [
    stem for stem in PRODUCT_12_STEMS if stem not in PRODUCT_DISABLED_STEMS
]
PRODUCT_11_BROAD_STEMS = [
    "vocals",
    "instrumental",
    "drums",
    "bass",
    "piano",
    "acoustic_guitar",
]
PRODUCT_11_SPECIALIST_STEMS = [
    "kick",
    "snare",
    "electric_guitar",
    "synth",
    "strings",
]
PRODUCT_11_EXCLUDED_STEMS = [
    "other",
    "guitar",
    "lead_vocals",
    "backing_vocals",
    "hi_hats_cymbals",
    "hi_hats",
    "cymbals",
    "crash",
    "ride",
    "toms",
    "sfx",
    "keys",
    "wind",
    "brass",
    "crowd",
]

# Compatibility aliases for modules that still expose the historical profile
# identifier. Their values now follow the canonical eleven-stem product contract.
QUALITY_8_STEM_PROFILE = PRODUCT_STEM_PROFILE
QUALITY_8_BROAD_STEMS = PRODUCT_11_BROAD_STEMS
QUALITY_8_SPECIALIST_STEMS = PRODUCT_11_SPECIALIST_STEMS
QUALITY_8_STEMS = PRODUCT_11_STEMS
QUALITY_8_EXCLUDED_STEMS = PRODUCT_11_EXCLUDED_STEMS

BASE_6_STEMS = list(PRODUCT_CONTRACT.model_supported_stems)
SAM_SPECIALIST_STEMS = list(PRODUCT_CONTRACT.specialist_candidate_stems)

DERIVED_STEM_RULES = {
    "drums": {
        "kick": {"kind": "lowpass", "low": None, "high": 180.0},
        "snare_clap": {"kind": "bandpass", "low": 180.0, "high": 2500.0},
        "hats_cymbals": {"kind": "highpass", "low": 4000.0, "high": None},
        "percussion": {"kind": "bandpass", "low": 600.0, "high": 6000.0},
    },
    "other": {
        "keys_synth": {"kind": "bandpass", "low": 180.0, "high": 5000.0},
        "pads_strings": {"kind": "bandpass", "low": 120.0, "high": 1800.0},
        "fx": {"kind": "highpass", "low": 5000.0, "high": None},
    },
}

PROFILE_CONFIG = {
    "preview": {
        "run_models": ["htdemucs_6s"],
        "publish_extended": False,
        "publish_derived": False,
        "generate_midi": False,
        "tempo_lock": False,
        "prefer_local_specialists": False,
        "use_mvsep": False,
    },
    "quality": {
        "run_models": ["mdx_extra", "htdemucs_ft", "htdemucs_6s"],
        "publish_extended": True,
        "publish_derived": True,
        "generate_midi": True,
        "tempo_lock": True,
        "prefer_local_specialists": True,
        "use_mvsep": False,
    },
    "benchmark_quality": {
        "run_models": ["mdx_extra", "htdemucs_ft"],
        "publish_extended": False,
        "publish_derived": True,
        "generate_midi": True,
        "tempo_lock": True,
        "prefer_local_specialists": True,
        "use_mvsep": False,
    },
    "quality_mvsep_experimental": {
        "run_models": ["mdx_extra", "htdemucs_ft", "htdemucs_6s"],
        "publish_extended": True,
        "publish_derived": True,
        "generate_midi": True,
        "tempo_lock": True,
        "prefer_local_specialists": True,
        "use_mvsep": True,
    },
    "quality_gpu_experimental": {
        "run_models": ["mdx_extra", "htdemucs_ft", "htdemucs_6s"],
        "publish_extended": True,
        "publish_derived": True,
        "generate_midi": True,
        "tempo_lock": True,
        "prefer_local_specialists": True,
        "use_mvsep": False,
        "use_gpu_worker": True,
        "allow_local_fallback": False,
    },
}

DEFAULT_PROFILE = os.getenv("DEFAULT_PROFILE", "quality").strip() or "quality"
RECOMMENDED_PROFILE = PRODUCT_STEM_PROFILE

PROFILE_CAPABILITIES = {
    "quality_gpu_experimental": {
        "label": "GPU 11-stem evaluation candidate",
        "public": True,
        "tier": "evaluation",
        "engine": "modal_gpu_worker",
        "contract": "product_11_stems",
        "target_stems": PRODUCT_11_STEMS,
        "fallback_policy": "fail_if_gpu_unavailable",
        "warnings": [
            "release_not_qualified",
            "internal_corpus_incomplete",
            "external_benchmarks_available",
            "wind_unavailable",
        ],
    },
    "preview": {
        "label": "Preview legacy",
        "public": False,
        "tier": "legacy",
        "engine": "local_demucs",
        "contract": "broad_preview",
        "target_stems": CORE_BROAD_STEMS,
        "fallback_policy": "none",
        "warnings": ["local_demucs_preview_only"],
    },
    "quality": {
        "label": "Quality local legacy",
        "public": False,
        "tier": "legacy",
        "engine": "local_demucs",
        "contract": "local_legacy",
        "target_stems": CORE_BROAD_STEMS + EXTENDED_BROAD_STEMS,
        "fallback_policy": "none",
        "warnings": ["legacy_not_8_stem_product"],
    },
    "quality_mvsep_experimental": {
        "label": "MVSEP experimental",
        "public": False,
        "tier": "experimental",
        "engine": "local_demucs_plus_remote_mvsep",
        "contract": "experimental_substems",
        "target_stems": [],
        "fallback_policy": "complete_with_local_outputs_if_remote_unavailable",
        "warnings": ["remote_optional", "not_a_product_output_contract"],
    },
    "benchmark_quality": {
        "label": "Benchmark local quality",
        "public": False,
        "tier": "diagnostic",
        "engine": "local_demucs",
        "contract": "benchmark",
        "target_stems": CORE_BROAD_STEMS,
        "fallback_policy": "none",
        "warnings": ["benchmark_only"],
    },
}
DERIVED_CONFIDENCE_THRESHOLD = 0.65
EXTENDED_CONFIDENCE_THRESHOLD = 0.55
MIDI_CONFIDENCE_THRESHOLD = 0.5

PUBLISH_THRESHOLDS = {
    "extended_stems": 0.60,
    "derived_stems": 0.65,
    "midi": 0.65,
    "specialist_substems": 0.65,
}

MVSEP_CONFIG = {
    "base_url": os.getenv("MVSEP_API_BASE_URL", "https://de2.mvsep.com/api").rstrip("/"),
    "timeout": int(os.getenv("MVSEP_TIMEOUT", "300")),
    "max_retries": int(os.getenv("MVSEP_MAX_RETRIES", "3")),
    "retry_delay": int(os.getenv("MVSEP_RETRY_DELAY", "5")),
    "poll_interval": int(os.getenv("MVSEP_POLL_INTERVAL", "5")),
    "max_polls": int(os.getenv("MVSEP_MAX_POLLS", "720")),
    "api_key": os.getenv("MVSEP_API_KEY"),
}

LOCAL_SPECIALIST_CONFIG = {
    "runner": os.getenv("LOCAL_SPECIALIST_RUNNER") or (str(BUNDLED_LOCAL_SPECIALIST_RUNNER) if BUNDLED_LOCAL_SPECIALIST_RUNNER.exists() else None),
    "timeout": int(os.getenv("LOCAL_SPECIALIST_TIMEOUT", "300")),
    "drum_model": "UVR-MDX-NET-Drums",
    "music_model": "UVR5-Reformer-HG-OSR",
}

SOTA_INSTRUMENT_CONFIG = {
    "runner": os.getenv("SOTA_INSTRUMENT_RUNNER") or (str(BUNDLED_SOTA_INSTRUMENT_RUNNER) if BUNDLED_SOTA_INSTRUMENT_RUNNER.exists() else None),
    "timeout": int(os.getenv("SOTA_INSTRUMENT_TIMEOUT", "900")),
    "model": os.getenv("SOTA_INSTRUMENT_MODEL", "htdemucs_6s.yaml"),
}

GPU_WORKER_CONFIG = {
    "base_url": os.getenv("GPU_WORKER_URL"),
    "api_key": os.getenv("GPU_WORKER_API_KEY"),
    "timeout": int(os.getenv("GPU_WORKER_TIMEOUT", "3600")),
    "poll_interval": float(os.getenv("GPU_WORKER_POLL_INTERVAL", "2.0")),
    "max_wait": int(os.getenv("GPU_WORKER_MAX_WAIT", "3600")),
    "max_execution_seconds": float(os.getenv("GPU_WORKER_MAX_EXECUTION_SECONDS", "0")),
    "artifact_import_mode": os.getenv("GPU_WORKER_ARTIFACT_IMPORT_MODE", "parallel_direct").lower(),
    "artifact_download_workers": int(os.getenv("GPU_WORKER_ARTIFACT_DOWNLOAD_WORKERS", "8")),
    "artifact_download_retries": int(os.getenv("GPU_WORKER_ARTIFACT_DOWNLOAD_RETRIES", "5")),
    "artifact_download_retry_delay": float(os.getenv("GPU_WORKER_ARTIFACT_DOWNLOAD_RETRY_DELAY", "1.5")),
    "prefer_volume_import": os.getenv("GPU_WORKER_PREFER_VOLUME_IMPORT", "1").lower() not in {"0", "false", "no"},
    "volume_name": os.getenv("GPU_WORKER_VOLUME_NAME", "stemsplitter-gpu-worker-jobs"),
    "modal_bin": os.getenv("GPU_WORKER_MODAL_BIN", "modal"),
    "modal_profile": os.getenv("GPU_WORKER_MODAL_PROFILE"),
    "volume_import_timeout": int(os.getenv("GPU_WORKER_VOLUME_IMPORT_TIMEOUT", "1800")),
}

OBJECT_STORAGE_CONFIG = {
    "backend": os.getenv("OBJECT_STORAGE_BACKEND", "local").lower(),
    "bucket": os.getenv("OBJECT_STORAGE_BUCKET"),
    "prefix": os.getenv("OBJECT_STORAGE_PREFIX", "stemsplitter"),
    "endpoint_url": os.getenv("OBJECT_STORAGE_ENDPOINT_URL"),
    "region": os.getenv("OBJECT_STORAGE_REGION") or os.getenv("AWS_REGION"),
    "access_key_id": os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID"),
    "secret_access_key": os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY"),
    "session_token": os.getenv("OBJECT_STORAGE_SESSION_TOKEN") or os.getenv("AWS_SESSION_TOKEN"),
    "presign_ttl": int(os.getenv("OBJECT_STORAGE_PRESIGN_TTL", "900")),
    "max_object_bytes": int(os.getenv("OBJECT_STORAGE_MAX_BYTES", str(MAX_CONTENT_LENGTH))),
}

AUDIUS_CONFIG = {
    "base_url": os.getenv("AUDIUS_API_BASE_URL", "https://api.audius.co/v1").rstrip("/"),
    "api_key": os.getenv("AUDIUS_API_KEY"),
    "timeout": int(os.getenv("AUDIUS_TIMEOUT", "30")),
    "max_import_bytes": int(os.getenv("AUDIUS_MAX_IMPORT_BYTES", str(MAX_CONTENT_LENGTH))),
    "max_duration_seconds": int(os.getenv("AUDIUS_MAX_DURATION_SECONDS", "1200")),
    "allow_noncommercial_licenses": os.getenv(
        "AUDIUS_ALLOW_NONCOMMERCIAL_LICENSES", "0"
    ).lower()
    in {"1", "true", "yes"},
}

SECTION_CONFIG = {
    "window_beats": 4,
    "min_section_seconds": 8.0,
    "merge_gap_seconds": 8.0,
    "boundary_sigma": 0.75,
}

AUDIO_SCORE_CONFIG = {
    "piano": {
        "band_low": 100.0,
        "band_high": 4200.0,
        "energy_low": 0.03,
        "energy_high": 0.42,
        "max_parent_share": 0.62,
        "coverage_low": 0.10,
        "transient": False,
    },
    "guitar": {
        "band_low": 80.0,
        "band_high": 6500.0,
        "energy_low": 0.03,
        "energy_high": 0.42,
        "max_parent_share": 0.60,
        "coverage_low": 0.08,
        "transient": False,
    },
    "lead_vocals": {
        "band_low": 120.0,
        "band_high": 8500.0,
        "energy_low": 0.05,
        "energy_high": 0.70,
        "max_parent_share": 0.95,
        "coverage_low": 0.12,
        "transient": False,
    },
    "backing_vocals": {
        "band_low": 120.0,
        "band_high": 8500.0,
        "energy_low": 0.02,
        "energy_high": 0.55,
        "max_parent_share": 0.80,
        "coverage_low": 0.06,
        "transient": False,
    },
    "vocal_reverb": {
        "band_low": 180.0,
        "band_high": 12000.0,
        "energy_low": 0.01,
        "energy_high": 0.35,
        "max_parent_share": 0.45,
        "coverage_low": 0.08,
        "transient": False,
    },
    "kick": {
        "band_low": 30.0,
        "band_high": 180.0,
        "energy_low": 0.04,
        "energy_high": 0.36,
        "max_parent_share": 0.55,
        "coverage_low": 0.05,
        "transient": True,
        "peak_density_low": 0.3,
        "peak_density_high": 6.0,
    },
    "snare_clap": {
        "band_low": 180.0,
        "band_high": 2500.0,
        "energy_low": 0.03,
        "energy_high": 0.30,
        "max_parent_share": 0.45,
        "coverage_low": 0.03,
        "transient": True,
        "peak_density_low": 0.4,
        "peak_density_high": 10.0,
    },
    "snare": {
        "band_low": 160.0,
        "band_high": 3200.0,
        "energy_low": 0.03,
        "energy_high": 0.32,
        "max_parent_share": 0.45,
        "coverage_low": 0.03,
        "transient": True,
        "peak_density_low": 0.4,
        "peak_density_high": 10.0,
    },
    "hi_hats": {
        "band_low": 4500.0,
        "band_high": None,
        "energy_low": 0.01,
        "energy_high": 0.24,
        "max_parent_share": 0.30,
        "coverage_low": 0.04,
        "transient": True,
        "peak_density_low": 1.0,
        "peak_density_high": 18.0,
    },
    "cymbals": {
        "band_low": 5000.0,
        "band_high": None,
        "energy_low": 0.01,
        "energy_high": 0.22,
        "max_parent_share": 0.26,
        "coverage_low": 0.03,
        "transient": True,
        "peak_density_low": 0.5,
        "peak_density_high": 8.0,
    },
    "toms": {
        "band_low": 80.0,
        "band_high": 1400.0,
        "energy_low": 0.02,
        "energy_high": 0.22,
        "max_parent_share": 0.35,
        "coverage_low": 0.02,
        "transient": True,
        "peak_density_low": 0.1,
        "peak_density_high": 4.0,
    },
    "hats_cymbals": {
        "band_low": 4000.0,
        "band_high": None,
        "energy_low": 0.02,
        "energy_high": 0.28,
        "max_parent_share": 0.35,
        "coverage_low": 0.04,
        "transient": True,
        "peak_density_low": 1.0,
        "peak_density_high": 18.0,
    },
    "percussion": {
        "band_low": 600.0,
        "band_high": 6000.0,
        "energy_low": 0.02,
        "energy_high": 0.28,
        "max_parent_share": 0.40,
        "coverage_low": 0.03,
        "transient": True,
        "peak_density_low": 0.5,
        "peak_density_high": 12.0,
    },
    "keys_synth": {
        "band_low": 180.0,
        "band_high": 5000.0,
        "energy_low": 0.04,
        "energy_high": 0.48,
        "max_parent_share": 0.65,
        "coverage_low": 0.08,
        "transient": False,
    },
    "strings": {
        "band_low": 180.0,
        "band_high": 3500.0,
        "energy_low": 0.02,
        "energy_high": 0.34,
        "max_parent_share": 0.50,
        "coverage_low": 0.08,
        "transient": False,
    },
    "pads_strings": {
        "band_low": 120.0,
        "band_high": 1800.0,
        "energy_low": 0.03,
        "energy_high": 0.42,
        "max_parent_share": 0.60,
        "coverage_low": 0.10,
        "transient": False,
    },
    "fx": {
        "band_low": 5000.0,
        "band_high": None,
        "energy_low": 0.01,
        "energy_high": 0.22,
        "max_parent_share": 0.28,
        "coverage_low": 0.02,
        "transient": False,
    },
}

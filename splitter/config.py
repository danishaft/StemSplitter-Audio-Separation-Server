from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT_DIR.parent
VENV_BIN = PROJECT_ROOT / "venv" / "bin"
DEMUCS_BIN = VENV_BIN / "demucs"
DEMUCS_JOBS = int(os.getenv("DEMUCS_JOBS", "1"))
BUNDLED_LOCAL_SPECIALIST_RUNNER = ROOT_DIR / "tools" / "local_specialist_runner.py"

UPLOAD_DIR = ROOT_DIR / "uploads"
JOBS_DIR = ROOT_DIR / "jobs"

ALLOWED_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "m4a"}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024

CORE_BROAD_STEMS = ["vocals", "drums", "bass", "other", "instrumental"]
EXTENDED_BROAD_STEMS = ["piano", "guitar"]

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
}

DEFAULT_PROFILE = "quality"
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
    "base_url": "https://mvsep.com/api/separate",
    "status_url": "https://mvsep.com/api/status",
    "timeout": int(os.getenv("MVSEP_TIMEOUT", "300")),
    "max_retries": int(os.getenv("MVSEP_MAX_RETRIES", "3")),
    "retry_delay": 5,
    "api_key": os.getenv("MVSEP_API_KEY"),
}

LOCAL_SPECIALIST_CONFIG = {
    "runner": os.getenv("LOCAL_SPECIALIST_RUNNER") or (str(BUNDLED_LOCAL_SPECIALIST_RUNNER) if BUNDLED_LOCAL_SPECIALIST_RUNNER.exists() else None),
    "timeout": int(os.getenv("LOCAL_SPECIALIST_TIMEOUT", "300")),
    "drum_model": "UVR-MDX-NET-Drums",
    "music_model": "UVR5-Reformer-HG-OSR",
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

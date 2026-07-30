from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from splitter.config import QUALITY_8_STEMS
from splitter.stem_contract import apply_quality_8_contract


def _write_audio(path: Path, frequency: float, *, seconds: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 22050
    time = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    audio = 0.18 * np.sin(2 * np.pi * frequency * time)
    sf.write(path, audio.astype(np.float32), sample_rate)
    return path


def _payload(path: Path, source_model: str = "test-model") -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "source_model": source_model,
        "publish_status": "published",
        "publish_reason": "test",
        "quality_score": None,
        "warnings": [],
        "metrics": {},
    }


def test_quality_8_contract_publishes_selected_outputs_and_rejects_extras(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    broad_dir = job_root / "broad_stems"
    specialist_dir = job_root / "specialist_substems"

    broad_outputs = {
        "vocals": _payload(_write_audio(broad_dir / "vocals.wav", 440.0)),
        "drums": _payload(_write_audio(broad_dir / "drums.wav", 110.0)),
        "bass": _payload(_write_audio(broad_dir / "bass.wav", 55.0)),
        "other": _payload(_write_audio(broad_dir / "other.wav", 330.0)),
        "song_piano_bs_roformer": _payload(_write_audio(broad_dir / "song_piano_bs_roformer.wav", 660.0)),
        "song_guitar_bs_roformer": _payload(_write_audio(broad_dir / "song_guitar_bs_roformer.wav", 880.0)),
    }
    specialist_outputs = {
        "backing_vocals_bve": _payload(_write_audio(specialist_dir / "backing_vocals_bve.wav", 390.0)),
        "kick": _payload(_write_audio(specialist_dir / "kick.wav", 80.0)),
        "snare": _payload(_write_audio(specialist_dir / "snare.wav", 220.0)),
        "electric_guitar": _payload(_write_audio(specialist_dir / "electric_guitar.wav", 980.0)),
        "synth": _payload(_write_audio(specialist_dir / "synth.wav", 520.0)),
        "strings": _payload(_write_audio(specialist_dir / "strings.wav", 740.0)),
        "hi_hats": _payload(_write_audio(specialist_dir / "hi_hats.wav", 7000.0)),
        "crash": _payload(_write_audio(specialist_dir / "crash.wav", 9000.0)),
        "sfx": _payload(_write_audio(specialist_dir / "sfx.wav", 1200.0)),
    }
    rejected = {"extended_stems": {}, "derived_stems": {}, "specialist_substems": {}, "midi": {}}
    missing: list[str] = []

    result = apply_quality_8_contract(
        job_root,
        broad_outputs=broad_outputs,
        derived_outputs={},
        specialist_outputs=specialist_outputs,
        rejected_candidates=rejected,
        missing_features=missing,
    )

    assert set(result["published_main_stems"]) == set(QUALITY_8_STEMS)
    assert set(result["published_broad_stems"]) == {
        "vocals",
        "instrumental",
        "drums",
        "bass",
        "acoustic_guitar",
        "piano",
    }
    assert set(result["published_specialist_substems"]) == {
        "kick",
        "snare",
        "electric_guitar",
        "synth",
        "strings",
    }
    assert result["stem_contract"]["status"] == "complete"
    assert result["stem_contract"]["delivery_status"] == "complete"
    assert result["stem_contract"]["quality_status"] == "rejected"
    assert result["stem_contract"]["production_release_eligible"] is False
    assert missing == []
    assert (job_root / "broad_stems" / "instrumental.wav").exists()
    instrumental = result["published_main_stems"]["instrumental"]
    assert instrumental["source_model"] == "synthetic_sum"
    assert instrumental["warnings"] == ["instrumental_synthesized_from_complete_non_vocal_partition"]
    assert len(instrumental["source_candidate_keys"]) == 5
    assert not (job_root / "broad_stems" / "other.wav").exists()
    assert not (job_root / "specialist_substems" / "hi_hats_cymbals.wav").exists()
    assert not (job_root / "specialist_substems" / "sfx.wav").exists()
    assert (job_root / "candidate_stems" / "specialist_substems" / "sfx.wav").exists()
    assert rejected["gpu_worker_artifacts"]["specialist_substems:sfx"]["publish_reason"] == "excluded_from_product_11_contract"
    assert "broad_stems:other" not in rejected["gpu_worker_artifacts"]
    assert rejected["gpu_worker_artifacts"]["specialist_substems:backing_vocals_bve"]["publish_reason"] == "excluded_from_product_11_contract"


def test_quality_8_contract_records_missing_kick_and_snare(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    broad_dir = job_root / "broad_stems"
    specialist_dir = job_root / "specialist_substems"
    broad_outputs = {
        name: _payload(_write_audio(broad_dir / f"{name}.wav", frequency))
        for name, frequency in {
            "vocals": 440.0,
            "instrumental": 220.0,
            "drums": 110.0,
            "bass": 55.0,
            "guitar": 880.0,
            "piano": 660.0,
            "other": 330.0,
        }.items()
    }
    specialist_outputs = {
        "electric_guitar": _payload(_write_audio(specialist_dir / "electric_guitar.wav", 980.0)),
        "synth": _payload(_write_audio(specialist_dir / "synth.wav", 520.0)),
        "strings": _payload(_write_audio(specialist_dir / "strings.wav", 740.0)),
        "hi_hats": _payload(_write_audio(specialist_dir / "hi_hats.wav", 7000.0)),
    }
    rejected = {"extended_stems": {}, "derived_stems": {}, "specialist_substems": {}, "midi": {}}
    missing: list[str] = []

    result = apply_quality_8_contract(
        job_root,
        broad_outputs=broad_outputs,
        derived_outputs={},
        specialist_outputs=specialist_outputs,
        rejected_candidates=rejected,
        missing_features=missing,
    )

    assert "kick" not in result["published_main_stems"]
    assert "snare" not in result["published_main_stems"]
    assert result["stem_contract"]["status"] == "partial"
    assert result["stem_contract"]["delivery_status"] == "partial"
    assert result["stem_contract"]["missing_stems"] == ["kick", "snare"]
    assert rejected["main_stems"]["kick"]["publish_reason"] == "product11_target_not_produced"
    assert "product11_kick_missing" in missing
    assert "product11_snare_missing" in missing


def test_quality_8_contract_does_not_publish_incomplete_instrumental(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    broad_dir = job_root / "broad_stems"
    broad_outputs = {
        name: _payload(_write_audio(broad_dir / f"{name}.wav", frequency))
        for name, frequency in {
            "vocals": 440.0,
            "drums": 110.0,
            "bass": 55.0,
            "guitar": 880.0,
            "piano": 660.0,
        }.items()
    }
    rejected = {"extended_stems": {}, "derived_stems": {}, "specialist_substems": {}, "midi": {}}
    missing: list[str] = []

    result = apply_quality_8_contract(
        job_root,
        broad_outputs=broad_outputs,
        derived_outputs={},
        specialist_outputs={},
        rejected_candidates=rejected,
        missing_features=missing,
    )

    assert "instrumental" not in result["published_main_stems"]
    assert "product11_instrumental_missing" in missing

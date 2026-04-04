from __future__ import annotations

from pathlib import Path
import shutil

import numpy as np
import soundfile as sf
from pretty_midi_fix import Instrument, Note, PrettyMIDI

import splitter.jobs as jobs


def _write_audio(path: Path, frequency: float, *, seconds: float = 4.0) -> Path:
    sample_rate = 22050
    time = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    audio = 0.18 * np.sin(2 * np.pi * frequency * time)
    sf.write(path, audio.astype(np.float32), sample_rate)
    return path


def _write_simple_midi(path: Path, *, pitch: int = 60) -> None:
    midi = PrettyMIDI(initial_tempo=120)
    instrument = Instrument(program=0)
    instrument.notes.append(Note(velocity=90, pitch=pitch, start=0.0, end=0.5))
    instrument.notes.append(Note(velocity=90, pitch=pitch, start=0.5, end=1.0))
    midi.instruments.append(instrument)
    midi.write(str(path))


def _fake_broad_outputs(job_root: Path) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    broad_dir = job_root / "broad_stems"
    broad_dir.mkdir(parents=True, exist_ok=True)
    core_payloads: dict[str, dict[str, object]] = {}
    for stem_name, frequency in {
        "vocals": 440.0,
        "drums": 110.0,
        "bass": 55.0,
        "other": 330.0,
        "instrumental": 220.0,
    }.items():
        stem_path = _write_audio(broad_dir / f"{stem_name}.wav", frequency)
        core_payloads[stem_name] = {
            "path": str(stem_path.resolve()),
            "confidence": 1.0,
            "publish_status": "published",
            "publish_reason": "core_broad_stem",
            "quality_score": 1.0,
            "warnings": [],
            "metrics": {},
        }

    extended_dir = job_root / "extended_candidates"
    extended_dir.mkdir(parents=True, exist_ok=True)
    extended = {}
    for stem_name, frequency in {"piano": 262.0, "guitar": 392.0}.items():
        stem_path = _write_audio(extended_dir / f"{stem_name}.wav", frequency)
        extended[stem_name] = {
            "stem_name": stem_name,
            "path": str(stem_path.resolve()),
            "parent_path": str(Path(str(core_payloads["other"]["path"])).resolve()),
            "candidate_group": "extended_stems",
            "source_model": "htdemucs_6s",
            "family": stem_name,
        }
    return core_payloads, extended


def _fake_score(candidate: dict[str, object], threshold: float) -> dict[str, object]:
    stem_name = str(candidate["stem_name"])
    should_publish = stem_name in {"piano", "kick", "keys_synth"}
    score = 0.82 if should_publish else 0.31
    return {
        **candidate,
        "quality_score": score,
        "publish_status": "published" if should_publish else "rejected",
        "publish_reason": "meets_threshold" if should_publish else "below_threshold",
        "warnings": [] if should_publish else ["low_quality_candidate"],
        "metrics": {"threshold": threshold, "score": score},
    }


def _fake_validate_midi(
    midi_path: Path,
    *,
    source_name: str,
    source_path: Path,
    audio_duration: float,
    threshold: float,
) -> dict[str, object]:
    should_publish = source_name in {"vocals", "bass", "keys_synth"}
    score = 0.79 if should_publish else 0.25
    return {
        "path": str(midi_path.resolve()),
        "source_name": source_name,
        "source_path": str(source_path.resolve()),
        "audio_duration": audio_duration,
        "quality_score": score,
        "publish_status": "published" if should_publish else "rejected",
        "publish_reason": "meets_threshold" if should_publish else "below_threshold",
        "warnings": [] if should_publish else ["invalid_note_shape"],
        "metrics": {"threshold": threshold, "score": score},
    }


def test_quality_job_writes_sections_and_rejections(
    job_dirs: Path,
    monkeypatch,
) -> None:
    status = jobs.create_job("fixture.wav", b"quality-fixture", profile="quality")
    job_id = str(status["job_id"])
    job_root = job_dirs / job_id

    def fake_build_broad_stems(
        input_path: Path,
        local_job_root: Path,
        profile: str,
        run_models: list[str],
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, str], list[str]]:
        broad_outputs, extended = _fake_broad_outputs(local_job_root)
        runs_root = local_job_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        return broad_outputs, extended, {"runs_root": str(runs_root.resolve())}, ["specialist_env_unavailable"]

    def fake_build_derived_stems(
        broad_outputs: dict[str, dict[str, object]],
        local_job_root: Path,
        use_specialist: bool = False,
    ) -> dict[str, dict[str, object]]:
        candidate_dir = local_job_root / "derived_candidates"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        parent_drums = Path(str(broad_outputs["drums"]["path"])).resolve()
        parent_other = Path(str(broad_outputs["other"]["path"])).resolve()
        derived = {}
        for stem_name, frequency, parent_path in [
            ("kick", 80.0, parent_drums),
            ("keys_synth", 550.0, parent_other),
            ("fx", 7000.0, parent_other),
        ]:
            candidate_path = _write_audio(candidate_dir / f"{stem_name}.wav", frequency)
            derived[stem_name] = {
                "stem_name": stem_name,
                "path": str(candidate_path.resolve()),
                "parent_path": str(parent_path.resolve()),
                "parent_stem": "drums" if parent_path == parent_drums else "other",
                "candidate_group": "derived_stems",
                "source_model": "heuristic:bandpass",
                "family": stem_name,
                "method": "test",
            }
        return derived

    def fake_run_audio2midi(input_path: Path, output_path: Path) -> bool:
        pitch = 45 if input_path.name == "bass.wav" else 72
        _write_simple_midi(output_path, pitch=pitch)
        return True

    def fake_write_chord_guide(source: Path, target: Path, beat_times: list[float] | None) -> None:
        _write_simple_midi(target, pitch=60)

    monkeypatch.setattr(jobs, "build_broad_stems", fake_build_broad_stems)
    monkeypatch.setattr(jobs, "build_derived_stems", fake_build_derived_stems)
    monkeypatch.setattr(
        jobs,
        "detect_tempo_and_beats",
        lambda path: {
            "tempo_bpm": 120.0,
            "first_beat_seconds": 0.0,
            "beat_times": [0.0, 0.5, 1.0, 1.5, 2.0],
        },
    )
    monkeypatch.setattr(jobs, "estimate_key", lambda path: {"key": "C major", "key_confidence": 0.88})
    monkeypatch.setattr(
        jobs,
        "detect_sections",
        lambda path, beat_times: {
            "version": 1,
            "strategy": "light",
            "sections": [
                {
                    "id": "section-1",
                    "label": "intro",
                    "start_seconds": 0.0,
                    "end_seconds": 2.0,
                    "confidence": 0.71,
                    "source": "test",
                },
                {
                    "id": "section-2",
                    "label": "hook",
                    "start_seconds": 2.0,
                    "end_seconds": 4.0,
                    "confidence": 0.83,
                    "source": "test",
                },
            ],
        },
    )
    monkeypatch.setattr(jobs, "create_tempo_locked_copy", lambda source, target, first_beat: shutil.copy2(source, target))
    monkeypatch.setattr(jobs, "score_audio_candidate", _fake_score)
    monkeypatch.setattr(jobs, "validate_midi_candidate", _fake_validate_midi)
    monkeypatch.setattr(jobs, "_run_audio2midi", fake_run_audio2midi)
    monkeypatch.setattr(jobs, "write_chord_guide_midi", fake_write_chord_guide)
    monkeypatch.setattr(jobs, "local_specialist_runtime_status", lambda: (False, "local_specialist_runner_missing"))
    monkeypatch.setattr(jobs, "build_vocal_substems_mvsep", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("quality should not call vocal MVSEP")))
    monkeypatch.setattr(jobs, "build_drum_substems_mvsep", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("quality should not call drum MVSEP")))
    monkeypatch.setattr(jobs, "build_instrument_substems_mvsep", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("quality should not call instrument MVSEP")))

    jobs.run_job(job_id)

    manifest = jobs.get_manifest(job_id)
    assert manifest is not None
    assert manifest["analysis_exports"]["sections"].endswith("analysis/sections.json")
    assert set(manifest["midi_exports"]) == {"melody", "bass", "chords_guide"}
    assert "piano" in manifest["published_broad_stems"]
    assert "guitar" not in manifest["published_broad_stems"]
    assert set(manifest["published_derived_stems"]) == {"kick", "keys_synth"}
    assert manifest["published_specialist_substems"] == {}
    assert "guitar" in manifest["rejected_candidates"]["extended_stems"]
    assert "fx" in manifest["rejected_candidates"]["derived_stems"]
    assert manifest["rejected_candidates"]["specialist_substems"] == {}
    assert manifest["bundle_exports"]["wav_plus_midi"].endswith("package/wav_plus_midi.zip")
    assert manifest["remote_adapter_status"] == "not_requested"
    assert manifest["remote_adapter_reason"] is None
    assert manifest["pipeline_mode"] == "local_fallback"
    assert "local_specialist_runner_missing" in manifest["missing_features"]
    assert manifest["candidate_winners"]["kick"]["published_group"] == "derived_stems"
    assert manifest["candidate_winners"]["midi:melody"]["winning_source"] == "vocals"

    status_payload = jobs.get_job_status(job_id)
    assert status_payload is not None
    assert status_payload["status"] == "completed"
    assert (job_root / "analysis" / "sections.json").exists()


def test_preview_job_skips_sections_derived_and_midi(
    job_dirs: Path,
    monkeypatch,
) -> None:
    status = jobs.create_job("fixture.wav", b"preview-fixture", profile="preview")
    job_id = str(status["job_id"])

    def fake_build_broad_stems(
        input_path: Path,
        local_job_root: Path,
        profile: str,
        run_models: list[str],
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, str], list[str]]:
        broad_outputs, _ = _fake_broad_outputs(local_job_root)
        runs_root = local_job_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        return broad_outputs, {}, {"runs_root": str(runs_root.resolve())}, []

    monkeypatch.setattr(jobs, "build_broad_stems", fake_build_broad_stems)
    monkeypatch.setattr(jobs, "build_derived_stems", lambda broad_outputs, local_job_root: {})

    jobs.run_job(job_id)

    manifest = jobs.get_manifest(job_id)
    assert manifest is not None
    assert manifest["analysis_exports"] == {}
    assert manifest["published_derived_stems"] == {}
    assert manifest["published_specialist_substems"] == {}
    assert manifest["midi_exports"] == {}
    assert manifest["rejected_candidates"] == {
        "extended_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
        "midi": {},
    }


def test_benchmark_quality_keeps_contract_without_extended_stems(
    job_dirs: Path,
    monkeypatch,
) -> None:
    status = jobs.create_job("fixture.wav", b"benchmark-quality-fixture", profile="benchmark_quality")
    job_id = str(status["job_id"])

    def fake_build_broad_stems(
        input_path: Path,
        local_job_root: Path,
        profile: str,
        run_models: list[str],
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, str], list[str]]:
        broad_outputs, extended = _fake_broad_outputs(local_job_root)
        runs_root = local_job_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        assert run_models == ["mdx_extra", "htdemucs_ft"]
        return broad_outputs, extended, {"runs_root": str(runs_root.resolve())}, []

    def fake_build_derived_stems(
        broad_outputs: dict[str, dict[str, object]],
        local_job_root: Path,
        use_specialist: bool = False,
    ) -> dict[str, dict[str, object]]:
        candidate_dir = local_job_root / "derived_candidates"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        parent_other = Path(str(broad_outputs["other"]["path"])).resolve()
        candidate_path = _write_audio(candidate_dir / "keys_synth.wav", 550.0)
        return {
            "keys_synth": {
                "stem_name": "keys_synth",
                "path": str(candidate_path.resolve()),
                "parent_path": str(parent_other.resolve()),
                "parent_stem": "other",
                "candidate_group": "derived_stems",
                "source_model": "heuristic:bandpass",
                "family": "keys_synth",
                "method": "test",
            }
        }

    def fake_run_audio2midi(input_path: Path, output_path: Path) -> bool:
        _write_simple_midi(output_path, pitch=72)
        return True

    monkeypatch.setattr(jobs, "build_broad_stems", fake_build_broad_stems)
    monkeypatch.setattr(jobs, "build_derived_stems", fake_build_derived_stems)
    monkeypatch.setattr(jobs, "detect_tempo_and_beats", lambda path: {"tempo_bpm": 120.0, "first_beat_seconds": 0.0, "beat_times": [0.0, 0.5]})
    monkeypatch.setattr(jobs, "estimate_key", lambda path: {"key": "C major", "key_confidence": 0.88})
    monkeypatch.setattr(jobs, "detect_sections", lambda path, beat_times: {"version": 1, "strategy": "light", "sections": []})
    monkeypatch.setattr(jobs, "create_tempo_locked_copy", lambda source, target, first_beat: shutil.copy2(source, target))
    monkeypatch.setattr(jobs, "score_audio_candidate", lambda candidate, threshold: {
        **candidate,
        "quality_score": 0.88,
        "publish_status": "published",
        "publish_reason": "quality_score_pass",
        "warnings": [],
        "metrics": {"threshold": threshold, "score": 0.88},
    })
    monkeypatch.setattr(jobs, "validate_midi_candidate", _fake_validate_midi)
    monkeypatch.setattr(jobs, "_run_audio2midi", fake_run_audio2midi)
    monkeypatch.setattr(jobs, "write_chord_guide_midi", lambda source, target, beat_times: _write_simple_midi(target, pitch=60))
    monkeypatch.setattr(jobs, "local_specialist_runtime_status", lambda: (False, "local_specialist_runner_missing"))

    jobs.run_job(job_id)

    manifest = jobs.get_manifest(job_id)
    assert manifest is not None
    assert manifest["profile"] == "benchmark_quality"
    assert "piano" not in manifest["published_broad_stems"]
    assert "guitar" not in manifest["published_broad_stems"]
    assert set(manifest["published_derived_stems"]) == {"keys_synth"}
    assert set(manifest["midi_exports"]) == {"melody", "bass", "chords_guide"}
    assert manifest["analysis_exports"]["sections"].endswith("analysis/sections.json")


def test_quality_mvsep_experimental_skips_remote_when_unconfigured(
    job_dirs: Path,
    monkeypatch,
) -> None:
    status = jobs.create_job("fixture.wav", b"experimental-fixture", profile="quality_mvsep_experimental")
    job_id = str(status["job_id"])

    def fake_build_broad_stems(
        input_path: Path,
        local_job_root: Path,
        profile: str,
        run_models: list[str],
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, str], list[str]]:
        broad_outputs, extended = _fake_broad_outputs(local_job_root)
        runs_root = local_job_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        return broad_outputs, extended, {"runs_root": str(runs_root.resolve())}, []

    monkeypatch.setattr(jobs, "build_broad_stems", fake_build_broad_stems)
    monkeypatch.setattr(jobs, "build_derived_stems", lambda broad_outputs, local_job_root, use_specialist=False: {})
    monkeypatch.setattr(jobs, "detect_tempo_and_beats", lambda path: {"tempo_bpm": 120.0, "first_beat_seconds": 0.0, "beat_times": [0.0, 0.5]})
    monkeypatch.setattr(jobs, "estimate_key", lambda path: {"key": "C major", "key_confidence": 0.88})
    monkeypatch.setattr(jobs, "detect_sections", lambda path, beat_times: {"version": 1, "strategy": "light", "sections": []})
    monkeypatch.setattr(jobs, "create_tempo_locked_copy", lambda source, target, first_beat: shutil.copy2(source, target))
    monkeypatch.setattr(jobs, "score_audio_candidate", _fake_score)
    monkeypatch.setattr(jobs, "validate_midi_candidate", _fake_validate_midi)
    monkeypatch.setattr(jobs, "_run_audio2midi", lambda input_path, output_path: False)
    monkeypatch.setattr(jobs, "mvsep_runtime_status", lambda: (False, "mvsep_api_key_missing"))
    monkeypatch.setattr(jobs, "local_specialist_runtime_status", lambda: (False, "local_specialist_runner_missing"))
    monkeypatch.setattr(jobs, "build_vocal_substems_mvsep", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("MVSEP branch should be skipped")))
    monkeypatch.setattr(jobs, "build_drum_substems_mvsep", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("MVSEP branch should be skipped")))
    monkeypatch.setattr(jobs, "build_instrument_substems_mvsep", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("MVSEP branch should be skipped")))

    jobs.run_job(job_id)

    manifest = jobs.get_manifest(job_id)
    assert manifest is not None
    assert manifest["published_specialist_substems"] == {}
    assert manifest["remote_adapter_status"] == "skipped"
    assert manifest["remote_adapter_reason"] == "mvsep_api_key_missing"
    assert "mvsep_api_key_missing" in manifest["missing_features"]
    assert "local_specialist_runner_missing" in manifest["missing_features"]
    assert manifest["rejected_candidates"]["specialist_substems"] == {}
    assert manifest["pipeline_mode"] == "local_fallback"


def test_quality_prefers_local_specialist_candidates_when_available(
    job_dirs: Path,
    monkeypatch,
) -> None:
    status = jobs.create_job("fixture.wav", b"local-specialist-fixture", profile="quality")
    job_id = str(status["job_id"])
    job_root = job_dirs / job_id

    def fake_build_broad_stems(
        input_path: Path,
        local_job_root: Path,
        profile: str,
        run_models: list[str],
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, str], list[str]]:
        broad_outputs, extended = _fake_broad_outputs(local_job_root)
        runs_root = local_job_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        return broad_outputs, extended, {"runs_root": str(runs_root.resolve())}, []

    def fake_local_candidates(
        broad_outputs: dict[str, dict[str, object]],
        local_job_root: Path,
    ) -> tuple[dict[str, dict[str, object]], list[str]]:
        candidate_dir = local_job_root / "local_specialist_candidates"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        kick_path = _write_audio(candidate_dir / "kick.wav", 72.0)
        return (
            {
                "kick": {
                    "stem_name": "kick",
                    "path": str(kick_path.resolve()),
                    "parent_path": str(Path(str(broad_outputs["drums"]["path"])).resolve()),
                    "parent_stem": "drums",
                    "candidate_group": "derived_stems",
                    "source_model": "local_specialist:UVR-MDX-NET-Drums",
                    "family": "kick",
                    "method": "local_specialist",
                }
            },
            [],
        )

    monkeypatch.setattr(jobs, "build_broad_stems", fake_build_broad_stems)
    monkeypatch.setattr(jobs, "build_derived_stems", lambda broad_outputs, local_job_root, use_specialist=False: {})
    monkeypatch.setattr(jobs, "build_local_derived_candidates", fake_local_candidates)
    monkeypatch.setattr(jobs, "local_specialist_runtime_status", lambda: (True, None))
    monkeypatch.setattr(jobs, "detect_tempo_and_beats", lambda path: {"tempo_bpm": 120.0, "first_beat_seconds": 0.0, "beat_times": [0.0, 0.5]})
    monkeypatch.setattr(jobs, "estimate_key", lambda path: {"key": "C major", "key_confidence": 0.88})
    monkeypatch.setattr(jobs, "detect_sections", lambda path, beat_times: {"version": 1, "strategy": "light", "sections": []})
    monkeypatch.setattr(jobs, "create_tempo_locked_copy", lambda source, target, first_beat: shutil.copy2(source, target))
    monkeypatch.setattr(jobs, "score_audio_candidate", lambda candidate, threshold: {
        **candidate,
        "quality_score": 0.88,
        "publish_status": "published",
        "publish_reason": "quality_score_pass",
        "warnings": [],
        "metrics": {"threshold": threshold, "score": 0.88},
    })
    monkeypatch.setattr(jobs, "_run_audio2midi", lambda input_path, output_path: False)

    jobs.run_job(job_id)

    manifest = jobs.get_manifest(job_id)
    assert manifest is not None
    assert manifest["pipeline_mode"] == "local_specialist"
    assert manifest["published_derived_stems"]["kick"]["source_model"] == "local_specialist:UVR-MDX-NET-Drums"
    assert manifest["candidate_winners"]["kick"]["winning_source"] == "local_specialist:UVR-MDX-NET-Drums"


def test_quality_mvsep_experimental_publishes_specialist_substems_separately(
    job_dirs: Path,
    monkeypatch,
) -> None:
    status = jobs.create_job("fixture.wav", b"experimental-fixture", profile="quality_mvsep_experimental")
    job_id = str(status["job_id"])
    job_root = job_dirs / job_id

    def fake_build_broad_stems(
        input_path: Path,
        local_job_root: Path,
        profile: str,
        run_models: list[str],
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, str], list[str]]:
        broad_outputs, extended = _fake_broad_outputs(local_job_root)
        runs_root = local_job_root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        return broad_outputs, extended, {"runs_root": str(runs_root.resolve())}, []

    def fake_specialist_candidates(*args, **kwargs):
        specialist_dir = job_root / "specialist_candidates"
        specialist_dir.mkdir(parents=True, exist_ok=True)
        lead = _write_audio(specialist_dir / "lead_vocals.wav", 520.0)
        snare = _write_audio(specialist_dir / "snare.wav", 220.0)
        strings = _write_audio(specialist_dir / "strings.wav", 660.0)
        return (
            {
                "lead_vocals": {
                    "stem_name": "lead_vocals",
                    "path": str(lead.resolve()),
                    "parent_path": str((job_root / "broad_stems" / "vocals.wav").resolve()),
                    "parent_stem": "vocals",
                    "candidate_group": "specialist_substems",
                    "source_model": "BS-Roformer-V2",
                    "family": "lead_vocals",
                },
                "snare": {
                    "stem_name": "snare",
                    "path": str(snare.resolve()),
                    "parent_path": str((job_root / "broad_stems" / "drums.wav").resolve()),
                    "parent_stem": "drums",
                    "candidate_group": "specialist_substems",
                    "source_model": "DrumSep",
                    "family": "snare",
                },
                "strings": {
                    "stem_name": "strings",
                    "path": str(strings.resolve()),
                    "parent_path": str((job_root / "broad_stems" / "other.wav").resolve()),
                    "parent_stem": "other",
                    "candidate_group": "specialist_substems",
                    "source_model": "MVSep-Plucked-Strings",
                    "family": "strings",
                },
            },
            [],
            "used",
            None,
        )

    monkeypatch.setattr(jobs, "build_broad_stems", fake_build_broad_stems)
    monkeypatch.setattr(jobs, "build_derived_stems", lambda broad_outputs, local_job_root, use_specialist=False: {})
    monkeypatch.setattr(jobs, "_collect_specialist_candidates", fake_specialist_candidates)
    monkeypatch.setattr(jobs, "local_specialist_runtime_status", lambda: (False, "local_specialist_runner_missing"))
    monkeypatch.setattr(jobs, "detect_tempo_and_beats", lambda path: {"tempo_bpm": 120.0, "first_beat_seconds": 0.0, "beat_times": [0.0, 0.5]})
    monkeypatch.setattr(jobs, "estimate_key", lambda path: {"key": "C major", "key_confidence": 0.88})
    monkeypatch.setattr(jobs, "detect_sections", lambda path, beat_times: {"version": 1, "strategy": "light", "sections": []})
    monkeypatch.setattr(jobs, "create_tempo_locked_copy", lambda source, target, first_beat: shutil.copy2(source, target))
    monkeypatch.setattr(jobs, "score_audio_candidate", lambda candidate, threshold: {
        **candidate,
        "quality_score": 0.91,
        "publish_status": "published",
        "publish_reason": "quality_score_pass",
        "warnings": [],
        "metrics": {"threshold": threshold, "score": 0.91},
    })
    monkeypatch.setattr(jobs, "validate_midi_candidate", _fake_validate_midi)
    monkeypatch.setattr(jobs, "_run_audio2midi", lambda input_path, output_path: False)

    jobs.run_job(job_id)

    manifest = jobs.get_manifest(job_id)
    assert manifest is not None
    assert set(manifest["published_broad_stems"]) >= {"vocals", "drums", "bass", "other", "instrumental"}
    assert set(manifest["published_specialist_substems"]) == {"lead_vocals", "snare", "strings"}
    assert "lead_vocals" not in manifest["published_broad_stems"]
    assert manifest["remote_adapter_status"] == "used"
    assert manifest["remote_adapter_reason"] is None
    assert manifest["pipeline_mode"] == "local_plus_mvsep_experimental"
    assert manifest["bundle_exports"]["stems"].endswith("package/stems.zip")
    assert (job_root / "specialist_substems" / "lead_vocals.wav").exists()

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from pretty_midi_fix import Instrument, Note, PrettyMIDI

from splitter.scoring import score_audio_candidate, validate_midi_candidate


def _write_audio(path: Path, audio: np.ndarray, sample_rate: int = 22050) -> None:
    sf.write(path, audio.astype(np.float32), sample_rate)


def test_score_audio_candidate_rejects_silent_candidate(tmp_path: Path) -> None:
    sample_rate = 22050
    seconds = 6.0
    time = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    parent = 0.18 * np.sin(2 * np.pi * 220.0 * time)
    candidate = np.zeros_like(parent)

    parent_path = tmp_path / "parent.wav"
    candidate_path = tmp_path / "candidate.wav"
    _write_audio(parent_path, parent, sample_rate)
    _write_audio(candidate_path, candidate, sample_rate)

    scored = score_audio_candidate(
        {
            "stem_name": "keys_synth",
            "path": str(candidate_path.resolve()),
            "parent_path": str(parent_path.resolve()),
            "candidate_group": "derived_stems",
            "source_model": "heuristic:bandpass",
            "family": "keys_synth",
        },
        threshold=0.65,
    )

    assert scored["publish_status"] == "rejected"
    assert scored["quality_score"] < 0.65
    assert "too_quiet_relative_to_parent" in scored["warnings"]


def test_score_audio_candidate_softens_parent_leakage_penalty_for_small_overage(tmp_path: Path) -> None:
    sample_rate = 22050
    seconds = 6.0
    time = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    parent = 0.18 * np.sin(2 * np.pi * 440.0 * time)
    candidate = 0.12 * np.sin(2 * np.pi * 440.0 * time)

    parent_path = tmp_path / "parent.wav"
    candidate_path = tmp_path / "candidate.wav"
    _write_audio(parent_path, parent, sample_rate)
    _write_audio(candidate_path, candidate, sample_rate)

    scored = score_audio_candidate(
        {
            "stem_name": "keys_synth",
            "path": str(candidate_path.resolve()),
            "parent_path": str(parent_path.resolve()),
            "candidate_group": "derived_stems",
            "source_model": "local_specialist:test",
            "family": "keys_synth",
        },
        threshold=0.65,
    )

    assert scored["metrics"]["inverse_parent_leakage"] > 0.0
    assert scored["metrics"]["parent_leakage"] < 1.0


def test_validate_midi_candidate_accepts_reasonable_midi(tmp_path: Path) -> None:
    midi_path = tmp_path / "bass.mid"
    midi = PrettyMIDI(initial_tempo=120)
    instrument = Instrument(program=33)
    notes = [
        Note(velocity=90, pitch=45, start=0.0, end=0.5),
        Note(velocity=90, pitch=45, start=0.5, end=1.0),
        Note(velocity=90, pitch=48, start=1.0, end=1.5),
        Note(velocity=90, pitch=43, start=1.5, end=2.0),
    ]
    instrument.notes.extend(notes)
    midi.instruments.append(instrument)
    midi.write(str(midi_path))

    scored = validate_midi_candidate(
        midi_path,
        source_name="bass",
        source_path=midi_path,
        audio_duration=2.0,
        threshold=0.65,
    )

    assert scored["publish_status"] == "published"
    assert scored["quality_score"] >= 0.65


def test_validate_midi_candidate_rejects_pathological_density(tmp_path: Path) -> None:
    midi_path = tmp_path / "dense.mid"
    midi = PrettyMIDI(initial_tempo=120)
    instrument = Instrument(program=0)
    cursor = 0.0
    for _ in range(120):
        instrument.notes.append(Note(velocity=70, pitch=72, start=cursor, end=cursor + 0.01))
        cursor += 0.01
    midi.instruments.append(instrument)
    midi.write(str(midi_path))

    scored = validate_midi_candidate(
        midi_path,
        source_name="vocals",
        source_path=midi_path,
        audio_duration=1.2,
        threshold=0.65,
    )

    assert scored["publish_status"] == "rejected"
    assert scored["publish_reason"] == "pathological_note_density"

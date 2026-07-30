from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from splitter.ground_truth import (
    build_babyslakh_references,
    evaluate_manifest_against_babyslakh,
    score_prediction_against_reference,
)


def _write_wav(path: Path, freq: float, sr: int = 16000) -> None:
    timeline = np.linspace(0.0, 1.0, sr, endpoint=False)
    audio = 0.2 * np.sin(2 * np.pi * freq * timeline)
    stereo = np.stack([audio, audio], axis=1).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, stereo, sr, subtype="PCM_16")


def test_score_prediction_against_reference_identical_audio_is_high(tmp_path: Path) -> None:
    reference = tmp_path / "reference.wav"
    prediction = tmp_path / "prediction.wav"
    _write_wav(reference, 220.0)
    _write_wav(prediction, 220.0)

    score = score_prediction_against_reference(prediction, reference)

    assert score.si_sdr > 60.0
    assert score.correlation == pytest.approx(1.0, abs=1e-4)


def test_score_prediction_against_reference_resamples_prediction(tmp_path: Path) -> None:
    reference = tmp_path / "reference.wav"
    prediction = tmp_path / "prediction.wav"
    _write_wav(reference, 220.0, sr=16000)
    _write_wav(prediction, 220.0, sr=44100)

    score = score_prediction_against_reference(prediction, reference)

    assert score.correlation > 0.95


def test_build_babyslakh_references_groups_stems(tmp_path: Path) -> None:
    track = tmp_path / "Track00001"
    metadata = """
stems:
  S00:
    inst_class: Bass
  S01:
    inst_class: Drums
  S02:
    inst_class: Guitar
"""
    (track / "metadata.yaml").parent.mkdir(parents=True)
    (track / "metadata.yaml").write_text(metadata)
    _write_wav(track / "stems" / "S00.wav", 80.0)
    _write_wav(track / "stems" / "S01.wav", 400.0)
    _write_wav(track / "stems" / "S02.wav", 900.0)

    references = build_babyslakh_references(track, tmp_path / "refs")

    assert sorted(references) == ["bass", "drums", "guitar", "other"]
    for path in references.values():
        assert path.exists()


def test_evaluate_manifest_against_babyslakh_scores_matching_prediction(tmp_path: Path) -> None:
    track = tmp_path / "Track00001"
    (track / "metadata.yaml").parent.mkdir(parents=True)
    (track / "metadata.yaml").write_text("stems:\n  S00:\n    inst_class: Bass\n")
    reference_source = track / "stems" / "S00.wav"
    prediction = tmp_path / "bass.wav"
    _write_wav(reference_source, 80.0)
    _write_wav(prediction, 80.0)
    manifest = {
        "published_broad_stems": {
            "bass": {"path": str(prediction)},
        },
        "published_derived_stems": {},
    }

    report = evaluate_manifest_against_babyslakh(manifest, track, tmp_path / "out")

    assert report.success is True
    assert "bass" in report.scores
    assert report.scores["bass"].si_sdr > 60.0

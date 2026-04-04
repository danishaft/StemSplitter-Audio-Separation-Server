"""Unit tests for separation module - stem building with mocking."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from splitter.separation import build_broad_stems, build_derived_stems


def _write_audio(path: Path, frequency: float = 440.0, *, seconds: float = 2.0) -> Path:
    sample_rate = 22050
    time = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    audio = 0.18 * np.sin(2 * np.pi * frequency * time)
    sf.write(path, audio.astype(np.float32), sample_rate)
    return path


class TestBuildDerivedStems:
    """Tests for derived stem generation."""

    def test_generates_drum_substems(self, tmp_path: Path) -> None:
        """Should generate drum family derived stems."""
        drums_path = _write_audio(tmp_path / "drums.wav", 110.0)
        other_path = _write_audio(tmp_path / "other.wav", 330.0)
        broad_outputs = {
            "drums": {"path": str(drums_path.resolve())},
            "other": {"path": str(other_path.resolve())},
        }

        derived = build_derived_stems(broad_outputs, tmp_path)

        drum_derived = {"kick", "snare_clap", "hats_cymbals", "percussion"}
        for stem_name in drum_derived:
            if stem_name in derived:
                assert "path" in derived[stem_name]
                assert "parent_stem" in derived[stem_name]
                assert derived[stem_name]["parent_stem"] == "drums"

    def test_generates_other_substems(self, tmp_path: Path) -> None:
        """Should generate other family derived stems."""
        drums_path = _write_audio(tmp_path / "drums.wav", 110.0)
        other_path = _write_audio(tmp_path / "other.wav", 330.0)
        broad_outputs = {
            "drums": {"path": str(drums_path.resolve())},
            "other": {"path": str(other_path.resolve())},
        }

        derived = build_derived_stems(broad_outputs, tmp_path)

        other_derived = {"keys_synth", "pads_strings", "fx"}
        for stem_name in other_derived:
            if stem_name in derived:
                assert "path" in derived[stem_name]
                assert "parent_stem" in derived[stem_name]
                assert derived[stem_name]["parent_stem"] == "other"

    def test_derived_stems_have_candidate_metadata(self, tmp_path: Path) -> None:
        """Derived stems should include candidate metadata."""
        drums_path = _write_audio(tmp_path / "drums.wav", 110.0)
        broad_outputs = {"drums": {"path": str(drums_path.resolve())}}

        derived = build_derived_stems(broad_outputs, tmp_path)

        for stem_name, payload in derived.items():
            assert "stem_name" in payload
            assert "path" in payload
            assert "parent_path" in payload
            assert "candidate_group" in payload
            assert payload["candidate_group"] == "derived_stems"

    def test_derived_stems_reference_parent_paths(self, tmp_path: Path) -> None:
        """Derived stems should have correct parent_path references."""
        drums_path = _write_audio(tmp_path / "drums.wav", 110.0)
        broad_outputs = {"drums": {"path": str(drums_path.resolve())}}

        derived = build_derived_stems(broad_outputs, tmp_path)

        for stem_name, payload in derived.items():
            if payload.get("parent_stem") == "drums":
                assert payload["parent_path"] == str(drums_path.resolve())

    def test_extended_candidates_use_resolved_instrumental_parent(self, tmp_path: Path) -> None:
        """Extended stems should score against a published same-rate parent, not the raw input mix."""
        input_path = _write_audio(tmp_path / "mix.wav", 220.0)

        def fake_run_demucs(input_path: Path, output_root: Path, *, model: str, two_stems: str | None = None) -> dict[str, Path]:
            model_dir = output_root / model / input_path.stem
            model_dir.mkdir(parents=True, exist_ok=True)
            outputs: dict[str, Path] = {}
            if model == "mdx_extra":
                outputs["vocals"] = _write_audio(model_dir / "vocals.wav", 440.0)
                outputs["no_vocals"] = _write_audio(model_dir / "no_vocals.wav", 330.0)
            elif model == "htdemucs_ft":
                outputs["drums"] = _write_audio(model_dir / "drums.wav", 110.0)
                outputs["bass"] = _write_audio(model_dir / "bass.wav", 90.0)
                outputs["other"] = _write_audio(model_dir / "other.wav", 550.0)
            elif model == "htdemucs_6s":
                outputs["piano"] = _write_audio(model_dir / "piano.wav", 660.0)
                outputs["guitar"] = _write_audio(model_dir / "guitar.wav", 880.0)
            return outputs

        with patch("splitter.separation.run_demucs", side_effect=fake_run_demucs):
            broad_outputs, extended_candidates, _, _ = build_broad_stems(
                input_path,
                tmp_path / "job",
                "quality",
                ["mdx_extra", "htdemucs_ft", "htdemucs_6s"],
            )

        assert broad_outputs["instrumental"]["source_model"] == "mdx_extra"
        expected_parent = broad_outputs["instrumental"]["path"]
        assert extended_candidates["piano"]["parent_path"] == expected_parent
        assert extended_candidates["guitar"]["parent_path"] == expected_parent
        assert extended_candidates["piano"]["parent_stem"] == "instrumental"

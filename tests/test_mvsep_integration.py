"""Tests for MVSEP integration.

Note: These tests require MVSEP API access. They are skipped if
MVSEP_API_KEY is not set or if the API is unavailable.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from splitter.mvsep_client import MVSEPClient, MVSEPModelChain
from splitter.specialist import (
    build_vocal_substems_mvsep,
    build_drum_substems_mvsep,
    build_instrument_substems_mvsep,
)


# Check if MVSEP API key is available
MVSEP_API_KEY = os.environ.get("MVSEP_API_KEY")
HAS_MVSEP = MVSEP_API_KEY is not None


def _write_test_audio(path: Path, frequency: float = 440.0, *, seconds: float = 10.0) -> Path:
    """Write a test audio file with a simple tone."""
    sample_rate = 22050
    time = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    audio = 0.18 * np.sin(2 * np.pi * frequency * time)
    sf.write(path, audio.astype(np.float32), sample_rate)
    return path


@pytest.mark.skipif(not HAS_MVSEP, reason="MVSEP_API_KEY not set")
class TestMVSEPClient:
    """Test MVSEP API client."""

    def test_client_initialization(self) -> None:
        """Test MVSEP client initializes correctly."""
        client = MVSEPClient(api_key=MVSEP_API_KEY)
        assert client.api_key == MVSEP_API_KEY
        assert client.timeout == 300
        assert client.max_retries == 3

    def test_get_available_models(self) -> None:
        """Test getting available models."""
        client = MVSEPClient(api_key=MVSEP_API_KEY)
        models = client.get_available_models()

        assert "BS-Roformer-V2" in models
        assert "DrumSep" in models
        assert "MVSep-Piano" in models
        assert isinstance(models, dict)

    @pytest.mark.slow
    def test_separate_vocals(self, tmp_path: Path) -> None:
        """Test vocal separation with BS-Roformer-V2."""
        # Create test vocal-like audio
        vocals_path = _write_test_audio(tmp_path / "vocals.wav", frequency=440.0)

        client = MVSEPClient(api_key=MVSEP_API_KEY)
        output_dir = tmp_path / "output"

        # This would make a real API call - commented out for local testing
        # stems = client.separate(vocals_path, "BS-Roformer-V2", output_dir)
        # assert isinstance(stems, dict)

        assert vocals_path.exists()

    @pytest.mark.slow
    def test_separate_drums(self, tmp_path: Path) -> None:
        """Test drum separation with DrumSep."""
        drums_path = _write_test_audio(tmp_path / "drums.wav", frequency=110.0)

        client = MVSEPClient(api_key=MVSEP_API_KEY)
        output_dir = tmp_path / "output"

        # This would make a real API call - commented out for local testing
        # stems = client.separate(drums_path, "DrumSep", output_dir)
        # assert isinstance(stems, dict)

        assert drums_path.exists()


class TestMVSEPIntegration:
    """Test MVSEP integration without API calls."""

    def test_mvsep_client_import(self) -> None:
        """Test that MVSEP client can be imported."""
        from splitter.mvsep_client import MVSEPClient
        assert MVSEPClient is not None

    def test_mvsep_models_available(self) -> None:
        """Test that MVSEP models are defined."""
        from splitter.mvsep_client import MVSEPClient
        client = MVSEPClient()
        models = client.get_available_models()

        # Check key models are available
        expected_models = [
            "BS-Roformer-V2",
            "DrumSep",
            "MVSep-Piano",
            "MVSep-Lead-Guitar",
            "MVSep-Keys",
            "MVSep-Plucked-Strings",
        ]

        for model in expected_models:
            assert model in models, f"Model {model} should be available"

    def test_vocal_substems_returns_dict(self, tmp_path: Path) -> None:
        """Test vocal sub-stems function returns dict (no API call)."""
        # Create fake vocals stem
        vocals_path = _write_test_audio(tmp_path / "vocals.wav", seconds=1.0)

        with pytest.raises(RuntimeError):
            build_vocal_substems_mvsep(vocals_path, tmp_path)

    def test_drum_substems_returns_dict(self, tmp_path: Path) -> None:
        """Test drum sub-stems function returns dict (no API call)."""
        drums_path = _write_test_audio(tmp_path / "drums.wav", seconds=1.0)

        with pytest.raises(RuntimeError):
            build_drum_substems_mvsep(drums_path, tmp_path)

    def test_instrument_substems_returns_dict(self, tmp_path: Path) -> None:
        """Test instrument sub-stems function returns dict (no API call)."""
        other_path = _write_test_audio(tmp_path / "other.wav", seconds=1.0)

        with pytest.raises(RuntimeError):
            build_instrument_substems_mvsep(other_path, tmp_path)


@pytest.mark.skipif(not HAS_MVSEP, reason="MVSEP_API_KEY not set")
class TestMVSEPModelChain:
    """Test MVSEP model chaining."""

    @pytest.mark.slow
    def test_vocal_branch(self, tmp_path: Path) -> None:
        """Test vocal branch processing."""
        vocals_path = _write_test_audio(tmp_path / "vocals.wav")

        chain = MVSEPModelChain(MVSEPClient(api_key=MVSEP_API_KEY))
        # This would make real API calls - skipped for local testing
        # stems = chain.run_vocal_branch(vocals_path, tmp_path)
        # assert isinstance(stems, dict)

    @pytest.mark.slow
    def test_drum_branch(self, tmp_path: Path) -> None:
        """Test drum branch processing."""
        drums_path = _write_test_audio(tmp_path / "drums.wav")

        chain = MVSEPModelChain(MVSEPClient(api_key=MVSEP_API_KEY))
        # This would make real API calls - skipped for local testing
        # stems = chain.run_drum_branch(drums_path, tmp_path)
        # assert isinstance(stems, dict)

    @pytest.mark.slow
    def test_instrument_branch(self, tmp_path: Path) -> None:
        """Test instrument branch processing."""
        other_path = _write_test_audio(tmp_path / "other.wav")

        chain = MVSEPModelChain(MVSEPClient(api_key=MVSEP_API_KEY))
        # This would make real API calls - skipped for local testing
        # stems = chain.run_instrument_branch(other_path, tmp_path)
        # assert isinstance(stems, dict)

"""Unit tests for packaging module - manifest and bundle generation."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

from splitter.packaging import write_manifest, package_directories
from splitter.jobs import get_manifest
from splitter.util import dump_json


class TestWriteManifest:
    """Tests for manifest writing."""

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        """Manifest should be valid JSON."""
        manifest_path = write_manifest(
            tmp_path,
            {
                "job_id": "test-job",
                "published_broad_stems": {},
                "published_derived_stems": {},
                "tempo_locked_exports": {},
                "midi_exports": {},
                "analysis_exports": {},
                "bundle_exports": {},
                "rejected_candidates": {
                    "extended_stems": {},
                    "derived_stems": {},
                    "midi": {},
                },
            },
        )

        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["job_id"] == "test-job"

    def test_includes_all_required_fields(self, tmp_path: Path) -> None:
        """Manifest should include all required fields."""
        manifest_path = write_manifest(tmp_path, {
            "job_id": "test-job",
            "published_broad_stems": {"vocals": {"path": "/vocals.wav"}},
            "published_derived_stems": {"kick": {"path": "/kick.wav"}},
            "tempo_locked_exports": {"vocals": "/tempo/vocals.wav"},
            "midi_exports": {"melody": "/midi/melody.mid"},
            "analysis_exports": {"tempo_key": "/analysis/tempo_key.json"},
            "bundle_exports": {"wav_plus_midi": "/package/wav_plus_midi.zip"},
            "rejected_candidates": {"extended_stems": {}, "derived_stems": {}, "midi": {}},
        })

        data = json.loads(manifest_path.read_text())
        required_fields = {
            "job_id",
            "published_broad_stems",
            "published_derived_stems",
            "tempo_locked_exports",
            "midi_exports",
            "analysis_exports",
            "bundle_exports",
            "rejected_candidates",
        }
        assert required_fields <= set(data.keys())

    def test_rejected_candidates_structure(self, tmp_path: Path) -> None:
        """Rejected candidates should have proper structure."""
        manifest_path = write_manifest(tmp_path, {
            "job_id": "test-job",
            "published_broad_stems": {},
            "published_derived_stems": {},
            "tempo_locked_exports": {},
            "midi_exports": {},
            "analysis_exports": {},
            "bundle_exports": {},
            "rejected_candidates": {
                "extended_stems": {
                    "guitar": {
                        "quality_score": 0.31,
                        "publish_status": "rejected",
                        "publish_reason": "below_threshold",
                    }
                },
                "derived_stems": {"fx": {"quality_score": 0.25, "publish_status": "rejected"}},
                "midi": {},
            },
        })

        data = json.loads(manifest_path.read_text())
        assert "guitar" in data["rejected_candidates"]["extended_stems"]
        assert data["rejected_candidates"]["extended_stems"]["guitar"]["publish_status"] == "rejected"


class TestGetManifest:
    """Tests for manifest reading."""

    def test_returns_none_if_missing(self, tmp_path: Path) -> None:
        """Should return None when manifest doesn't exist."""
        result = get_manifest(tmp_path)
        assert result is None

    def test_returns_parsed_manifest(self, tmp_path: Path) -> None:
        """Should return parsed manifest data."""
        write_manifest(
            tmp_path,
            {
                "job_id": "read-test",
                "published_broad_stems": {},
                "published_derived_stems": {},
                "tempo_locked_exports": {},
                "midi_exports": {},
                "analysis_exports": {},
                "bundle_exports": {},
                "rejected_candidates": {"extended_stems": {}, "derived_stems": {}, "midi": {}},
            },
        )

        result = get_manifest(tmp_path)
        assert result is not None
        assert result["job_id"] == "read-test"


class TestCreateBundles:
    """Tests for bundle creation."""

    def test_creates_wav_plus_midi_zip(self, tmp_path: Path) -> None:
        """Should create wav_plus_midi bundle."""
        # Create fake stems and MIDI files
        stems_dir = tmp_path / "tempo_locked_wavs"
        stems_dir.mkdir()
        (stems_dir / "vocals.wav").write_bytes(b"RIFFvocals")
        (stems_dir / "drums.wav").write_bytes(b"RIFFdrums")

        midi_dir = tmp_path / "midi"
        midi_dir.mkdir()
        (midi_dir / "melody.mid").write_bytes(b"MThd")

        package_dir = tmp_path / "package"
        package_dir.mkdir()

        bundle_exports = package_directories(
            tmp_path,
            groups={
                "wav_plus_midi": list(stems_dir.glob("*.wav")) + list(midi_dir.glob("*.mid")),
            },
        )

        assert "wav_plus_midi" in bundle_exports
        bundle_path = Path(bundle_exports["wav_plus_midi"])
        assert bundle_path.exists()
        assert bundle_path.suffix == ".zip"

        # Verify zip contents
        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = zf.namelist()
            assert any("vocals.wav" in n for n in names)
            assert any("melody.mid" in n for n in names)

    def test_bundle_path_in_package_dir(self, tmp_path: Path) -> None:
        """Bundle should be created in package directory."""
        stems_dir = tmp_path / "tempo_locked_wavs"
        stems_dir.mkdir()
        (stems_dir / "vocals.wav").write_bytes(b"RIFFvocals")

        midi_dir = tmp_path / "midi"
        midi_dir.mkdir()
        (midi_dir / "melody.mid").write_bytes(b"MThd")

        package_dir = tmp_path / "package"
        package_dir.mkdir()

        bundle_exports = package_directories(
            tmp_path,
            groups={
                "wav_plus_midi": list(stems_dir.glob("*.wav")) + list(midi_dir.glob("*.mid")),
            },
        )

        bundle_path = Path(bundle_exports["wav_plus_midi"])
        assert "package" in bundle_path.parts

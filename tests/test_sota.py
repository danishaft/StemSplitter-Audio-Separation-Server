from __future__ import annotations

import json
import subprocess as sp
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from splitter.sota import (
    collect_manifest_instrument_candidates,
    compare_instrument_candidates_against_babyslakh,
)


def _write_wav(path: Path, freq: float, sr: int = 16000) -> None:
    timeline = np.linspace(0.0, 1.0, sr, endpoint=False)
    audio = 0.2 * np.sin(2 * np.pi * freq * timeline)
    stereo = np.stack([audio, audio], axis=1).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, stereo, sr, subtype="PCM_16")


def test_collect_manifest_instrument_candidates_includes_published_and_rejected(tmp_path: Path) -> None:
    piano = tmp_path / "piano.wav"
    guitar = tmp_path / "guitar.wav"
    _write_wav(piano, 220.0)
    _write_wav(guitar, 440.0)
    manifest = {
        "published_broad_stems": {
            "piano": {"path": str(piano), "source_model": "published-piano"},
        },
        "published_specialist_substems": {},
        "rejected_candidates": {
            "extended_stems": {
                "guitar": {"path": str(guitar), "source_model": "rejected-guitar"},
            },
        },
    }

    candidates = collect_manifest_instrument_candidates(manifest)

    assert candidates["piano"][0]["source"] == "published-piano"
    assert candidates["guitar"][0]["source"] == "rejected-guitar"


def test_compare_instrument_candidates_selects_best_candidate(tmp_path: Path) -> None:
    track = tmp_path / "Track00001"
    (track / "metadata.yaml").parent.mkdir(parents=True)
    (track / "metadata.yaml").write_text("stems:\n  S00:\n    inst_class: Piano\n")
    reference = track / "stems" / "S00.wav"
    good = tmp_path / "good-piano.wav"
    bad = tmp_path / "bad-piano.wav"
    _write_wav(reference, 220.0)
    _write_wav(good, 220.0)
    _write_wav(bad, 880.0)
    manifest = {
        "published_broad_stems": {
            "piano": {"path": str(bad), "source_model": "bad"},
        },
        "published_specialist_substems": {
            "piano": {"path": str(good), "source_model": "good"},
        },
        "rejected_candidates": {"extended_stems": {}},
    }

    report = compare_instrument_candidates_against_babyslakh(
        manifest,
        track,
        tmp_path / "out",
    )

    assert report.winners["piano"].source == "good"
    assert report.winners["piano"].si_sdr > 60.0


def test_audio_separator_sota_runner_normalizes_audio_separator_outputs(tmp_path: Path) -> None:
    fake_bin = tmp_path / "audio-separator"
    fake_bin.write_text(
        """#!/usr/bin/env python3
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("audio_file")
parser.add_argument("--model_filename")
parser.add_argument("--output_format")
parser.add_argument("--output_dir")
parser.add_argument("--model_file_dir")
parser.add_argument("--single_stem")
parser.add_argument("--custom_output_names")
parser.add_argument("--log_level")
args = parser.parse_args()
out = Path(args.output_dir) / f"fixture_({args.single_stem})_mock.wav"
out.write_bytes(b"fake wav payload")
""",
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)
    input_audio = tmp_path / "input.wav"
    input_audio.write_bytes(b"fake input")
    output_dir = tmp_path / "out"
    runner = Path(__file__).resolve().parents[1] / "tools" / "audio_separator_sota_runner.py"

    result = sp.run(
        [
            sys.executable,
            str(runner),
            "--input",
            str(input_audio),
            "--output",
            str(output_dir),
            "--targets",
            "piano,guitar",
            "--model",
            "mock.yaml",
            "--audio-separator-bin",
            str(fake_bin),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert sorted(payload["outputs"]) == ["guitar", "piano"]
    assert (output_dir / "piano.wav").read_bytes() == b"fake wav payload"
    assert (output_dir / "guitar.wav").read_bytes() == b"fake wav payload"

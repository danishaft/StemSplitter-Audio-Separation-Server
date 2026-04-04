from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tools" / "local_specialist_runner.py"
PYTHON = ROOT.parent / "venv" / "bin" / "python"


def _write_fixture(path: Path) -> None:
    sr = 22050
    duration = 2.0
    timeline = np.linspace(0.0, duration, int(sr * duration), endpoint=False)
    low = 0.35 * np.sin(2 * np.pi * 70.0 * timeline)
    mid = 0.25 * np.sin(2 * np.pi * 900.0 * timeline)
    high = 0.2 * np.sin(2 * np.pi * 7000.0 * timeline)
    pulse = np.zeros_like(timeline)
    pulse[:: int(sr * 0.25)] = 1.0
    pulse = np.convolve(pulse, np.hanning(256), mode="same")
    left = low + mid + high + 0.3 * pulse
    right = low - mid + 0.8 * high + 0.25 * pulse
    stereo = np.stack([left, right], axis=1).astype(np.float32)
    sf.write(path, stereo, sr, subtype="PCM_16")


def _assert_non_silent(path: Path) -> None:
    audio, _ = sf.read(path, always_2d=True)
    assert audio.size > 0
    assert float(np.max(np.abs(audio))) > 1e-4


def _spectral_energy(path: Path, low: float, high: float | None = None) -> float:
    audio, sr = sf.read(path, always_2d=True)
    mono = audio.mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / sr)
    if high is None:
        mask = freqs >= low
    else:
        mask = (freqs >= low) & (freqs <= high)
    return float(np.sum(spectrum[mask]))


def test_bundled_runner_emits_drum_stems(tmp_path: Path) -> None:
    input_path = tmp_path / "fixture.wav"
    output_dir = tmp_path / "drums"
    _write_fixture(input_path)

    subprocess.run(
        [
            str(PYTHON),
            str(RUNNER),
            "--input",
            str(input_path),
            "--output",
            str(output_dir),
            "--task",
            "drums",
            "--model",
            "UVR-MDX-NET-Drums",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    expected = {"kick", "snare_clap", "hats_cymbals", "percussion"}
    assert {item.stem for item in output_dir.glob("*.wav")} == expected
    for stem_name in expected:
        _assert_non_silent(output_dir / f"{stem_name}.wav")


def test_bundled_runner_emits_music_stems(tmp_path: Path) -> None:
    input_path = tmp_path / "fixture.wav"
    output_dir = tmp_path / "other"
    _write_fixture(input_path)

    subprocess.run(
        [
            str(PYTHON),
            str(RUNNER),
            "--input",
            str(input_path),
            "--output",
            str(output_dir),
            "--task",
            "other",
            "--model",
            "UVR5-Reformer-HG-OSR",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    expected = {"keys_synth", "pads_strings", "fx"}
    assert {item.stem for item in output_dir.glob("*.wav")} == expected
    for stem_name in expected:
        _assert_non_silent(output_dir / f"{stem_name}.wav")

    pads_path = output_dir / "pads_strings.wav"
    keys_path = output_dir / "keys_synth.wav"
    fx_path = output_dir / "fx.wav"

    pads_high_energy = _spectral_energy(pads_path, 2200.0)
    keys_high_energy = _spectral_energy(keys_path, 2200.0)
    assert pads_high_energy < keys_high_energy

    fx_top_energy = _spectral_energy(fx_path, 5000.0)
    pads_top_energy = _spectral_energy(pads_path, 5000.0)
    assert pads_top_energy < fx_top_energy

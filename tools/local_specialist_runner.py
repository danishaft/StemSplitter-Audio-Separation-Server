from __future__ import annotations

import argparse
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter
from scipy.signal import butter, sosfiltfilt


def _ensure_stereo(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return np.vstack([audio, audio])
    if audio.ndim == 2:
        return audio
    raise ValueError("audio must be mono or stereo")


def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = librosa.load(path, sr=None, mono=False)
    return _ensure_stereo(np.asarray(audio, dtype=np.float32)), int(sr)


def _safe_sos(kind: str, sr: int, low: float | None = None, high: float | None = None) -> np.ndarray:
    nyquist = max(sr / 2.0, 1.0)
    if kind == "lowpass":
        assert high is not None
        cutoff = min(max(high / nyquist, 1e-4), 0.99)
        return butter(4, cutoff, btype="lowpass", output="sos")
    if kind == "highpass":
        assert low is not None
        cutoff = min(max(low / nyquist, 1e-4), 0.99)
        return butter(4, cutoff, btype="highpass", output="sos")
    if kind == "bandpass":
        assert low is not None and high is not None
        low_cut = min(max(low / nyquist, 1e-4), 0.98)
        high_cut = min(max(high / nyquist, low_cut + 1e-4), 0.99)
        return butter(4, [low_cut, high_cut], btype="bandpass", output="sos")
    raise ValueError(f"unsupported filter kind: {kind}")


def _filter_audio(
    audio: np.ndarray,
    sr: int,
    kind: str,
    low: float | None = None,
    high: float | None = None,
) -> np.ndarray:
    sos = _safe_sos(kind, sr, low=low, high=high)
    filtered = np.vstack([sosfiltfilt(sos, channel) for channel in audio])
    return filtered.astype(np.float32)


def _hpss(audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    harmonic_channels: list[np.ndarray] = []
    percussive_channels: list[np.ndarray] = []
    for channel in audio:
        harmonic, percussive = librosa.effects.hpss(channel)
        harmonic_channels.append(harmonic.astype(np.float32))
        percussive_channels.append(percussive.astype(np.float32))
    return np.vstack(harmonic_channels), np.vstack(percussive_channels)


def _sustained_band(audio: np.ndarray, sr: int, low: float, high: float, smooth_frames: int = 31) -> np.ndarray:
    sustained_channels: list[np.ndarray] = []
    for channel in audio:
        stft = librosa.stft(channel, n_fft=2048, hop_length=512)
        magnitude = np.abs(stft)
        phase = np.exp(1j * np.angle(stft))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        band_mask = ((freqs >= low) & (freqs <= high)).astype(np.float32)[:, None]
        band_mag = magnitude * band_mask
        smoothed = median_filter(band_mag, size=(1, smooth_frames))
        sustained = librosa.istft(smoothed * phase, hop_length=512, length=len(channel))
        sustained_channels.append(sustained.astype(np.float32))
    return np.vstack(sustained_channels)


def _peak_limit(audio: np.ndarray, reference_peak: float) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak <= 1e-8:
        return audio.astype(np.float32)
    target = min(max(reference_peak, 0.1), 0.99)
    if peak > target:
        audio = audio * (target / peak)
    return audio.astype(np.float32)


def _write_outputs(output_dir: Path, sr: int, stems: dict[str, np.ndarray], reference_peak: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stem_name, audio in stems.items():
        bounded = _peak_limit(audio, reference_peak)
        sf.write(output_dir / f"{stem_name}.wav", bounded.T, sr, subtype="PCM_16")


def _run_drums(audio: np.ndarray, sr: int) -> dict[str, np.ndarray]:
    _, percussive = _hpss(audio)
    kick = _filter_audio(percussive, sr, "lowpass", high=180.0)
    snare_clap = _filter_audio(percussive, sr, "bandpass", low=180.0, high=2500.0)
    hats_cymbals = _filter_audio(percussive, sr, "highpass", low=4000.0)
    percussion_band = _filter_audio(percussive, sr, "bandpass", low=600.0, high=6000.0)
    percussion = percussion_band - (0.35 * snare_clap) - (0.15 * hats_cymbals)
    return {
        "kick": kick,
        "snare_clap": snare_clap,
        "hats_cymbals": hats_cymbals,
        "percussion": percussion,
    }


def _run_other(audio: np.ndarray, sr: int) -> dict[str, np.ndarray]:
    harmonic, percussive = _hpss(audio)
    keys_synth = _filter_audio(harmonic, sr, "bandpass", low=180.0, high=5000.0)
    pads_base = _sustained_band(harmonic, sr, low=180.0, high=1600.0, smooth_frames=41)
    pads_strings = pads_base - (0.25 * _filter_audio(keys_synth, sr, "bandpass", low=700.0, high=1800.0))
    fx_source = 0.5 * percussive + 0.5 * (audio - harmonic)
    fx = _filter_audio(fx_source, sr, "highpass", low=5000.0)
    return {
        "keys_synth": keys_synth,
        "pads_strings": pads_strings,
        "fx": fx,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundled local specialist runner.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--task", required=True, choices=("drums", "other"))
    parser.add_argument("--model", required=True, help="Accepted for adapter compatibility.")
    args = parser.parse_args()

    audio, sr = _load_audio(args.input)
    reference_peak = float(np.max(np.abs(audio))) if audio.size else 0.8

    if args.task == "drums":
        stems = _run_drums(audio, sr)
    else:
        stems = _run_other(audio, sr)

    _write_outputs(args.output, sr, stems, reference_peak)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

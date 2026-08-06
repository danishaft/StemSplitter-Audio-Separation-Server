from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import soundfile as sf

from .util import ensure_dir

DEFAULT_PEAK_BINS = 960


def _stem_peaks(path: Path, bins: int) -> dict[str, object]:
    with sf.SoundFile(path) as audio:
        frame_count = len(audio)
        sample_rate = int(audio.samplerate)
        block_frames = max(1, math.ceil(frame_count / bins))
        raw_peaks: list[float] = []

        while len(raw_peaks) < bins:
            block = audio.read(block_frames, dtype="float32", always_2d=True)
            if not len(block):
                break
            raw_peaks.append(float(np.max(np.abs(block))))

    peak_amplitude = max(raw_peaks, default=0.0)
    scale = peak_amplitude if peak_amplitude > 1e-9 else 1.0
    normalized = [round(value / scale, 4) for value in raw_peaks]
    if len(normalized) < bins:
        normalized.extend([0.0] * (bins - len(normalized)))

    return {
        "duration_seconds": round(frame_count / max(sample_rate, 1), 3),
        "sample_rate": sample_rate,
        "peak_amplitude": round(peak_amplitude, 6),
        "peaks": normalized,
    }


def write_waveform_peaks(
    stems: Mapping[str, Path],
    output_path: Path,
    *,
    bins: int = DEFAULT_PEAK_BINS,
) -> Path:
    if bins < 64 or bins > 4096:
        raise ValueError("waveform_peak_bins_out_of_range")

    stem_payload = {
        str(name): _stem_peaks(Path(path), bins)
        for name, path in sorted(stems.items())
        if Path(path).is_file()
    }
    duration = max(
        (float(payload["duration_seconds"]) for payload in stem_payload.values()),
        default=0.0,
    )
    payload = {
        "version": 1,
        "bins": bins,
        "duration_seconds": round(duration, 3),
        "normalization": "per_stem_peak",
        "stems": stem_payload,
    }
    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return output_path

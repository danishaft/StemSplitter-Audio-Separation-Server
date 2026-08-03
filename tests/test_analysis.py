from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from splitter.analysis import detect_sections


def test_detect_sections_returns_ordered_labeled_sections(tmp_path: Path) -> None:
    sample_rate = 22050
    segment_seconds = 6.0
    total_seconds = segment_seconds * 4
    segments = []
    frequencies = [220.0, 440.0, 330.0, 440.0]
    amplitudes = [0.08, 0.28, 0.18, 0.28]
    for frequency, amplitude in zip(frequencies, amplitudes):
        time = np.linspace(0, segment_seconds, int(sample_rate * segment_seconds), endpoint=False)
        tone = amplitude * np.sin(2 * np.pi * frequency * time)
        pulse = np.zeros_like(tone)
        for beat_start in np.arange(0.0, segment_seconds, 0.5):
            index = int(beat_start * sample_rate)
            pulse[index:index + 600] += 0.15 * np.hanning(min(600, len(pulse) - index))
        segments.append(np.clip(tone + pulse, -1.0, 1.0))

    audio = np.concatenate(segments)
    audio_path = tmp_path / "sections.wav"
    sf.write(audio_path, audio, sample_rate)

    beat_times = np.arange(0.0, total_seconds + 0.5, 0.5).tolist()
    result = detect_sections(audio_path, beat_times)
    sections = result["sections"]

    assert result["strategy"] == "light"
    assert sections
    assert sections[0]["start_seconds"] == 0.0
    assert sections[-1]["end_seconds"] == pytest.approx(total_seconds, abs=0.5)
    assert any(section["label"] == "hook" for section in sections)

    previous_end = 0.0
    allowed = {"intro", "verse", "hook", "bridge", "outro", "unknown"}
    for section in sections:
        assert section["label"] in allowed
        assert section["end_seconds"] > section["start_seconds"]
        assert section["start_seconds"] >= previous_end
        previous_end = section["end_seconds"]

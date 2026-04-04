from __future__ import annotations

import json
from pathlib import Path

import librosa
import numpy as np
from pretty_midi_fix import Instrument, Note, PrettyMIDI
import soundfile as sf

from .config import SECTION_CONFIG
from .util import ensure_dir

KEY_NAMES = [
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
]

MAJOR_PROFILE = np.asarray(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float32,
)
MINOR_PROFILE = np.asarray(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float32,
)
MAJOR_TRIAD = np.asarray([1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
MINOR_TRIAD = np.asarray([1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)


def detect_tempo_and_beats(audio_path: Path) -> dict[str, object]:
    audio, sample_rate = librosa.load(audio_path, sr=44100, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sample_rate)
    tempo_value = 0.0
    if np.size(tempo):
        tempo_value = float(np.asarray(tempo).reshape(-1)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate).tolist()
    return {
        "bpm": round(tempo_value, 3),
        "first_beat_seconds": round(float(beat_times[0]), 3) if beat_times else 0.0,
        "beat_count": len(beat_times),
        "beat_times": [round(float(item), 3) for item in beat_times[:512]],
    }


def estimate_key(audio_path: Path) -> dict[str, object]:
    audio, sample_rate = librosa.load(audio_path, sr=22050, mono=True)
    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    chroma_mean = chroma.mean(axis=1)
    chroma_mean = chroma_mean / (np.linalg.norm(chroma_mean) + 1e-12)

    best_score = -1.0
    best_key = "Unknown"
    best_mode = "unknown"
    for idx, name in enumerate(KEY_NAMES):
        major_score = float(np.dot(chroma_mean, np.roll(MAJOR_PROFILE, idx)))
        minor_score = float(np.dot(chroma_mean, np.roll(MINOR_PROFILE, idx)))
        if major_score > best_score:
            best_score = major_score
            best_key = name
            best_mode = "major"
        if minor_score > best_score:
            best_score = minor_score
            best_key = name
            best_mode = "minor"
    return {"key": best_key, "mode": best_mode, "confidence": round(best_score, 3)}


def create_tempo_locked_copy(input_path: Path, output_path: Path, start_seconds: float) -> Path:
    ensure_dir(output_path.parent)
    audio, sample_rate = sf.read(input_path, always_2d=True)
    start_frame = max(0, int(start_seconds * sample_rate))
    trimmed = audio[start_frame:]
    sf.write(output_path, trimmed, sample_rate)
    return output_path


def write_tempo_key_analysis(output_path: Path, analysis: dict[str, object]) -> Path:
    ensure_dir(output_path.parent)
    payload = {
        "bpm": analysis.get("bpm", 0.0),
        "first_beat_seconds": analysis.get("first_beat_seconds", 0.0),
        "beat_count": analysis.get("beat_count", 0),
        "beat_times": analysis.get("beat_times", []),
        "key": analysis.get("key", "Unknown"),
        "mode": analysis.get("mode", "unknown"),
        "confidence": analysis.get("confidence", 0.0),
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def _label_sections(section_features: list[dict[str, object]], duration: float) -> list[str]:
    labels = ["unknown"] * len(section_features)
    if not section_features:
        return labels

    energies = np.asarray([float(item["energy"]) for item in section_features], dtype=np.float32)
    max_energy = float(np.max(energies)) if energies.size else 1.0

    similarity_matrix = np.zeros((len(section_features), len(section_features)), dtype=np.float32)
    for left in range(len(section_features)):
        for right in range(left + 1, len(section_features)):
            similarity = _cosine_similarity(
                np.asarray(section_features[left]["signature"], dtype=np.float32),
                np.asarray(section_features[right]["signature"], dtype=np.float32),
            )
            similarity_matrix[left, right] = similarity
            similarity_matrix[right, left] = similarity

    repeat_counts = (similarity_matrix >= 0.88).sum(axis=1)
    repeated_indices = [idx for idx, count in enumerate(repeat_counts) if count > 0]

    if section_features[0]["start_seconds"] <= 1.0 and float(section_features[0]["energy"]) <= max_energy * 0.7:
        labels[0] = "intro"

    if len(section_features) > 1:
        last = section_features[-1]
        if duration - float(last["start_seconds"]) <= max(SECTION_CONFIG["min_section_seconds"] * 1.4, 14.0):
            labels[-1] = "outro"

    hook_index = None
    if repeated_indices:
        hook_index = max(
            repeated_indices,
            key=lambda idx: (repeat_counts[idx], float(section_features[idx]["energy"])),
        )
        if labels[hook_index] == "unknown":
            labels[hook_index] = "hook"

    if "hook" not in labels and len(section_features) > 1:
        hook_candidates = [
            idx for idx, label in enumerate(labels)
            if label not in {"intro", "outro"}
        ]
        if hook_candidates:
            hook_index = max(
                hook_candidates,
                key=lambda idx: (float(section_features[idx]["energy"]), repeat_counts[idx]),
            )
            labels[hook_index] = "hook"

    for idx in repeated_indices:
        if labels[idx] != "unknown":
            continue
        labels[idx] = "verse"

    if hook_index is not None:
        for idx, item in enumerate(section_features):
            if labels[idx] != "unknown":
                continue
            if idx > hook_index and idx < len(section_features) - 1:
                labels[idx] = "bridge"

    return labels


def detect_sections(audio_path: Path, beat_times: list[float] | None = None) -> dict[str, object]:
    audio, sample_rate = librosa.load(audio_path, sr=22050, mono=True)
    duration = float(librosa.get_duration(y=audio, sr=sample_rate))
    if duration <= 0:
        return {"version": 1, "strategy": "light", "sections": []}

    beats = [float(item) for item in (beat_times or []) if 0.0 <= float(item) < duration]
    if len(beats) < SECTION_CONFIG["window_beats"] + 1:
        step = max(2.0, duration / 12.0)
        beats = list(np.arange(0.0, duration, step))
    if not beats or beats[0] > 0.0:
        beats = [0.0] + beats
    if beats[-1] < duration:
        beats.append(duration)

    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
    contrast = librosa.feature.spectral_contrast(y=audio, sr=sample_rate)
    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    frame_times = librosa.times_like(rms, sr=sample_rate)

    window_beats = int(SECTION_CONFIG["window_beats"])
    windows: list[dict[str, object]] = []
    index = 0
    while index < len(beats) - 1:
        start = beats[index]
        end_index = min(index + window_beats, len(beats) - 1)
        end = beats[end_index]
        mask = (frame_times >= start) & (frame_times < end)
        if not np.any(mask):
            index += window_beats
            continue
        energy = float(np.mean(rms[mask]))
        contrast_mean = np.mean(contrast[:, mask], axis=1)
        chroma_mean = np.mean(chroma[:, mask], axis=1)
        signature = np.concatenate(
            [
                np.asarray([energy], dtype=np.float32),
                contrast_mean.astype(np.float32),
                chroma_mean.astype(np.float32),
            ]
        )
        windows.append(
            {
                "start_seconds": round(float(start), 3),
                "end_seconds": round(float(end), 3),
                "energy": energy,
                "signature": signature,
            }
        )
        index += window_beats

    if not windows:
        return {
            "version": 1,
            "strategy": "light",
            "sections": [
                {
                    "id": "section-01",
                    "label": "unknown",
                    "start_seconds": 0.0,
                    "end_seconds": round(duration, 3),
                    "confidence": 0.3,
                    "source": "fallback_single_section",
                }
            ],
        }

    signatures = np.vstack([item["signature"] for item in windows]).astype(np.float32)
    feature_std = np.std(signatures, axis=0) + 1e-6
    normalized = (signatures - np.mean(signatures, axis=0)) / feature_std
    distances = np.linalg.norm(np.diff(normalized, axis=0), axis=1) if len(normalized) > 1 else np.asarray([], dtype=np.float32)
    distance_threshold = float(np.mean(distances) + SECTION_CONFIG["boundary_sigma"] * np.std(distances)) if distances.size else 0.0

    boundaries = [0.0]
    for idx, distance in enumerate(distances):
        candidate = float(windows[idx + 1]["start_seconds"])
        if distance <= distance_threshold:
            continue
        if candidate - boundaries[-1] < SECTION_CONFIG["merge_gap_seconds"]:
            continue
        boundaries.append(candidate)
    if duration - boundaries[-1] < SECTION_CONFIG["merge_gap_seconds"] and len(boundaries) > 1:
        boundaries[-1] = float(boundaries[-1])
    if boundaries[-1] < duration:
        boundaries.append(duration)

    merged_boundaries = [float(boundaries[0])]
    for boundary in boundaries[1:]:
        if boundary - merged_boundaries[-1] < SECTION_CONFIG["min_section_seconds"] and len(merged_boundaries) > 1:
            continue
        merged_boundaries.append(float(boundary))
    if merged_boundaries[-1] < duration:
        merged_boundaries[-1] = duration

    sections: list[dict[str, object]] = []
    section_features: list[dict[str, object]] = []
    for index, (start, end) in enumerate(zip(merged_boundaries[:-1], merged_boundaries[1:]), start=1):
        if end <= start:
            continue
        covered = [
            item for item in windows
            if float(item["start_seconds"]) < end and float(item["end_seconds"]) > start
        ]
        if covered:
            energy = float(np.mean([item["energy"] for item in covered]))
            signature = np.mean(np.vstack([item["signature"] for item in covered]), axis=0)
        else:
            energy = 0.0
            signature = np.zeros_like(windows[0]["signature"])
        section_features.append(
            {
                "id": f"section-{index:02d}",
                "start_seconds": round(float(start), 3),
                "end_seconds": round(float(end), 3),
                "energy": energy,
                "signature": signature,
            }
        )

    labels = _label_sections(section_features, duration)
    similarities = np.zeros(len(section_features), dtype=np.float32)
    for idx, current in enumerate(section_features):
        others = [
            _cosine_similarity(
                np.asarray(current["signature"], dtype=np.float32),
                np.asarray(other["signature"], dtype=np.float32),
            )
            for other_index, other in enumerate(section_features)
            if other_index != idx
        ]
        similarities[idx] = max(others) if others else 0.0

    for idx, item in enumerate(section_features):
        confidence = 0.35 + 0.65 * min(1.0, similarities[idx] if labels[idx] in {"hook", "verse"} else 0.5 + similarities[idx] / 2.0)
        sections.append(
            {
                "id": item["id"],
                "label": labels[idx],
                "start_seconds": item["start_seconds"],
                "end_seconds": item["end_seconds"],
                "confidence": round(float(confidence), 3),
                "source": "light_structure_pass",
            }
        )

    return {"version": 1, "strategy": "light", "sections": sections}


def write_sections_analysis(output_path: Path, analysis: dict[str, object]) -> Path:
    ensure_dir(output_path.parent)
    output_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _best_chord(chroma_slice: np.ndarray) -> tuple[int, str]:
    best_root = 0
    best_mode = "major"
    best_score = -1.0
    for root in range(12):
        major_score = float(np.dot(chroma_slice, np.roll(MAJOR_TRIAD, root)))
        minor_score = float(np.dot(chroma_slice, np.roll(MINOR_TRIAD, root)))
        if major_score > best_score:
            best_root = root
            best_mode = "major"
            best_score = major_score
        if minor_score > best_score:
            best_root = root
            best_mode = "minor"
            best_score = minor_score
    return best_root, best_mode


def write_chord_guide_midi(
    audio_path: Path,
    output_path: Path,
    beat_times: list[float] | None = None,
    *,
    group_beats: int = 2,
    use_bass_detection: bool = True,
) -> Path:
    """Create chord guide MIDI with improved note detection and velocity variation.
    
    Phase 3 improvements:
    - Better chord detection with bass note awareness
    - Velocity variation based on spectral energy
    - Smoother voice leading between chords
    """
    ensure_dir(output_path.parent)
    audio, sample_rate = librosa.load(audio_path, sr=22050, mono=True)
    duration = librosa.get_duration(y=audio, sr=sample_rate)
    if duration <= 0:
        raise ValueError("Cannot create chord guide from empty audio")

    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    times = librosa.times_like(chroma, sr=sample_rate)
    
    # Phase 3: Add spectral centroid for velocity mapping
    centroid = librosa.feature.spectral_centroid(y=audio, sr=sample_rate)[0]

    usable_beats = [float(item) for item in (beat_times or []) if 0.0 <= float(item) < duration]
    if len(usable_beats) < 2:
        step = max(duration / 16.0, 0.5)
        usable_beats = list(np.arange(0.0, duration, step))
    if not usable_beats or usable_beats[0] > 0.0:
        usable_beats = [0.0] + usable_beats
    if usable_beats[-1] < duration:
        usable_beats.append(duration)

    grouped_times: list[float] = []
    index = 0
    while index < len(usable_beats) - 1:
        grouped_times.append(usable_beats[index])
        index += max(1, group_beats)
    if grouped_times[-1] != usable_beats[-1]:
        grouped_times.append(usable_beats[-1])

    midi = PrettyMIDI(initial_tempo=120)
    instrument = Instrument(program=0)
    
    prev_chord_notes: set[int] = set()
    
    for i, (start, end) in enumerate(zip(grouped_times[:-1], grouped_times[1:])):
        mask = (times >= start) & (times < end)
        if not np.any(mask):
            continue
        chroma_slice = chroma[:, mask].mean(axis=1)
        if float(np.max(chroma_slice)) <= 0:
            continue
        
        # Normalize for chord detection
        chroma_norm = chroma_slice / (np.linalg.norm(chroma_slice) + 1e-12)
        root, mode = _best_chord(chroma_norm)
        
        # Phase 3: Determine bass note from low-frequency chroma
        bass_root = root
        if use_bass_detection:
            low_freq_mask = (times >= start) & (times < end)
            if np.any(low_freq_mask):
                # Use first 3 octaves for bass detection
                low_chroma = chroma[:12, mask].mean(axis=1)
                if np.max(low_chroma) > 0:
                    bass_root = int(np.argmax(low_chroma))
        
        # Phase 3: Velocity from spectral energy
        centroid_mask = (times >= start) & (times < end)
        if np.any(centroid_mask):
            avg_centroid = float(np.mean(centroid[centroid_mask]))
            # Map centroid (typically 200-4000 Hz) to velocity (60-100)
            base_velocity = 70 + int(min(30, (avg_centroid - 200) / 100))
        else:
            base_velocity = 80
        
        # Build chord with voice leading awareness
        root_pitch = 48 + root
        if mode == "major":
            intervals = (0, 4, 7)  # Major triad
        else:
            intervals = (0, 3, 7)  # Minor triad
        
        # Phase 3: Add seventh for richer chords on longer segments
        segment_length = end - start
        if segment_length >= 2.0:
            if mode == "major":
                intervals = intervals + (11,)  # Major 7th
            else:
                intervals = intervals + (10,)  # Minor 7th
        
        for j, interval in enumerate(intervals):
            pitch = root_pitch + interval
            # Phase 3: Velocity variation by chord position
            # Bass note (lowest) gets slightly higher velocity
            velocity = base_velocity - (j * 3)
            velocity = max(50, min(100, velocity))
            
            # Phase 3: Smoother voice leading - avoid large jumps
            if pitch in prev_chord_notes:
                # Keep common tones at same velocity
                velocity = max(velocity, 65)
            
            instrument.notes.append(
                Note(
                    velocity=velocity,
                    pitch=pitch,
                    start=float(start),
                    end=float(end),
                )
            )
        
        prev_chord_notes = {root_pitch + interval for interval in intervals}

    midi.instruments.append(instrument)
    midi.write(str(output_path))
    return output_path

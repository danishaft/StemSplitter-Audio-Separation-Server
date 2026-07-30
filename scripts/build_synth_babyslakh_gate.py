from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_ROOT = Path(
    "/home/ayodele/Desktop/marlon-music/marlon-model/data/external/"
    "babyslakh/extracted/babyslakh_16k"
)
SYNTH_CLASSES = {"Synth Lead", "Synth Pad"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an independent multi-track synth qualification gate."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT
        / "benchmarks/specialist_open/synth-babyslakh-9-v1",
    )
    parser.add_argument("--clip-seconds", type=float, default=10.0)
    return parser.parse_args()


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    return audio, int(sample_rate)


def sum_sources(paths: list[Path]) -> tuple[np.ndarray, int]:
    mixed: np.ndarray | None = None
    sample_rate: int | None = None
    for path in paths:
        audio, current_rate = read_audio(path)
        if sample_rate is None:
            sample_rate = current_rate
        elif current_rate != sample_rate:
            raise RuntimeError(f"sample rate mismatch: {path}")
        if mixed is None:
            mixed = np.zeros_like(audio)
        length = min(len(mixed), len(audio))
        mixed = mixed[:length]
        mixed += audio[:length]
    if mixed is None or sample_rate is None:
        raise RuntimeError("cannot sum an empty source list")
    return mixed, sample_rate


def strongest_window(reference: np.ndarray, window: int) -> int:
    mono_power = np.mean(np.square(reference), axis=1)
    if len(mono_power) <= window:
        return 0
    cumulative = np.concatenate(([0.0], np.cumsum(mono_power)))
    hop = max(1, window // 10)
    starts = np.arange(0, len(mono_power) - window + 1, hop)
    energies = cumulative[starts + window] - cumulative[starts]
    return int(starts[int(np.argmax(energies))])


def main() -> int:
    args = parse_args()
    dataset_root = args.dataset_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if args.clip_seconds <= 0:
        raise SystemExit("clip-seconds must be positive")

    mix_clips: list[np.ndarray] = []
    reference_clips: list[np.ndarray] = []
    segments: list[dict[str, object]] = []
    sample_rate: int | None = None

    for track_dir in sorted(dataset_root.glob("Track*")):
        metadata = yaml.safe_load(
            (track_dir / "metadata.yaml").read_text(encoding="utf-8")
        )
        source_ids = [
            stem_id
            for stem_id, stem in metadata.get("stems", {}).items()
            if str(stem.get("inst_class", "")) in SYNTH_CLASSES
            and (track_dir / "stems" / f"{stem_id}.wav").is_file()
        ]
        if not source_ids:
            continue

        reference, reference_rate = sum_sources(
            [track_dir / "stems" / f"{stem_id}.wav" for stem_id in source_ids]
        )
        mixture, mixture_rate = read_audio(track_dir / "mix.wav")
        if reference_rate != mixture_rate:
            raise RuntimeError(f"mixture sample rate mismatch: {track_dir}")
        if sample_rate is None:
            sample_rate = reference_rate
        elif reference_rate != sample_rate:
            raise RuntimeError(f"dataset sample rate mismatch: {track_dir}")

        clip_frames = int(round(args.clip_seconds * reference_rate))
        common_length = min(len(reference), len(mixture))
        reference = reference[:common_length]
        mixture = mixture[:common_length]
        start = strongest_window(reference, clip_frames)
        stop = min(start + clip_frames, common_length)
        if stop - start < clip_frames:
            start = max(0, stop - clip_frames)
        mix_clip = mixture[start:stop]
        reference_clip = reference[start:stop]
        if len(mix_clip) < clip_frames:
            padding = clip_frames - len(mix_clip)
            mix_clip = np.pad(mix_clip, ((0, padding), (0, 0)))
            reference_clip = np.pad(reference_clip, ((0, padding), (0, 0)))

        mix_clips.append(mix_clip)
        reference_clips.append(reference_clip)
        segments.append(
            {
                "track_id": track_dir.name,
                "source_ids": source_ids,
                "source_classes": sorted(SYNTH_CLASSES),
                "source_start_seconds": round(start / reference_rate, 3),
                "gate_start_seconds": round(
                    (len(segments) * clip_frames) / reference_rate,
                    3,
                ),
                "duration_seconds": args.clip_seconds,
            }
        )

    if not segments or sample_rate is None:
        raise SystemExit("no positive synth tracks found")

    output_root.mkdir(parents=True, exist_ok=True)
    mixture_path = output_root / "mix.wav"
    reference_path = output_root / "reference_synth.wav"
    sf.write(
        mixture_path,
        np.concatenate(mix_clips),
        sample_rate,
        subtype="PCM_16",
    )
    sf.write(
        reference_path,
        np.concatenate(reference_clips),
        sample_rate,
        subtype="PCM_16",
    )
    receipt = {
        "schema_version": "1.0",
        "gate_id": output_root.name,
        "dataset": "BabySlakh 16k",
        "target_classes": sorted(SYNTH_CLASSES),
        "sample_rate": sample_rate,
        "clip_seconds": args.clip_seconds,
        "segment_count": len(segments),
        "total_duration_seconds": round(
            len(segments) * args.clip_seconds,
            3,
        ),
        "mixture": str(mixture_path),
        "reference": str(reference_path),
        "selection": "maximum_target_energy_with_one_second_hop",
        "segments": segments,
    }
    (output_root / "gate.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from array import array
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = (
    ROOT
    / "datasets/staging/rawstems/current-pinned-at-acquisition/selections/"
    "rawstems-curated-specialists-v1"
)
DEFAULT_OUTPUT = ROOT / "datasets/calibration/synth-cleaner-v1"
DEFAULT_MANIFEST = (
    ROOT / "datasets/manifests/calibration/synth-cleaner-v1.json"
)
AUDIO_SUFFIXES = {".flac", ".wav"}
LABEL_GROUPS = {
    "positive": {"Synth"},
    "confuser": {"Gtr", "Kbs", "Orch"},
    "target_absent": {"Bass", "Rhy", "Voc"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a song-disjoint synth-cleaner calibration corpus."
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--clip-seconds", type=float, default=24.0)
    parser.add_argument("--confuser-songs", type=int, default=25)
    parser.add_argument("--target-absent-songs", type=int, default=25)
    parser.add_argument("--calibration-fraction", type=float, default=0.7)
    parser.add_argument("--seed", default="synth-cleaner-v1")
    return parser.parse_args()


def stable_order(values: set[str], namespace: str) -> list[str]:
    return sorted(
        values,
        key=lambda value: hashlib.sha256(
            f"{namespace}:{value}".encode()
        ).hexdigest(),
    )


def inventory(root: Path) -> dict[str, dict[str, list[Path]]]:
    pools: dict[str, dict[str, list[Path]]] = {
        label: defaultdict(list) for label in LABEL_GROUPS
    }
    for path in root.rglob("*"):
        if path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        parts = path.relative_to(root).parts
        if len(parts) < 2:
            continue
        song_id, group = parts[:2]
        for label, groups in LABEL_GROUPS.items():
            if group in groups:
                pools[label][song_id].append(path)
                break
    return pools


def decode_probe(path: Path, sample_rate: int = 2000) -> array:
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    samples = array("f")
    samples.frombytes(result.stdout)
    return samples


def strongest_offset(samples: array, clip_seconds: float, sample_rate: int) -> float:
    window = round(clip_seconds * sample_rate)
    if len(samples) < window:
        raise ValueError("source_shorter_than_calibration_clip")
    hop = max(1, round(2.0 * sample_rate))
    energy = sum(value * value for value in samples[:window])
    best_energy = energy
    best_start = 0
    start = hop
    while start + window <= len(samples):
        previous = start - hop
        energy -= sum(
            value * value for value in samples[previous : previous + hop]
        )
        energy += sum(
            value * value
            for value in samples[start + window - hop : start + window]
        )
        if energy > best_energy:
            best_energy = energy
            best_start = start
        start += hop
    return best_start / sample_rate


def export_clip(
    source: Path,
    destination: Path,
    offset: float,
    clip_seconds: float,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-ss",
            f"{offset:.6f}",
            "-i",
            str(source),
            "-t",
            f"{clip_seconds:.6f}",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "flac",
            str(destination),
        ],
        check=True,
    )


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def pick_songs(
    pools: dict[str, dict[str, list[Path]]],
    seed: str,
    confuser_count: int,
    absent_count: int,
) -> dict[str, list[str]]:
    positive = stable_order(set(pools["positive"]), f"{seed}:positive")
    used = set(positive)
    absent_available = set(pools["target_absent"]) - used
    absent = stable_order(absent_available, f"{seed}:target_absent")[
        :absent_count
    ]
    used.update(absent)
    confuser_available = set(pools["confuser"]) - used
    confuser = stable_order(confuser_available, f"{seed}:confuser")[
        :confuser_count
    ]
    return {
        "positive": positive,
        "confuser": confuser,
        "target_absent": absent,
    }


def split_assignments(
    selected: dict[str, list[str]],
    fraction: float,
    seed: str,
) -> dict[tuple[str, str], str]:
    assignments = {}
    for label, songs in selected.items():
        ordered = stable_order(set(songs), f"{seed}:{label}:split")
        cutoff = math.ceil(len(ordered) * fraction)
        for index, song_id in enumerate(ordered):
            assignments[(label, song_id)] = (
                "calibration" if index < cutoff else "validation"
            )
    return assignments


def main() -> int:
    args = parse_args()
    source_root = args.source_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    pools = inventory(source_root)
    selected = pick_songs(
        pools,
        args.seed,
        args.confuser_songs,
        args.target_absent_songs,
    )
    assignments = split_assignments(
        selected,
        args.calibration_fraction,
        args.seed,
    )

    candidates = []
    failures = []
    for label, songs in selected.items():
        for song_id in songs:
            paths = sorted(
                pools[label][song_id],
                key=lambda path: (-path.stat().st_size, str(path)),
            )
            for source in paths:
                try:
                    samples = decode_probe(source)
                    offset = strongest_offset(samples, args.clip_seconds, 2000)
                    break
                except (subprocess.CalledProcessError, ValueError):
                    source = None
            if source is None:
                failures.append({"label": label, "song_id": song_id})
                continue
            candidate_id = hashlib.sha256(
                f"{label}:{song_id}:{source}".encode()
            ).hexdigest()[:20]
            destination = (
                output_root
                / label
                / f"{candidate_id}.flac"
            )
            export_clip(source, destination, offset, args.clip_seconds)
            candidates.append(
                {
                    "id": candidate_id,
                    "path": str(destination),
                    "metadata": {
                        "label": label,
                        "song_id": song_id,
                        "split": assignments[(label, song_id)],
                        "source_path": str(source),
                        "source_sha256": file_digest(source),
                        "clip_offset_seconds": offset,
                        "clip_seconds": args.clip_seconds,
                    },
                }
            )

    counts = Counter(
        (item["metadata"]["label"], item["metadata"]["split"])
        for item in candidates
    )
    manifest = {
        "schema_version": "1.0",
        "calibration_id": "synth-cleaner-v1",
        "source_id": "rawstems",
        "source_root": str(source_root),
        "split_policy": "song_disjoint_across_labels_and_splits",
        "clip_selection": "highest_energy_fixed_duration",
        "clip_seconds": args.clip_seconds,
        "seed": args.seed,
        "candidate_count": len(candidates),
        "counts": {
            f"{label}:{split_name}": count
            for (label, split_name), count in sorted(counts.items())
        },
        "failures": failures,
        "candidates": candidates,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "counts": manifest["counts"],
                "failure_count": len(failures),
                "manifest": str(manifest_path),
            },
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

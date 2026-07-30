from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from build_synth_cleaner_calibration import (
    decode_probe,
    export_clip,
    file_digest,
    stable_order,
    strongest_offset,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = (
    ROOT
    / "datasets/staging/rawstems/current-pinned-at-acquisition/selections/"
    "rawstems-curated-specialists-v1"
)
DEFAULT_OUTPUT = ROOT / "datasets/calibration/acmid-cleaner-v1"
DEFAULT_MANIFEST = (
    ROOT / "datasets/manifests/calibration/acmid-cleaner-v1.json"
)
FAMILY_PATHS = {
    "acoustic_guitar": ("/gtr/ag/",),
    "electric_guitar": ("/gtr/eg/",),
    "strings": ("/orch/str/",),
    "wind_brass": ("/orch/br/", "/orch/ww/"),
}
INSTRUMENTS = {
    "acoustic_guitar": "acoustic_guitar",
    "electric_guitar": "electric_guitar",
    "strings": "strings",
    "wind_brass": "wind",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the independent ACMID cleaner benchmark corpus."
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--clip-seconds", type=float, default=45.0)
    parser.add_argument("--positive-songs", type=int, default=25)
    parser.add_argument("--negative-songs", type=int, default=25)
    parser.add_argument("--seed", default="acmid-cleaner-v1")
    return parser.parse_args()


def classify(relative_path: Path) -> str | None:
    normalized = f"/{str(relative_path).lower()}/"
    for family, markers in FAMILY_PATHS.items():
        if any(marker in normalized for marker in markers):
            return family
    return None


def inventory(root: Path) -> dict[str, dict[str, list[Path]]]:
    pools = {
        family: defaultdict(list)
        for family in FAMILY_PATHS
    }
    for path in root.rglob("*"):
        if path.suffix.lower() not in {".flac", ".wav"}:
            continue
        relative_path = path.relative_to(root)
        family = classify(relative_path)
        if family is not None:
            pools[family][relative_path.parts[0]].append(path)
    return pools


def choose_source(
    paths: list[Path],
    clip_seconds: float,
) -> tuple[Path, float] | None:
    for path in sorted(paths, key=lambda item: (-item.stat().st_size, str(item))):
        try:
            samples = decode_probe(path)
            offset = strongest_offset(samples, clip_seconds, 2000)
            return path, offset
        except (ValueError, OSError):
            continue
    return None


def main() -> int:
    args = parse_args()
    source_root = args.source_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    pools = inventory(source_root)
    all_songs = set().union(*(set(pool) for pool in pools.values()))
    candidates = []
    failures = []

    for family, pool in pools.items():
        positives = stable_order(
            set(pool),
            f"{args.seed}:{family}:positive",
        )[: args.positive_songs]
        negative_songs = stable_order(
            all_songs - set(pool),
            f"{args.seed}:{family}:negative",
        )[: args.negative_songs]
        selections = [
            ("positive", song_id, pool[song_id])
            for song_id in positives
        ]
        for song_id in negative_songs:
            paths = [
                path
                for other_family, other_pool in pools.items()
                if other_family != family
                for path in other_pool.get(song_id, [])
            ]
            selections.append(("negative", song_id, paths))

        for label, song_id, paths in selections:
            selected = choose_source(paths, args.clip_seconds)
            if selected is None:
                failures.append(
                    {"family": family, "label": label, "song_id": song_id}
                )
                continue
            source, offset = selected
            candidate_id = hashlib.sha256(
                f"{family}:{label}:{song_id}:{source}".encode()
            ).hexdigest()[:20]
            destination = (
                output_root / family / label / f"{candidate_id}.flac"
            )
            export_clip(source, destination, offset, args.clip_seconds)
            candidates.append(
                {
                    "id": candidate_id,
                    "path": str(destination),
                    "instrument": INSTRUMENTS[family],
                    "metadata": {
                        "benchmark_family": family,
                        "label": label,
                        "song_id": song_id,
                        "source_path": str(source),
                        "source_sha256": file_digest(source),
                        "clip_offset_seconds": offset,
                        "clip_seconds": args.clip_seconds,
                    },
                }
            )

    counts = Counter(
        (
            candidate["metadata"]["benchmark_family"],
            candidate["metadata"]["label"],
        )
        for candidate in candidates
    )
    manifest = {
        "schema_version": "1.0",
        "benchmark_id": "acmid-cleaner-v1",
        "source_id": "rawstems",
        "split_policy": "song_disjoint_within_each_family",
        "threshold_policy": "official_fixed_0.995",
        "targets": {
            "minimum_precision": 0.99,
            "minimum_recall": 0.5,
            "minimum_chunks_per_label": 200,
        },
        "clip_seconds": args.clip_seconds,
        "candidate_count": len(candidates),
        "counts": {
            f"{family}:{label}": count
            for (family, label), count in sorted(counts.items())
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

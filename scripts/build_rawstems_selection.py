from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_corpus import classify_target_family  # noqa: E402
from splitter.training_data_acquisition import (  # noqa: E402
    _remote_zip_selection_runs,
)
from splitter.training_data_registry import (  # noqa: E402
    load_training_data_registry,
)

CURATION = (
    ROOT / "datasets" / "manifests" / "curation" / "xlance-rawstems-v1.json"
)
BASELINE_SPLITS = (
    ROOT
    / "datasets"
    / "manifests"
    / "splits"
    / "rawstems-family-aware-song-disjoint-v1-baseline.json"
)
INVENTORY_ROOT = (
    ROOT
    / "datasets"
    / "inventories"
    / "rawstems"
    / "current-pinned-at-acquisition"
)
OUTPUT = (
    ROOT
    / "datasets"
    / "manifests"
    / "selections"
    / "rawstems-curated-specialists-v1.json"
)
FAMILIES = (
    "acoustic_guitar",
    "electric_guitar",
    "strings",
    "synth",
    "wind_brass",
)
HELD_OUT_PER_SPLIT = 18
AUDIO_SUFFIXES = {".flac", ".wav", ".aif", ".aiff"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_inventory(index: int) -> tuple[Path, dict[str, Any]]:
    path = INVENTORY_ROOT / f"RawStems_{index}.zip.entries.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    return path, payload


def _rank(split: str, song_id: str) -> bytes:
    return hashlib.sha256(
        f"rawstems-specialists-v1:{split}:{song_id}".encode()
    ).digest()


def _minimum_cost_artists(
    split: str,
    remaining_artists: set[str],
    songs_by_artist: dict[str, set[str]],
    available_families: dict[str, set[str]],
    context_sizes: dict[str, int],
    baseline_assignments: dict[str, str],
) -> tuple[str, ...]:
    artists = sorted(remaining_artists, key=lambda item: _rank(split, item))
    contributions = np.asarray(
        [
            [
                sum(
                    family in available_families[song_id]
                    for song_id in songs_by_artist[artist_id]
                )
                for artist_id in artists
            ]
            for family in FAMILIES
        ],
        dtype=float,
    )
    if np.any(contributions.sum(axis=1) < HELD_OUT_PER_SPLIT):
        raise RuntimeError(
            f"cannot allocate {HELD_OUT_PER_SPLIT} {split} songs "
            "for every specialist family"
        )

    context_mib = np.asarray(
        [
            sum(
                context_sizes.get(song_id, 0)
                for song_id in songs_by_artist[artist_id]
                if baseline_assignments.get(song_id, "train") == "train"
            )
            / (1024 * 1024)
            for artist_id in artists
        ],
        dtype=float,
    )
    moved_songs = np.asarray(
        [
            sum(
                baseline_assignments.get(song_id, "train") != split
                for song_id in songs_by_artist[artist_id]
            )
            for artist_id in artists
        ],
        dtype=float,
    )
    # Context transfer dominates, then baseline churn and deterministic rank.
    rank_tiebreak = np.arange(len(artists), dtype=float) / max(
        1,
        len(artists),
    )
    objective = context_mib + moved_songs * 1e-3 + rank_tiebreak * 1e-6
    result = milp(
        c=objective,
        integrality=np.ones(len(artists), dtype=int),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(
            contributions,
            lb=np.full(len(FAMILIES), HELD_OUT_PER_SPLIT, dtype=float),
            ub=np.full(len(FAMILIES), np.inf, dtype=float),
        ),
        options={"time_limit": 300},
    )
    if not result.success or result.x is None:
        raise RuntimeError(
            f"cannot allocate {HELD_OUT_PER_SPLIT} {split} songs "
            f"for every specialist family: {result.message}"
        )
    selected = tuple(
        artist_id
        for artist_id, value in zip(artists, result.x, strict=True)
        if value >= 0.5
    )
    actual = contributions[:, result.x >= 0.5].sum(axis=1)
    if np.any(actual < HELD_OUT_PER_SPLIT):
        raise RuntimeError(
            f"solver returned an invalid {split} specialist allocation"
        )
    return selected


def _allocate_held_out(
    available_families: dict[str, set[str]],
    context_sizes: dict[str, int],
    baseline_assignments: dict[str, str],
) -> dict[str, str]:
    songs_by_artist: dict[str, set[str]] = {}
    for song_id in available_families:
        artist_id = song_id.split("|", 1)[0]
        songs_by_artist.setdefault(artist_id, set()).add(song_id)

    candidates: list[tuple[tuple[int, int, bytes], dict[str, str]]] = []
    for order in (("test", "validation"), ("validation", "test")):
        remaining_artists = set(songs_by_artist)
        assignments: dict[str, str] = {}
        try:
            for split in order:
                selected = _minimum_cost_artists(
                    split,
                    remaining_artists,
                    songs_by_artist,
                    available_families,
                    context_sizes,
                    baseline_assignments,
                )
                for artist_id in selected:
                    remaining_artists.remove(artist_id)
                    for song_id in songs_by_artist[artist_id]:
                        assignments[song_id] = split
        except RuntimeError:
            continue
        for artist_id in remaining_artists:
            for song_id in songs_by_artist[artist_id]:
                assignments[song_id] = "train"
        selected_songs = {
            song_id
            for song_id, split in assignments.items()
            if split != "train"
        }
        score = (
            sum(
                context_sizes.get(song_id, 0)
                for song_id in selected_songs
                if baseline_assignments.get(song_id, "train") == "train"
            ),
            sum(
                baseline_assignments.get(song_id, "train") != split
                for song_id, split in assignments.items()
            ),
            _rank("allocation", "|".join(order)),
        )
        candidates.append((score, assignments))
    if not candidates:
        raise RuntimeError("no artist-disjoint held-out allocation is feasible")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def main() -> int:
    registry = load_training_data_registry()
    source = registry.sources["rawstems"]
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE_SPLITS.read_text(encoding="utf-8"))
    baseline_assignments = baseline["song_split_assignments"]
    curated_songs = curation["songs"]

    inventories: list[tuple[Path, dict[str, Any]]] = []
    entry_rows: list[dict[str, Any]] = []
    available_families: dict[str, set[str]] = {}
    context_sizes: dict[str, int] = {}
    provider_revisions: set[str] = set()
    for index in range(1, 7):
        inventory_path, inventory = _load_inventory(index)
        inventories.append((inventory_path, inventory))
        archive_path = str(inventory["provider_path"])
        provider_revision = str(inventory.get("provider_revision") or "")
        if provider_revision:
            provider_revisions.add(provider_revision)
        for entry in inventory["entries"]:
            path = Path(str(entry["path"]))
            if entry.get("is_directory") or path.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            song_id = path.parts[0]
            curated = curated_songs.get(song_id)
            if not isinstance(curated, dict):
                continue
            family, _ = classify_target_family(source, path)
            curated_families = set(curated.get("families") or [])
            if family is not None and family not in curated_families:
                family = None
            if family is not None:
                available_families.setdefault(song_id, set()).add(family)
            else:
                context_sizes[song_id] = (
                    context_sizes.get(song_id, 0)
                    + int(entry["compressed_size_bytes"])
                )
            entry_rows.append(
                {
                    "archive": archive_path,
                    "path": str(entry["path"]),
                    "song_id": song_id,
                    "family": family,
                    "compressed_size_bytes": int(
                        entry["compressed_size_bytes"]
                    ),
                    "uncompressed_size_bytes": int(
                        entry["uncompressed_size_bytes"]
                    ),
                }
            )

    assignments = _allocate_held_out(
        available_families,
        context_sizes,
        baseline_assignments,
    )
    selected: list[dict[str, Any]] = []
    for row in entry_rows:
        split = assignments.get(row["song_id"])
        if split is None:
            continue
        if split == "train" and row["family"] is None:
            continue
        selected.append(
            {
                **row,
                "split": split,
                "role": (
                    "target" if row["family"] is not None else "hard_negative"
                ),
            }
        )

    archive_rows = []
    total_transfer_size = 0
    maximum_run_size = 0
    for inventory_path, inventory in inventories:
        archive_path = str(inventory["provider_path"])
        entries = [
            row for row in selected if row["archive"] == archive_path
        ]
        selected_paths = {row["path"] for row in entries}
        runs = _remote_zip_selection_runs(
            inventory["entries"],
            selected_paths=selected_paths,
            archive_size=int(inventory["provider_size_bytes"]),
        )
        transfer_size = sum(
            int(run["end"]) - int(run["start"]) + 1 for run in runs
        )
        max_run_size = max(
            (
                int(run["end"]) - int(run["start"]) + 1
                for run in runs
            ),
            default=0,
        )
        total_transfer_size += transfer_size
        maximum_run_size = max(maximum_run_size, max_run_size)
        archive_rows.append(
            {
                "provider_path": archive_path,
                "provider_size_bytes": int(inventory["provider_size_bytes"]),
                "provider_checksum_algorithm": inventory.get(
                    "provider_checksum_algorithm"
                ),
                "provider_checksum": inventory.get("provider_checksum"),
                "provider_revision": inventory.get("provider_revision"),
                "remote_inventory": str(inventory_path.relative_to(ROOT)),
                "remote_inventory_sha256": _sha256(inventory_path),
                "entry_count": len(entries),
                "range_run_count": len(runs),
                "transfer_size_bytes": transfer_size,
                "maximum_run_size_bytes": max_run_size,
                "compressed_size_bytes": sum(
                    row["compressed_size_bytes"] for row in entries
                ),
                "uncompressed_size_bytes": sum(
                    row["uncompressed_size_bytes"] for row in entries
                ),
                "paths": [row["path"] for row in entries],
            }
        )

    family_split_counts = {
        family: {
            split: len(
                {
                    row["song_id"]
                    for row in selected
                    if row["family"] == family and row["split"] == split
                }
            )
            for split in ("train", "validation", "test")
        }
        for family in FAMILIES
    }
    payload = {
        "schema_version": "1.0",
        "selection_name": "rawstems-curated-specialists-v1",
        "source_id": "rawstems",
        "source_version": source.version,
        "provider_revisions": sorted(provider_revisions),
        "curation_manifest": str(CURATION.relative_to(ROOT)),
        "curation_manifest_sha256": _sha256(CURATION),
        "xlance_commit": curation["xlance_commit"],
        "split_policy": {
            "name": "baseline-preserving-family-aware-artist-disjoint-v2",
            "held_out_songs_per_family_per_split": HELD_OUT_PER_SPLIT,
            "baseline_manifest": str(BASELINE_SPLITS.relative_to(ROOT)),
            "baseline_manifest_sha256": _sha256(BASELINE_SPLITS),
            "migration_policy": (
                "minimum-cost whole-artist allocation by newly required "
                "train-song context bytes"
            ),
        },
        "family_split_song_counts": family_split_counts,
        "song_split_assignments": dict(sorted(assignments.items())),
        "entry_count": len(selected),
        "song_count": len({row["song_id"] for row in selected}),
        "compressed_size_bytes": sum(
            row["compressed_size_bytes"] for row in selected
        ),
        "transfer_size_bytes": total_transfer_size,
        "maximum_run_size_bytes": maximum_run_size,
        "uncompressed_size_bytes": sum(
            row["uncompressed_size_bytes"] for row in selected
        ),
        "archives": archive_rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT.relative_to(ROOT)),
                "entry_count": payload["entry_count"],
                "song_count": payload["song_count"],
                "compressed_size_bytes": payload["compressed_size_bytes"],
                "transfer_size_bytes": payload["transfer_size_bytes"],
                "maximum_run_size_bytes": payload[
                    "maximum_run_size_bytes"
                ],
                "uncompressed_size_bytes": payload[
                    "uncompressed_size_bytes"
                ],
                "family_split_song_counts": family_split_counts,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from training.manifests import (  # noqa: E402
    FAMILIES,
    PROFILE_PATHS,
    TrainingManifestError,
    load_audited_items,
)

REMOTE_ROOT = Path("/training/source_audio")
SELECTION_ROOTS = {
    "albumdb": ROOT
    / "datasets/staging/albumdb/zenodo-19683000/selections/raw-stems",
    "cocochorales": ROOT
    / (
        "datasets/staging/cocochorales/full-v1-train-shards-1-25/"
        "selections/bounded-main-train-v1"
    ),
    "eg_ipt": ROOT
    / "datasets/staging/eg_ipt/zenodo-15205644/selections/dyn-close-mic",
    "medleydb_sample": ROOT
    / (
        "datasets/staging/medleydb_sample/zenodo-1438309/"
        "selections/audio-only-v1"
    ),
    "rawstems": ROOT
    / (
        "datasets/staging/rawstems/current-pinned-at-acquisition/"
        "selections/rawstems-curated-specialists-v1"
    ),
    "spheres": ROOT
    / (
        "datasets/staging/spheres/zenodo-17347681/"
        "selections/stereo-mix-audio-v1"
    ),
    "urmp": ROOT
    / (
        "datasets/staging/urmp/zenodo-5034983/"
        "selections/audio-only-v1"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build X-LANCE-style on-the-fly training indexes."
    )
    parser.add_argument(
        "--profile",
        choices=("research_all", "release_eligible"),
        default="research_all",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "training/online_indexes",
    )
    return parser.parse_args()


@lru_cache(maxsize=None)
def _archive_members(
    source_id: str,
    version: str,
) -> dict[str, Path]:
    manifests = sorted(
        (
            ROOT
            / "datasets/manifests/items"
            / source_id
            / version
        ).glob("*/items.jsonl")
    )
    result: dict[str, Path] = {}
    for manifest in manifests:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            audio_hash = str(item.get("audio", {}).get("sha256") or "")
            if not audio_hash:
                continue
            result[audio_hash] = (
                ROOT
                / "datasets/extracted"
                / source_id
                / version
                / manifest.parent.name
                / str(item["relative_path"])
            )
    return result


def _archive_root(row: dict[str, Any]) -> Path:
    source_id = str(row["source_id"])
    version = str(row["source_version"])
    audio_hash = str(row["audio"]["sha256"])
    try:
        return _archive_members(source_id, version)[audio_hash]
    except KeyError as exc:
        raise TrainingManifestError(
            f"cannot resolve archive member for {source_id}:{audio_hash}"
        ) from exc


def _source_path(row: dict[str, Any]) -> Path:
    value = str(row.get("local_path") or "")
    if value:
        local = Path(value)
        if not local.is_absolute():
            local = ROOT / local
        if local.is_file():
            return local
    root = SELECTION_ROOTS.get(str(row["source_id"]))
    if root is not None:
        return root / str(row["relative_path"])
    return _archive_root(row)


def _remote_path(local: Path) -> str:
    try:
        relative = local.relative_to(ROOT)
    except ValueError as exc:
        raise TrainingManifestError(
            f"training source is outside repository storage: {local}"
        ) from exc
    return str(REMOTE_ROOT / relative)


def _indexed_path(row: dict[str, Any]) -> str:
    local_path = Path(str(row.get("local_path") or ""))
    if local_path.is_absolute():
        if "source_audio" in local_path.parts:
            source_index = local_path.parts.index("source_audio")
            return str(
                REMOTE_ROOT.joinpath(*local_path.parts[source_index + 1 :])
            )
        try:
            local_path.relative_to(REMOTE_ROOT)
        except ValueError:
            pass
        else:
            return str(local_path)
    return _remote_path(_source_path(row))


def _digest(rows: list[dict[str, str]]) -> str:
    payload = "\n".join(
        f"{row['instrum']},{row['path']},{row['sha256']}" for row in rows
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    args = parse_args()
    try:
        profile_manifest = json.loads(
            PROFILE_PATHS[args.profile].read_text(encoding="utf-8")
        )
        profile_families = tuple(profile_manifest["target_families"])
        if profile_families != FAMILIES:
            raise TrainingManifestError(
                "profile target families do not match the training contract: "
                f"{profile_families!r} != {FAMILIES!r}"
            )
        output_dir = (
            args.output_root.expanduser().resolve() / args.profile
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        reports: dict[str, Any] = {}
        for family in FAMILIES:
            source_ids = profile_manifest["family_sources"][family]
            items = load_audited_items(args.profile, source_ids)
            indexed: dict[str, dict[str, str]] = {}
            pending = 0
            for row in items:
                if row["split"] != "train":
                    continue
                if row.get("family") == family:
                    label = family
                elif (
                    row.get("item_role") == "hard_negative"
                    or row.get("family") in FAMILIES
                ):
                    label = "other"
                else:
                    continue
                indexed_path = _indexed_path(row)
                if not Path(indexed_path).is_file():
                    pending += 1
                audio_hash = str(row["audio"]["sha256"])
                candidate = {
                    "instrum": label,
                    "path": indexed_path,
                    "sha256": audio_hash,
                    "source_id": str(row["source_id"]),
                    "composition_id": str(row["composition_id"]),
                }
                prior = indexed.get(audio_hash)
                if prior is None or label == family:
                    indexed[audio_hash] = candidate

            rows = sorted(
                indexed.values(),
                key=lambda row: (
                    row["instrum"],
                    row["source_id"],
                    row["composition_id"],
                    row["path"],
                ),
            )
            counts = {
                label: sum(row["instrum"] == label for row in rows)
                for label in (family, "other")
            }
            if not all(counts.values()):
                raise TrainingManifestError(
                    f"empty online training class for {family}: {counts}"
                )
            csv_path = output_dir / f"{family}.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            reports[family] = {
                "path": str(csv_path.relative_to(ROOT)),
                "row_count": len(rows),
                "counts": counts,
                "sources": sorted({row["source_id"] for row in rows}),
                "pending_materialization_count": pending,
                "sha256": _digest(rows),
            }

        receipt = {
            "schema_version": "1.0",
            "profile": args.profile,
            "method": "on_the_fly_random_stem_mixing",
            "segment_seconds": 10,
            "families": reports,
        }
        (output_dir / "index.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        KeyError,
        OSError,
        TrainingManifestError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"online training index build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

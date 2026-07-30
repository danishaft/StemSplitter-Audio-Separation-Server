from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XLANCE_ROOT = ROOT / "external_repos" / "xlance-msr"
SPLIT_ROOT = XLANCE_ROOT / "data" / "data_split"
OUTPUT = ROOT / "datasets" / "manifests" / "curation" / "xlance-rawstems-v1.json"

FAMILY_LISTS = {
    "acoustic_guitar": ("Gtr_AG_train.txt", "Gtr_AG_test.txt"),
    "electric_guitar": ("Gtr_EG_train.txt", "Gtr_EG_test.txt"),
    "synth": ("Synth_train.txt", "Synth_test.txt"),
    "strings": ("Orch_STR_train.txt", "Orch_STR_test.txt"),
    "wind_brass": (
        "Orch_WW_train.txt",
        "Orch_WW_test.txt",
        "Orch_BR_train.txt",
        "Orch_BR_test.txt",
    ),
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    commit = subprocess.check_output(
        ["git", "-C", str(XLANCE_ROOT), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    songs: dict[str, dict[str, object]] = {}
    inputs: dict[str, dict[str, object]] = {}

    for family, filenames in FAMILY_LISTS.items():
        for filename in filenames:
            path = SPLIT_ROOT / filename
            declared_split = "test" if "_test." in filename else "train"
            values = [line.strip() for line in path.read_text().splitlines() if line.strip()]
            inputs[filename] = {
                "sha256": file_sha256(path),
                "entry_count": len(values),
            }
            for value in values:
                song_id = value.removeprefix("RawStems/")
                row = songs.setdefault(
                    song_id,
                    {
                        "song_id": song_id,
                        "families": [],
                        "xlance_declared_splits": [],
                        "source_lists": [],
                    },
                )
                if family not in row["families"]:
                    row["families"].append(family)
                if declared_split not in row["xlance_declared_splits"]:
                    row["xlance_declared_splits"].append(declared_split)
                row["source_lists"].append(filename)

    payload = {
        "schema_version": "1.0",
        "source_id": "rawstems",
        "curation_source": "X-LANCE xlance-msr",
        "xlance_commit": commit,
        "split_policy": (
            "Use the lists as label-curation evidence only. Assign one deterministic "
            "composition-level split in our corpus builder."
        ),
        "inputs": inputs,
        "family_counts": {
            family: sum(family in row["families"] for row in songs.values())
            for family in FAMILY_LISTS
        },
        "unique_song_count": len(songs),
        "songs": {
            song_id: {
                **row,
                "families": sorted(row["families"]),
                "xlance_declared_splits": sorted(row["xlance_declared_splits"]),
                "source_lists": sorted(row["source_lists"]),
            }
            for song_id, row in sorted(songs.items())
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {OUTPUT} with {len(songs)} unique songs and "
        f"family counts {payload['family_counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

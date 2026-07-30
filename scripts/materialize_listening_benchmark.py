#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.object_storage import object_store_from_config
from splitter.util import ensure_dir


RELEASE_STEMS = {
    "vocals",
    "instrumental",
    "drums",
    "bass",
    "guitar",
    "piano",
    "kick",
    "snare",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download private benchmark stems and create a listening sheet."
    )
    parser.add_argument("report", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--all", action="store_true", help="include ground-truth songs")
    args = parser.parse_args()

    report_path = args.report.expanduser().resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    store = object_store_from_config()
    if store is None:
        raise SystemExit("object storage is not configured")
    output_dir = ensure_dir(args.output_dir.expanduser().resolve())
    rows: list[dict[str, object]] = []
    downloaded = 0
    for result in report.get("results", []):
        if not args.all and result.get("evidence_level") != "blind_listening_only":
            continue
        song_id = str(result["song_id"])
        artifacts = result.get("object_artifacts")
        if not isinstance(artifacts, dict):
            continue
        mixture = (
            report_path.parent / "inputs" / f"{song_id}.wav"
        ).resolve()
        for group in artifacts.values():
            if not isinstance(group, dict):
                continue
            for stem, reference in group.items():
                if stem not in RELEASE_STEMS or not isinstance(reference, dict):
                    continue
                target = output_dir / song_id / f"{stem}.wav"
                store.download(reference, target)
                downloaded += 1
                rows.append(
                    {
                        "song_id": song_id,
                        "stem": stem,
                        "mixture_path": str(mixture),
                        "stem_path": str(target.resolve()),
                        "isolation_1_to_5": "",
                        "artifacts_1_to_5": "",
                        "musicality_1_to_5": "",
                        "comments": "",
                    }
                )

    review_path = output_dir / "listening-review.csv"
    fieldnames = list(rows[0]) if rows else ["song_id", "stem"]
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"downloaded_stems={downloaded}")
    print(f"review_csv={review_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

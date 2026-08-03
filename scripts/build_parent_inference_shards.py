from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from training.parent_shards import (  # noqa: E402
    ParentShardError,
    build_parent_shards,
    pending_parent_receipts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pack pending parent inputs into efficient inference shards."
    )
    parser.add_argument(
        "--rendered-root",
        type=Path,
        default=ROOT / "training" / "rendered",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "training" / "parent_shards",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        specs = yaml.safe_load(
            (ROOT / "training/base_specs.yaml").read_text(encoding="utf-8")
        )
        parent = specs["parent_models"]["instrumental_parent"]
        rendered_root = args.rendered_root.expanduser().resolve()
        manifests = build_parent_shards(
            pending_parent_receipts(rendered_root),
            args.output_root.expanduser().resolve(),
            shard_seconds=int(parent["shard_seconds"]),
            guard_seconds=int(parent["guard_seconds"]),
            minimum_shard_seconds=int(parent["minimum_shard_seconds"]),
        )
    except (
        KeyError,
        OSError,
        ParentShardError,
        TypeError,
        ValueError,
        yaml.YAMLError,
    ) as exc:
        print(f"parent shard build failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "pending_receipts": len(
                    pending_parent_receipts(rendered_root)
                ),
                "shard_count": len(manifests),
                "manifests": [str(path) for path in manifests],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

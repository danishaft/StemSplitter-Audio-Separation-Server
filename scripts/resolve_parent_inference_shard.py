from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from training.parent_shards import (  # noqa: E402
    ParentShardError,
    resolve_parent_shard,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve one inferred instrumental parent shard."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("instrumental", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = resolve_parent_shard(
            args.manifest.expanduser().resolve(),
            args.instrumental.expanduser().resolve(),
        )
    except (
        KeyError,
        OSError,
        ParentShardError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"parent shard resolution failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

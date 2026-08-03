from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_data_registry import (  # noqa: E402
    DEFAULT_REGISTRY_PATH,
    write_training_source_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a rights-aware specialist training source manifest."
    )
    parser.add_argument(
        "--profile",
        choices=("research_all", "release_eligible"),
        required=True,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = write_training_source_manifest(
        args.output,
        profile=args.profile,
        registry_path=args.registry,
    )
    print(
        f"wrote {args.profile} manifest with "
        f"{len(manifest['selected_source_ids'])} selected sources and "
        f"{len(manifest['blocked_source_ids'])} blocked sources: {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

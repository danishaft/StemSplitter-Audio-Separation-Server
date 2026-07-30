from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from training.audio_recipes import (  # noqa: E402
    RecipeRenderError,
    render_recipe,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render deterministic specialist training recipes."
    )
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "training" / "rendered",
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def _load_recipes(paths: list[Path]) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    recipe_ids: set[str] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        for line in resolved.read_text(encoding="utf-8").splitlines():
            recipe = json.loads(line)
            recipe_id = str(recipe["recipe_id"])
            if recipe_id in recipe_ids:
                raise RecipeRenderError(f"duplicate recipe ID: {recipe_id}")
            recipe_ids.add(recipe_id)
            recipes.append(recipe)
    return recipes


def _render_one(
    recipe: dict[str, Any],
    output_root: str,
) -> dict[str, Any]:
    return render_recipe(recipe, Path(output_root))


def main() -> int:
    args = parse_args()
    try:
        recipes = _load_recipes(args.manifests)
        if args.limit is not None:
            if args.limit < 1:
                raise RecipeRenderError("--limit must be positive")
            recipes = recipes[: args.limit]
        output_root = args.output_root.expanduser().resolve()
        worker_count = max(1, int(args.workers))
        if worker_count == 1:
            receipts = [
                render_recipe(recipe, output_root) for recipe in recipes
            ]
        else:
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                receipts = list(
                    executor.map(
                        _render_one,
                        recipes,
                        [str(output_root)] * len(recipes),
                    )
                )
    except (
        KeyError,
        OSError,
        RecipeRenderError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"training recipe render failed: {exc}", file=sys.stderr)
        return 1

    summary = {
        "rendered": len(receipts),
        "resolved": sum(
            receipt["parent_status"] == "resolved"
            for receipt in receipts
        ),
        "pending_upstream_inference": sum(
            receipt["parent_status"] == "pending_upstream_inference"
            for receipt in receipts
        ),
        "output_root": str(output_root),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

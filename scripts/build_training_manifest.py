from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from training.manifests import (  # noqa: E402
    FAMILIES,
    TrainingManifestError,
    apply_recipe_budget,
    build_family_recipes,
    load_audited_items,
    sha256_file,
    write_recipe_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic specialist training recipe manifests."
    )
    parser.add_argument(
        "--profile",
        choices=("research_all", "release_eligible"),
        default="research_all",
    )
    parser.add_argument(
        "--family",
        choices=FAMILIES,
        action="append",
        dest="families",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "training/manifests",
    )
    parser.add_argument(
        "--validation-only",
        action="store_true",
        help="Write held-out validation recipes without applying train budgets.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        specs_path = ROOT / "training/base_specs.yaml"
        specs = yaml.safe_load(specs_path.read_text(encoding="utf-8"))
        families = args.families or list(FAMILIES)
        reports = {}
        for family in families:
            base = specs["bases"][family]
            rows = load_audited_items(
                args.profile,
                base["training_sources"][args.profile],
            )
            config_path = Path(str(base["config_path"]))
            if not config_path.is_absolute():
                config_path = ROOT / config_path
            config = yaml.load(
                config_path.read_text(encoding="utf-8"),
                Loader=yaml.FullLoader,
            )
            recipes = build_family_recipes(
                rows,
                family,
                sample_rate=int(config["audio"]["sample_rate"]),
                chunk_samples=int(config["audio"]["chunk_size"]),
                input_contract=str(base["input_contract"]),
            )
            if args.validation_only:
                recipes = [
                    recipe
                    for recipe in recipes
                    if recipe["split"] == "validation"
                ]
                if not recipes:
                    raise TrainingManifestError(
                        f"no validation recipes for {family}"
                    )
            else:
                recipes = apply_recipe_budget(
                    recipes,
                    specs["recipe_budget"],
                )
            output = (
                args.output_root.expanduser().resolve()
                / args.profile
                / "specialist-recipes-v1"
                / f"{family}.jsonl"
            )
            reports[family] = write_recipe_manifest(recipes, output)

        summary = {
            "schema_version": "1.0",
            "profile": args.profile,
            "validation_only": args.validation_only,
            "base_specs": str(specs_path.relative_to(ROOT)),
            "base_specs_sha256": sha256_file(specs_path),
            "families": reports,
        }
        summary_path = (
            args.output_root.expanduser().resolve()
            / args.profile
            / "specialist-recipes-v1"
            / "summary.json"
        )
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        KeyError,
        OSError,
        TrainingManifestError,
        TypeError,
        ValueError,
        yaml.YAMLError,
    ) as exc:
        print(f"training manifest build failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

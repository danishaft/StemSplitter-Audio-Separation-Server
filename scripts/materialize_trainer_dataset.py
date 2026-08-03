from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
)


class TrainerDatasetError(RuntimeError):
    """Raised when rendered recipes cannot form a trainer dataset."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize one immutable specialist trainer dataset."
    )
    parser.add_argument(
        "base_id",
        choices=SPECIALIST_BASE_IDS,
    )
    parser.add_argument("stage", type=int, choices=(25, 50, 100))
    parser.add_argument(
        "--profile",
        choices=("research_all", "release_eligible"),
        default="research_all",
    )
    parser.add_argument(
        "--manifest-root",
        type=Path,
        default=ROOT / "training" / "manifests",
    )
    parser.add_argument(
        "--rendered-root",
        type=Path,
        default=ROOT / "training" / "rendered",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "training" / "trainer_datasets",
    )
    parser.add_argument(
        "--min-target-rms-dbfs",
        type=float,
        default=-50.0,
        help="Reject rendered targets quieter than this RMS level.",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_recipes(
    manifest_root: Path,
    profile: str,
    families: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    recipes = []
    provenance = []
    for family in families:
        path = (
            manifest_root
            / profile
            / "specialist-recipes-v1"
            / f"{family}.jsonl"
        )
        if not path.is_file():
            raise TrainerDatasetError(f"recipe manifest is missing: {path}")
        provenance.append({"path": str(path), "sha256": _sha256(path)})
        for line in path.read_text(encoding="utf-8").splitlines():
            recipe = json.loads(line)
            if recipe["family"] != family:
                raise TrainerDatasetError(
                    f"recipe family mismatch in {path}"
                )
            recipes.append(recipe)
    return recipes, provenance


def _link(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise TrainerDatasetError(f"rendered artifact is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)


def _rms_dbfs(path: Path) -> float:
    squared_sum = 0.0
    sample_count = 0
    with sf.SoundFile(path) as audio:
        for block in audio.blocks(
            blocksize=262_144,
            dtype="float32",
            always_2d=True,
        ):
            values = np.asarray(block, dtype=np.float64)
            squared_sum += float(np.square(values).sum())
            sample_count += int(values.size)
    if sample_count == 0 or squared_sum == 0.0:
        return -240.0
    return 20.0 * math.log10(math.sqrt(squared_sum / sample_count))


def _selected_for_stage(
    recipe: dict[str, Any],
    stage: int,
) -> bool:
    return (
        recipe["split"] != "train"
        or int(recipe["minimum_stage_percent"]) <= stage
    )


def main() -> int:
    args = parse_args()
    try:
        specs_path = ROOT / "training" / "base_specs.yaml"
        specs = yaml.safe_load(specs_path.read_text(encoding="utf-8"))
        base = specs["bases"][args.base_id]
        families = tuple(str(item) for item in base["output_instruments"])
        recipes, recipe_manifests = _load_recipes(
            args.manifest_root.expanduser().resolve(),
            args.profile,
            families,
        )
        selected = [
            recipe
            for recipe in recipes
            if _selected_for_stage(recipe, args.stage)
        ]
        if not selected:
            raise TrainerDatasetError("stage selected no recipes")

        rendered_root = args.rendered_root.expanduser().resolve()
        output_dir = (
            args.output_root.expanduser().resolve()
            / args.profile
            / args.base_id
            / f"stage_{args.stage}"
        )
        receipt_path = output_dir / "dataset.json"
        expected_ids = sorted(str(recipe["recipe_id"]) for recipe in selected)
        input_digest = hashlib.sha256(
            (
                "\n".join(expected_ids)
                + f"\nmin_target_rms_dbfs={args.min_target_rms_dbfs}"
            ).encode()
        ).hexdigest()
        if receipt_path.is_file():
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
            if existing.get("input_recipe_set_sha256") == input_digest:
                print(json.dumps(existing, sort_keys=True))
                return 0
            raise TrainerDatasetError(
                f"dataset path has different provenance: {output_dir}"
            )
        temporary_dir = output_dir.with_name(f".stage_{args.stage}.tmp")
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        temporary_dir.mkdir(parents=True)

        counts: Counter[tuple[str, str]] = Counter()
        parent_modes: Counter[str] = Counter()
        accepted_ids = []
        rejected_target_activity = []
        for recipe in selected:
            recipe_id = str(recipe["recipe_id"])
            family = str(recipe["family"])
            rendered_receipt_path = (
                rendered_root
                / "artifacts"
                / family
                / recipe_id
                / "receipt.json"
            )
            if not rendered_receipt_path.is_file():
                raise TrainerDatasetError(
                    f"render receipt is missing: {recipe_id}"
                )
            rendered = json.loads(
                rendered_receipt_path.read_text(encoding="utf-8")
            )
            if rendered.get("parent_status") != "resolved":
                raise TrainerDatasetError(
                    f"parent input is unresolved: {recipe_id}"
                )
            split = str(recipe["split"])
            track_dir = temporary_dir / split / recipe_id
            target = Path(
                str(rendered["outputs"]["target"]["path"])
            )
            mixture = Path(
                str(rendered["outputs"]["mixture"]["path"])
            )
            if _sha256(target) != rendered["outputs"]["target"]["sha256"]:
                raise TrainerDatasetError(
                    f"rendered target checksum mismatch: {recipe_id}"
                )
            if _sha256(mixture) != rendered["outputs"]["mixture"]["sha256"]:
                raise TrainerDatasetError(
                    f"rendered mixture checksum mismatch: {recipe_id}"
                )
            target_rms_dbfs = _rms_dbfs(target)
            if target_rms_dbfs < args.min_target_rms_dbfs:
                rejected_target_activity.append(
                    {
                        "recipe_id": recipe_id,
                        "family": family,
                        "split": split,
                        "target_rms_dbfs": round(target_rms_dbfs, 3),
                    }
                )
                continue
            _link(target, track_dir / f"{family}.flac")
            _link(mixture, track_dir / "mixture.flac")
            counts[(split, family)] += 1
            parent_modes[str(rendered["parent_mode"])] += 1
            accepted_ids.append(recipe_id)

        for family in families:
            for split in ("train", "validation"):
                if counts[(split, family)] == 0:
                    raise TrainerDatasetError(
                        f"activity gate removed every {split} {family} recipe"
                    )

        recipe_set_digest = hashlib.sha256(
            "\n".join(sorted(accepted_ids)).encode()
        ).hexdigest()

        receipt = {
            "schema_version": "1.0",
            "profile": args.profile,
            "base_id": args.base_id,
            "stage_percent": args.stage,
            "dataset_type": 6,
            "instruments": list(families),
            "base_specs": str(specs_path),
            "base_specs_sha256": _sha256(specs_path),
            "recipe_manifests": recipe_manifests,
            "input_recipe_count": len(selected),
            "input_recipe_set_sha256": input_digest,
            "recipe_count": len(accepted_ids),
            "recipe_set_sha256": recipe_set_digest,
            "min_target_rms_dbfs": args.min_target_rms_dbfs,
            "rejected_target_activity_count": len(
                rejected_target_activity
            ),
            "rejected_target_activity": rejected_target_activity,
            "counts": {
                f"{split}:{family}": count
                for (split, family), count in sorted(counts.items())
            },
            "parent_modes": dict(sorted(parent_modes.items())),
            "train_path": str(output_dir / "train"),
            "validation_path": str(output_dir / "validation"),
            "test_path": str(output_dir / "test"),
        }
        (temporary_dir / "dataset.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        temporary_dir.replace(output_dir)
    except (
        KeyError,
        OSError,
        TrainerDatasetError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as exc:
        print(f"trainer dataset materialization failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

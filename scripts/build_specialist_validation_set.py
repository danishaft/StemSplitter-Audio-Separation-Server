from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from training.audio_recipes import RecipeRenderError, render_recipe  # noqa: E402
from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
)

FAMILIES = SPECIALIST_BASE_IDS


class ValidationSetError(RuntimeError):
    """Raised when a reproducible held-out validation set cannot be built."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic specialist validation set."
    )
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--profile", default="research_all")
    parser.add_argument("--set-id", default="specialists-validation-30-v2")
    parser.add_argument(
        "--family",
        choices=FAMILIES,
        action="append",
        dest="families",
    )
    parser.add_argument(
        "--manifest-root",
        type=Path,
        default=ROOT / "training/manifests",
    )
    parser.add_argument(
        "--render-root",
        type=Path,
        default=ROOT / "training/rendered",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "training/validation_sets",
    )
    parser.add_argument("--min-target-rms-dbfs", type=float, default=-50.0)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    if sample_count == 0 or squared_sum == 0:
        return -240.0
    return 20 * math.log10(math.sqrt(squared_sum / sample_count))


def _round_robin_by_composition(
    recipes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recipe in recipes:
        grouped[str(recipe["target"]["composition_id"])].append(recipe)
    for values in grouped.values():
        values.sort(key=lambda recipe: str(recipe["recipe_id"]))

    ordered: list[dict[str, Any]] = []
    depth = 0
    while True:
        added = False
        for composition_id in sorted(grouped):
            values = grouped[composition_id]
            if depth < len(values):
                ordered.append(values[depth])
                added = True
        if not added:
            return ordered
        depth += 1


def _load_candidates(
    manifest: Path,
) -> list[dict[str, Any]]:
    candidates = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        recipe = json.loads(line)
        if recipe["split"] != "validation":
            continue
        if recipe.get("parent_input", {}).get("mode") != "full_mixture":
            continue
        candidates.append(recipe)
    return _round_robin_by_composition(candidates)


def _existing_artifact(
    family: str,
    recipe_id: str,
    render_root: Path,
) -> tuple[dict[str, Any], Path] | None:
    roots = (
        render_root / "artifacts" / family / recipe_id,
        ROOT / "training/rendered/sprint-v1/artifacts" / family / recipe_id,
    )
    for artifact_root in roots:
        receipt_path = artifact_root / "receipt.json"
        if not receipt_path.is_file():
            continue
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("parent_status") == "resolved":
            return receipt, artifact_root
    return None


def _link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)


def _resolve_output(
    receipt: dict[str, Any],
    name: str,
) -> Path:
    path = Path(str(receipt["outputs"][name]["path"]))
    if not path.is_absolute():
        path = ROOT / path
    return path


def _portable_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _build_family(
    family: str,
    manifest: Path,
    render_root: Path,
    output_root: Path,
    count: int,
    min_target_rms_dbfs: float,
) -> dict[str, Any]:
    accepted = []
    rejected = []
    reused = 0
    rendered = 0
    for recipe in _load_candidates(manifest):
        recipe_id = str(recipe["recipe_id"])
        try:
            existing = _existing_artifact(
                family,
                recipe_id,
                render_root,
            )
            if existing is None:
                receipt = render_recipe(recipe, render_root)
                artifact_root = (
                    render_root / "artifacts" / family / recipe_id
                )
                rendered += 1
            else:
                receipt, artifact_root = existing
                reused += 1

            target = _resolve_output(receipt, "target")
            mixture = _resolve_output(receipt, "mixture")
            if not target.is_file() or not mixture.is_file():
                raise ValidationSetError("rendered audio is missing")
            target_rms_dbfs = _rms_dbfs(target)
            if target_rms_dbfs < min_target_rms_dbfs:
                rejected.append(
                    {
                        "recipe_id": recipe_id,
                        "reason": "target_below_rms_gate",
                        "target_rms_dbfs": round(target_rms_dbfs, 3),
                    }
                )
                continue

            track_root = output_root / family / recipe_id
            _link(target, track_root / f"{family}.flac")
            _link(mixture, track_root / "mixture.flac")
            accepted.append(
                {
                    "recipe_id": recipe_id,
                    "composition_id": recipe["target"]["composition_id"],
                    "target_audio_sha256": recipe["target"]["audio_sha256"],
                    "target_rms_dbfs": round(target_rms_dbfs, 3),
                    "target_sha256": _sha256(target),
                    "mixture_sha256": _sha256(mixture),
                    "artifact_root": _portable_path(artifact_root),
                }
            )
            if len(accepted) == count:
                break
        except (KeyError, OSError, RecipeRenderError, ValidationSetError) as exc:
            rejected.append(
                {
                    "recipe_id": recipe_id,
                    "reason": str(exc),
                }
            )

    if len(accepted) != count:
        raise ValidationSetError(
            f"{family} produced {len(accepted)}/{count} validation clips"
        )
    return {
        "count": len(accepted),
        "composition_count": len(
            {item["composition_id"] for item in accepted}
        ),
        "reused_render_count": reused,
        "new_render_count": rendered,
        "manifest": _portable_path(manifest),
        "manifest_sha256": _sha256(manifest),
        "accepted": accepted,
        "rejected_before_completion": rejected,
    }


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be positive")
    if not args.set_id.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("--set-id contains unsupported characters")

    families_to_build = args.families or list(FAMILIES)
    manifest_root = args.manifest_root.expanduser().resolve()
    render_root = args.render_root.expanduser().resolve() / args.set_id
    output_root = args.output_root.expanduser().resolve() / args.set_id
    receipt_path = output_root / "validation-set.json"
    if receipt_path.exists():
        print(receipt_path)
        return 0

    temporary_root = output_root.with_name(f".{args.set_id}.tmp")
    shutil.rmtree(temporary_root, ignore_errors=True)
    temporary_root.mkdir(parents=True)
    try:
        families = {}
        for family in families_to_build:
            manifest = (
                manifest_root
                / args.profile
                / "specialist-recipes-v1"
                / f"{family}.jsonl"
            )
            if not manifest.is_file():
                raise ValidationSetError(f"missing manifest: {manifest}")
            families[family] = _build_family(
                family,
                manifest,
                render_root,
                temporary_root,
                args.count,
                args.min_target_rms_dbfs,
            )
        receipt = {
            "schema_version": "1.0",
            "set_id": args.set_id,
            "profile": args.profile,
            "split": "validation",
            "count_per_family": args.count,
            "min_target_rms_dbfs": args.min_target_rms_dbfs,
            "families": families,
        }
        (temporary_root / "validation-set.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output_root.parent.mkdir(parents=True, exist_ok=True)
        temporary_root.replace(output_root)
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        ValidationSetError,
        json.JSONDecodeError,
    ) as exc:
        shutil.rmtree(temporary_root, ignore_errors=True)
        print(f"validation set build failed: {exc}", file=sys.stderr)
        return 1

    print(receipt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

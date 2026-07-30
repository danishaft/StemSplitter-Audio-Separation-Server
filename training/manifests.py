from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = (
    "acoustic_guitar",
    "electric_guitar",
    "synth",
    "strings",
    "wind_brass",
)
SPLITS = ("train", "validation", "test")
PROFILE_PATHS = {
    "research_all": (
        ROOT / "datasets/corpora/research_all/specialist-sources-v1.json"
    ),
    "release_eligible": (
        ROOT / "datasets/corpora/release_eligible/specialist-sources-v1.json"
    ),
}
BASE_SPECS_PATH = ROOT / "training/base_specs.yaml"


class TrainingManifestError(RuntimeError):
    """Raised when audited items cannot form a safe training manifest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(*parts: object) -> bytes:
    value = ":".join(str(part) for part in parts)
    return hashlib.sha256(value.encode()).digest()


def stable_seed(*parts: object) -> int:
    return int.from_bytes(stable_digest(*parts)[:8], "big")


def _profile_sources(profile: str) -> set[str]:
    try:
        path = PROFILE_PATHS[profile]
    except KeyError as exc:
        raise TrainingManifestError(f"unknown profile: {profile}") from exc
    payload = json.loads(path.read_text(encoding="utf-8"))
    return set(payload["selected_source_ids"])


def load_audited_items(
    profile: str,
    source_ids: Iterable[str],
) -> list[dict[str, Any]]:
    selected_sources = _profile_sources(profile)
    requested_sources = set(source_ids)
    invalid_sources = requested_sources - selected_sources
    if invalid_sources:
        raise TrainingManifestError(
            "training sources are outside the rights profile: "
            + ",".join(sorted(invalid_sources))
        )
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (ROOT / "datasets/manifests/items").glob("**/items.jsonl")
    ):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if (
                row.get("accepted") is True
                and row.get("source_id") in requested_sources
                and row.get("split") in SPLITS
                and row.get("item_role")
                in {"target", "hard_negative", "mixture"}
            ):
                rows.append(row)
    return _deduplicate_and_validate(rows)


def _deduplicate_and_validate(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_hash: dict[str, dict[str, Any]] = {}
    composition_splits: dict[str, str] = {}
    rawstems_artist_splits: dict[str, str] = {}
    for row in rows:
        composition_id = str(row["composition_id"])
        split = str(row["split"])
        prior_split = composition_splits.setdefault(composition_id, split)
        if prior_split != split:
            raise TrainingManifestError(
                f"composition crosses splits: {composition_id}"
            )
        if row["source_id"] == "rawstems":
            artist_id = composition_id.partition(":")[2].split("|", 1)[0]
            prior_artist_split = rawstems_artist_splits.setdefault(
                artist_id,
                split,
            )
            if prior_artist_split != split:
                raise TrainingManifestError(
                    f"RawStems artist crosses splits: {artist_id}"
                )
        audio_hash = str(row["audio"]["sha256"])
        prior = by_hash.get(audio_hash)
        if prior is not None:
            if prior["split"] != split:
                raise TrainingManifestError(
                    f"audio hash crosses splits: {audio_hash}"
                )
            continue
        by_hash[audio_hash] = row
    return list(by_hash.values())


def _resolve_local_path(row: dict[str, Any]) -> Path:
    value = str(row.get("local_path") or "")
    if not value:
        raise TrainingManifestError(
            "audited item lacks local_path: "
            f"{row['source_id']}:{row['relative_path']}"
        )
    path = Path(value)
    resolved = path if path.is_absolute() else ROOT / path
    training_root = os.getenv("STEM_SPLITTER_TRAINING_ROOT", "").strip()
    if (
        not resolved.is_file()
        and training_root
        and not path.is_absolute()
        and path.parts
        and path.parts[0] == "datasets"
    ):
        resolved = Path(training_root) / "source_audio" / path
    if (
        not resolved.is_file()
        and training_root
        and "source_audio" in resolved.parts
    ):
        source_index = resolved.parts.index("source_audio")
        resolved = Path(training_root).joinpath(
            *resolved.parts[source_index:]
        )
    if not resolved.is_file():
        raise TrainingManifestError(f"audited item is unavailable: {value}")
    if resolved.stat().st_size <= 0:
        raise TrainingManifestError(f"audited item is empty: {value}")
    return resolved


def _minimum_stage_by_composition(
    target_rows: list[dict[str, Any]],
    family: str,
) -> dict[str, int]:
    compositions = sorted(
        {str(row["composition_id"]) for row in target_rows},
        key=lambda value: stable_digest("specialist-stage-v1", family, value),
    )
    if not compositions:
        raise TrainingManifestError(f"no training compositions for {family}")
    count_25 = max(1, math.ceil(len(compositions) * 0.25))
    count_50 = max(count_25, math.ceil(len(compositions) * 0.50))
    result: dict[str, int] = {}
    for index, composition_id in enumerate(compositions):
        if index < count_25:
            result[composition_id] = 25
        elif index < count_50:
            result[composition_id] = 50
        else:
            result[composition_id] = 100
    return result


def _source_ref(row: dict[str, Any], offset_seconds: float) -> dict[str, Any]:
    return {
        "source_id": row["source_id"],
        "source_version": row["source_version"],
        "composition_id": row["composition_id"],
        "family": row.get("family"),
        "item_role": row["item_role"],
        "local_path": str(_resolve_local_path(row)),
        "audio_sha256": row["audio"]["sha256"],
        "offset_seconds": round(offset_seconds, 6),
    }


def _offset_seconds(
    row: dict[str, Any],
    chunk_seconds: float,
    rng: random.Random,
) -> float:
    duration = float(row["audio"]["duration_seconds"])
    return rng.uniform(0.0, max(0.0, duration - chunk_seconds))


def _identity_augmentation() -> dict[str, Any]:
    return {
        "gain_db": 0.0,
        "pan": 0.0,
        "eq_low_shelf_db": 0.0,
        "eq_high_shelf_db": 0.0,
        "compression_threshold_db": 0.0,
        "compression_ratio": 1.0,
        "saturation_drive_db": 0.0,
        "reverb_wet": 0.0,
        "delay_seconds": 0.0,
        "delay_wet": 0.0,
    }


def _augmentation(rng: random.Random, *, target: bool) -> dict[str, Any]:
    return {
        "gain_db": round(rng.uniform(-6.0, 3.0) if target else rng.uniform(-18.0, 3.0), 4),
        "pan": round(rng.uniform(-0.25, 0.25) if target else rng.uniform(-0.8, 0.8), 4),
        "eq_low_shelf_db": round(rng.uniform(-3.0, 3.0), 4),
        "eq_high_shelf_db": round(rng.uniform(-3.0, 3.0), 4),
        "compression_threshold_db": round(rng.uniform(-24.0, -8.0), 4),
        "compression_ratio": round(rng.uniform(1.5, 4.0), 4),
        "saturation_drive_db": round(rng.uniform(0.0, 6.0), 4),
        "reverb_wet": round(rng.uniform(0.0, 0.2), 4),
        "delay_seconds": round(rng.uniform(0.05, 0.3), 4),
        "delay_wet": round(rng.uniform(0.0, 0.12), 4),
    }


def _vocal_augmentation(
    rng: random.Random,
    *,
    residual_leak: bool,
) -> dict[str, Any]:
    result = _identity_augmentation()
    result["gain_db"] = round(
        rng.uniform(-30.0, -12.0)
        if residual_leak
        else rng.uniform(-9.0, 3.0),
        4,
    )
    result["pan"] = round(rng.uniform(-0.25, 0.25), 4)
    return result


def _is_vocal(row: dict[str, Any]) -> bool:
    source_label = str(row.get("source_label") or "").lower()
    if source_label in {
        "bv",
        "lead_vocal",
        "lead_vocals",
        "lv",
        "vocal",
        "vocals",
        "vox",
    }:
        return True
    parts = {
        part.lower()
        for part in Path(str(row.get("relative_path") or "")).parts
    }
    return "voc" in parts or any(
        token in part
        for part in parts
        for token in ("vocal", "vox")
    )


def _select_interferers(
    target: dict[str, Any],
    pool: list[dict[str, Any]],
    by_composition: dict[str, list[dict[str, Any]]],
    rng: random.Random,
    count: int = 3,
) -> list[dict[str, Any]]:
    target_hash = str(target["audio"]["sha256"])
    selected: list[dict[str, Any]] = []
    seen_hashes = {target_hash}
    same_composition = [
        row
        for row in by_composition.get(str(target["composition_id"]), [])
        if str(row["audio"]["sha256"]) not in seen_hashes
    ]
    same_composition.sort(
        key=lambda row: stable_digest(
            "same-composition-interferer-v1",
            target_hash,
            row["audio"]["sha256"],
        )
    )
    if same_composition:
        selected.append(same_composition[0])
        seen_hashes.add(str(same_composition[0]["audio"]["sha256"]))

    attempts = 0
    while len(selected) < count and pool and attempts < len(pool) * 2:
        candidate = pool[rng.randrange(len(pool))]
        candidate_hash = str(candidate["audio"]["sha256"])
        attempts += 1
        if candidate_hash in seen_hashes:
            continue
        selected.append(candidate)
        seen_hashes.add(candidate_hash)
    return selected


def build_family_recipes(
    rows: list[dict[str, Any]],
    family: str,
    *,
    sample_rate: int,
    chunk_samples: int,
    input_contract: str,
) -> list[dict[str, Any]]:
    if family not in FAMILIES:
        raise TrainingManifestError(f"unknown family: {family}")
    if input_contract != "full_mixture":
        raise TrainingManifestError(
            f"unsupported specialist input contract: {input_contract}"
        )
    for row in rows:
        _resolve_local_path(row)

    target_rows = [
        row
        for row in rows
        if row.get("family") == family and row["item_role"] == "target"
    ]
    train_targets = [row for row in target_rows if row["split"] == "train"]
    minimum_stage = _minimum_stage_by_composition(train_targets, family)
    instrumental_pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    vocal_pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_composition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["item_role"] not in {"target", "hard_negative"}:
            continue
        if _is_vocal(row):
            vocal_pools[str(row["split"])].append(row)
        else:
            instrumental_pools[str(row["split"])].append(row)
            by_composition[str(row["composition_id"])].append(row)

    chunk_seconds = chunk_samples / sample_rate
    recipes: list[dict[str, Any]] = []
    for target in sorted(
        target_rows,
        key=lambda row: (
            str(row["split"]),
            str(row["composition_id"]),
            str(row["audio"]["sha256"]),
        ),
    ):
        active_seconds = (
            float(target["audio"]["duration_seconds"])
            * float(target["audio"]["active_fraction"])
        )
        window_count = max(
            1,
            min(64, math.ceil(active_seconds / chunk_seconds)),
        )
        for window_index in range(window_count):
            seed = stable_seed(
                "specialist-recipe-v1",
                family,
                target["audio"]["sha256"],
                window_index,
            )
            rng = random.Random(seed)
            target_offset = _offset_seconds(target, chunk_seconds, rng)
            recipe_id = hashlib.sha256(
                f"{family}:{target['audio']['sha256']}:{window_index}".encode()
            ).hexdigest()
            interferers = _select_interferers(
                target,
                instrumental_pools[str(target["split"])],
                by_composition,
                rng,
            )
            if len(interferers) < 2:
                raise TrainingManifestError(
                    f"fewer than two instrumental interferers: {recipe_id}"
                )
            vocal_sources = _select_interferers(
                target,
                vocal_pools[str(target["split"])],
                {},
                rng,
                count=1,
            )
            if not vocal_sources:
                raise TrainingManifestError(
                    f"no vocal source for full mixture: {recipe_id}"
                )
            is_training = target["split"] == "train"
            recipe = {
                "schema_version": "1.0",
                "recipe_id": recipe_id,
                "seed": seed,
                "family": family,
                "split": target["split"],
                "minimum_stage_percent": (
                    minimum_stage[str(target["composition_id"])]
                    if is_training
                    else 0
                ),
                "sample_rate": sample_rate,
                "chunk_samples": chunk_samples,
                "target": {
                    **_source_ref(target, target_offset),
                    "augmentation": (
                        _augmentation(rng, target=True)
                        if is_training
                        else _identity_augmentation()
                    ),
                },
                "interferers": [
                    {
                        **_source_ref(
                            row,
                            (
                                target_offset
                                if row["composition_id"]
                                == target["composition_id"]
                                else _offset_seconds(row, chunk_seconds, rng)
                            ),
                        ),
                        "augmentation": (
                            _augmentation(rng, target=False)
                            if is_training
                            else _identity_augmentation()
                        ),
                    }
                    for row in interferers
                ],
                "parent_input": {
                    "mode": "full_mixture",
                    "upstream_model": None,
                    "vocal_sources": [
                        {
                            **_source_ref(
                                row,
                                _offset_seconds(row, chunk_seconds, rng),
                            ),
                            "augmentation": (
                                _vocal_augmentation(
                                    rng,
                                    residual_leak=False,
                                )
                                if is_training
                                else _identity_augmentation()
                            ),
                        }
                        for row in vocal_sources
                    ],
                },
                "peak_limit_dbfs": -1.0,
            }
            recipes.append(recipe)
    return recipes


def _select_with_composition_coverage(
    recipes: list[dict[str, Any]],
    limit: int,
    *rank_parts: object,
) -> list[dict[str, Any]]:
    by_composition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recipe in recipes:
        by_composition[str(recipe["target"]["composition_id"])].append(recipe)
    for composition_recipes in by_composition.values():
        composition_recipes.sort(
            key=lambda recipe: stable_digest(
                *rank_parts,
                "within-composition",
                recipe["recipe_id"],
            )
        )
    selected: list[dict[str, Any]] = []
    composition_ids = sorted(
        by_composition,
        key=lambda value: stable_digest(
            *rank_parts,
            "composition",
            value,
        ),
    )
    while len(selected) < limit:
        progressed = False
        for composition_id in composition_ids:
            available = by_composition[composition_id]
            if not available:
                continue
            selected.append(available.pop(0))
            progressed = True
            if len(selected) == limit:
                break
        if not progressed:
            break
    return selected


def apply_recipe_budget(
    recipes: list[dict[str, Any]],
    budget: dict[str, Any],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    train_cumulative = {
        int(stage): int(count)
        for stage, count in budget["train_cumulative"].items()
    }
    previous_count = 0
    for stage in (25, 50, 100):
        cumulative_count = train_cumulative[stage]
        stage_limit = cumulative_count - previous_count
        if stage_limit < 0:
            raise TrainingManifestError(
                "training recipe budget must be cumulative"
            )
        candidates = [
            recipe
            for recipe in recipes
            if recipe["split"] == "train"
            and int(recipe["minimum_stage_percent"]) == stage
        ]
        stage_recipes = _select_with_composition_coverage(
            candidates,
            stage_limit,
            "specialist-budget-v1",
            stage,
        )
        if len(stage_recipes) != stage_limit:
            raise TrainingManifestError(
                f"stage {stage} has {len(stage_recipes)} recipes; "
                f"{stage_limit} required"
            )
        selected.extend(stage_recipes)
        previous_count = cumulative_count

    for split in ("validation", "test"):
        split_limit = int(budget[split])
        candidates = [
            recipe for recipe in recipes if recipe["split"] == split
        ]
        split_recipes = _select_with_composition_coverage(
            candidates,
            min(split_limit, len(candidates)),
            "specialist-budget-v1",
            split,
        )
        if not split_recipes:
            raise TrainingManifestError(f"no {split} recipes")
        selected.extend(split_recipes)
    return sorted(
        selected,
        key=lambda recipe: (
            str(recipe["split"]),
            int(recipe["minimum_stage_percent"]),
            str(recipe["recipe_id"]),
        ),
    )


def write_recipe_manifest(
    recipes: list[dict[str, Any]],
    path: Path,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for recipe in recipes:
            handle.write(json.dumps(recipe, sort_keys=True) + "\n")
    counts = Counter(
        (
            str(recipe["split"]),
            int(recipe["minimum_stage_percent"]),
        )
        for recipe in recipes
    )
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256_file(path),
        "recipe_count": len(recipes),
        "counts": {
            f"{split}:{stage}": count
            for (split, stage), count in sorted(counts.items())
        },
    }

from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import shutil

import numpy as np
import soundfile as sf

from .config import (
    PRODUCT_11_BROAD_STEMS,
    PRODUCT_11_EXCLUDED_STEMS,
    PRODUCT_11_SPECIALIST_STEMS,
    PRODUCT_11_STEMS,
)
from .qualification import load_stem_qualification
from .util import ensure_dir


ArtifactMap = dict[str, dict[str, object]]
GroupMap = dict[str, ArtifactMap]

RAW_GROUPS = ("broad_stems", "derived_stems", "specialist_substems")

TARGET_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "vocals": (("broad_stems", ("vocals", "vocal")),),
    "instrumental": (("broad_stems", ("instrumental", "no_vocals", "no_vocal", "inst")),),
    "drums": (("broad_stems", ("drums", "drum")),),
    "bass": (
        ("broad_stems", ("bass",)),
    ),
    "acoustic_guitar": (("broad_stems", ("acoustic_guitar", "guitar")),),
    "electric_guitar": (
        ("specialist_substems", ("electric_guitar",)),
    ),
    "piano": (("broad_stems", ("piano",)),),
    "other": (("broad_stems", ("other",)),),
    "synth": (("specialist_substems", ("synth", "synth_xlance_v2")),),
    "strings": (("specialist_substems", ("strings",)),),
    "lead_vocals": (("specialist_substems", ("lead_vocals",)),),
    "backing_vocals": (
        ("specialist_substems", ("backing_vocals", "backing_vocals_bve")),
    ),
    "kick": (
        ("specialist_substems", ("kick",)),
        ("derived_stems", ("kick",)),
    ),
    "snare": (
        ("specialist_substems", ("snare",)),
        ("derived_stems", ("snare",)),
    ),
}

CYMBAL_FAMILY_ALIASES = ("hi_hats_cymbals", "hats_cymbals", "hi_hats", "cymbals", "crash", "ride")


def apply_product_11_contract(
    job_root: Path,
    *,
    broad_outputs: ArtifactMap,
    derived_outputs: ArtifactMap,
    specialist_outputs: ArtifactMap,
    rejected_candidates: dict[str, dict[str, dict[str, object]]],
    missing_features: list[str],
) -> dict[str, object]:
    raw_groups = _archive_raw_outputs(
        job_root,
        {
            "broad_stems": broad_outputs,
            "derived_stems": derived_outputs,
            "specialist_substems": specialist_outputs,
        },
    )
    published: GroupMap = {
        "broad_stems": {},
        "derived_stems": {},
        "specialist_substems": {},
    }
    published_main: ArtifactMap = {}
    selected_keys: set[tuple[str, str]] = set()

    broad_publish_order = [
        stem for stem in PRODUCT_11_BROAD_STEMS if stem != "instrumental"
    ] + ["instrumental"]
    for target in broad_publish_order:
        candidate = _find_candidate(raw_groups, target)
        if candidate is None and target == "instrumental":
            candidate = _synthesize_instrumental(job_root, raw_groups["broad_stems"])
        if candidate is None:
            _record_missing_target(target, rejected_candidates, missing_features)
            continue
        _publish_target(
            job_root,
            target=target,
            group="broad_stems",
            candidate=candidate,
            published=published,
            published_main=published_main,
            selected_keys=selected_keys,
        )

    specialist_publish_order = (
        [stem for stem in PRODUCT_11_SPECIALIST_STEMS if stem == "backing_vocals"]
        + [stem for stem in PRODUCT_11_SPECIALIST_STEMS if stem == "lead_vocals"]
        + [
            stem
            for stem in PRODUCT_11_SPECIALIST_STEMS
            if stem not in {"backing_vocals", "lead_vocals"}
        ]
    )
    for target in specialist_publish_order:
        if target == "hi_hats_cymbals":
            candidate = _build_cymbal_family_candidate(job_root, raw_groups)
        else:
            candidate = _find_candidate(raw_groups, target)
        if candidate is None and target == "lead_vocals":
            candidate = _synthesize_lead_vocals(job_root, published)
        if candidate is None:
            _record_missing_target(target, rejected_candidates, missing_features)
            continue
        _publish_target(
            job_root,
            target=target,
            group="specialist_substems",
            candidate=candidate,
            published=published,
            published_main=published_main,
            selected_keys=selected_keys,
        )

    _record_unselected_candidates(raw_groups, selected_keys, rejected_candidates)
    missing_stems = [stem for stem in PRODUCT_11_STEMS if stem not in published_main]
    delivery_status = "complete" if not missing_stems else "partial"
    qualification = load_stem_qualification(PRODUCT_11_STEMS)
    return {
        "published_broad_stems": published["broad_stems"],
        "published_derived_stems": published["derived_stems"],
        "published_specialist_substems": published["specialist_substems"],
        "published_main_stems": published_main,
        "stem_contract": {
            "name": "product_11_stems",
            "target_stems": list(PRODUCT_11_STEMS),
            "published_stems": sorted(published_main),
            "missing_stems": missing_stems,
            "excluded_stems": list(PRODUCT_11_EXCLUDED_STEMS),
            # status remains the delivery-status compatibility field. Quality is
            # governed independently by the benchmark-backed qualification ledger.
            "status": delivery_status,
            "delivery_status": delivery_status,
            "quality_status": qualification["release_decision"],
            "production_release_eligible": qualification["production_release_eligible"],
            "qualification": qualification,
        },
    }


# Keep the historical import stable while callers migrate to the canonical name.
apply_quality_8_contract = apply_product_11_contract


def _archive_raw_outputs(job_root: Path, groups: GroupMap) -> GroupMap:
    raw_root = ensure_dir(job_root / "candidate_stems")
    archived: GroupMap = {group: {} for group in RAW_GROUPS}
    for group, outputs in groups.items():
        target_dir = ensure_dir(raw_root / group)
        for artifact_name, payload in outputs.items():
            source = Path(str(payload["path"]))
            archived_path = _move_candidate_file(source, target_dir)
            archived[group][artifact_name] = {
                **payload,
                "path": str(archived_path.resolve()),
                "candidate_name": artifact_name,
                "candidate_group": group,
            }

        published_dir = job_root / group
        if not published_dir.exists():
            continue
        for source in sorted(published_dir.iterdir()):
            if not source.is_file():
                continue
            archived_path = _move_candidate_file(source, target_dir)
            artifact_name = _unique_payload_name(archived[group], source.stem)
            archived[group][artifact_name] = {
                "path": str(archived_path.resolve()),
                "source_model": "gpu_worker",
                "publish_status": "candidate",
                "publish_reason": "raw_gpu_worker_artifact",
                "quality_score": None,
                "warnings": [],
                "metrics": {},
                "candidate_name": artifact_name,
                "candidate_group": group,
            }
    return archived


def _move_candidate_file(source: Path, target_dir: Path) -> Path:
    ensure_dir(target_dir)
    target = _unique_file_path(target_dir / source.name)
    if source.exists():
        shutil.move(str(source), target)
    return target


def _unique_file_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _unique_payload_name(payloads: ArtifactMap, base_name: str) -> str:
    name = _safe_name(base_name)
    if name not in payloads:
        return name
    counter = 2
    while f"{name}_{counter}" in payloads:
        counter += 1
    return f"{name}_{counter}"


def _find_candidate(raw_groups: GroupMap, target: str) -> dict[str, object] | None:
    for group, aliases in TARGET_RULES[target]:
        match = _match_candidate(raw_groups[group], aliases)
        if match:
            return match
    return None


def _match_candidate(candidates: ArtifactMap, aliases: tuple[str, ...]) -> dict[str, object] | None:
    alias_keys = tuple(_safe_name(alias) for alias in aliases)
    for alias in alias_keys:
        if alias in candidates:
            return candidates[alias]
    for artifact_name, payload in candidates.items():
        name_key = _safe_name(artifact_name)
        for alias in alias_keys:
            if name_key == alias or name_key.endswith(f"_{alias}") or f"_{alias}_" in name_key:
                return payload
    return None


def _publish_target(
    job_root: Path,
    *,
    target: str,
    group: str,
    candidate: dict[str, object],
    published: GroupMap,
    published_main: ArtifactMap,
    selected_keys: set[tuple[str, str]],
) -> None:
    publish_dir = ensure_dir(job_root / group)
    source = Path(str(candidate["path"]))
    target_path = publish_dir / f"{target}.wav"
    if source.resolve() != target_path.resolve():
        shutil.copy2(source, target_path)
    candidate_group = str(candidate.get("candidate_group") or group)
    candidate_name = str(candidate.get("candidate_name") or target)
    selected_keys.add((candidate_group, candidate_name))
    for source_key in candidate.get("source_candidate_keys") or []:
        if isinstance(source_key, (list, tuple)) and len(source_key) == 2:
            selected_keys.add((str(source_key[0]), str(source_key[1])))
    warnings = list(candidate.get("warnings") or [])
    if candidate_name != target:
        warnings.append(f"product11_selected_from:{candidate_group}:{candidate_name}")
    payload = {
        **candidate,
        "path": str(target_path.resolve()),
        "stem_name": target,
        "candidate_group": group,
        "publish_status": "published",
        "publish_reason": "product11_contract_selected",
        "warnings": warnings,
    }
    published[group][target] = payload
    published_main[target] = {**payload, "artifact_group": group}


def _record_missing_target(
    target: str,
    rejected_candidates: dict[str, dict[str, dict[str, object]]],
    missing_features: list[str],
) -> None:
    rejected_candidates.setdefault("main_stems", {})[target] = {
        "stem_name": target,
        "publish_status": "missing",
        "publish_reason": "product11_target_not_produced",
        "warnings": ["target_stem_missing"],
        "metrics": {},
    }
    missing_key = f"product11_{target}_missing"
    if missing_key not in missing_features:
        missing_features.append(missing_key)


def _record_unselected_candidates(
    raw_groups: GroupMap,
    selected_keys: set[tuple[str, str]],
    rejected_candidates: dict[str, dict[str, dict[str, object]]],
) -> None:
    rejected = rejected_candidates.setdefault("gpu_worker_artifacts", {})
    for group, payloads in raw_groups.items():
        for artifact_name, payload in payloads.items():
            key = (group, artifact_name)
            if key in selected_keys:
                continue
            normalized = _safe_name(artifact_name)
            excluded = any(_safe_name(stem) in normalized for stem in PRODUCT_11_EXCLUDED_STEMS)
            rejected[f"{group}:{artifact_name}"] = {
                **payload,
                "publish_status": "rejected",
                "publish_reason": "excluded_from_product_11_contract" if excluded else "not_selected_for_product_11",
            }


def _synthesize_instrumental(job_root: Path, broad_outputs: ArtifactMap) -> dict[str, object] | None:
    required_stems = ("drums", "bass", "guitar", "piano", "other")
    parts = {
        name: _match_candidate(broad_outputs, (name,))
        for name in required_stems
    }
    if any(part is None for part in parts.values()):
        return None
    resolved_parts = {name: part for name, part in parts.items() if part is not None}
    inputs = [Path(str(resolved_parts[name]["path"])) for name in required_stems]
    target = ensure_dir(job_root / "contract_candidates") / "instrumental.wav"
    output_path = _mix_audio(inputs, target)
    return {
        "path": str(output_path.resolve()),
        "source_model": "synthetic_sum",
        "publish_status": "candidate",
        "publish_reason": "synthesized_from_broad_stems",
        "quality_score": None,
        "warnings": ["instrumental_synthesized_from_complete_non_vocal_partition"],
        "metrics": {},
        "candidate_name": "instrumental",
        "candidate_group": "contract_candidates",
        "source_candidate_keys": [
            (
                str(resolved_parts[name].get("candidate_group") or "broad_stems"),
                str(resolved_parts[name].get("candidate_name") or name),
            )
            for name in required_stems
        ],
    }


def _synthesize_lead_vocals(job_root: Path, published: GroupMap) -> dict[str, object] | None:
    vocals = published["broad_stems"].get("vocals")
    backing = published["specialist_substems"].get("backing_vocals")
    if not vocals or not backing:
        return None
    target = ensure_dir(job_root / "contract_candidates") / "lead_vocals.wav"
    output_path = _subtract_audio(
        Path(str(vocals["path"])),
        Path(str(backing["path"])),
        target,
    )
    return {
        "path": str(output_path.resolve()),
        "source_model": "residual:vocals_minus_backing_vocals",
        "publish_status": "candidate",
        "publish_reason": "derived_from_vocal_residual",
        "quality_score": None,
        "warnings": ["lead_vocals_derived_from_vocals_minus_backing_vocals"],
        "metrics": {},
        "candidate_name": "lead_vocals_residual",
        "candidate_group": "contract_candidates",
        "source_candidate_keys": [
            (str(vocals.get("candidate_group") or "broad_stems"), str(vocals.get("candidate_name") or "vocals")),
            (
                str(backing.get("candidate_group") or "specialist_substems"),
                str(backing.get("candidate_name") or "backing_vocals"),
            ),
        ],
    }


def _build_cymbal_family_candidate(job_root: Path, raw_groups: GroupMap) -> dict[str, object] | None:
    direct = _match_candidate(raw_groups["specialist_substems"], ("hi_hats_cymbals", "hats_cymbals"))
    if direct:
        return direct
    direct = _match_candidate(raw_groups["derived_stems"], ("hi_hats_cymbals", "hats_cymbals"))
    if direct:
        return direct

    parts: list[dict[str, object]] = []
    for alias in CYMBAL_FAMILY_ALIASES[2:]:
        match = _match_candidate(raw_groups["specialist_substems"], (alias,))
        if match:
            parts.append(match)
    if not parts:
        return None
    if len(parts) == 1:
        return {
            **parts[0],
            "warnings": list(parts[0].get("warnings") or []) + ["partial_cymbal_family_source"],
        }
    target = ensure_dir(job_root / "contract_candidates") / "hi_hats_cymbals.wav"
    output_path = _mix_audio([Path(str(part["path"])) for part in parts], target)
    return {
        "path": str(output_path.resolve()),
        "source_model": "synthetic_sum",
        "publish_status": "candidate",
        "publish_reason": "combined_cymbal_family",
        "quality_score": None,
        "warnings": ["hi_hats_cymbals_combined_from_available_parts"],
        "metrics": {},
        "candidate_name": "hi_hats_cymbals",
        "candidate_group": "contract_candidates",
        "source_candidate_keys": [
            (str(part.get("candidate_group") or "specialist_substems"), str(part.get("candidate_name") or ""))
            for part in parts
        ],
    }


def _mix_audio(paths: list[Path], target: Path) -> Path:
    mixed_audio = None
    mixed_rate = None
    for path in paths:
        audio, sample_rate = sf.read(path, always_2d=True)
        audio = audio.astype(np.float32)
        if mixed_audio is None:
            mixed_audio = audio
            mixed_rate = sample_rate
            continue
        if sample_rate != mixed_rate:
            raise RuntimeError("quality8_mix_sample_rate_mismatch")
        length = min(len(mixed_audio), len(audio))
        mixed_audio = mixed_audio[:length] + audio[:length]
    if mixed_audio is None or mixed_rate is None:
        raise RuntimeError("quality8_mix_missing_inputs")
    ensure_dir(target.parent)
    sf.write(target, np.clip(mixed_audio, -1.0, 1.0), int(mixed_rate))
    return target


def _subtract_audio(source_path: Path, subtract_path: Path, target: Path) -> Path:
    source_audio, source_rate = sf.read(source_path, always_2d=True)
    subtract_audio, subtract_rate = sf.read(subtract_path, always_2d=True)
    if source_rate != subtract_rate:
        raise RuntimeError("quality8_residual_sample_rate_mismatch")
    source_audio = source_audio.astype(np.float32)
    subtract_audio = subtract_audio.astype(np.float32)
    length = min(len(source_audio), len(subtract_audio))
    residual = source_audio[:length] - subtract_audio[:length]
    ensure_dir(target.parent)
    sf.write(target, np.clip(residual, -1.0, 1.0), int(source_rate))
    return target


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

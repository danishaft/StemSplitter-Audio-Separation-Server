from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = ROOT_DIR / "models" / "product_12_stem_contract.yaml"


class ProductContractError(ValueError):
    """Raised when the canonical product stem contract is inconsistent."""


@dataclass(frozen=True)
class ProductStemContract:
    name: str
    target_stems: tuple[str, ...]
    hierarchy: dict[str, tuple[str, ...]]
    stems: dict[str, dict[str, str]]
    production_release_eligible: bool

    @property
    def model_supported_stems(self) -> tuple[str, ...]:
        return tuple(
            stem
            for stem in self.target_stems
            if self.stems[stem]["availability"] == "model_supported"
        )

    @property
    def specialist_candidate_stems(self) -> tuple[str, ...]:
        return tuple(
            stem
            for stem in self.target_stems
            if self.stems[stem]["availability"] != "model_supported"
        )

    @property
    def delivery_models(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(self.stems[stem]["delivery_model"] for stem in self.target_stems)
        )


def load_product_contract(path: Path | None = None) -> ProductStemContract:
    contract_path = path or DEFAULT_CONTRACT_PATH
    try:
        payload = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, yaml.YAMLError) as exc:
        raise ProductContractError(f"invalid_product_contract:{contract_path}") from exc
    if not isinstance(payload, dict):
        raise ProductContractError("product_contract_must_be_mapping")

    target_stems = tuple(str(stem) for stem in payload.get("target_order") or ())
    raw_stems = payload.get("stems")
    raw_hierarchy = payload.get("hierarchy")
    if not target_stems or len(set(target_stems)) != len(target_stems):
        raise ProductContractError("product_contract_target_order_invalid")
    if not isinstance(raw_stems, dict) or set(raw_stems) != set(target_stems):
        raise ProductContractError("product_contract_stem_coverage_mismatch")
    if not isinstance(raw_hierarchy, dict):
        raise ProductContractError("product_contract_hierarchy_missing")

    hierarchy = {
        str(parent): tuple(str(child) for child in children)
        for parent, children in raw_hierarchy.items()
        if isinstance(children, list)
    }
    hierarchy_children = [child for children in hierarchy.values() for child in children]
    if set(hierarchy_children) != set(target_stems):
        raise ProductContractError("product_contract_hierarchy_coverage_mismatch")
    if len(hierarchy_children) != len(set(hierarchy_children)):
        raise ProductContractError("product_contract_stem_has_multiple_parents")

    stems: dict[str, dict[str, str]] = {}
    for stem in target_stems:
        metadata = raw_stems[stem]
        if not isinstance(metadata, dict):
            raise ProductContractError(f"product_contract_stem_invalid:{stem}")
        normalized = {
            "parent": str(metadata.get("parent") or ""),
            "delivery_model": str(metadata.get("delivery_model") or ""),
            "availability": str(metadata.get("availability") or ""),
            "release_state": str(metadata.get("release_state") or ""),
        }
        if not all(normalized.values()):
            raise ProductContractError(f"product_contract_stem_metadata_missing:{stem}")
        if stem not in hierarchy.get(normalized["parent"], ()):
            raise ProductContractError(f"product_contract_parent_mismatch:{stem}")
        stems[stem] = normalized

    return ProductStemContract(
        name=str(payload.get("name") or "hierarchical_12_stems"),
        target_stems=target_stems,
        hierarchy=hierarchy,
        stems=stems,
        production_release_eligible=payload.get("production_release_eligible") is True,
    )

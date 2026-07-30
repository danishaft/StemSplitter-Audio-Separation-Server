from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = ROOT_DIR / "datasets" / "registry" / "specialist_sources.yaml"

ALLOWED_PROFILES = {"research_all", "release_eligible"}
ALLOWED_RESEARCH_USE = {"allowed", "blocked"}
ALLOWED_RELEASE_USE = {
    "allowed",
    "allowed_with_attribution",
    "item_approval_required",
    "permission_required",
}
RELEASE_ALLOWED = {"allowed", "allowed_with_attribution"}


class TrainingDataRegistryError(ValueError):
    """Raised when the training-data registry violates its safety contract."""


@dataclass(frozen=True)
class TrainingSource:
    source_id: str
    display_name: str
    version: str
    source_url: str
    license: str
    rights_status: str
    research_use: str
    release_use: str
    quality_status: str
    families: tuple[str, ...]
    roles: tuple[str, ...]
    raw: dict[str, Any]

    @property
    def is_research_allowed(self) -> bool:
        return self.research_use == "allowed"

    @property
    def is_release_allowed(self) -> bool:
        return self.release_use in RELEASE_ALLOWED


@dataclass(frozen=True)
class TrainingDataRegistry:
    schema_version: str
    status: str
    path: Path
    target_families: tuple[str, ...]
    sources: dict[str, TrainingSource]
    registry_sha256: str

    def sources_for_profile(self, profile: str) -> list[TrainingSource]:
        if profile not in ALLOWED_PROFILES:
            raise TrainingDataRegistryError(f"unknown training-data profile: {profile}")
        if profile == "research_all":
            return [
                source for source in self.sources.values() if source.is_research_allowed
            ]
        return [
            source for source in self.sources.values() if source.is_release_allowed
        ]

    def blocked_sources_for_profile(self, profile: str) -> list[TrainingSource]:
        selected = {source.source_id for source in self.sources_for_profile(profile)}
        return [
            source
            for source in self.sources.values()
            if source.source_id not in selected
        ]

    def build_manifest(self, profile: str) -> dict[str, Any]:
        selected = self.sources_for_profile(profile)
        blocked = self.blocked_sources_for_profile(profile)
        try:
            registry_path = str(self.path.relative_to(ROOT_DIR))
        except ValueError:
            registry_path = str(self.path)
        family_sources = {
            family: [
                source.source_id
                for source in selected
                if family in source.families
            ]
            for family in self.target_families
        }
        return {
            "schema_version": self.schema_version,
            "profile": profile,
            "release_eligible": profile == "release_eligible",
            "registry_path": registry_path,
            "registry_sha256": self.registry_sha256,
            "target_families": list(self.target_families),
            "selected_source_ids": [source.source_id for source in selected],
            "blocked_source_ids": [source.source_id for source in blocked],
            "family_sources": family_sources,
            "sources": {
                source.source_id: {
                    "display_name": source.display_name,
                    "version": source.version,
                    "source_url": source.source_url,
                    "license": source.license,
                    "rights_status": source.rights_status,
                    "research_use": source.research_use,
                    "release_use": source.release_use,
                    "quality_status": source.quality_status,
                    "families": list(source.families),
                    "roles": list(source.roles),
                    **(
                        {"caveat": str(source.raw["caveat"])}
                        if source.raw.get("caveat")
                        else {}
                    ),
                }
                for source in selected
            },
        }


def load_training_data_registry(
    path: Path | None = None,
) -> TrainingDataRegistry:
    registry_path = (path or DEFAULT_REGISTRY_PATH).expanduser().resolve()
    if not registry_path.exists():
        raise TrainingDataRegistryError(
            f"training-data registry not found: {registry_path}"
        )

    raw_bytes = registry_path.read_bytes()
    try:
        payload = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as exc:
        raise TrainingDataRegistryError(
            f"invalid YAML in training-data registry: {registry_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise TrainingDataRegistryError("training-data registry must be a mapping")

    for field_name in ("schema_version", "status", "policy", "sources"):
        if field_name not in payload:
            raise TrainingDataRegistryError(
                f"missing training-data registry field: {field_name}"
            )
    policy = payload["policy"]
    sources_payload = payload["sources"]
    if not isinstance(policy, dict) or not isinstance(sources_payload, dict):
        raise TrainingDataRegistryError("policy and sources must be mappings")

    target_families = tuple(str(value) for value in policy["target_families"])
    if not target_families:
        raise TrainingDataRegistryError("policy.target_families cannot be empty")

    sources: dict[str, TrainingSource] = {}
    for source_id, source_payload in sources_payload.items():
        sources[source_id] = _build_source(
            str(source_id),
            source_payload,
            target_families,
        )

    missing_families = [
        family
        for family in target_families
        if not any(family in source.families for source in sources.values())
    ]
    if missing_families:
        raise TrainingDataRegistryError(
            "target families have no sources: " + ", ".join(missing_families)
        )

    return TrainingDataRegistry(
        schema_version=str(payload["schema_version"]),
        status=str(payload["status"]),
        path=registry_path,
        target_families=target_families,
        sources=sources,
        registry_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def write_training_source_manifest(
    output_path: Path,
    *,
    profile: str,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    registry = load_training_data_registry(registry_path)
    manifest = registry.build_manifest(profile)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _build_source(
    source_id: str,
    payload: Any,
    target_families: tuple[str, ...],
) -> TrainingSource:
    if not isinstance(payload, dict):
        raise TrainingDataRegistryError(f"source must be a mapping: {source_id}")
    required = (
        "display_name",
        "version",
        "source_url",
        "license",
        "rights_status",
        "research_use",
        "release_use",
        "quality_status",
        "families",
        "roles",
    )
    for field_name in required:
        if field_name not in payload or payload[field_name] in (None, ""):
            raise TrainingDataRegistryError(
                f"missing training source field: {source_id}.{field_name}"
            )

    research_use = str(payload["research_use"])
    release_use = str(payload["release_use"])
    if research_use not in ALLOWED_RESEARCH_USE:
        raise TrainingDataRegistryError(
            f"{source_id} has unknown research_use: {research_use}"
        )
    if release_use not in ALLOWED_RELEASE_USE:
        raise TrainingDataRegistryError(
            f"{source_id} has unknown release_use: {release_use}"
        )

    families = tuple(str(value) for value in payload["families"])
    roles = tuple(str(value) for value in payload["roles"])
    unknown_families = sorted(set(families) - set(target_families))
    if unknown_families:
        raise TrainingDataRegistryError(
            f"{source_id} has unknown families: {', '.join(unknown_families)}"
        )
    if not families or not roles:
        raise TrainingDataRegistryError(
            f"{source_id} families and roles cannot be empty"
        )

    return TrainingSource(
        source_id=source_id,
        display_name=str(payload["display_name"]),
        version=str(payload["version"]),
        source_url=str(payload["source_url"]),
        license=str(payload["license"]),
        rights_status=str(payload["rights_status"]),
        research_use=research_use,
        release_use=release_use,
        quality_status=str(payload["quality_status"]),
        families=families,
        roles=roles,
        raw=dict(payload),
    )

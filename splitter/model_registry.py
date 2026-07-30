from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = ROOT_DIR / "models" / "registry.yaml"

ALLOWED_RUNNERS = {
    "audio_separator",
    "bs_roformer_infer",
    "commercial_comparator",
    "external_python",
    "melband_roformer_infer",
    "mvsep_remote",
}
ALLOWED_DOWNLOAD_POLICIES = {
    "blocked_until_source_verified",
    "comparator_only",
    "external_runner_experimental",
    "immediate",
    "later_if_needed",
    "quarantined_replaced",
    "remote_only",
}
ALLOWED_LICENSE_STATUSES = {
    "commercial_approved",
    "non_commercial",
    "open_repo_allowed",
    "remote_service",
    "research_only",
    "unknown",
}
COMMERCIAL_SAFE_LICENSE_STATUSES = {"commercial_approved", "open_repo_allowed"}
REMOTE_RUNNERS = {"commercial_comparator", "mvsep_remote"}


class ModelRegistryError(ValueError):
    """Raised when the model registry is missing required or safe data."""


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    display_name: str
    runner: str
    output_stems: tuple[str, ...]
    use_for: tuple[str, ...]
    license_status: str
    download_policy: str
    selection_status: str
    reason: str
    raw: dict[str, Any]

    @property
    def is_remote(self) -> bool:
        return self.runner in REMOTE_RUNNERS

    @property
    def is_downloadable_now(self) -> bool:
        return self.download_policy == "immediate"

    @property
    def is_commercial_safe(self) -> bool:
        return self.license_status in COMMERCIAL_SAFE_LICENSE_STATUSES

    @property
    def normalized_output_stems(self) -> tuple[str, ...]:
        raw_stems = self.raw.get("normalized_output_stems") or self.output_stems
        return tuple(str(stem) for stem in raw_stems)


@dataclass(frozen=True)
class DownloadPack:
    pack_id: str
    priority: int
    model_ids: tuple[str, ...]


@dataclass(frozen=True)
class ModelRegistry:
    schema_version: str
    status: str
    path: Path
    models: dict[str, ModelEntry]
    download_packs: dict[str, DownloadPack]

    def get_model(self, model_id: str) -> ModelEntry:
        try:
            return self.models[model_id]
        except KeyError as exc:
            raise ModelRegistryError(f"unknown model id: {model_id}") from exc

    def get_pack(self, pack_id: str) -> DownloadPack:
        try:
            return self.download_packs[pack_id]
        except KeyError as exc:
            raise ModelRegistryError(f"unknown download pack: {pack_id}") from exc

    def models_for_pack(self, pack_id: str) -> list[ModelEntry]:
        return [self.get_model(model_id) for model_id in self.get_pack(pack_id).model_ids]

    def models_for_download_policy(self, policy: str) -> list[ModelEntry]:
        if policy not in ALLOWED_DOWNLOAD_POLICIES:
            raise ModelRegistryError(f"unknown download policy: {policy}")
        return [model for model in self.models.values() if model.download_policy == policy]

    def models_for_runner(self, runner: str) -> list[ModelEntry]:
        if runner not in ALLOWED_RUNNERS:
            raise ModelRegistryError(f"unknown runner: {runner}")
        return [model for model in self.models.values() if model.runner == runner]

    def models_for_use(self, use_case: str) -> list[ModelEntry]:
        return [model for model in self.models.values() if use_case in model.use_for]

    def models_for_output_stem(self, stem_name: str) -> list[ModelEntry]:
        return [
            model
            for model in self.models.values()
            if stem_name in model.output_stems or stem_name in model.normalized_output_stems
        ]

    def assert_models_allowed_for_profile(self, model_ids: list[str], profile: str) -> None:
        if profile != "commercial_candidate":
            return

        unsafe = [
            model.model_id
            for model in (self.get_model(model_id) for model_id in model_ids)
            if not model.is_commercial_safe
        ]
        if unsafe:
            raise ModelRegistryError(
                "commercial_candidate profile requires commercial-safe licenses: "
                + ", ".join(sorted(unsafe))
            )


def load_model_registry(path: Path | None = None) -> ModelRegistry:
    registry_path = (path or DEFAULT_REGISTRY_PATH).expanduser().resolve()
    data = _load_yaml_with_include(registry_path)
    _validate_registry_payload(data, registry_path)

    models = {
        model_id: _build_model_entry(model_id, payload)
        for model_id, payload in data["models"].items()
    }
    download_packs = {
        pack_id: DownloadPack(
            pack_id=pack_id,
            priority=int(payload["priority"]),
            model_ids=tuple(str(model_id) for model_id in payload["models"]),
        )
        for pack_id, payload in data["download_packs"].items()
    }
    return ModelRegistry(
        schema_version=str(data["schema_version"]),
        status=str(data["status"]),
        path=registry_path,
        models=models,
        download_packs=download_packs,
    )


def _load_yaml_with_include(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ModelRegistryError(f"model registry not found: {path}")

    payload = _read_yaml(path)
    include = payload.get("include")
    if not include:
        return payload

    include_path = (path.parent / str(include)).resolve()
    included = _read_yaml(include_path)
    merged = dict(included)
    merged.update({key: value for key, value in payload.items() if key != "include"})
    for key in ("download_packs", "models"):
        if key not in merged and key in included:
            merged[key] = included[key]
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ModelRegistryError(f"invalid yaml in model registry: {path}") from exc
    if not isinstance(payload, dict):
        raise ModelRegistryError(f"model registry must be a mapping: {path}")
    return payload


def _build_model_entry(model_id: str, payload: dict[str, Any]) -> ModelEntry:
    return ModelEntry(
        model_id=model_id,
        display_name=str(payload["display_name"]),
        runner=str(payload["runner"]),
        output_stems=tuple(str(stem) for stem in payload["output_stems"]),
        use_for=tuple(str(use_case) for use_case in payload["use_for"]),
        license_status=str(payload["license_status"]),
        download_policy=str(payload["download_policy"]),
        selection_status=str(payload["selection_status"]),
        reason=str(payload["reason"]),
        raw=dict(payload),
    )


def _validate_registry_payload(payload: dict[str, Any], path: Path) -> None:
    _require_mapping(payload, "models", path)
    _require_mapping(payload, "download_packs", path)
    _require_field(payload, "schema_version", path)
    _require_field(payload, "status", path)

    model_ids = set(payload["models"])
    packed_model_ids: set[str] = set()
    for pack_id, pack in payload["download_packs"].items():
        _validate_pack(pack_id, pack, model_ids, path)
        packed_model_ids.update(str(model_id) for model_id in pack["models"])

    unpacked = sorted(model_ids - packed_model_ids)
    if unpacked:
        raise ModelRegistryError(f"models missing from download packs: {', '.join(unpacked)}")

    for model_id, model in payload["models"].items():
        _validate_model(model_id, model, path)


def _validate_pack(pack_id: str, pack: Any, model_ids: set[str], path: Path) -> None:
    if not isinstance(pack, dict):
        raise ModelRegistryError(f"download pack must be a mapping: {pack_id}")
    _require_field(pack, "priority", path, context=pack_id)
    _require_list(pack, "models", path, context=pack_id)
    for model_id in pack["models"]:
        if model_id not in model_ids:
            raise ModelRegistryError(f"download pack {pack_id} references unknown model: {model_id}")


def _validate_model(model_id: str, model: Any, path: Path) -> None:
    if not isinstance(model, dict):
        raise ModelRegistryError(f"model entry must be a mapping: {model_id}")
    for field_name in (
        "display_name",
        "runner",
        "output_stems",
        "use_for",
        "license_status",
        "download_policy",
        "selection_status",
        "reason",
    ):
        _require_field(model, field_name, path, context=model_id)

    _require_list(model, "output_stems", path, context=model_id)
    _require_list(model, "use_for", path, context=model_id)

    runner = str(model["runner"])
    if runner not in ALLOWED_RUNNERS:
        raise ModelRegistryError(f"{model_id} has unknown runner: {runner}")

    license_status = str(model["license_status"])
    if license_status not in ALLOWED_LICENSE_STATUSES:
        raise ModelRegistryError(f"{model_id} has unknown license_status: {license_status}")

    download_policy = str(model["download_policy"])
    if download_policy not in ALLOWED_DOWNLOAD_POLICIES:
        raise ModelRegistryError(f"{model_id} has unknown download_policy: {download_policy}")

    if runner in REMOTE_RUNNERS and download_policy != "remote_only" and download_policy != "comparator_only":
        raise ModelRegistryError(f"{model_id} uses remote runner but has local download policy: {download_policy}")

    if download_policy == "immediate" and runner in REMOTE_RUNNERS:
        raise ModelRegistryError(f"{model_id} cannot be immediate because runner is remote: {runner}")

    has_source = any(
        model.get(field_name)
        for field_name in (
            "audio_separator_model_filename",
            "checkpoint_source",
            "model_filename",
            "registry_slug",
            "source",
        )
    )
    if not has_source:
        raise ModelRegistryError(f"{model_id} has no model source or filename")


def _require_mapping(payload: dict[str, Any], field_name: str, path: Path) -> None:
    _require_field(payload, field_name, path)
    if not isinstance(payload[field_name], dict):
        raise ModelRegistryError(f"{field_name} must be a mapping in {path}")


def _require_list(payload: dict[str, Any], field_name: str, path: Path, *, context: str) -> None:
    _require_field(payload, field_name, path, context=context)
    value = payload[field_name]
    if not isinstance(value, list) or not value:
        raise ModelRegistryError(f"{context}.{field_name} must be a non-empty list in {path}")


def _require_field(payload: dict[str, Any], field_name: str, path: Path, *, context: str | None = None) -> None:
    if field_name not in payload or payload[field_name] in (None, ""):
        prefix = f"{context}." if context else ""
        raise ModelRegistryError(f"missing required model registry field: {prefix}{field_name} in {path}")

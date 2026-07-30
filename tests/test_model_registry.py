from __future__ import annotations

from pathlib import Path

import pytest

from splitter.model_registry import ModelRegistryError, load_model_registry


def test_load_default_model_registry_contains_only_runtime_models() -> None:
    registry = load_model_registry()

    assert registry.schema_version == "1.0"
    assert registry.status == "runtime_registry"
    assert set(registry.models) == {
        "melband_kim_vocals",
        "bs_roformer_sw",
        "mdx23c_drumsep_jarredou_aufr33",
        "bs_roformer_sw_electric_guitar_head",
        "oulianov_bs_roformer_bowed_strings",
        "xlance_bs_roformer_synth_v2",
    }
    assert set(registry.download_packs) == {"runtime_models"}
    assert all(model.download_policy == "immediate" for model in registry.models.values())


def test_model_registry_assigns_one_runtime_owner_per_stem_family() -> None:
    registry = load_model_registry()

    runtime_ids = [model.model_id for model in registry.models_for_pack("runtime_models")]
    assert runtime_ids == [
        "melband_kim_vocals",
        "bs_roformer_sw",
        "mdx23c_drumsep_jarredou_aufr33",
        "bs_roformer_sw_electric_guitar_head",
        "oulianov_bs_roformer_bowed_strings",
        "xlance_bs_roformer_synth_v2",
    ]
    assert [model.model_id for model in registry.models_for_use("vocals")] == [
        "melband_kim_vocals"
    ]
    assert [model.model_id for model in registry.models_for_use("guitar")] == [
        "bs_roformer_sw"
    ]
    assert [model.model_id for model in registry.models_for_use("kick")] == [
        "mdx23c_drumsep_jarredou_aufr33"
    ]
    assert [model.model_id for model in registry.models_for_use("electric_guitar")] == [
        "bs_roformer_sw_electric_guitar_head"
    ]
    assert [model.model_id for model in registry.models_for_use("strings")] == [
        "oulianov_bs_roformer_bowed_strings"
    ]
    assert [model.model_id for model in registry.models_for_use("synth")] == [
        "xlance_bs_roformer_synth_v2"
    ]


def test_model_registry_rejects_missing_required_model_field(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
schema_version: 1.0
status: runtime_registry
download_packs:
  pack_1:
    priority: 1
    models: [broken_model]
models:
  broken_model:
    display_name: Broken
    output_stems: [vocals]
    use_for: [vocals]
    license_status: unknown
    download_policy: immediate
    selection_status: primary
    reason: Missing runner
""",
        encoding="utf-8",
    )

    with pytest.raises(ModelRegistryError, match="broken_model.runner"):
        load_model_registry(registry_path)


def test_model_registry_rejects_unknown_pack_model_reference(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
schema_version: 1.0
status: runtime_registry
download_packs:
  pack_1:
    priority: 1
    models: [missing_model]
models:
  valid_model:
    display_name: Valid
    runner: audio_separator
    model_filename: valid.onnx
    output_stems: [vocals]
    use_for: [vocals]
    license_status: unknown
    download_policy: immediate
    selection_status: primary
    reason: Valid fixture
""",
        encoding="utf-8",
    )

    with pytest.raises(ModelRegistryError, match="references unknown model"):
        load_model_registry(registry_path)


def test_model_registry_blocks_unknown_license_for_commercial_profile() -> None:
    registry = load_model_registry()

    with pytest.raises(ModelRegistryError, match="commercial-safe licenses"):
        registry.assert_models_allowed_for_profile(["bs_roformer_sw"], "commercial_candidate")

    registry.assert_models_allowed_for_profile(["bs_roformer_sw"], "research_specialist")


def test_model_registry_rejects_remote_model_with_local_download_policy(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
schema_version: 1.0
status: runtime_registry
download_packs:
  pack_1:
    priority: 1
    models: [remote_model]
models:
  remote_model:
    display_name: Remote
    runner: mvsep_remote
    source: https://example.test/model
    output_stems: [strings]
    use_for: [strings]
    license_status: remote_service
    download_policy: immediate
    selection_status: primary_remote
    reason: Invalid remote policy
""",
        encoding="utf-8",
    )

    with pytest.raises(ModelRegistryError, match="remote runner"):
        load_model_registry(registry_path)

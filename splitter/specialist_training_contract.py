from __future__ import annotations


SPECIALIST_BASE_IDS = (
    "electric_guitar",
    "strings",
    "synth",
    "wind_brass",
)

LEGACY_VALIDATION_GROUPS = {
    "electric_guitar": "electric_guitar",
    "strings": "strings_wind_brass",
    "wind_brass": "strings_wind_brass",
}


def legacy_validation_group(base_id: str) -> str | None:
    if base_id not in SPECIALIST_BASE_IDS:
        raise ValueError(f"unsupported specialist base: {base_id}")
    return LEGACY_VALIDATION_GROUPS.get(base_id)

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_QUALIFICATION_PATH = ROOT_DIR / "models" / "stem_qualification.yaml"


class StemQualificationError(ValueError):
    """Raised when release qualification evidence is missing or inconsistent."""


def load_stem_qualification(
    expected_stems: Iterable[str],
    path: Path | None = None,
) -> dict[str, Any]:
    qualification_path = path or DEFAULT_QUALIFICATION_PATH
    try:
        payload = yaml.safe_load(qualification_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StemQualificationError(
            f"stem qualification ledger not found: {qualification_path}"
        ) from exc
    except yaml.YAMLError as exc:
        raise StemQualificationError(
            f"invalid stem qualification ledger: {qualification_path}"
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("stems"), dict):
        raise StemQualificationError("stem qualification ledger must contain a stems mapping")

    expected = set(expected_stems)
    actual = set(payload["stems"])
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise StemQualificationError(
            f"stem qualification coverage mismatch; missing={missing}, unexpected={unexpected}"
        )

    passed_initial = sorted(
        stem
        for stem, evidence in payload["stems"].items()
        if str(evidence.get("benchmark_status", "")).startswith("passed_initial_")
    )
    production_qualified = sorted(
        stem
        for stem, evidence in payload["stems"].items()
        if evidence.get("production_eligible") is True
    )
    return {
        **payload,
        "passed_initial_stems": passed_initial,
        "production_qualified_stems": production_qualified,
        "unresolved_stems": sorted(expected - set(production_qualified)),
        "ledger_path": str(qualification_path.relative_to(ROOT_DIR)),
    }

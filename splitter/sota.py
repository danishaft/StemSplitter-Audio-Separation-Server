from __future__ import annotations

import json
import subprocess as sp
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import SOTA_INSTRUMENT_CONFIG, VENV_BIN
from .ground_truth import build_babyslakh_references, score_prediction_against_reference
from .util import ensure_dir

SOTA_INSTRUMENT_TARGETS = ("piano", "guitar")


@dataclass
class InstrumentCandidateScore:
    stem_name: str
    source: str
    path: str
    si_sdr: float
    sdr: float
    correlation: float
    error_loudness_db: float


@dataclass
class InstrumentComparisonReport:
    dataset: str
    song_name: str
    scores: dict[str, list[InstrumentCandidateScore]] = field(default_factory=dict)
    winners: dict[str, InstrumentCandidateScore] = field(default_factory=dict)
    missing_references: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def sota_instrument_runtime_status() -> tuple[bool, str | None]:
    runner = SOTA_INSTRUMENT_CONFIG.get("runner")
    if not runner:
        return False, "sota_instrument_runner_missing"
    if not Path(str(runner)).exists():
        return False, "sota_instrument_runner_missing"
    return True, None


def run_sota_instrument_runner(
    input_path: Path,
    output_dir: Path,
    *,
    targets: tuple[str, ...] = SOTA_INSTRUMENT_TARGETS,
    model: str | None = None,
) -> dict[str, Path]:
    runner = SOTA_INSTRUMENT_CONFIG.get("runner")
    if not runner:
        raise RuntimeError("sota_instrument_runner_missing")

    ensure_dir(output_dir)
    runner_path = Path(str(runner))
    if runner_path.suffix == ".py":
        python_bin = VENV_BIN / "python"
        cmd = [
            str(python_bin if python_bin.exists() else Path(sys.executable)),
            str(runner_path),
        ]
    else:
        cmd = [str(runner_path)]
    cmd.extend(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_dir),
            "--targets",
            ",".join(targets),
            "--model",
            model or str(SOTA_INSTRUMENT_CONFIG["model"]),
        ]
    )
    sp.run(cmd, check=True, capture_output=True, timeout=int(SOTA_INSTRUMENT_CONFIG["timeout"]))
    outputs: dict[str, Path] = {}
    for target in targets:
        path = output_dir / f"{target}.wav"
        if path.exists():
            outputs[target] = path.resolve()
    if not outputs:
        raise RuntimeError("sota_instrument_runner_produced_no_outputs")
    return outputs


def collect_manifest_instrument_candidates(manifest: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    candidates: dict[str, list[dict[str, str]]] = {target: [] for target in SOTA_INSTRUMENT_TARGETS}
    for group_name in ("published_broad_stems", "published_specialist_substems"):
        group = manifest.get(group_name, {})
        for target in SOTA_INSTRUMENT_TARGETS:
            payload = group.get(target)
            if payload and payload.get("path"):
                candidates[target].append(
                    {
                        "source": str(payload.get("source_model", group_name)),
                        "path": str(payload["path"]),
                    }
                )
    rejected_extended = manifest.get("rejected_candidates", {}).get("extended_stems", {})
    for target in SOTA_INSTRUMENT_TARGETS:
        payload = rejected_extended.get(target)
        if payload and payload.get("path"):
            candidates[target].append(
                {
                    "source": str(payload.get("source_model", "rejected_extended")),
                    "path": str(payload["path"]),
                }
            )
    return candidates


def compare_instrument_candidates_against_babyslakh(
    manifest: dict[str, Any],
    track_dir: Path,
    output_dir: Path,
    *,
    include_sota_runner: bool = False,
) -> InstrumentComparisonReport:
    report = InstrumentComparisonReport(dataset="babyslakh", song_name=track_dir.name)
    references = build_babyslakh_references(track_dir, ensure_dir(output_dir / "references"))
    candidates = collect_manifest_instrument_candidates(manifest)

    if include_sota_runner:
        available, reason = sota_instrument_runtime_status()
        if available:
            input_payload = manifest.get("published_broad_stems", {}).get("other") or manifest.get("published_broad_stems", {}).get("instrumental")
            if input_payload and input_payload.get("path"):
                try:
                    outputs = run_sota_instrument_runner(
                        Path(str(input_payload["path"])),
                        ensure_dir(output_dir / "sota_candidates"),
                    )
                except Exception as exc:
                    report.errors.append(f"sota_runner_failed:{exc}")
                else:
                    for stem_name, path in outputs.items():
                        if stem_name in candidates:
                            candidates[stem_name].append(
                                {
                                    "source": str(SOTA_INSTRUMENT_CONFIG["model"]),
                                    "path": str(path),
                                }
                            )
            else:
                report.errors.append("sota_runner_input_missing")
        elif reason:
            report.errors.append(reason)

    for stem_name in SOTA_INSTRUMENT_TARGETS:
        reference = references.get(stem_name)
        if not reference:
            report.missing_references.append(stem_name)
            continue
        for candidate in candidates.get(stem_name, []):
            path = Path(candidate["path"])
            if not path.exists():
                report.errors.append(f"candidate_missing:{stem_name}:{path}")
                continue
            score = score_prediction_against_reference(path, reference)
            report.scores.setdefault(stem_name, []).append(
                InstrumentCandidateScore(
                    stem_name=stem_name,
                    source=candidate["source"],
                    path=str(path.resolve()),
                    si_sdr=score.si_sdr,
                    sdr=score.sdr,
                    correlation=score.correlation,
                    error_loudness_db=score.error_loudness_db,
                )
            )
        if report.scores.get(stem_name):
            report.winners[stem_name] = max(report.scores[stem_name], key=lambda item: item.si_sdr)
    return report


def instrument_comparison_to_dict(report: InstrumentComparisonReport) -> dict[str, Any]:
    return {
        "dataset": report.dataset,
        "song_name": report.song_name,
        "missing_references": report.missing_references,
        "errors": report.errors,
        "scores": {
            stem_name: [
                {
                    "source": score.source,
                    "path": score.path,
                    "si_sdr": score.si_sdr,
                    "sdr": score.sdr,
                    "correlation": score.correlation,
                    "error_loudness_db": score.error_loudness_db,
                }
                for score in scores
            ]
            for stem_name, scores in report.scores.items()
        },
        "winners": {
            stem_name: {
                "source": score.source,
                "path": score.path,
                "si_sdr": score.si_sdr,
                "sdr": score.sdr,
                "correlation": score.correlation,
                "error_loudness_db": score.error_loudness_db,
            }
            for stem_name, score in report.winners.items()
        },
    }


def write_instrument_comparison(report: InstrumentComparisonReport, output_path: Path) -> Path:
    ensure_dir(output_path.parent)
    output_path.write_text(
        json.dumps(instrument_comparison_to_dict(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path

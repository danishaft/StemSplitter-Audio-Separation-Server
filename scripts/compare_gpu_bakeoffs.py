from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SystemExit(f"invalid bake-off report: {path}")
    return payload


def _quality_values(report: dict[str, object]) -> list[float]:
    return [
        float(score["si_sdr"])
        for result in report["results"]
        for score in result.get("ground_truth_scores", {}).values()
    ]


def _max_latency_seconds(report: dict[str, object], summary: dict[str, object]) -> float:
    wall_seconds = [
        float(result["unit_economics"]["worker_wall_seconds"])
        for result in report["results"]
        if isinstance(result.get("unit_economics"), dict)
        and result["unit_economics"].get("worker_wall_seconds") is not None
    ]
    if wall_seconds:
        return max(wall_seconds)
    return float(summary["max_gpu_seconds"])


def _comparable_costs(
    candidate: dict[str, object], other: dict[str, object]
) -> tuple[float, float]:
    candidate_actual = candidate.get("actual_interval_cost_usd")
    other_actual = other.get("actual_interval_cost_usd")
    if candidate_actual is not None and other_actual is not None:
        return float(candidate_actual), float(other_actual)
    return (
        float(candidate["estimated_base_gpu_cost_usd"]),
        float(other["estimated_base_gpu_cost_usd"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare compatible GPU bake-off reports.")
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latency-target-seconds", type=float, default=60.0)
    parser.add_argument("--quality-tolerance-si-sdr", type=float, default=0.05)
    args = parser.parse_args()

    reports = [_load(path.expanduser().resolve()) for path in args.reports]
    corpus_ids = {str(report.get("corpus_id")) for report in reports}
    selected_song_sets = {
        tuple(sorted(str(song_id) for song_id in report.get("selected_song_ids", [])))
        for report in reports
    }
    if len(corpus_ids) != 1 or len(selected_song_sets) != 1:
        raise SystemExit("reports must use the same corpus and selected songs")

    baseline_quality_values = _quality_values(reports[0])
    baseline_quality = mean(baseline_quality_values) if baseline_quality_values else None
    candidates: dict[str, dict[str, object]] = {}
    for report in reports:
        report_candidates = report.get("candidates")
        if not isinstance(report_candidates, dict) or len(report_candidates) != 1:
            raise SystemExit("each report must contain exactly one GPU candidate")
        gpu_type, summary = next(iter(report_candidates.items()))
        if not isinstance(summary, dict):
            raise SystemExit(f"invalid candidate summary for {gpu_type}")
        quality_values = _quality_values(report)
        quality = mean(quality_values) if quality_values else None
        max_seconds = _max_latency_seconds(report, summary)
        cost = float(summary["estimated_base_gpu_cost_usd"])
        candidates[str(gpu_type)] = {
            **summary,
            "max_latency_seconds": max_seconds,
            "actual_interval_cost_usd": (
                report.get("actual_billing", {}).get("actual_cost_per_selected_song_usd")
                if isinstance(report.get("actual_billing"), dict)
                else None
            ),
            "meets_latency_target": max_seconds <= args.latency_target_seconds,
            "quality_delta_si_sdr": (
                round(quality - baseline_quality, 6)
                if quality is not None and baseline_quality is not None
                else None
            ),
            "quality_within_tolerance": (
                abs(quality - baseline_quality) <= args.quality_tolerance_si_sdr
                if quality is not None and baseline_quality is not None
                else None
            ),
            "dominated": False,
        }

    for gpu_type, candidate in candidates.items():
        for other_gpu, other in candidates.items():
            if gpu_type == other_gpu:
                continue
            candidate_cost, other_cost = _comparable_costs(candidate, other)
            no_worse = (
                float(other["max_latency_seconds"]) <= float(candidate["max_latency_seconds"])
                and other_cost <= candidate_cost
            )
            strictly_better = (
                float(other["max_latency_seconds"]) < float(candidate["max_latency_seconds"])
                or other_cost < candidate_cost
            )
            if no_worse and strictly_better:
                candidate["dominated"] = True
                candidate["dominated_by"] = other_gpu
                break

    output = {
        "corpus_id": next(iter(corpus_ids)),
        "selected_song_ids": list(next(iter(selected_song_sets))),
        "latency_target_seconds": args.latency_target_seconds,
        "quality_tolerance_si_sdr": args.quality_tolerance_si_sdr,
        "baseline_gpu": next(iter(candidates)),
        "candidates": candidates,
    }
    target = args.output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(f"comparison={target}")
    for gpu_type, candidate in candidates.items():
        print(
            f"gpu={gpu_type} latency={candidate['max_latency_seconds']} "
            f"cost={candidate['estimated_base_gpu_cost_usd']} "
            f"actual_cost={candidate.get('actual_interval_cost_usd')} "
            f"meets_target={candidate['meets_latency_target']} "
            f"dominated={candidate['dominated']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

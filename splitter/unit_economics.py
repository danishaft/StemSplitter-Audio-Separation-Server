from __future__ import annotations

from typing import Any, Iterator


MODAL_RATE_CARD = {
    "provider": "modal",
    "effective_date": "2026-07-18",
    "source": "https://modal.com/pricing",
    "gpu_usd_per_second": {
        "B300": 0.001972,
        "B200": 0.001736,
        "H200": 0.001261,
        "H100": 0.001097,
        "RTX_PRO_6000": 0.000842,
        "A100_80GB": 0.000694,
        "A100_40GB": 0.000583,
        "L40S": 0.000542,
        "A10": 0.000306,
        "L4": 0.000222,
        "T4": 0.000164,
    },
}

GPU_TYPE_ALIASES = {
    "A100-80GB": "A100_80GB",
    "A100-40GB": "A100_40GB",
    "A100-80G": "A100_80GB",
    "A100-40G": "A100_40GB",
    "RTX-PRO-6000": "RTX_PRO_6000",
    "RTX PRO 6000": "RTX_PRO_6000",
}


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _storage_references(payload: object) -> Iterator[dict[str, object]]:
    if isinstance(payload, dict):
        if all(key in payload for key in ("provider", "bucket", "key")):
            yield payload
            return
        for value in payload.values():
            yield from _storage_references(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from _storage_references(value)


def _unique_storage_bytes(payload: object) -> tuple[int, int]:
    references: dict[tuple[str, str, str], int] = {}
    for reference in _storage_references(payload):
        identity = (
            str(reference.get("provider") or ""),
            str(reference.get("bucket") or ""),
            str(reference.get("key") or ""),
        )
        size = _number(reference.get("size_bytes")) or 0.0
        references[identity] = max(references.get(identity, 0), int(size))
    return sum(references.values()), len(references)


def _gpu_allocations(timings: dict[str, Any]) -> list[dict[str, object]]:
    payload = timings.get("gpu_allocations")
    if not isinstance(payload, list):
        return []
    allocations: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        gpu_type_raw = str(item.get("gpu_type") or "unknown")
        gpu_type = GPU_TYPE_ALIASES.get(gpu_type_raw.upper(), gpu_type_raw.upper())
        gpu_seconds = _number(item.get("gpu_seconds"))
        rate = MODAL_RATE_CARD["gpu_usd_per_second"].get(gpu_type)
        if gpu_seconds is None or gpu_seconds < 0:
            continue
        cost = gpu_seconds * rate if rate is not None else None
        allocations.append(
            {
                "role": str(item.get("role") or "unspecified"),
                "model_key": str(item.get("model_key") or ""),
                "gpu_type": gpu_type,
                "gpu_seconds": round(gpu_seconds, 3),
                "gpu_rate_usd_per_second": rate,
                "estimated_base_gpu_cost_usd": round(cost, 6) if cost is not None else None,
            }
        )
    return allocations


def build_unit_economics(worker_payload: dict[str, Any]) -> dict[str, object]:
    timings_payload = worker_payload.get("timings")
    timings = timings_payload if isinstance(timings_payload, dict) else {}
    gpu_type_raw = str(timings.get("gpu_type") or worker_payload.get("gpu_type") or "unknown")
    gpu_type = GPU_TYPE_ALIASES.get(gpu_type_raw.upper(), gpu_type_raw.upper())
    worker_wall_seconds = _number(timings.get("worker_total_seconds"))
    allocations = _gpu_allocations(timings)
    gpu_seconds = (
        sum(float(allocation["gpu_seconds"]) for allocation in allocations)
        if allocations
        else worker_wall_seconds
    )
    model_runs = timings.get("model_runs")
    model_seconds = 0.0
    if isinstance(model_runs, list):
        model_seconds = sum(
            _number(run.get("total_seconds")) or _number(run.get("duration_seconds")) or 0.0
            for run in model_runs
            if isinstance(run, dict)
        )

    input_duration = _number(timings.get("input_duration_seconds"))
    input_bytes, input_object_count = _unique_storage_bytes(worker_payload.get("input_object"))
    output_bytes, output_object_count = _unique_storage_bytes(worker_payload.get("object_artifacts"))
    bundle_bytes, bundle_object_count = _unique_storage_bytes(worker_payload.get("object_bundle"))
    rate = MODAL_RATE_CARD["gpu_usd_per_second"].get(gpu_type)
    allocation_costs = [allocation["estimated_base_gpu_cost_usd"] for allocation in allocations]
    if allocations and all(cost is not None for cost in allocation_costs):
        estimated_gpu_cost = sum(float(cost) for cost in allocation_costs)
    else:
        estimated_gpu_cost = gpu_seconds * rate if gpu_seconds is not None and rate is not None else None

    return {
        "evidence_level": "public_rate_estimate_not_invoice",
        "rate_card": {
            "provider": MODAL_RATE_CARD["provider"],
            "effective_date": MODAL_RATE_CARD["effective_date"],
            "source": MODAL_RATE_CARD["source"],
        },
        "gpu_type": gpu_type,
        "gpu_seconds": round(gpu_seconds, 3) if gpu_seconds is not None else None,
        "gpu_allocations": allocations,
        "worker_wall_seconds": round(worker_wall_seconds, 3) if worker_wall_seconds is not None else None,
        "model_seconds": round(model_seconds, 3),
        "gpu_rate_usd_per_second": rate,
        "estimated_base_gpu_cost_usd": round(estimated_gpu_cost, 6) if estimated_gpu_cost is not None else None,
        "estimated_base_gpu_cost_per_audio_minute_usd": (
            round(estimated_gpu_cost / (input_duration / 60.0), 6)
            if estimated_gpu_cost is not None and input_duration and input_duration > 0
            else None
        ),
        "input_duration_seconds": round(input_duration, 3) if input_duration is not None else None,
        "worker_realtime_factor": (
            round(worker_wall_seconds / input_duration, 4)
            if worker_wall_seconds is not None and input_duration and input_duration > 0
            else None
        ),
        "aggregate_gpu_realtime_factor": (
            round(gpu_seconds / input_duration, 4)
            if gpu_seconds is not None and input_duration and input_duration > 0
            else None
        ),
        "storage": {
            "input_bytes": input_bytes,
            "input_object_count": input_object_count,
            "output_stem_bytes": output_bytes,
            "output_stem_object_count": output_object_count,
            "bundle_bytes": bundle_bytes,
            "bundle_object_count": bundle_object_count,
            "total_unique_bytes": input_bytes + output_bytes + bundle_bytes,
        },
        "excluded_from_estimate": [
            "cpu",
            "memory",
            "container_cold_start_outside_worker_timer",
            "object_storage_months",
            "network_egress",
            "failed_jobs_and_retries",
            "payment_fees",
            "support",
            "credits_and_discounts",
        ],
    }

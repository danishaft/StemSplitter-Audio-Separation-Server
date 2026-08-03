from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

import librosa
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env_file(ROOT / ".env.local")

from splitter.benchmark_corpus import load_and_validate_corpus  # noqa: E402
from splitter.config import QUALITY_8_STEMS  # noqa: E402
from splitter.gpu_worker_client import GPUWorkerClient, wait_for_worker_job  # noqa: E402
from splitter.ground_truth import build_babyslakh_references, score_prediction_against_reference  # noqa: E402
from splitter.object_storage import object_store_from_config  # noqa: E402
from splitter.unit_economics import MODAL_RATE_CARD, build_unit_economics  # noqa: E402
from splitter.util import ensure_dir  # noqa: E402


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "candidate"


def _candidate(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("candidate must use GPU_TYPE[+GPU_TYPE]=https://worker-url")
    candidate_id, url = value.split("=", 1)
    candidate_id = candidate_id.strip().upper()
    gpu_types = [gpu_type.strip() for gpu_type in candidate_id.split("+") if gpu_type.strip()]
    unsupported = [
        gpu_type
        for gpu_type in gpu_types
        if gpu_type not in MODAL_RATE_CARD["gpu_usd_per_second"]
    ]
    if not gpu_types or unsupported:
        raise argparse.ArgumentTypeError(
            f"unsupported GPU type(s): {','.join(unsupported) or candidate_id}"
        )
    if not url.startswith("http"):
        raise argparse.ArgumentTypeError("candidate URL must start with http")
    return candidate_id, url.rstrip("/") + "/"


def _write_excerpt(song: dict[str, object], target: Path) -> Path:
    source = Path(str(song["path"])).expanduser().resolve()
    start = float(song["excerpt_start_seconds"])
    duration = float(song["excerpt_duration_seconds"])
    audio, sample_rate = librosa.load(source, sr=None, mono=False, offset=start, duration=duration)
    if audio.ndim == 1:
        audio = audio.reshape(1, -1)
    ensure_dir(target.parent)
    sf.write(target, audio.T, sample_rate, subtype="PCM_16")
    return target


def _reference_excerpt(source: Path, target: Path, *, start: float, duration: float) -> Path:
    audio, sample_rate = librosa.load(source, sr=None, mono=False, offset=start, duration=duration)
    if audio.ndim == 1:
        audio = audio.reshape(1, -1)
    ensure_dir(target.parent)
    sf.write(target, audio.T, sample_rate, subtype="PCM_16")
    return target


def _ground_truth_scores(
    song: dict[str, object],
    worker_payload: dict[str, object],
    output_dir: Path,
    store,
) -> dict[str, dict[str, float]]:
    if song.get("evidence_level") != "ground_truth":
        return {}
    reference_root = Path(str(song["reference_root"])).expanduser().resolve()
    if (reference_root / "metadata.yaml").is_file():
        full_references = build_babyslakh_references(
            reference_root,
            ensure_dir(output_dir / "full_references"),
        )
    else:
        full_references = {
            path.stem: path
            for path in sorted(reference_root.glob("*.wav"))
        }
    object_artifacts = worker_payload.get("object_artifacts")
    if not isinstance(object_artifacts, dict):
        return {}
    predictions: dict[str, dict[str, object]] = {}
    for group in object_artifacts.values():
        if isinstance(group, dict):
            predictions.update({name: ref for name, ref in group.items() if isinstance(ref, dict)})

    scores: dict[str, dict[str, float]] = {}
    start = float(song["excerpt_start_seconds"])
    duration = float(song["excerpt_duration_seconds"])
    for stem_name, full_reference in full_references.items():
        prediction_ref = predictions.get(stem_name)
        if prediction_ref is None:
            continue
        prediction_path = output_dir / "predictions" / f"{stem_name}.wav"
        if not prediction_path.is_file():
            prediction_path = store.download(prediction_ref, prediction_path)
        reference_path = output_dir / "references" / f"{stem_name}.wav"
        if not reference_path.is_file():
            reference_path = _reference_excerpt(
                full_reference,
                reference_path,
                start=start,
                duration=duration,
            )
        score = score_prediction_against_reference(prediction_path, reference_path)
        scores[stem_name] = {
            "si_sdr": round(score.si_sdr, 4),
            "sdr": round(score.sdr, 4),
            "correlation": round(score.correlation, 4),
            "error_loudness_db": round(score.error_loudness_db, 4),
        }
    return scores


def _contract_failure(payload: dict[str, object]) -> str | None:
    if payload.get("status") != "completed":
        return f"worker_status_{payload.get('status') or 'unknown'}"
    contract = payload.get("stem_contract")
    if not isinstance(contract, dict) or contract.get("status") != "complete":
        return "quality_8_contract_incomplete"
    object_artifacts = payload.get("object_artifacts")
    if not isinstance(object_artifacts, dict):
        return "object_artifacts_missing"
    published = {
        str(name)
        for group in object_artifacts.values()
        if isinstance(group, dict)
        for name, reference in group.items()
        if isinstance(reference, dict)
    }
    missing = [stem for stem in QUALITY_8_STEMS if stem not in published]
    return f"object_artifacts_incomplete:{','.join(missing)}" if missing else None


def _topology_failure(payload: dict[str, object], candidate_id: str) -> str | None:
    expected_gpu_count = len([part for part in candidate_id.split("+") if part])
    if expected_gpu_count <= 1:
        return None
    timings = payload.get("timings")
    if not isinstance(timings, dict):
        return "topology_mismatch:worker_timings_missing"
    if timings.get("execution_mode") != "heterogeneous_parallel":
        return (
            "topology_mismatch:"
            f"expected=heterogeneous_parallel,actual={timings.get('execution_mode') or 'sequential'}"
        )
    allocations = timings.get("gpu_allocations")
    actual_gpu_count = len(allocations) if isinstance(allocations, list) else 0
    if actual_gpu_count != expected_gpu_count:
        return f"topology_mismatch:expected_gpus={expected_gpu_count},actual_gpus={actual_gpu_count}"
    return None


def _candidate_summary(results: list[dict[str, object]], candidate_id: str) -> dict[str, object]:
    candidate_results = [item for item in results if item["gpu_type"] == candidate_id]
    completed_results = [
        item
        for item in candidate_results
        if item["status"] == "completed" and not item.get("contract_failure")
    ]
    gpu_seconds = [
        float(item["unit_economics"]["gpu_seconds"])
        for item in completed_results
        if item["unit_economics"].get("gpu_seconds") is not None
    ]
    worker_wall_seconds = [
        float(item["unit_economics"]["worker_wall_seconds"])
        for item in completed_results
        if item["unit_economics"].get("worker_wall_seconds") is not None
    ]
    costs = [
        float(item["unit_economics"]["estimated_base_gpu_cost_usd"])
        for item in completed_results
        if item["unit_economics"].get("estimated_base_gpu_cost_usd") is not None
    ]
    si_sdr_values = [
        score["si_sdr"]
        for item in completed_results
        for score in item["ground_truth_scores"].values()
    ]
    return {
        "completed_count": len(completed_results),
        "song_count": len(candidate_results),
        "avg_gpu_seconds": round(mean(gpu_seconds), 4) if gpu_seconds else None,
        "max_gpu_seconds": round(max(gpu_seconds), 4) if gpu_seconds else None,
        "avg_worker_wall_seconds": round(mean(worker_wall_seconds), 4) if worker_wall_seconds else None,
        "max_worker_wall_seconds": round(max(worker_wall_seconds), 4) if worker_wall_seconds else None,
        "estimated_base_gpu_cost_usd": round(sum(costs), 6),
        "avg_ground_truth_si_sdr": round(mean(si_sdr_values), 4) if si_sdr_values else None,
    }


def _write_report(
    report_path: Path,
    *,
    args: argparse.Namespace,
    validation,
    songs: list[dict[str, object]],
    projected_ceiling: float,
    results: list[dict[str, object]],
) -> None:
    candidate_ids = [candidate_id for candidate_id, _ in args.candidate]
    planned_result_count = len(songs) * len(candidate_ids)
    valid_result_count = sum(
        item.get("status") == "completed"
        and not item.get("contract_failure")
        and not item.get("quality_scoring_error")
        for item in results
    )
    has_failure = any(
        item.get("contract_failure") or item.get("quality_scoring_error")
        for item in results
    )
    benchmark_status = (
        "failed_early"
        if has_failure
        else "completed"
        if valid_result_count == planned_result_count
        else "in_progress"
    )
    report = {
        "benchmark_id": args.benchmark_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "corpus_id": validation.corpus_id,
        "selected_song_ids": [song["id"] for song in songs],
        "benchmark_status": benchmark_status,
        "planned_result_count": planned_result_count,
        "valid_result_count": valid_result_count,
        "release_claim_eligible": (
            benchmark_status == "completed"
            and validation.release_claim_eligible
            and args.diagnostic_duration_seconds is None
            and not args.skip_quality_scoring
        ),
        "diagnostic": args.diagnostic_duration_seconds is not None,
        "diagnostic_duration_seconds": args.diagnostic_duration_seconds,
        "worker_input_transport": args.worker_input_transport,
        "quality_scoring_enabled": not args.skip_quality_scoring,
        "projected_base_gpu_ceiling_usd": round(projected_ceiling, 6),
        "budget_usd": args.budget_usd,
        "rate_card": MODAL_RATE_CARD,
        "candidates": {
            candidate_id: _candidate_summary(results, candidate_id)
            for candidate_id in candidate_ids
        },
        "results": results,
    }
    temporary = report_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(report_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a budget-capped GPU cost and latency bake-off.")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--candidate", type=_candidate, action="append", required=True)
    parser.add_argument("--song-id", action="append", default=[])
    parser.add_argument("--diagnostic-duration-seconds", type=float)
    parser.add_argument("--max-worker-seconds-per-excerpt", type=float, default=180.0)
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--worker-input-transport",
        choices=("object", "direct"),
        default="object",
    )
    parser.add_argument("--skip-quality-scoring", action="store_true")
    parser.add_argument(
        "--reuse-existing-inputs",
        action="store_true",
        help="Reuse deterministic benchmark input keys without uploading them again.",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks" / "gpu_bakeoff")
    args = parser.parse_args()

    corpus, validation = load_and_validate_corpus(args.corpus.expanduser().resolve())
    songs = list(corpus["songs"])
    if args.song_id:
        requested_ids = set(args.song_id)
        songs = [song for song in songs if song["id"] in requested_ids]
        missing_ids = requested_ids - {str(song["id"]) for song in songs}
        if missing_ids:
            raise SystemExit(f"unknown song ids: {','.join(sorted(missing_ids))}")
    if args.diagnostic_duration_seconds is not None:
        diagnostic_duration = args.diagnostic_duration_seconds
        if diagnostic_duration <= 0:
            raise SystemExit("--diagnostic-duration-seconds must be positive")
        if any(diagnostic_duration > float(song["excerpt_duration_seconds"]) for song in songs):
            raise SystemExit("diagnostic duration cannot exceed the frozen excerpt duration")
        songs = [
            {**song, "excerpt_duration_seconds": diagnostic_duration}
            for song in songs
        ]
    rates = MODAL_RATE_CARD["gpu_usd_per_second"]
    projected_ceiling = sum(
        sum(rates[gpu_type] for gpu_type in candidate_id.split("+"))
        * args.max_worker_seconds_per_excerpt
        * len(songs)
        for candidate_id, _ in args.candidate
    )
    print(f"benchmark_id={args.benchmark_id}")
    print(f"song_count={len(songs)}")
    print(f"candidate_count={len(args.candidate)}")
    print(f"projected_base_gpu_ceiling_usd={projected_ceiling:.6f}")
    if not args.execute:
        print("execution=blocked_without_execute")
        return 0
    if args.budget_usd is None or args.budget_usd <= 0:
        raise SystemExit("--budget-usd is required with --execute")
    if projected_ceiling > args.budget_usd:
        raise SystemExit(
            f"projected ceiling ${projected_ceiling:.6f} exceeds budget ${args.budget_usd:.6f}"
        )

    store = object_store_from_config()
    if store is None and (
        args.worker_input_transport == "object" or not args.skip_quality_scoring
    ):
        raise SystemExit("object storage is not configured")
    benchmark_root = ensure_dir(args.output_dir.expanduser().resolve() / _slug(args.benchmark_id))
    report_path = benchmark_root / "report.json"
    results: list[dict[str, object]] = []
    if args.resume and report_path.is_file():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        if previous.get("benchmark_id") != args.benchmark_id:
            raise SystemExit("resume report benchmark id does not match")
        results = list(previous.get("results") or [])

    uploaded_inputs: dict[str, tuple[Path, dict[str, object] | None]] = {}

    def benchmark_input(song: dict[str, object]) -> tuple[Path, dict[str, object] | None]:
        song_id = str(song["id"])
        if song_id in uploaded_inputs:
            return uploaded_inputs[song_id]
        excerpt = _write_excerpt(song, benchmark_root / "inputs" / f"{song_id}.wav")
        if args.worker_input_transport == "direct":
            uploaded_inputs[song_id] = (excerpt, None)
            return uploaded_inputs[song_id]
        assert store is not None
        key = f"{store.prefix}/benchmarks/{_slug(args.benchmark_id)}/inputs/{song_id}.wav"
        content_type = mimetypes.guess_type(excerpt.name)[0] or "audio/wav"
        if args.reuse_existing_inputs:
            reference = {
                "provider": "s3",
                "bucket": store.bucket,
                "key": key,
                "content_type": content_type,
                "size_bytes": excerpt.stat().st_size,
            }
        else:
            reference = store.upload(excerpt, key, content_type).as_dict()
        uploaded_inputs[song_id] = (excerpt, reference)
        return uploaded_inputs[song_id]

    for candidate_id, base_url in args.candidate:
        client = GPUWorkerClient(
            base_url=base_url,
            api_key=os.getenv("GPU_WORKER_API_KEY") or None,
            timeout=int(os.getenv("GPU_WORKER_TIMEOUT", "30")),
        )
        for song in songs:
            song_id = str(song["id"])
            result_key = (candidate_id, song_id)
            prior = next(
                (
                    item
                    for item in results
                    if (item.get("gpu_type"), item.get("song_id")) == result_key
                ),
                None,
            )
            if (
                prior is not None
                and prior.get("status") == "completed"
                and not prior.get("contract_failure")
                and not prior.get("quality_scoring_error")
            ):
                print(f"gpu={candidate_id} song={song_id} status=resume_skipped", flush=True)
                continue
            results = [
                item
                for item in results
                if (item.get("gpu_type"), item.get("song_id")) != result_key
            ]
            excerpt, input_reference = benchmark_input(song)
            worker_job_id = _slug(f"{args.benchmark_id}-{candidate_id}-{song_id}")
            if input_reference is None:
                submitted = client.submit(
                    excerpt,
                    profile="quality_gpu_experimental",
                    local_job_id=worker_job_id,
                    max_worker_seconds=args.max_worker_seconds_per_excerpt,
                )
            else:
                submitted = client.submit_object(
                    input_reference,
                    input_name=excerpt.name,
                    profile="quality_gpu_experimental",
                    local_job_id=worker_job_id,
                    max_worker_seconds=args.max_worker_seconds_per_excerpt,
                )
            if str(submitted.get("status")) in {"completed", "error", "failed"}:
                completed = submitted
            else:
                completed = wait_for_worker_job(client, worker_job_id, on_update=lambda _: None)
            economics = build_unit_economics(completed)
            contract_failure = _contract_failure(completed) or _topology_failure(
                completed,
                candidate_id,
            )
            result: dict[str, object] = {
                "gpu_type": candidate_id,
                "song_id": song_id,
                "evidence_level": song.get("evidence_level"),
                "difficulty": song.get("difficulty"),
                "excerpt_start_seconds": song.get("excerpt_start_seconds"),
                "excerpt_duration_seconds": song.get("excerpt_duration_seconds"),
                "worker_job_id": worker_job_id,
                "status": completed.get("status"),
                "stage": completed.get("stage"),
                "error": completed.get("error"),
                "missing_features": completed.get("missing_features"),
                "contract_failure": contract_failure,
                "stem_contract": completed.get("stem_contract"),
                "object_artifacts": completed.get("object_artifacts"),
                "timings": completed.get("timings"),
                "unit_economics": economics,
                "ground_truth_scores": {},
            }
            results.append(result)
            _write_report(
                report_path,
                args=args,
                validation=validation,
                songs=songs,
                projected_ceiling=projected_ceiling,
                results=results,
            )
            print(
                f"gpu={candidate_id} song={song_id} status={completed.get('status')} "
                f"gpu_seconds={economics.get('gpu_seconds')} "
                f"estimated_gpu_usd={economics.get('estimated_base_gpu_cost_usd')}",
                flush=True,
            )
            if contract_failure:
                raise SystemExit(
                    f"benchmark stopped after {candidate_id}/{song_id}: {contract_failure}; "
                    f"checkpoint={report_path}"
                )
            if args.skip_quality_scoring:
                _write_report(
                    report_path,
                    args=args,
                    validation=validation,
                    songs=songs,
                    projected_ceiling=projected_ceiling,
                    results=results,
                )
                continue
            assert store is not None
            try:
                result["ground_truth_scores"] = _ground_truth_scores(
                    song,
                    completed,
                    benchmark_root / "quality" / candidate_id / song_id,
                    store,
                )
            except Exception as exc:
                result["quality_scoring_error"] = f"{type(exc).__name__}:{exc}"
                _write_report(
                    report_path,
                    args=args,
                    validation=validation,
                    songs=songs,
                    projected_ceiling=projected_ceiling,
                    results=results,
                )
                raise
            _write_report(
                report_path,
                args=args,
                validation=validation,
                songs=songs,
                projected_ceiling=projected_ceiling,
                results=results,
            )

    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

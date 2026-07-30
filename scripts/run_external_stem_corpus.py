from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import librosa
import requests
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.external_stem_benchmark import (  # noqa: E402
    ExternalStemBenchmarkConfig,
    run_external_stem_benchmark,
)
from splitter.util import ensure_dir  # noqa: E402


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _headers() -> dict[str, str]:
    api_key = os.getenv("COCKTAIL_FORK_WORKER_API_KEY")
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "song"


def _load_corpus(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("corpus file must contain a list")
    return payload


def _write_excerpt(input_path: Path, output_path: Path, max_seconds: float | None) -> Path:
    if max_seconds is None:
        return input_path
    audio, sample_rate = librosa.load(input_path, sr=None, mono=False)
    if audio.ndim == 1:
        audio = audio.reshape(1, -1)
    max_samples = int(sample_rate * max_seconds)
    excerpt = audio[:, :max_samples].T
    ensure_dir(output_path.parent)
    sf.write(output_path, excerpt, sample_rate, subtype="PCM_16")
    return output_path


def _download(base_url: str, artifact_url: str, target: Path) -> None:
    ensure_dir(target.parent)
    url = artifact_url if artifact_url.startswith("http") else urljoin(base_url, artifact_url.lstrip("/"))
    with requests.get(url, headers=_headers(), stream=True, timeout=300) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def _run_cocktail_fork(
    input_path: Path,
    *,
    worker_job_id: str,
    output_dir: Path,
    reuse_existing: bool,
) -> dict[str, object]:
    stems_dir = output_dir / "specialist_substems"
    status_path = output_dir / "status.json"
    if reuse_existing and status_path.exists() and all((stems_dir / f"{stem}.wav").exists() for stem in ("speech_dialog", "music", "sfx")):
        return json.loads(status_path.read_text(encoding="utf-8"))

    base_url = os.getenv("COCKTAIL_FORK_WORKER_URL")
    if not base_url:
        raise SystemExit("COCKTAIL_FORK_WORKER_URL is not configured")
    base_url = base_url.rstrip("/") + "/"
    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
    timeout = int(os.getenv("COCKTAIL_FORK_WORKER_TIMEOUT", "1800"))
    with input_path.open("rb") as handle:
        response = requests.post(
            urljoin(base_url, "separate"),
            headers=_headers(),
            data={"local_job_id": worker_job_id},
            files={"file": (input_path.name, handle, content_type)},
            timeout=timeout,
        )
    response.raise_for_status()
    payload = response.json()
    ensure_dir(output_dir)
    status_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    artifacts = payload.get("artifacts", {}).get("specialist_substems", {})
    if isinstance(artifacts, dict):
        for stem_name, artifact_url in artifacts.items():
            if isinstance(artifact_url, str):
                _download(base_url, artifact_url, stems_dir / f"{stem_name}.wav")
    return payload


def _write_aggregate_markdown(payload: dict[str, object]) -> str:
    lines = [
        f"# External stem corpus benchmark {payload['benchmark_id']}",
        "",
        "This report aggregates speech, music, and SFX external-runner evidence",
        "across a small corpus. It is not a production quality claim unless",
        "ground-truth or comparator scores are present.",
        "",
        f"- System: `{payload['system_name']}`",
        f"- Corpus: `{payload['corpus_file']}`",
        f"- Songs: `{payload['song_count']}`",
        f"- Successful workers: `{payload['worker_success_count']}`",
        f"- Sanity pass count: `{payload['sanity_pass_count']}`",
        f"- Evidence levels: `{payload['evidence_levels']}`",
        "",
        "## Songs",
        "",
        "| Song | Worker | Evidence | Sanity | Warnings | Residual dB vs input |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for result in payload["results"]:
        reconstruction = result.get("reconstruction") or {}
        lines.append(
            f"| `{result['song_name']}` | `{result['worker_status']}` | "
            f"`{result['evidence_level']}` | `{result['sanity_pass']}` | "
            f"`{', '.join(result['warnings']) or 'none'}` | "
            f"{reconstruction.get('residual_rms_db_vs_input', 'n/a')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    _load_env_file(ROOT / ".env.local")
    parser = argparse.ArgumentParser(description="Run Cocktail Fork speech/music/SFX benchmark on a corpus.")
    parser.add_argument("--corpus-file", type=Path, required=True)
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--system-name", default="cocktail_fork_mrx")
    parser.add_argument("--max-seconds", type=float, default=20.0)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks" / "external_stems")
    parser.add_argument("--jobs-dir", type=Path, default=ROOT / "jobs" / "external_stem_corpus")
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--comparator-root", type=Path, action="append", default=[])
    parser.add_argument("--reuse-existing", action="store_true")
    args = parser.parse_args()

    corpus_path = args.corpus_file.expanduser().resolve()
    songs = _load_corpus(corpus_path)
    job_root = ensure_dir(args.jobs_dir.expanduser().resolve() / args.benchmark_id)
    report_root = ensure_dir(args.output_dir.expanduser().resolve() / args.benchmark_id)

    results: list[dict[str, object]] = []
    for item in songs:
        input_path = Path(str(item["path"])).expanduser().resolve()
        song_name = _slug(str(item.get("name") or input_path.stem))
        song_root = ensure_dir(job_root / song_name)
        excerpt_path = _write_excerpt(input_path, song_root / "input" / f"{song_name}-{int(args.max_seconds)}s.wav", args.max_seconds)
        worker_job_id = f"{args.benchmark_id}_{song_name}"
        print(f"{song_name}: worker start", flush=True)
        worker_payload = _run_cocktail_fork(
            excerpt_path,
            worker_job_id=worker_job_id,
            output_dir=song_root,
            reuse_existing=args.reuse_existing,
        )
        print(f"{song_name}: worker status={worker_payload.get('status')}", flush=True)

        reference_dir = args.reference_root.expanduser().resolve() / song_name if args.reference_root else None
        if reference_dir is not None and not reference_dir.exists():
            reference_dir = None
        comparator_dirs = []
        for root in args.comparator_root:
            candidate = root.expanduser().resolve() / song_name
            if candidate.exists():
                comparator_dirs.append(candidate)

        benchmark_payload = run_external_stem_benchmark(
            ExternalStemBenchmarkConfig(
                benchmark_id=f"{args.benchmark_id}_{song_name}",
                system_name=args.system_name,
                input_path=excerpt_path,
                prediction_dir=song_root / "specialist_substems",
                output_dir=report_root / "songs",
                reference_dir=reference_dir,
                comparator_dirs=tuple(comparator_dirs),
            )
        )
        results.append(
            {
                "song_name": song_name,
                "input_path": str(input_path),
                "excerpt_path": str(excerpt_path),
                "worker_job_id": worker_job_id,
                "worker_status": worker_payload.get("status"),
                "worker_missing_features": worker_payload.get("missing_features") or [],
                "report_json": str((report_root / "songs" / f"{args.benchmark_id}_{song_name}.json").resolve()),
                "report_md": str((report_root / "songs" / f"{args.benchmark_id}_{song_name}.md").resolve()),
                "evidence_level": benchmark_payload["evidence_level"],
                "sanity_pass": benchmark_payload["sanity_pass"],
                "warnings": benchmark_payload["warnings"],
                "reconstruction": benchmark_payload["reconstruction"],
            }
        )

    aggregate = {
        "benchmark_id": args.benchmark_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "system_name": args.system_name,
        "corpus_file": str(corpus_path),
        "song_count": len(results),
        "worker_success_count": sum(1 for result in results if result["worker_status"] == "completed"),
        "sanity_pass_count": sum(1 for result in results if result["sanity_pass"]),
        "evidence_levels": sorted({str(result["evidence_level"]) for result in results}),
        "results": results,
    }
    aggregate_json = report_root / "aggregate.json"
    aggregate_md = report_root / "aggregate.md"
    aggregate_json.write_text(json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8")
    aggregate_md.write_text(_write_aggregate_markdown(aggregate), encoding="utf-8")
    print(f"aggregate_json={aggregate_json}")
    print(f"aggregate_md={aggregate_md}")
    print(f"worker_success_count={aggregate['worker_success_count']}/{aggregate['song_count']}")
    print(f"sanity_pass_count={aggregate['sanity_pass_count']}/{aggregate['song_count']}")
    return 0 if aggregate["worker_success_count"] == aggregate["song_count"] and aggregate["sanity_pass_count"] == aggregate["song_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

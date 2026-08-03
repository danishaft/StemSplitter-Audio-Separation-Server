from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.benchmark import BenchmarkRunner, BenchmarkSong, compare_benchmarks


def _load_corpus_from_entries(entries: list[list[str]]) -> list[BenchmarkSong]:
    songs: list[BenchmarkSong] = []
    for difficulty, raw_path in entries:
        path = Path(raw_path).expanduser().resolve()
        songs.append(
            BenchmarkSong(
                name=path.stem,
                path=path,
                difficulty=difficulty,
            )
        )
    return songs


def _load_corpus_from_file(path: Path) -> list[BenchmarkSong]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    songs: list[BenchmarkSong] = []
    for item in payload:
        songs.append(
            BenchmarkSong(
                name=item.get("name") or Path(item["path"]).stem,
                path=Path(item["path"]).expanduser().resolve(),
                difficulty=item["difficulty"],
                genre=item.get("genre"),
                bpm=item.get("bpm"),
                duration=item.get("duration"),
                notes=item.get("notes", ""),
            )
        )
    return songs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local benchmark harness on a song corpus.")
    parser.add_argument("--profile", default="quality", help="Runtime profile to benchmark.")
    parser.add_argument(
        "--song",
        action="append",
        nargs=2,
        metavar=("DIFFICULTY", "PATH"),
        help="Add a song entry as: --song mixed /abs/path/to/file.wav",
    )
    parser.add_argument("--corpus-file", type=Path, help="Optional JSON corpus file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks") / "results",
        help="Directory where benchmark reports should be written.",
    )
    parser.add_argument("--benchmark-id", help="Optional benchmark id. Defaults to UTC timestamp.")
    parser.add_argument("--compare-to", type=Path, help="Optional prior benchmark JSON for comparison.")
    args = parser.parse_args()

    if args.corpus_file:
        corpus = _load_corpus_from_file(args.corpus_file.expanduser().resolve())
    elif args.song:
        corpus = _load_corpus_from_entries(args.song)
    else:
        raise SystemExit("Provide either --song entries or --corpus-file.")

    benchmark_id = args.benchmark_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    runner = BenchmarkRunner(corpus, args.output_dir.expanduser().resolve())
    report = runner.run(benchmark_id=benchmark_id, profile=args.profile)

    current_report = args.output_dir.expanduser().resolve() / f"benchmark_{benchmark_id}.json"
    print(f"benchmark_id={report.benchmark_id}")
    print(f"report_json={current_report}")
    print(f"evidence_level={report.evidence_level}")
    print(f"release_claim_eligible={str(report.release_claim_eligible).lower()}")
    print(f"success_rate={report.success_rate:.3f}")
    print(f"avg_broad_quality={report.avg_broad_quality:.3f}")
    print(f"avg_derived_quality={report.avg_derived_quality:.3f}")
    print(f"avg_specialist_quality={report.avg_specialist_quality:.3f}")
    print(f"publish_rate_broad={report.publish_rate_broad:.3f}")
    print(f"publish_rate_derived={report.publish_rate_derived:.3f}")
    print(f"publish_rate_specialist={report.publish_rate_specialist:.3f}")

    if args.compare_to:
        comparison = compare_benchmarks(current_report, args.compare_to.expanduser().resolve())
        print("comparison=" + json.dumps(comparison, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

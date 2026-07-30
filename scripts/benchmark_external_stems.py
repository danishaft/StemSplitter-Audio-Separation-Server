from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.external_stem_benchmark import (  # noqa: E402
    ExternalStemBenchmarkConfig,
    run_external_stem_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark external speech/music/SFX stem outputs.",
    )
    parser.add_argument("--input", type=Path, required=True, help="Original mixture audio.")
    parser.add_argument(
        "--prediction-dir",
        type=Path,
        required=True,
        help="Directory containing speech_dialog/music/sfx WAV outputs.",
    )
    parser.add_argument("--system-name", default="external_runner")
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "benchmarks" / "external_stems",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        help="Optional ground-truth directory with speech/music/sfx WAVs.",
    )
    parser.add_argument(
        "--comparator-dir",
        type=Path,
        action="append",
        default=[],
        help="Optional comparator output directory, for example MVSep or CDX.",
    )
    args = parser.parse_args()

    payload = run_external_stem_benchmark(
        ExternalStemBenchmarkConfig(
            benchmark_id=args.benchmark_id,
            system_name=args.system_name,
            input_path=args.input,
            prediction_dir=args.prediction_dir,
            output_dir=args.output_dir,
            reference_dir=args.reference_dir,
            comparator_dirs=tuple(args.comparator_dir),
        )
    )

    print(f"benchmark_id={payload['benchmark_id']}")
    print(f"report_json={args.output_dir.expanduser().resolve() / (args.benchmark_id + '.json')}")
    print(f"report_md={args.output_dir.expanduser().resolve() / (args.benchmark_id + '.md')}")
    print(f"evidence_level={payload['evidence_level']}")
    print(f"sanity_pass={payload['sanity_pass']}")
    print(f"warnings={payload['warnings']}")
    if payload["reconstruction"]:
        print(f"stem_sum_sdr_to_input={payload['reconstruction']['stem_sum_sdr_to_input']}")
        print(f"residual_rms_db_vs_input={payload['reconstruction']['residual_rms_db_vs_input']}")
    return 0 if payload["sanity_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

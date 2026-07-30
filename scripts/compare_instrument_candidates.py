from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.sota import (
    compare_instrument_candidates_against_babyslakh,
    write_instrument_comparison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare piano/guitar candidates against ground truth.")
    parser.add_argument("--dataset", choices=("babyslakh",), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--track-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks") / "sota_candidates")
    parser.add_argument("--report-name", default="instrument-candidates.json")
    parser.add_argument("--include-sota-runner", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.expanduser().resolve().read_text(encoding="utf-8"))
    if args.dataset == "babyslakh":
        report = compare_instrument_candidates_against_babyslakh(
            manifest,
            args.track_dir.expanduser().resolve(),
            args.output_dir.expanduser().resolve(),
            include_sota_runner=args.include_sota_runner,
        )
    else:
        raise SystemExit(f"unsupported dataset: {args.dataset}")

    report_path = write_instrument_comparison(
        report,
        args.output_dir.expanduser().resolve() / args.report_name,
    )
    print(f"report_json={report_path}")
    for stem_name, winner in sorted(report.winners.items()):
        print(
            f"{stem_name}: winner={winner.source} "
            f"si_sdr={winner.si_sdr:.3f} sdr={winner.sdr:.3f} corr={winner.correlation:.3f}"
        )
    if report.errors:
        print("errors=" + ",".join(report.errors))
    if report.missing_references:
        print("missing_references=" + ",".join(report.missing_references))
    return 0 if report.winners else 1


if __name__ == "__main__":
    raise SystemExit(main())

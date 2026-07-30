from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.ground_truth import evaluate_manifest_against_babyslakh, write_ground_truth_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a completed job manifest against ground-truth stems.")
    parser.add_argument("--dataset", choices=("babyslakh",), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--track-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks") / "ground_truth")
    parser.add_argument("--report-name", default="ground-truth-report.json")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.expanduser().resolve().read_text(encoding="utf-8"))
    output_dir = args.output_dir.expanduser().resolve()
    if args.dataset == "babyslakh":
        report = evaluate_manifest_against_babyslakh(
            manifest,
            args.track_dir.expanduser().resolve(),
            output_dir,
        )
    else:
        raise SystemExit(f"unsupported dataset: {args.dataset}")

    report_path = write_ground_truth_report(report, output_dir / args.report_name)
    print(f"report_json={report_path}")
    print(f"success={report.success}")
    print(f"scored_stems={','.join(sorted(report.scores))}")
    if report.missing_predictions:
        print(f"missing_predictions={','.join(report.missing_predictions)}")
    if report.missing_references:
        print(f"missing_references={','.join(report.missing_references)}")
    if report.error_message:
        print(f"error={report.error_message}")
    for stem_name, score in sorted(report.scores.items()):
        print(
            f"{stem_name}: si_sdr={score.si_sdr:.3f} "
            f"sdr={score.sdr:.3f} corr={score.correlation:.3f}"
        )
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

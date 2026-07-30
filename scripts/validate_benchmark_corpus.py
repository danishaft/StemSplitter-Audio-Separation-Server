from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.benchmark_corpus import load_and_validate_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a frozen stem-separation benchmark corpus.")
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--skip-file-verification", action="store_true")
    args = parser.parse_args()

    _, result = load_and_validate_corpus(
        args.corpus.expanduser().resolve(),
        verify_files=not args.skip_file_verification,
    )
    print(f"corpus_id={result.corpus_id}")
    print(f"song_count={result.song_count}")
    print(f"ground_truth_count={result.ground_truth_count}")
    print(f"listening_only_count={result.listening_only_count}")
    print(f"total_excerpt_seconds={result.total_excerpt_seconds}")
    print(f"release_claim_eligible={str(result.release_claim_eligible).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

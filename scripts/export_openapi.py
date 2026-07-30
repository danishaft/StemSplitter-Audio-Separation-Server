from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio_api import app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI contract.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("frontend/src/api/openapi.json"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()

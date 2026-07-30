from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parent.parent


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


def _download(base_url: str, artifact_url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    url = artifact_url if artifact_url.startswith("http") else urljoin(base_url, artifact_url.lstrip("/"))
    with requests.get(url, headers=_headers(), stream=True, timeout=300) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def main() -> int:
    _load_env_file(ROOT / ".env.local")
    parser = argparse.ArgumentParser(description="Smoke-test Cocktail Fork worker.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--job-id", default="cocktail_fork_smoke")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "jobs" / "cocktail_fork_smoke")
    args = parser.parse_args()

    base_url = os.getenv("COCKTAIL_FORK_WORKER_URL")
    if not base_url:
        raise SystemExit("COCKTAIL_FORK_WORKER_URL is not configured")
    base_url = base_url.rstrip("/") + "/"

    input_path = args.input.resolve()
    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
    with input_path.open("rb") as handle:
        response = requests.post(
            urljoin(base_url, "separate"),
            headers=_headers(),
            data={"local_job_id": args.job_id},
            files={"file": (input_path.name, handle, content_type)},
            timeout=1800,
        )
    response.raise_for_status()
    payload = response.json()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "status.json").write_text(response.text, encoding="utf-8")
    artifacts = payload.get("artifacts", {}).get("specialist_substems", {})
    if isinstance(artifacts, dict):
        for name, artifact_url in artifacts.items():
            if isinstance(artifact_url, str):
                _download(base_url, artifact_url, args.out_dir / "specialist_substems" / f"{name}.wav")

    print(f"status={payload.get('status')}")
    print(f"missing={payload.get('missing_features')}")
    print(f"runner_reason={payload.get('runner_reason')}")
    if payload.get("runner_stderr_tail"):
        print("runner_stderr_tail:")
        print(payload["runner_stderr_tail"])
    print(f"artifacts={sorted(artifacts) if isinstance(artifacts, dict) else []}")
    print(f"out_dir={args.out_dir}")
    return 0 if payload.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

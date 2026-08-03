from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


PROFILES = [
    "candidate_uvr_bve_backing_vocals",
    "candidate_mdxnet_karaoke_2",
    "candidate_karaoke_gabox",
    "candidate_karaoke_becruily",
    "candidate_melband_crowd",
    "candidate_mdxnet_crowd_hq_1",
]


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

from splitter.gpu_worker_client import GPUWorkerClient, copy_worker_artifacts  # noqa: E402
from splitter.util import ensure_dir  # noqa: E402


def _zip_outputs(job_root: Path, target: Path) -> None:
    ensure_dir(target.parent)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((job_root / "outputs").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(job_root).as_posix())
        manifest = job_root / "manifest.json"
        if manifest.exists():
            archive.write(manifest, manifest.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run focused GPU candidate bake-off.")
    parser.add_argument("input", type=Path, help="Input audio file.")
    parser.add_argument("--job-id", default="", help="Stable local bake-off id.")
    args = parser.parse_args()

    client = GPUWorkerClient.from_config()
    if client is None:
        raise SystemExit("GPU_WORKER_URL is not configured")

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"input not found: {input_path}")

    bakeoff_id = args.job_id or f"bakeoff_{input_path.stem}"
    job_root = ensure_dir(ROOT / "jobs" / bakeoff_id)
    manifest: dict[str, object] = {
        "bakeoff_id": bakeoff_id,
        "input": str(input_path),
        "profiles": {},
    }

    for profile in PROFILES:
        worker_job_id = f"{bakeoff_id}_{profile}"
        print(f"{profile}: start", flush=True)
        payload = client.submit(input_path, profile=profile, local_job_id=worker_job_id)
        profile_root = ensure_dir(job_root / "outputs" / profile)
        copied = copy_worker_artifacts(client, payload, profile_root, seen=set())
        artifacts = copied.get("specialist_substems", {})
        manifest["profiles"][profile] = {
            "worker_job_id": worker_job_id,
            "status": payload.get("status"),
            "missing_features": payload.get("missing_features") or [],
            "artifact_names": sorted(artifacts),
            "artifact_paths": {
                name: str(info.get("path"))
                for name, info in sorted(artifacts.items())
                if isinstance(info, dict)
            },
        }
        print(
            f"{profile}: status={payload.get('status')} "
            f"missing={payload.get('missing_features') or []} "
            f"artifacts={sorted(artifacts)}",
            flush=True,
        )

    manifest_path = job_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    zip_path = job_root / "candidate_bakeoff_outputs.zip"
    _zip_outputs(job_root, zip_path)
    print(f"manifest={manifest_path}")
    print(f"zip={zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

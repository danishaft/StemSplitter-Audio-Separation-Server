from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import librosa
import numpy as np
import requests
import soundfile as sf


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
    api_key = os.getenv("BANDIT_WORKER_API_KEY")
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _write_clip(input_path: Path, clip_path: Path, *, seconds: float, sample_rate: int) -> None:
    audio, _ = librosa.load(input_path, sr=sample_rate, mono=False, duration=seconds)
    if audio.ndim == 1:
        audio = audio[None, :]
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(clip_path, audio.T, sample_rate)


def _download(base_url: str, artifact_url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    url = artifact_url if artifact_url.startswith("http") else urljoin(base_url, artifact_url.lstrip("/"))
    with requests.get(url, headers=_headers(), stream=True, timeout=300) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


def _audio_stats(path: Path) -> dict[str, object]:
    audio, sample_rate = sf.read(path, always_2d=True)
    mono = audio.mean(axis=1)
    return {
        "path": str(path),
        "sample_rate": sample_rate,
        "duration_seconds": round(len(audio) / sample_rate, 3),
        "channels": audio.shape[1],
        "size_bytes": path.stat().st_size,
        "rms": float(np.sqrt(np.mean(np.square(mono))) if mono.size else 0.0),
        "peak": float(np.max(np.abs(mono)) if mono.size else 0.0),
    }


def main() -> int:
    _load_env_file(ROOT / ".env.local")
    parser = argparse.ArgumentParser(description="Smoke-test BandIt worker.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--job-id", default="bandit_worker_smoke")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "jobs" / "bandit_worker_smoke")
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--sample-rate", type=int, default=48000)
    args = parser.parse_args()

    base_url = os.getenv("BANDIT_WORKER_URL")
    if not base_url:
        raise SystemExit("BANDIT_WORKER_URL is not configured")
    base_url = base_url.rstrip("/") + "/"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    input_clip = args.out_dir / "input" / "bandit-smoke-input.wav"
    _write_clip(args.input.resolve(), input_clip, seconds=args.seconds, sample_rate=args.sample_rate)

    content_type = mimetypes.guess_type(input_clip.name)[0] or "application/octet-stream"
    with input_clip.open("rb") as handle:
        response = requests.post(
            urljoin(base_url, "separate"),
            headers=_headers(),
            data={"local_job_id": args.job_id},
            files={"file": (input_clip.name, handle, content_type)},
            timeout=1800,
        )
    response.raise_for_status()
    payload = response.json()
    (args.out_dir / "status.json").write_text(response.text, encoding="utf-8")

    artifacts = payload.get("artifacts", {}).get("specialist_substems", {})
    downloaded: dict[str, object] = {}
    if isinstance(artifacts, dict):
        for name, artifact_url in artifacts.items():
            if isinstance(artifact_url, str):
                target = args.out_dir / "specialist_substems" / f"{name}.wav"
                _download(base_url, artifact_url, target)
                downloaded[str(name)] = _audio_stats(target)

    report = {
        "job_id": args.job_id,
        "status": payload.get("status"),
        "missing_features": payload.get("missing_features"),
        "runner_reason": payload.get("runner_reason"),
        "input": _audio_stats(input_clip),
        "artifact_stats": downloaded,
        "passed_file_smoke": payload.get("status") == "completed" and len(downloaded) == 3,
    }
    report_path = args.out_dir / "bandit_worker_smoke_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"status={payload.get('status')}")
    print(f"missing={payload.get('missing_features')}")
    print(f"runner_reason={payload.get('runner_reason')}")
    if payload.get("runner_stderr_tail"):
        print("runner_stderr_tail:")
        print(str(payload["runner_stderr_tail"])[-1200:])
    print(f"artifacts={sorted(downloaded)}")
    print(f"report={report_path}")
    return 0 if report["passed_file_smoke"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

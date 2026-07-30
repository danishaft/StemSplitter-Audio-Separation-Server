from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from external_runners.bandit_runner import run_bandit


def _write_clip(input_path: Path, clip_path: Path, *, seconds: float, sample_rate: int) -> None:
    audio, _ = librosa.load(input_path, sr=sample_rate, mono=False, duration=seconds)
    if audio.ndim == 1:
        audio = audio[None, :]
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(clip_path, audio.T, sample_rate)


def _audio_stats(path: Path) -> dict[str, Any]:
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
    parser = argparse.ArgumentParser(description="Run a short BandIt smoke test.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--job-id", default="bandit_smoke")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "jobs" / "bandit_smoke")
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    out_dir = args.out_dir / args.job_id
    input_clip = out_dir / "input" / "bandit-smoke-input.wav"
    _write_clip(args.input.resolve(), input_clip, seconds=args.seconds, sample_rate=args.sample_rate)

    run_dir = out_dir / "runs" / "bandit"
    result = run_bandit(input_clip, run_dir, device=args.device, timeout=args.timeout)
    artifacts = {
        name: _audio_stats(Path(path))
        for name, path in sorted(result.get("artifacts", {}).items())
        if Path(str(path)).exists()
    }
    report = {
        "job_id": args.job_id,
        "input": _audio_stats(input_clip),
        "runner": result,
        "artifact_stats": artifacts,
        "expected_artifacts": ["speech_dialog", "music", "sfx"],
        "passed_file_smoke": result.get("status") == "completed" and len(artifacts) == 3,
    }
    report_path = out_dir / "analysis" / "bandit_smoke_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"status={result.get('status')}")
    print(f"reason={result.get('reason')}")
    print(f"passed_file_smoke={report['passed_file_smoke']}")
    print(f"artifacts={sorted(artifacts)}")
    print(f"report={report_path}")
    if result.get("stderr_tail"):
        print("stderr_tail:")
        print(str(result["stderr_tail"])[-1200:])
    return 0 if report["passed_file_smoke"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

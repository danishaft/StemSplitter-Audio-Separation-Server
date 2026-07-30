from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess as sp
import sys
from pathlib import Path
from typing import Any


DEFAULT_REPO = Path(os.getenv("BANDIT_REPO", "external_repos/bandit-v2"))
DEFAULT_CHECKPOINT = Path(os.getenv("BANDIT_CHECKPOINT", "checkpoints/checkpoint-multi.ckpt"))
STEM_MAP = {
    "speech": "speech_dialog",
    "music": "music",
    "sfx": "sfx",
}


def _validate_file(path: Path, reason: str) -> tuple[bool, str | None]:
    if not path.exists():
        return False, f"{reason}:{path}"
    if path.stat().st_size < 1024:
        return False, f"{reason}_too_small:{path}"
    return True, None


def _validate_repo(repo: Path, checkpoint: Path) -> tuple[bool, str | None]:
    if not repo.exists():
        return False, f"bandit_repo_missing:{repo}"
    inference_py = repo / "inference.py"
    valid, reason = _validate_file(inference_py, "bandit_inference_missing")
    if not valid:
        return False, reason
    configs_dir = repo / "configs"
    if not configs_dir.exists():
        return False, f"bandit_configs_missing:{configs_dir}"
    valid, reason = _validate_file(checkpoint, "bandit_checkpoint_missing")
    if not valid:
        return False, reason
    return True, None


def run_bandit(
    input_path: Path,
    output_dir: Path,
    *,
    repo: Path = DEFAULT_REPO,
    checkpoint: Path | None = None,
    device: str = "cpu",
    inference_batch_size: int = 1,
    timeout: int = 1800,
) -> dict[str, Any]:
    repo = repo.resolve()
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    checkpoint_path = (repo / (checkpoint or DEFAULT_CHECKPOINT)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    valid, reason = _validate_repo(repo, checkpoint_path)
    if not valid:
        return {"status": "skipped", "reason": reason, "artifacts": {}}

    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(repo / "inference.py"),
        f"hydra.searchpath=[file://{repo / 'configs'}]",
        f"ckpt_path={checkpoint_path}",
        f"+test_audio={input_path}",
        f"+output_path={raw_dir}",
        "+model_variant=multi",
        f"+device={device}",
        f"inference.kwargs.inference_batch_size={inference_batch_size}",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("LOGS_ROOT", str((output_dir / "logs").resolve()))
    try:
        result = sp.run(
            command,
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except sp.TimeoutExpired as exc:
        return {
            "status": "error",
            "reason": "bandit_inference_timeout",
            "stderr_tail": (exc.stderr or "")[-1200:] if isinstance(exc.stderr, str) else "",
            "stdout_tail": (exc.stdout or "")[-1200:] if isinstance(exc.stdout, str) else "",
            "artifacts": {},
        }
    except OSError as exc:
        return {"status": "error", "reason": f"bandit_subprocess_error:{exc}", "artifacts": {}}

    if result.returncode != 0:
        return {
            "status": "error",
            "reason": "bandit_inference_failed",
            "stderr_tail": result.stderr[-2000:],
            "stdout_tail": result.stdout[-2000:],
            "artifacts": {},
            "command": command,
        }

    artifacts: dict[str, str] = {}
    for source_name, target_name in STEM_MAP.items():
        source = raw_dir / f"{source_name}_estimate.wav"
        if not source.exists():
            continue
        target = output_dir / f"{target_name}.wav"
        shutil.copy2(source, target)
        artifacts[target_name] = str(target)

    status = "completed" if len(artifacts) == len(STEM_MAP) else "error"
    reason = None if status == "completed" else "bandit_missing_expected_outputs"
    return {
        "status": status,
        "reason": reason,
        "artifacts": artifacts,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "command": command,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BandIt speech/music/SFX separation.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--inference-batch-size", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    result = run_bandit(
        args.input,
        args.out_dir,
        repo=args.repo,
        checkpoint=args.checkpoint,
        device=args.device,
        inference_batch_size=args.inference_batch_size,
        timeout=args.timeout,
    )
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

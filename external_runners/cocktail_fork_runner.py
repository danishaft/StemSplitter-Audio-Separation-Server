from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess as sp
import sys
from pathlib import Path
from typing import Any


DEFAULT_REPO = Path(os.getenv("COCKTAIL_FORK_REPO", "external_repos/cocktail-fork-separation"))
DEFAULT_CHECKPOINT = "default_mrx_pre_trained_weights.pth"
STEM_MAP = {
    "speech": "speech_dialog",
    "music": "music",
    "sfx": "sfx",
}


def _is_lfs_pointer(path: Path) -> bool:
    try:
        head = path.read_bytes()[:128]
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/")


def _validate_repo(repo: Path, checkpoint_name: str) -> tuple[bool, str | None]:
    if not repo.exists():
        return False, f"cocktail_fork_repo_missing:{repo}"
    separate_py = repo / "separate.py"
    if not separate_py.exists():
        return False, f"cocktail_fork_separate_py_missing:{separate_py}"
    checkpoint = repo / "checkpoints" / checkpoint_name
    if not checkpoint.exists():
        return False, f"cocktail_fork_checkpoint_missing:{checkpoint}"
    if _is_lfs_pointer(checkpoint):
        return False, f"cocktail_fork_checkpoint_is_git_lfs_pointer:{checkpoint}"
    return True, None


def run_cocktail_fork(
    input_path: Path,
    output_dir: Path,
    *,
    repo: Path = DEFAULT_REPO,
    checkpoint_name: str = DEFAULT_CHECKPOINT,
    gpu_device: int = -1,
    mixture_residual: str = "pass",
) -> dict[str, Any]:
    repo = repo.resolve()
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    valid, reason = _validate_repo(repo, checkpoint_name)
    if not valid:
        return {
            "status": "skipped",
            "reason": reason,
            "artifacts": {},
        }

    command = [
        sys.executable,
        str(repo / "separate.py"),
        "--audio-path",
        str(input_path),
        "--out-dir",
        str(output_dir / "raw"),
        "--gpu-device",
        str(gpu_device),
        "--mixture-residual",
        mixture_residual,
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = sp.run(command, cwd=repo, env=env, capture_output=True, text=True, check=False)
    except OSError as exc:
        return {
            "status": "error",
            "reason": f"cocktail_fork_subprocess_error:{exc}",
            "artifacts": {},
        }
    if result.returncode != 0:
        return {
            "status": "error",
            "reason": "cocktail_fork_inference_failed",
            "stderr_tail": result.stderr[-1200:],
            "stdout_tail": result.stdout[-1200:],
            "artifacts": {},
        }

    artifacts: dict[str, str] = {}
    for source_name, target_name in STEM_MAP.items():
        source = output_dir / "raw" / f"{source_name}.wav"
        if not source.exists():
            continue
        target = output_dir / f"{target_name}.wav"
        shutil.copy2(source, target)
        artifacts[target_name] = str(target)

    status = "completed" if len(artifacts) == len(STEM_MAP) else "error"
    reason = None if status == "completed" else "cocktail_fork_missing_expected_outputs"
    return {
        "status": status,
        "reason": reason,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Cocktail Fork speech/music/SFX separation.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--gpu-device", type=int, default=-1)
    parser.add_argument("--mixture-residual", default="pass", choices=["all", "pass", "music_sfx"])
    args = parser.parse_args()

    result = run_cocktail_fork(
        args.input,
        args.out_dir,
        repo=args.repo,
        checkpoint_name=args.checkpoint,
        gpu_device=args.gpu_device,
        mixture_residual=args.mixture_residual,
    )
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

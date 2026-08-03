from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd
import soundfile as sf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_ROOT = PROJECT_ROOT / "training/online_indexes/research_all"
LISTENING_ROOT = PROJECT_ROOT / "training/listening"
TRAINING_SUBMITTER = PROJECT_ROOT / "scripts/submit_specialist_training.py"
MODAL_VOLUME = "stemsplitter-specialist-training"
BASE_IDS = ("electric_guitar", "strings", "wind_brass")


@dataclass(frozen=True)
class AudioMetadata:
    path: str
    sample_rate: int
    frames: int
    channels: int
    duration_seconds: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(
    command: Sequence[str],
    *,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def modal_executable() -> str:
    configured = os.getenv("MODAL_EXECUTABLE")
    if configured:
        return configured
    project_modal = PROJECT_ROOT / ".venvs/gpu-worker/bin/modal"
    if project_modal.is_file():
        return str(project_modal)
    discovered = shutil.which("modal")
    if discovered:
        return discovered
    raise FileNotFoundError(
        "Modal CLI not found; authenticate the project GPU environment first"
    )


def modal_python_executable() -> str:
    modal_path = Path(modal_executable())
    environment_python = modal_path.with_name("python")
    if environment_python.is_file():
        return str(environment_python)
    return os.getenv("PYTHON", "python3")


def load_index_manifest() -> dict[str, Any]:
    return json.loads((INDEX_ROOT / "index.json").read_text(encoding="utf-8"))


def load_family_index(base_id: str) -> pd.DataFrame:
    if base_id not in BASE_IDS:
        raise ValueError(f"unsupported base_id: {base_id}")
    frame = pd.read_csv(INDEX_ROOT / f"{base_id}.csv")
    expected = {"instrum", "path", "sha256", "source_id", "composition_id"}
    missing = expected.difference(frame.columns)
    if missing:
        raise ValueError(f"index is missing columns: {sorted(missing)}")
    return frame


def summarize_indexes() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for base_id in BASE_IDS:
        frame = load_family_index(base_id)
        target_count = int((frame["instrum"] == base_id).sum())
        rows.append(
            {
                "base_id": base_id,
                "rows": len(frame),
                "targets": target_count,
                "interference": len(frame) - target_count,
                "sources": int(frame["source_id"].nunique()),
                "compositions": int(frame["composition_id"].nunique()),
                "duplicate_audio_hashes": int(frame["sha256"].duplicated().sum()),
            }
        )
    return pd.DataFrame(rows).set_index("base_id")


def source_coverage(base_id: str) -> pd.DataFrame:
    frame = load_family_index(base_id)
    return (
        frame.groupby(["source_id", "instrum"], observed=True)
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )


def local_listening_examples(
    profile: str = "clean-candidate-v1",
    base_id: str | None = None,
) -> pd.DataFrame:
    root = LISTENING_ROOT / profile
    paths: Iterable[Path]
    if base_id:
        if base_id not in BASE_IDS:
            raise ValueError(f"unsupported base_id: {base_id}")
        legacy_base = (
            "strings_wind_brass"
            if base_id in {"strings", "wind_brass"}
            else base_id
        )
        paths = (root / legacy_base).rglob("*")
    else:
        paths = root.rglob("*")
    rows = []
    for path in sorted(paths):
        if path.suffix.lower() not in {".flac", ".wav"}:
            continue
        metadata = audio_metadata(path)
        rows.append(asdict(metadata))
    return pd.DataFrame(rows)


def audio_metadata(path: str | Path) -> AudioMetadata:
    resolved = Path(path).resolve()
    info = sf.info(resolved)
    return AudioMetadata(
        path=str(resolved),
        sample_rate=int(info.samplerate),
        frames=int(info.frames),
        channels=int(info.channels),
        duration_seconds=round(float(info.duration), 3),
    )


def modal_volume_paths(remote_path: str = "/") -> list[str]:
    completed = _run(
        [
            modal_executable(),
            "volume",
            "ls",
            MODAL_VOLUME,
            remote_path,
        ]
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def build_modal_command(
    *,
    action: str,
    base_id: str = "electric_guitar",
    run_id: str = "research-run",
    steps: int = 200_000,
    epochs: int = 1,
    resume_checkpoint: str = "",
    max_examples: int = 3,
    dataset_id: str = "complete-source-pools",
) -> list[str]:
    if action not in {"prepare", "train", "export"}:
        raise ValueError("action must be prepare, train, or export")
    if base_id not in BASE_IDS:
        raise ValueError(f"unsupported base_id: {base_id}")
    command = [
        modal_python_executable(),
        str(TRAINING_SUBMITTER),
        "--action",
        action,
        "--base-id",
        base_id,
        "--run-id",
        run_id,
        "--dataset-id",
        dataset_id,
    ]
    if action == "train":
        command.extend(["--steps", str(steps), "--epochs", str(epochs)])
        if resume_checkpoint:
            command.extend(["--resume-checkpoint", resume_checkpoint])
    elif action == "export":
        command.extend(["--max-examples", str(max_examples)])
    return command


def display_command(command: Sequence[str]) -> str:
    return shlex.join(command)


def submit_modal_command(
    command: Sequence[str],
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        raise ValueError("set confirm=True to launch a paid cloud operation")
    completed = _run(command)
    payload = json.loads(completed.stdout.strip())
    if not payload.get("function_call_id"):
        raise RuntimeError("Modal submission returned no function-call ID")
    return payload


def experiment_snapshot(
    *,
    run_id: str,
    base_id: str,
    steps: int,
    epochs: int,
) -> dict[str, Any]:
    command = build_modal_command(
        action="train",
        base_id=base_id,
        run_id=run_id,
        steps=steps,
        epochs=epochs,
    )
    git_commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    git_dirty = bool(_run(["git", "status", "--porcelain"]).stdout.strip())
    index_path = INDEX_ROOT / f"{base_id}.csv"
    snapshot = {
        "schema_version": "1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "base_id": base_id,
        "steps": steps,
        "epochs": epochs,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "index_path": str(index_path.relative_to(PROJECT_ROOT)),
        "index_sha256": _sha256(index_path),
        "command": display_command(command),
    }
    run_root = PROJECT_ROOT / "research/runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    output = run_root / f"{base_id}-experiment.json"
    output.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot


def find_metric_json(root: str | Path = PROJECT_ROOT / "training") -> list[Path]:
    resolved = Path(root)
    candidates = []
    for path in resolved.rglob("*.json"):
        name = path.name.lower()
        if any(token in name for token in ("metric", "score", "receipt")):
            candidates.append(path)
    return sorted(candidates)

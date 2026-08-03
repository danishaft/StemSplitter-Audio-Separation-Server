from __future__ import annotations

import os
import re
from pathlib import Path

JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def safe_job_id(value: str) -> str:
    if not JOB_ID_PATTERN.fullmatch(value):
        raise ValueError("invalid_job_id")
    return value


def _resolve_descendant(root: Path, *parts: str) -> Path:
    resolved_root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(resolved_root, *parts))
    if not target.startswith(f"{resolved_root}{os.sep}"):
        raise ValueError("path_outside_root")
    return Path(target)


def resolve_job_root(jobs_dir: Path, job_id: str) -> Path:
    return _resolve_descendant(jobs_dir, safe_job_id(job_id))


def resolve_artifact_path(job_root: Path, artifact_path: str) -> Path:
    if not artifact_path or artifact_path.startswith(("/", "\\")):
        raise ValueError("invalid_artifact_path")

    parts = artifact_path.split("/")
    if any(part in {"", ".", ".."} or "\\" in part for part in parts):
        raise ValueError("invalid_artifact_path")
    return _resolve_descendant(job_root, *parts)

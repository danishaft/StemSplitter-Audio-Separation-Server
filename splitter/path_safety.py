from __future__ import annotations

import re
from pathlib import Path

JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def safe_job_id(value: str) -> str:
    candidate = Path(value).name
    if candidate != value or not JOB_ID_PATTERN.fullmatch(candidate):
        raise ValueError("invalid_job_id")
    return candidate


def resolve_job_root(jobs_dir: Path, job_id: str) -> Path:
    root = jobs_dir.resolve()
    target = (root / safe_job_id(job_id)).resolve()
    target.relative_to(root)
    return target


def resolve_artifact_path(job_root: Path, artifact_path: str) -> Path:
    relative = Path(artifact_path)
    if relative.is_absolute() or not relative.parts:
        raise ValueError("invalid_artifact_path")

    parts: list[str] = []
    for part in relative.parts:
        if part in {"", ".", ".."} or "\\" in part or Path(part).name != part:
            raise ValueError("invalid_artifact_path")
        parts.append(part)

    root = job_root.resolve()
    target = root.joinpath(*parts).resolve()
    target.relative_to(root)
    return target

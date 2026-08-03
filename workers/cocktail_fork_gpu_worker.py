from __future__ import annotations

import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

from external_runners.cocktail_fork_runner import run_cocktail_fork
from splitter.path_safety import resolve_artifact_path, resolve_job_root

WORKER_ROOT = Path(os.getenv("COCKTAIL_FORK_WORKER_ROOT", "/tmp/cocktail-fork-worker"))
JOBS_DIR = Path(os.getenv("COCKTAIL_FORK_JOBS_DIR", str(WORKER_ROOT / "jobs")))
REPO_DIR = Path(os.getenv("COCKTAIL_FORK_REPO", "/opt/cocktail-fork-separation"))
API_KEY = os.getenv("COCKTAIL_FORK_WORKER_API_KEY") or os.getenv("WORKER_API_KEY")

api_app = FastAPI(title="Cocktail Fork GPU Worker")


def _authorize(authorization: str | None) -> None:
    if not API_KEY:
        return
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _job_root(job_id: str) -> Path:
    try:
        return resolve_job_root(JOBS_DIR, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job id") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _status_path(job_id: str) -> Path:
    return _job_root(job_id) / "status.json"


def _bundle(job_id: str) -> str | None:
    root = _job_root(job_id)
    output_dir = root / "specialist_substems"
    if not output_dir.exists():
        return None
    package_dir = _ensure_dir(root / "package")
    bundle_path = package_dir / "cocktail_fork_artifacts.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.glob("*.wav")):
            archive.write(path, path.relative_to(root).as_posix())
        manifest = root / "analysis" / "manifest.json"
        if manifest.exists():
            archive.write(manifest, manifest.relative_to(root).as_posix())
    return f"/artifacts/{job_id}/package/{bundle_path.name}"


@api_app.post("/separate")
async def separate(
    file: UploadFile = File(...),
    local_job_id: str = Form(""),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(authorization)
    job_id = local_job_id or uuid.uuid4().hex
    root = _ensure_dir(_job_root(job_id))
    input_dir = _ensure_dir(root / "input")
    input_path = input_dir / Path(file.filename or "input.wav").name
    input_path.write_bytes(await file.read())

    status = {
        "job_id": job_id,
        "status": "running",
        "stage": "cocktail_fork",
        "artifacts": {},
        "missing_features": [],
    }
    _write_json(_status_path(job_id), status)

    run_dir = _ensure_dir(root / "runs" / "cocktail_fork")
    result = run_cocktail_fork(input_path, run_dir, repo=REPO_DIR, gpu_device=0)
    output_dir = _ensure_dir(root / "specialist_substems")
    artifacts: dict[str, str] = {}
    for name, raw_path in result.get("artifacts", {}).items():
        source = Path(str(raw_path))
        if not source.exists():
            continue
        target = output_dir / f"{name}.wav"
        shutil.copy2(source, target)
        artifacts[str(name)] = f"/artifacts/{job_id}/specialist_substems/{target.name}"

    analysis_dir = _ensure_dir(root / "analysis")
    _write_json(analysis_dir / "manifest.json", {"cocktail_fork": result})
    bundle_url = _bundle(job_id)
    status = {
        "job_id": job_id,
        "status": "completed" if result.get("status") == "completed" else "error",
        "stage": "done",
        "artifacts": {"specialist_substems": artifacts},
        "artifact_sources": {
            "specialist_substems": {name: "cocktail_fork_mrx" for name in artifacts}
        },
        "missing_features": [] if artifacts else [str(result.get("reason") or "cocktail_fork_failed")],
        "error": result.get("reason"),
        "runner_status": result.get("status"),
        "runner_reason": result.get("reason"),
        "runner_stderr_tail": result.get("stderr_tail"),
        "runner_stdout_tail": result.get("stdout_tail"),
        "bundle_artifact": bundle_url,
    }
    _write_json(_status_path(job_id), status)
    return status


@api_app.get("/jobs/{job_id}")
def job_status(job_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    path = _status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return _read_json(path)


@api_app.get("/artifacts/{job_id}/{artifact_path:path}")
def artifact(job_id: str, artifact_path: str, authorization: str | None = Header(default=None)) -> FileResponse:
    _authorize(authorization)
    root = _job_root(job_id).resolve()
    try:
        target = resolve_artifact_path(root, artifact_path)
    except ValueError:
        raise HTTPException(status_code=404, detail="Artifact not found") from None
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(target)


try:
    import modal
except Exception:  # pragma: no cover
    app = api_app
else:
    app = modal.App("stemsplitter-cocktail-fork-gpu")
    jobs_volume = modal.Volume.from_name("stemsplitter-cocktail-fork-jobs", create_if_missing=True)
    image = (
        modal.Image.debian_slim(python_version="3.10")
        .apt_install("ffmpeg", "git", "git-lfs", "libsndfile1")
        .pip_install(
            "fastapi[standard]",
            "python-multipart",
            "numpy<2",
            "pyloudnorm==0.1.1",
            "pytorch_lightning==1.9.0",
            "torch==1.13.1",
            "torchaudio==0.13.1",
        )
        .run_commands(
            "git clone https://github.com/merlresearch/cocktail-fork-separation.git /opt/cocktail-fork-separation",
            "cd /opt/cocktail-fork-separation && git lfs pull",
        )
        .add_local_dir("external_runners", "/root/external_runners", copy=True)
        .add_local_dir("splitter", "/root/splitter", copy=True)
    )

    @app.function(
        image=image,
        gpu=os.getenv("COCKTAIL_FORK_MODAL_GPU", "T4"),
        timeout=int(os.getenv("COCKTAIL_FORK_MODAL_TIMEOUT", "1800")),
        min_containers=int(os.getenv("COCKTAIL_FORK_KEEP_WARM", "0")),
        volumes={"/tmp/cocktail-fork-worker/jobs": jobs_volume},
    )
    @modal.asgi_app()
    def fastapi_app():
        return api_app

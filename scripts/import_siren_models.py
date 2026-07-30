from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import modal


MODEL_ID = "hilarl/siren-separate"
MODEL_REVISION = "3dc6968b475d7b1be0a93defade1405f745f4dc7"
MODEL_ROOT = Path("/models/siren-separate")

app = modal.App("stemsplitter-siren-model-import")
model_volume = modal.Volume.from_name("stemsplitter-siren-models", create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "huggingface-hub==0.35.3",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@app.function(
    image=image,
    cpu=2.0,
    memory=4096,
    timeout=1800,
    volumes={"/models": model_volume},
    secrets=[modal.Secret.from_name("stemsplitter-huggingface")],
)
def import_snapshot() -> dict[str, Any]:
    from huggingface_hub import HfApi, snapshot_download

    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("hf_token_missing")
    identity = HfApi().whoami(token=token)
    account_name = str(identity.get("name") or identity.get("fullname") or "unknown")

    try:
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            local_dir=MODEL_ROOT,
            token=token,
        )
    except Exception as exc:
        return {
            "status": "blocked",
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "huggingface_account": account_name,
            "error_type": type(exc).__name__,
            "reason": str(exc)[:500],
        }
    model_volume.commit()

    files = []
    for path in sorted(MODEL_ROOT.rglob("*")):
        if not path.is_file():
            continue
        files.append(
            {
                "path": str(path.relative_to(MODEL_ROOT)),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "status": "imported",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "huggingface_account": account_name,
        "files": files,
    }


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(import_snapshot.remote(), indent=2, sort_keys=True))

from __future__ import annotations

import hashlib
from pathlib import Path

import modal


APP_NAME = "stemsplitter-audiosep-model-import"
VOLUME_NAME = "stemsplitter-audiosep-models"
MODEL_REPO = "nielsr/audiosep-demo"
MODEL_REVISION = "9188caa202a0d31845367e4dad8bb5549eddb4ba"
MODEL_SHA256 = "37f1691fb067e2575f1ad1cfbfe44b7b3da18e52f33fcb2b0937b72952f11ba1"
TOKENIZER_REPO = "FacebookAI/roberta-base"
TOKENIZER_REVISION = "e2da8e2f811d1448a5b465c236feacd80ffbac7b"  # gitleaks:allow
TOKENIZER_FILES = (
    "config.json",
    "merges.txt",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)

app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "huggingface-hub==0.35.3"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@app.function(
    image=image,
    cpu=4,
    memory=8192,
    timeout=3600,
    volumes={"/models": volume},
)
def import_models() -> dict[str, object]:
    from huggingface_hub import hf_hub_download, snapshot_download

    model_path = Path(
        hf_hub_download(
            repo_id=MODEL_REPO,
            filename="pytorch_model.bin",
            revision=MODEL_REVISION,
            local_dir="/models",
        )
    )
    observed_hash = _sha256(model_path)
    if observed_hash != MODEL_SHA256:
        raise RuntimeError(
            f"audiosep_checkpoint_hash_mismatch:{observed_hash}"
        )

    tokenizer_dir = Path(
        snapshot_download(
            repo_id=TOKENIZER_REPO,
            revision=TOKENIZER_REVISION,
            allow_patterns=list(TOKENIZER_FILES),
            local_dir="/models/roberta-base",
        )
    )
    missing = [
        filename
        for filename in TOKENIZER_FILES
        if not (tokenizer_dir / filename).exists()
    ]
    if missing:
        raise RuntimeError("audiosep_tokenizer_incomplete:" + ",".join(missing))
    volume.commit()
    return {
        "status": "ready",
        "model_path": str(model_path),
        "model_sha256": observed_hash,
        "model_revision": MODEL_REVISION,
        "tokenizer_path": str(tokenizer_dir),
        "tokenizer_revision": TOKENIZER_REVISION,
        "tokenizer_files": list(TOKENIZER_FILES),
    }


@app.local_entrypoint()
def main() -> None:
    result = import_models.remote()
    for key, value in sorted(result.items()):
        print(f"{key}={value}")

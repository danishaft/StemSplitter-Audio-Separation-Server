from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import modal


MODELS = {
    "strings": {
        "model_id": "oulianov/BS-Roformer-BowedStrings-Duality",
        "revision": "77e1cc62d1deef965496d9d0a060f77d1464a319",
        "checkpoint": "gilliaan_bowedstrings_bs_v1.ckpt",
        "sha256": "282fabc28fb106edcc5e5e8383ea36559602fe53d0c406c736e08f58d66710fc",
    },
    "synth": {
        "model_id": "oulianov/bsroformer-lead-synth",
        "revision": "ae2a351854d1fcf7787d8fd7b2fd2ecc0920239e",
        "checkpoint": "model_bs_roformer_ep_1_sdr_4.9869_fixed.ckpt",
        "sha256": "c1e5565cb92939794e7db741969eac225a2fff45b0e17694f9a9ff1d8dc45c65",
    },
    "synth_xlance_v1": {
        "model_id": "noblebarkrr/mvsepless_resources",
        "revision": "cf01b871f6c324c11c828b18ad05658656e9ae7f",
        "checkpoint": "bs_roformer/bs_syn_xlancer.ckpt",
        "sha256": "e747867f1d0696760e4f5e83f259c1a022af20214a7f66fbef0d4f5df81a21bd",
    },
    "synth_xlance_v2": {
        "model_id": "noblebarkrr/mvsepless_resources",
        "revision": "cf01b871f6c324c11c828b18ad05658656e9ae7f",
        "checkpoint": "bs_roformer/bs_syn2_xlancer.ckpt",
        "sha256": "c1f692422fd1d235b358751e8f9d712b15cc11c84c5e93356cb726c91a1f7ab0",
    },
}
MODEL_ROOT = Path("/models")

app = modal.App("stemsplitter-open-specialist-model-import")
model_volume = modal.Volume.from_name(
    "stemsplitter-open-specialist-models",
    create_if_missing=True,
)
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
    volumes={str(MODEL_ROOT): model_volume},
)
def import_models() -> dict[str, Any]:
    from huggingface_hub import hf_hub_download

    imported = {}
    for stem_name, model in MODELS.items():
        model_dir = MODEL_ROOT / stem_name
        model_dir.mkdir(parents=True, exist_ok=True)
        downloaded = Path(
            hf_hub_download(
                repo_id=model["model_id"],
                revision=model["revision"],
                filename=model["checkpoint"],
                local_dir=model_dir,
            )
        )
        actual_sha256 = _sha256(downloaded)
        if actual_sha256 != model["sha256"]:
            raise RuntimeError(
                f"checkpoint_hash_mismatch:{stem_name}:"
                f"expected={model['sha256']}:actual={actual_sha256}"
            )
        imported[stem_name] = {
            "path": str(downloaded),
            "size_bytes": downloaded.stat().st_size,
            "sha256": actual_sha256,
        }
    model_volume.commit()
    return {"status": "imported", "models": imported}


@app.local_entrypoint()
def main() -> None:
    print(json.dumps(import_models.remote(), indent=2, sort_keys=True))

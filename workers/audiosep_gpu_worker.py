from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "models" / "audiosep_research.yaml"
CONTAINER_CONFIG_PATH = Path("/root/models/audiosep_research.yaml")
CONTAINER_AUDIOSEP_PATH = Path("/root/audiosep")
MODEL_VOLUME_PATH = Path("/models")
TOKENIZER_PATH = MODEL_VOLUME_PATH / "roberta-base"
AUDIO_SUFFIXES = {".flac", ".m4a", ".mp3", ".ogg", ".wav"}


class AudioSepWorkerError(RuntimeError):
    """Raised when the isolated AudioSep qualification worker is invalid."""


def load_audiosep_config(path: Path | None = None) -> dict[str, Any]:
    payload = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AudioSepWorkerError("audiosep_config_must_be_mapping")
    model = payload.get("model")
    runtime = payload.get("runtime")
    targets = payload.get("target_stems")
    if not isinstance(model, dict) or not model.get("checkpoint"):
        raise AudioSepWorkerError("audiosep_checkpoint_missing")
    if not isinstance(runtime, dict) or not runtime.get("source_revision"):
        raise AudioSepWorkerError("audiosep_runtime_revision_missing")
    if not isinstance(targets, dict) or len(targets) != 6:
        raise AudioSepWorkerError("audiosep_six_target_prompts_required")
    if any(not isinstance(prompt, str) or not prompt.strip() for prompt in targets.values()):
        raise AudioSepWorkerError("audiosep_target_prompt_invalid")
    return payload


def _safe_job_id(value: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
    return normalized[:96] or f"audiosepq-{uuid.uuid4().hex[:12]}"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


try:
    import modal
except ImportError:  # pragma: no cover - Modal is a deployment dependency
    modal = None
    app = None
else:
    config = load_audiosep_config(
        CONFIG_PATH if modal.is_local() else CONTAINER_CONFIG_PATH
    )
    model_config = config["model"]
    runtime_config = config["runtime"]
    target_prompts = config["target_stems"]

    app = modal.App(os.getenv("AUDIOSEP_MODAL_APP_NAME", "stemsplitter-audiosep"))
    model_volume = modal.Volume.from_name(
        "stemsplitter-audiosep-models",
        create_if_missing=False,
    )
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "libsndfile1")
        .pip_install(
            "boto3>=1.35.0",
            "ftfy==6.1.1",
            "h5py",
            "librosa==0.10.2.post1",
            "numpy==1.26.4",
            "pillow",
            "pyyaml",
            "regex",
            "scipy",
            "soundfile",
            "torch==2.2.2",
            "torchaudio==2.2.2",
            "torchlibrosa==0.1.0",
            "torchvision==0.17.2",
            "transformers==4.35.2",
        )
        .env(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            }
        )
        .add_local_python_source("splitter")
        .add_local_dir(
            "external_repos/AudioSep",
            remote_path=str(CONTAINER_AUDIOSEP_PATH),
        )
        .add_local_file(
            "models/audiosep_research.yaml",
            str(CONTAINER_CONFIG_PATH),
        )
    )

    @app.cls(
        image=image,
        gpu=os.getenv("AUDIOSEP_MODAL_GPU", "A100-80GB"),
        cpu=float(os.getenv("AUDIOSEP_MODAL_CPU", "8")),
        memory=int(os.getenv("AUDIOSEP_MODAL_MEMORY_MB", "32768")),
        timeout=int(os.getenv("AUDIOSEP_MODAL_TIMEOUT", "7200")),
        max_containers=int(os.getenv("AUDIOSEP_MODAL_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("AUDIOSEP_MODAL_SCALEDOWN_WINDOW", "300")),
        volumes={str(MODEL_VOLUME_PATH): model_volume},
        secrets=[
            modal.Secret.from_name(
                os.getenv("OBJECT_STORAGE_MODAL_SECRET", "stemsplitter-b2")
            )
        ],
    )
    class AudioSepSpecialist:
        @modal.enter()
        def load_model(self) -> None:
            import torch
            from torch import nn
            from transformers import RobertaConfig, RobertaModel, RobertaTokenizer

            sys.path.insert(0, str(CONTAINER_AUDIOSEP_PATH))
            from models.CLAP.open_clip import create_model
            from models.CLAP.open_clip import model as clap_model_module
            from models.resunet import ResUNet30

            checkpoint_path = MODEL_VOLUME_PATH / str(model_config["checkpoint"])
            required_tokenizer_files = (
                "config.json",
                "merges.txt",
                "tokenizer.json",
                "tokenizer_config.json",
                "vocab.json",
            )
            if not checkpoint_path.exists() or any(
                not (TOKENIZER_PATH / filename).exists()
                for filename in required_tokenizer_files
            ):
                raise AudioSepWorkerError("audiosep_model_volume_incomplete")

            class TextCLAPEncoder(nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.tokenize = RobertaTokenizer.from_pretrained(
                        TOKENIZER_PATH,
                        local_files_only=True,
                    )
                    roberta_config = RobertaConfig.from_json_file(
                        str(TOKENIZER_PATH / "config.json")
                    )
                    original_roberta_class = clap_model_module.RobertaModel

                    class LocalRobertaFactory:
                        @staticmethod
                        def from_pretrained(*_args: Any, **_kwargs: Any) -> Any:
                            return RobertaModel(roberta_config)

                    clap_model_module.RobertaModel = LocalRobertaFactory
                    try:
                        self.model, _ = create_model(
                            "HTSAT-base",
                            "roberta",
                            "",
                            precision="fp32",
                            device=torch.device("cpu"),
                            enable_fusion=False,
                            fusion_type="aff_2d",
                        )
                    finally:
                        clap_model_module.RobertaModel = original_roberta_class

                def encode(self, prompts: list[str]) -> Any:
                    tokens = self.tokenize(
                        prompts,
                        padding="max_length",
                        truncation=True,
                        max_length=512,
                        return_tensors="pt",
                    )
                    return self.model.get_text_embedding(tokens).float()

            class AudioSepRuntime(nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.ss_model = ResUNet30(
                        input_channels=1,
                        output_channels=1,
                        condition_size=512,
                    )
                    self.query_encoder = TextCLAPEncoder()

            runtime = AudioSepRuntime()
            state = torch.load(
                str(checkpoint_path),
                map_location="cpu",
                mmap=True,
                weights_only=True,
            )
            legacy_position_ids = (
                "query_encoder.model.text_branch.embeddings.position_ids"
            )
            if legacy_position_ids not in state:
                raise AudioSepWorkerError(
                    "audiosep_legacy_position_ids_buffer_missing"
                )
            state.pop(legacy_position_ids)
            incompatible = runtime.load_state_dict(state, strict=True, assign=True)
            if incompatible.missing_keys or incompatible.unexpected_keys:
                raise AudioSepWorkerError(
                    "audiosep_checkpoint_incompatible:"
                    f"missing={len(incompatible.missing_keys)},"
                    f"unexpected={len(incompatible.unexpected_keys)}"
                )

            self.torch = torch
            self.device = torch.device("cuda")
            torch.backends.cuda.matmul.allow_tf32 = True
            runtime = runtime.eval().to(self.device)
            prompts = list(target_prompts.values())
            with torch.inference_mode():
                embeddings = runtime.query_encoder.encode(prompts)
            self.conditions = {
                stem_name: embeddings[index : index + 1]
                for index, stem_name in enumerate(target_prompts)
            }
            self.parameter_count = sum(
                parameter.numel() for parameter in runtime.parameters()
            )
            self.ss_model = runtime.ss_model
            self.ss_model_parameter_count = sum(
                parameter.numel() for parameter in self.ss_model.parameters()
            )
            del runtime.query_encoder
            del runtime
            torch.cuda.empty_cache()

        @modal.method()
        def preflight(self) -> dict[str, Any]:
            device = self.torch.cuda.get_device_properties(self.device)
            return {
                "status": "ready",
                "model_id": model_config["model_id"],
                "model_revision": model_config["source_revision"],
                "runtime_revision": runtime_config["source_revision"],
                "checkpoint_sha256": model_config["checkpoint_sha256"],
                "device_name": device.name,
                "device_memory_bytes": int(device.total_memory),
                "model_parameter_count": self.parameter_count,
                "separation_parameter_count": self.ss_model_parameter_count,
                "model_dtype": str(next(self.ss_model.parameters()).dtype),
                "target_prompts": dict(target_prompts),
            }

        def _load_mix(self, input_path: Path) -> tuple[Any, int]:
            import numpy as np
            import soundfile as sf
            from scipy.signal import resample_poly

            audio, sample_rate = sf.read(input_path, always_2d=True, dtype="float32")
            audio = audio.mean(axis=1)
            target_rate = int(runtime_config["sample_rate"])
            if sample_rate != target_rate:
                audio = resample_poly(audio, target_rate, sample_rate)
            return np.ascontiguousarray(audio, dtype=np.float32), target_rate

        @modal.method()
        def separate(self, request: dict[str, Any]) -> dict[str, Any]:
            import numpy as np
            import soundfile as sf

            from splitter.object_storage import (
                materialize_object,
                object_store_from_config,
            )

            job_id = _safe_job_id(str(request.get("job_id") or ""))
            input_object = request.get("input_object")
            if not isinstance(input_object, dict):
                raise AudioSepWorkerError("audiosep_input_object_missing")
            store = object_store_from_config()
            if store is None:
                raise AudioSepWorkerError("object_storage_not_configured")

            report: dict[str, Any] = {
                "schema_version": 1,
                "job_id": job_id,
                "model_id": model_config["model_id"],
                "model_revision": model_config["source_revision"],
                "runtime_revision": runtime_config["source_revision"],
                "started_at": datetime.now(UTC).isoformat(),
                "status": "running",
                "outputs": {},
                "failures": {},
            }
            with tempfile.TemporaryDirectory(prefix=f"{job_id}-") as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                input_path = materialize_object(input_object, temp_dir / "input.wav")
                mix, sample_rate = self._load_mix(input_path)
                mixture = self.torch.from_numpy(mix)[None, None, :].to(self.device)

                started = time.perf_counter()
                for stem_name, prompt in target_prompts.items():
                    target_path = temp_dir / f"{stem_name}.wav"
                    try:
                        with self.torch.inference_mode():
                            waveform = self.ss_model(
                                {
                                    "mixture": mixture,
                                    "condition": self.conditions[stem_name],
                                }
                            )["waveform"]
                        output = (
                            waveform.squeeze(0)
                            .squeeze(0)
                            .float()
                            .cpu()
                            .numpy()
                        )
                        output = np.clip(output, -1.0, 1.0)
                        sf.write(target_path, output, sample_rate, subtype="PCM_24")
                        key = store.artifact_key(
                            job_id,
                            "audiosep_specialists",
                            target_path.name,
                        )
                        reference = store.upload(target_path, key, "audio/wav")
                        report["outputs"][stem_name] = {
                            "prompt": prompt,
                            "object": reference.as_dict(),
                            "channels": 1,
                            "sample_rate": sample_rate,
                            "duration_seconds": round(len(output) / sample_rate, 4),
                            "encoding": "PCM_24",
                        }
                    except Exception as exc:
                        report["failures"][stem_name] = {
                            "error_type": type(exc).__name__,
                            "reason": str(exc)[:500],
                        }
                report["inference_seconds"] = round(time.perf_counter() - started, 4)
                report["finished_at"] = datetime.now(UTC).isoformat()
                report["status"] = (
                    "completed"
                    if not report["failures"]
                    else "completed_with_failures"
                )
                report_path = temp_dir / "audiosep-report.json"
                report_path.write_text(
                    json.dumps(report, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                report_ref = store.upload(
                    report_path,
                    store.artifact_key(job_id, "analysis", report_path.name),
                    "application/json",
                )
                report["report_object"] = report_ref.as_dict()
            return report

    @app.local_entrypoint()
    def main(
        input: str,
        output_dir: str = "benchmarks/audiosep",
        job_id: str = "",
    ) -> None:
        _load_env_file(ROOT_DIR / ".env.local")
        from splitter.object_storage import object_store_from_config

        input_path = Path(input).expanduser().resolve()
        if not input_path.exists() or input_path.suffix.lower() not in AUDIO_SUFFIXES:
            raise AudioSepWorkerError(f"invalid_audio_input:{input_path}")
        store = object_store_from_config()
        if store is None:
            raise AudioSepWorkerError("object_storage_not_configured")

        resolved_job_id = _safe_job_id(job_id)
        input_key = (
            f"{store.prefix}/research/audiosep/{resolved_job_id}/"
            f"input/{input_path.name}"
        )
        input_ref = store.upload(input_path, input_key, _content_type(input_path))
        result = AudioSepSpecialist().separate.remote(
            {
                "job_id": resolved_job_id,
                "input_object": input_ref.as_dict(),
            }
        )

        local_output_dir = Path(output_dir).expanduser().resolve() / resolved_job_id
        local_output_dir.mkdir(parents=True, exist_ok=True)
        for stem_name, payload in result["outputs"].items():
            store.download(payload["object"], local_output_dir / f"{stem_name}.wav")
        report_path = local_output_dir / "audiosep-report.json"
        report_path.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"status={result['status']}")
        print(f"outputs={','.join(sorted(result['outputs']))}")
        print(f"failures={','.join(sorted(result['failures']))}")
        print(f"report={report_path}")

from __future__ import annotations

import json
import mimetypes
import os
import re
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from splitter.product_contract import load_product_contract


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "models" / "sam_audio_specialist.yaml"
CONTAINER_CONFIG_PATH = Path("/root/models/sam_audio_specialist.yaml")
AUDIO_SUFFIXES = {".flac", ".m4a", ".mp3", ".ogg", ".wav"}


class SAMAudioWorkerError(RuntimeError):
    """Raised when the isolated SAM Audio qualification worker is misconfigured."""


def load_sam_audio_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SAMAudioWorkerError("sam_audio_config_must_be_mapping")

    model = payload.get("model")
    targets = payload.get("target_stems")
    inference = payload.get("inference")
    if not isinstance(model, dict) or not model.get("model_id"):
        raise SAMAudioWorkerError("sam_audio_model_id_missing")
    if not isinstance(inference, dict):
        raise SAMAudioWorkerError("sam_audio_inference_config_missing")
    if not isinstance(targets, dict) or not targets:
        raise SAMAudioWorkerError("sam_audio_target_stems_missing")
    expected_targets = set(load_product_contract().specialist_candidate_stems)
    if set(targets) != expected_targets:
        raise SAMAudioWorkerError("sam_audio_product_contract_mismatch")
    for stem_name, stem_config in targets.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(stem_name)):
            raise SAMAudioWorkerError(f"invalid_sam_audio_stem:{stem_name}")
        if not isinstance(stem_config, dict) or not str(stem_config.get("prompt") or "").strip():
            raise SAMAudioWorkerError(f"sam_audio_prompt_missing:{stem_name}")
    return payload


def resolve_requested_stems(config: dict[str, Any], requested: list[str] | None) -> list[str]:
    configured = list(config["target_stems"])
    if not requested:
        return configured
    normalized = [str(stem).strip().lower() for stem in requested if str(stem).strip()]
    unknown = sorted(set(normalized) - set(configured))
    if unknown:
        raise SAMAudioWorkerError("unknown_sam_audio_stems:" + ",".join(unknown))
    return list(dict.fromkeys(normalized))


def _safe_job_id(value: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
    return normalized[:96] or f"samq-{uuid.uuid4().hex[:12]}"


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
    config = load_sam_audio_config(CONFIG_PATH if modal.is_local() else CONTAINER_CONFIG_PATH)
    model_config = config["model"]
    inference_config = config["inference"]

    app = modal.App(os.getenv("SAM_AUDIO_MODAL_APP_NAME", "stemsplitter-sam-audio-specialists"))
    model_cache = modal.Volume.from_name("stemsplitter-sam-audio-models", create_if_missing=True)
    ranker_cache = modal.Volume.from_name(
        "stemsplitter-sam-audio-ranker",
        create_if_missing=True,
    )
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "git", "libsndfile1")
        .pip_install(
            "boto3>=1.35.0",
            "huggingface-hub==0.35.3",
            "pyyaml",
            "soundfile",
            "torch==2.10.0",
            "torchaudio==2.10.0",
            "torchcodec==0.10.0",
            "torchvision==0.25.0",
            "transformers==4.57.3",
            "git+https://github.com/facebookresearch/sam-audio.git"
            f"@{model_config['source_revision']}",
        )
        .add_local_python_source("splitter")
        .add_local_file(
            "models/sam_audio_specialist.yaml",
            "/root/models/sam_audio_specialist.yaml",
        )
        .add_local_file(
            "models/product_12_stem_contract.yaml",
            "/root/models/product_12_stem_contract.yaml",
        )
    )
    secrets = [
        modal.Secret.from_name(os.getenv("OBJECT_STORAGE_MODAL_SECRET", "stemsplitter-b2")),
        modal.Secret.from_name(
            os.getenv("SAM_AUDIO_HF_MODAL_SECRET", str(model_config["huggingface_secret"]))
        ),
    ]

    @app.cls(
        image=image,
        gpu=os.getenv("SAM_AUDIO_MODAL_GPU", "A100-80GB"),
        cpu=float(os.getenv("SAM_AUDIO_MODAL_CPU", "8")),
        memory=int(os.getenv("SAM_AUDIO_MODAL_MEMORY_MB", "32768")),
        timeout=int(os.getenv("SAM_AUDIO_MODAL_TIMEOUT", "7200")),
        max_containers=int(os.getenv("SAM_AUDIO_MODAL_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("SAM_AUDIO_MODAL_SCALEDOWN_WINDOW", "600")),
        volumes={
            "/root/.cache/huggingface": model_cache,
            "/root/.checkpoints": ranker_cache,
        },
        secrets=secrets,
    )
    class SAMAudioSpecialist:
        @modal.enter()
        def load_model(self) -> None:
            if not os.getenv("HF_TOKEN"):
                raise SAMAudioWorkerError("hf_token_missing")

            import torch
            from sam_audio import SAMAudio, SAMAudioProcessor

            self.torch = torch
            self.device = torch.device("cuda")
            self.model_id = str(model_config["model_id"])
            torch.backends.cuda.matmul.allow_tf32 = True
            self.processor = SAMAudioProcessor.from_pretrained(self.model_id)
            self.model = SAMAudio.from_pretrained(self.model_id).eval().to(self.device)
            model_cache.commit()
            ranker_cache.commit()

        @modal.method()
        def preflight(self) -> dict[str, Any]:
            device = self.torch.cuda.get_device_properties(self.device)
            return {
                "status": "ready",
                "model_id": self.model_id,
                "source_revision": model_config["source_revision"],
                "device_name": device.name,
                "device_memory_bytes": int(device.total_memory),
                "model_parameter_count": sum(
                    parameter.numel() for parameter in self.model.parameters()
                ),
                "processor_sample_rate": int(self.processor.audio_sampling_rate),
            }

        def _load_channels(self, input_path: Path) -> tuple[list[Any], int]:
            import torchaudio

            audio, sample_rate = torchaudio.load(str(input_path))
            target_rate = int(inference_config["sample_rate"])
            if sample_rate != target_rate:
                audio = torchaudio.functional.resample(audio, sample_rate, target_rate)
            if audio.shape[0] == 1:
                return [audio], target_rate
            return [audio[0:1], audio[1:2]], target_rate

        def _separate_stem(
            self,
            channels: list[Any],
            sample_rate: int,
            prompt: str,
            seed: int,
            target_path: Path,
        ) -> dict[str, Any]:
            import soundfile as sf

            self.torch.manual_seed(seed)
            if self.torch.cuda.is_available():
                self.torch.cuda.manual_seed_all(seed)
            batch = self.processor(
                audios=channels,
                descriptions=[prompt] * len(channels),
            ).to(self.device)
            started = time.perf_counter()
            with self.torch.inference_mode():
                result = self.model.separate(
                    batch,
                    predict_spans=bool(inference_config["predict_spans"]),
                    reranking_candidates=int(inference_config["reranking_candidates"]),
                )
            elapsed = time.perf_counter() - started
            target_channels = [channel.detach().float().cpu() for channel in result.target]
            length = min(channel.shape[-1] for channel in target_channels)
            target = self.torch.stack([channel[:length] for channel in target_channels], dim=0)
            sf.write(
                target_path,
                target.transpose(0, 1).numpy(),
                sample_rate,
                subtype="PCM_24",
            )
            return {
                "latency_seconds": round(elapsed, 4),
                "channels": int(target.shape[0]),
                "sample_rate": sample_rate,
                "duration_seconds": round(length / sample_rate, 4),
                "encoding": "PCM_24",
            }

        @modal.method()
        def separate(self, request: dict[str, Any]) -> dict[str, Any]:
            from splitter.object_storage import materialize_object, object_store_from_config

            job_id = _safe_job_id(str(request.get("job_id") or ""))
            stems = resolve_requested_stems(config, request.get("stems"))
            input_object = request.get("input_object")
            if not isinstance(input_object, dict):
                raise SAMAudioWorkerError("sam_audio_input_object_missing")

            store = object_store_from_config()
            if store is None:
                raise SAMAudioWorkerError("object_storage_not_configured")

            report: dict[str, Any] = {
                "schema_version": 1,
                "job_id": job_id,
                "model_id": self.model_id,
                "source_revision": model_config["source_revision"],
                "started_at": datetime.now(UTC).isoformat(),
                "status": "running",
                "outputs": {},
                "failures": {},
            }
            with tempfile.TemporaryDirectory(prefix=f"{job_id}-") as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                input_path = materialize_object(input_object, temp_dir / "input.wav")
                channels, sample_rate = self._load_channels(input_path)
                for index, stem_name in enumerate(stems):
                    prompt = str(config["target_stems"][stem_name]["prompt"])
                    target_path = temp_dir / f"{stem_name}.wav"
                    try:
                        evidence = self._separate_stem(
                            channels,
                            sample_rate,
                            prompt,
                            int(inference_config["seed"]) + index,
                            target_path,
                        )
                        key = store.artifact_key(
                            job_id,
                            "sam_specialists",
                            target_path.name,
                        )
                        reference = store.upload(target_path, key, "audio/wav")
                        report["outputs"][stem_name] = {
                            "prompt": prompt,
                            "object": reference.as_dict(),
                            **evidence,
                        }
                    except Exception as exc:
                        report["failures"][stem_name] = {
                            "error_type": type(exc).__name__,
                            "reason": str(exc)[:500],
                        }

                report["finished_at"] = datetime.now(UTC).isoformat()
                report["status"] = (
                    "completed" if not report["failures"] else "completed_with_failures"
                )
                report_path = temp_dir / "sam-audio-report.json"
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
        stems: str = "",
        output_dir: str = "benchmarks/sam_audio",
        job_id: str = "",
    ) -> None:
        _load_env_file(ROOT_DIR / ".env.local")
        from splitter.object_storage import object_store_from_config

        input_path = Path(input).expanduser().resolve()
        if not input_path.exists() or input_path.suffix.lower() not in AUDIO_SUFFIXES:
            raise SAMAudioWorkerError(f"invalid_audio_input:{input_path}")
        store = object_store_from_config()
        if store is None:
            raise SAMAudioWorkerError("object_storage_not_configured")

        resolved_job_id = _safe_job_id(job_id)
        input_key = (
            f"{store.prefix}/research/sam-audio/{resolved_job_id}/"
            f"input/{input_path.name}"
        )
        input_ref = store.upload(input_path, input_key, _content_type(input_path))
        requested = [value.strip() for value in stems.split(",") if value.strip()]
        result = SAMAudioSpecialist().separate.remote(
            {
                "job_id": resolved_job_id,
                "input_object": input_ref.as_dict(),
                "stems": requested,
            }
        )

        local_output_dir = Path(output_dir).expanduser().resolve() / resolved_job_id
        local_output_dir.mkdir(parents=True, exist_ok=True)
        for stem_name, payload in result["outputs"].items():
            store.download(payload["object"], local_output_dir / f"{stem_name}.wav")
        report_path = local_output_dir / "sam-audio-report.json"
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(f"status={result['status']}")
        print(f"outputs={','.join(sorted(result['outputs']))}")
        print(f"failures={','.join(sorted(result['failures']))}")
        print(f"report={report_path}")

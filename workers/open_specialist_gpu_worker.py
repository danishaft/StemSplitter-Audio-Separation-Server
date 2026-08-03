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
CONFIG_PATH = ROOT_DIR / "models" / "open_specialist_research.yaml"
CONTAINER_MODEL_CONFIG_ROOT = Path("/root/models")
CONTAINER_CONFIG_PATH = CONTAINER_MODEL_CONFIG_ROOT / CONFIG_PATH.name
CONTAINER_MSST_PATH = Path("/root/msst")
MODEL_VOLUME_PATH = Path("/models")
AUDIO_SUFFIXES = {".flac", ".m4a", ".mp3", ".ogg", ".wav"}


class OpenSpecialistWorkerError(RuntimeError):
    """Raised when the isolated open-specialist worker is misconfigured."""


def load_open_specialist_config(path: Path | None = None) -> dict[str, Any]:
    payload = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OpenSpecialistWorkerError("open_specialist_config_must_be_mapping")
    runtime = payload.get("runtime")
    models = payload.get("models")
    pipelines = payload.get("pipelines", {})
    if not isinstance(runtime, dict) or not runtime.get("source_revision"):
        raise OpenSpecialistWorkerError("open_specialist_runtime_missing")
    if not isinstance(models, dict) or not models:
        raise OpenSpecialistWorkerError("open_specialist_models_missing")
    if not isinstance(pipelines, dict):
        raise OpenSpecialistWorkerError("open_specialist_pipelines_invalid")
    required = {
        "model_id",
        "source_revision",
        "checkpoint",
        "checkpoint_sha256",
        "architecture_config",
        "output_key",
        "parameter_count",
    }
    for stem_name, model in models.items():
        if not isinstance(model, dict) or required - set(model):
            raise OpenSpecialistWorkerError(f"open_specialist_model_invalid:{stem_name}")
    for pipeline_name, pipeline in pipelines.items():
        if not isinstance(pipeline, dict):
            raise OpenSpecialistWorkerError(
                f"open_specialist_pipeline_invalid:{pipeline_name}"
            )
        stages = pipeline.get("stages")
        if (
            not isinstance(stages, list)
            or len(stages) < 2
            or any(stage not in models for stage in stages)
        ):
            raise OpenSpecialistWorkerError(
                f"open_specialist_pipeline_stages_invalid:{pipeline_name}"
            )
        if not pipeline.get("output_key"):
            raise OpenSpecialistWorkerError(
                f"open_specialist_pipeline_output_missing:{pipeline_name}"
            )
    return payload


def _safe_job_id(value: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
    return normalized[:96] or f"openspec-{uuid.uuid4().hex[:12]}"


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
    config = load_open_specialist_config(
        CONFIG_PATH if modal.is_local() else CONTAINER_CONFIG_PATH
    )
    runtime_config = config["runtime"]
    model_configs = config["models"]
    pipeline_configs = config.get("pipelines", {})

    app = modal.App(
        os.getenv("OPEN_SPECIALIST_MODAL_APP_NAME", "stemsplitter-open-specialists")
    )
    model_volume = modal.Volume.from_name(
        "stemsplitter-open-specialist-models",
        create_if_missing=False,
    )
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "libsndfile1")
        .pip_install(
            "boto3>=1.35.0",
            "beartype==0.14.1",
            "einops==0.8.1",
            "librosa",
            "ml-collections==1.1.0",
            "numpy>=2.0.0",
            "omegaconf==2.2.3",
            "packaging",
            "pyyaml",
            "rotary-embedding-torch==0.3.5",
            "scipy",
            "soundfile",
            "torch==2.10.0",
            "torchaudio==2.10.0",
            "tqdm",
        )
        .add_local_python_source("splitter")
        .add_local_dir(
            "external_repos/Music-Source-Separation-Training",
            remote_path=str(CONTAINER_MSST_PATH),
        )
        .add_local_file(
            "models/open_specialist_research.yaml",
            str(CONTAINER_CONFIG_PATH),
        )
        .add_local_file(
            "models/bsroformer_bowedstrings_candidate.yaml",
            str(CONTAINER_MODEL_CONFIG_ROOT / "bsroformer_bowedstrings_candidate.yaml"),
        )
        .add_local_file(
            "models/bsroformer_synth_lead_candidate.yaml",
            str(CONTAINER_MODEL_CONFIG_ROOT / "bsroformer_synth_lead_candidate.yaml"),
        )
        .add_local_file(
            "models/bsroformer_synth_xlance_candidate.yaml",
            str(CONTAINER_MODEL_CONFIG_ROOT / "bsroformer_synth_xlance_candidate.yaml"),
        )
        .add_local_file(
            "training/generated/bases/electric_guitar_bsroformer_stage_100.yaml",
            str(CONTAINER_MODEL_CONFIG_ROOT / "electric_guitar_bsroformer.yaml"),
        )
    )

    @app.cls(
        image=image,
        gpu=os.getenv("OPEN_SPECIALIST_MODAL_GPU", "L4"),
        cpu=float(os.getenv("OPEN_SPECIALIST_MODAL_CPU", "8")),
        memory=int(os.getenv("OPEN_SPECIALIST_MODAL_MEMORY_MB", "32768")),
        timeout=int(os.getenv("OPEN_SPECIALIST_MODAL_TIMEOUT", "3600")),
        max_containers=int(os.getenv("OPEN_SPECIALIST_MODAL_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("OPEN_SPECIALIST_MODAL_SCALEDOWN_WINDOW", "300")),
        volumes={str(MODEL_VOLUME_PATH): model_volume},
        secrets=[
            modal.Secret.from_name(
                os.getenv("OBJECT_STORAGE_MODAL_SECRET", "stemsplitter-b2")
            )
        ],
    )
    class OpenSpecialist:
        @modal.enter()
        def load_models(self) -> None:
            import torch

            sys.path.insert(0, str(CONTAINER_MSST_PATH))
            from utils.settings import get_model_from_config

            self.torch = torch
            self.device = torch.device("cuda")
            torch.backends.cuda.matmul.allow_tf32 = True
            self.runtimes: dict[str, dict[str, Any]] = {}
            for stem_name, model_config in model_configs.items():
                checkpoint_path = MODEL_VOLUME_PATH / str(model_config["checkpoint"])
                architecture_path = CONTAINER_MODEL_CONFIG_ROOT / str(
                    model_config["architecture_config"]
                )
                if not checkpoint_path.exists():
                    raise OpenSpecialistWorkerError(
                        f"open_specialist_checkpoint_missing:{stem_name}"
                    )

                model, architecture = get_model_from_config(
                    str(runtime_config["architecture"]),
                    str(architecture_path),
                )
                state = torch.load(
                    checkpoint_path,
                    map_location="cpu",
                    mmap=True,
                    weights_only=True,
                )
                incompatible = model.load_state_dict(state, strict=False, assign=True)
                if incompatible.missing_keys or incompatible.unexpected_keys:
                    raise OpenSpecialistWorkerError(
                        f"open_specialist_checkpoint_incompatible:{stem_name}:"
                        f"missing={len(incompatible.missing_keys)},"
                        f"unexpected={len(incompatible.unexpected_keys)}"
                    )
                parameter_count = sum(parameter.numel() for parameter in model.parameters())
                if parameter_count != int(model_config["parameter_count"]):
                    raise OpenSpecialistWorkerError(
                        f"open_specialist_parameter_count_mismatch:{stem_name}:"
                        f"expected={model_config['parameter_count']}:"
                        f"actual={parameter_count}"
                    )
                output_key = str(model_config["output_key"])
                available_outputs = (
                    [str(architecture.training.target_instrument)]
                    if architecture.training.get("target_instrument")
                    else list(architecture.training.instruments)
                )
                if output_key not in available_outputs:
                    raise OpenSpecialistWorkerError(
                        f"open_specialist_output_key_invalid:{stem_name}:{output_key}"
                    )
                self.runtimes[stem_name] = {
                    "model": model.eval().to(self.device),
                    "architecture": architecture,
                    "output_key": output_key,
                    "parameter_count": parameter_count,
                }

        @modal.method()
        def preflight(self) -> dict[str, Any]:
            device = self.torch.cuda.get_device_properties(self.device)
            return {
                "status": "ready",
                "runtime_revision": runtime_config["source_revision"],
                "device_name": device.name,
                "device_memory_bytes": int(device.total_memory),
                "models": {
                    stem_name: {
                        "model_id": model_configs[stem_name]["model_id"],
                        "model_revision": model_configs[stem_name]["source_revision"],
                        "checkpoint_sha256": model_configs[stem_name][
                            "checkpoint_sha256"
                        ],
                        "parameter_count": runtime["parameter_count"],
                        "output_key": runtime["output_key"],
                    }
                    for stem_name, runtime in self.runtimes.items()
                },
                "pipelines": {
                    pipeline_name: {
                        "stages": list(pipeline["stages"]),
                        "output_key": str(pipeline["output_key"]),
                    }
                    for pipeline_name, pipeline in pipeline_configs.items()
                },
            }

        def _load_mix(self, input_path: Path) -> tuple[Any, int]:
            import numpy as np
            import soundfile as sf
            from scipy.signal import resample_poly

            audio, sample_rate = sf.read(input_path, always_2d=True, dtype="float32")
            target_rate = int(runtime_config["sample_rate"])
            if sample_rate != target_rate:
                audio = resample_poly(audio, target_rate, sample_rate, axis=0)
            if audio.shape[1] == 1:
                audio = np.repeat(audio, 2, axis=1)
            elif audio.shape[1] > 2:
                audio = audio[:, :2]
            return np.ascontiguousarray(audio.T, dtype=np.float32), target_rate

        @modal.method()
        def separate(self, request: dict[str, Any]) -> dict[str, Any]:
            import soundfile as sf

            sys.path.insert(0, str(CONTAINER_MSST_PATH))
            from splitter.object_storage import materialize_object, object_store_from_config
            from utils.model_utils import demix

            job_id = _safe_job_id(str(request.get("job_id") or ""))
            input_object = request.get("input_object")
            if not isinstance(input_object, dict):
                raise OpenSpecialistWorkerError("open_specialist_input_object_missing")
            available_targets = set(self.runtimes) | set(pipeline_configs)
            requested_raw = request.get("targets")
            if requested_raw is None:
                requested_targets = sorted(available_targets)
            elif isinstance(requested_raw, list):
                requested_targets = list(
                    dict.fromkeys(str(target) for target in requested_raw)
                )
            else:
                raise OpenSpecialistWorkerError("open_specialist_targets_invalid")
            unknown_targets = sorted(set(requested_targets) - available_targets)
            if not requested_targets or unknown_targets:
                raise OpenSpecialistWorkerError(
                    "open_specialist_targets_unknown:" + ",".join(unknown_targets)
                )
            selected_models = set(requested_targets) & set(self.runtimes)
            selected_pipelines = set(requested_targets) & set(pipeline_configs)
            store = object_store_from_config()
            if store is None:
                raise OpenSpecialistWorkerError("object_storage_not_configured")

            report: dict[str, Any] = {
                "schema_version": 1,
                "job_id": job_id,
                "runtime_revision": runtime_config["source_revision"],
                "started_at": datetime.now(UTC).isoformat(),
                "status": "running",
                "requested_targets": requested_targets,
                "outputs": {},
                "failures": {},
            }
            with tempfile.TemporaryDirectory(prefix=f"{job_id}-") as temp_dir_name:
                temp_dir = Path(temp_dir_name)
                input_path = materialize_object(input_object, temp_dir / "input.wav")
                mix, sample_rate = self._load_mix(input_path)
                waveform_cache: dict[str, Any] = {}

                for stem_name, runtime in self.runtimes.items():
                    if stem_name not in selected_models:
                        continue
                    target_path = temp_dir / f"{stem_name}.wav"
                    try:
                        started = time.perf_counter()
                        separated = demix(
                            runtime["architecture"],
                            runtime["model"],
                            mix,
                            self.device,
                            str(runtime_config["architecture"]),
                            pbar=False,
                        )
                        inference_seconds = round(time.perf_counter() - started, 4)
                        output_key = runtime["output_key"]
                        waveform = separated[output_key]
                        waveform_cache[stem_name] = waveform
                        sf.write(
                            target_path,
                            waveform.T,
                            sample_rate,
                            subtype="PCM_24",
                        )
                        key = store.artifact_key(
                            job_id,
                            "open_specialists",
                            target_path.name,
                        )
                        reference = store.upload(target_path, key, "audio/wav")
                        report["outputs"][stem_name] = {
                            "model_id": model_configs[stem_name]["model_id"],
                            "model_output": output_key,
                            "object": reference.as_dict(),
                            "channels": int(waveform.shape[0]),
                            "sample_rate": sample_rate,
                            "duration_seconds": round(waveform.shape[-1] / sample_rate, 4),
                            "inference_seconds": inference_seconds,
                            "encoding": "PCM_24",
                        }
                    except Exception as exc:
                        report["failures"][stem_name] = {
                            "error_type": type(exc).__name__,
                            "reason": str(exc)[:500],
                        }

                for pipeline_name, pipeline in pipeline_configs.items():
                    if pipeline_name not in selected_pipelines:
                        continue
                    target_path = temp_dir / f"{pipeline_name}.wav"
                    stages = [str(stage) for stage in pipeline["stages"]]
                    stage_seconds: dict[str, float] = {}
                    try:
                        started = time.perf_counter()
                        first_stage = stages[0]
                        waveform = waveform_cache.get(first_stage)
                        if waveform is None:
                            first_runtime = self.runtimes[first_stage]
                            stage_started = time.perf_counter()
                            separated = demix(
                                first_runtime["architecture"],
                                first_runtime["model"],
                                mix,
                                self.device,
                                str(runtime_config["architecture"]),
                                pbar=False,
                            )
                            stage_seconds[first_stage] = round(
                                time.perf_counter() - stage_started,
                                4,
                            )
                            waveform = separated[first_runtime["output_key"]]
                        else:
                            stage_seconds[first_stage] = 0.0

                        for stage_name in stages[1:]:
                            stage_runtime = self.runtimes[stage_name]
                            stage_started = time.perf_counter()
                            separated = demix(
                                stage_runtime["architecture"],
                                stage_runtime["model"],
                                waveform,
                                self.device,
                                str(runtime_config["architecture"]),
                                pbar=False,
                            )
                            stage_seconds[stage_name] = round(
                                time.perf_counter() - stage_started,
                                4,
                            )
                            waveform = separated[stage_runtime["output_key"]]

                        inference_seconds = round(time.perf_counter() - started, 4)
                        sf.write(
                            target_path,
                            waveform.T,
                            sample_rate,
                            subtype="PCM_24",
                        )
                        key = store.artifact_key(
                            job_id,
                            "open_specialists",
                            target_path.name,
                        )
                        reference = store.upload(target_path, key, "audio/wav")
                        report["outputs"][pipeline_name] = {
                            "model_id": str(pipeline["model_id"]),
                            "model_output": str(pipeline["output_key"]),
                            "stages": stages,
                            "stage_inference_seconds": stage_seconds,
                            "object": reference.as_dict(),
                            "channels": int(waveform.shape[0]),
                            "sample_rate": sample_rate,
                            "duration_seconds": round(
                                waveform.shape[-1] / sample_rate,
                                4,
                            ),
                            "inference_seconds": inference_seconds,
                            "encoding": "PCM_24",
                        }
                    except Exception as exc:
                        report["failures"][pipeline_name] = {
                            "error_type": type(exc).__name__,
                            "reason": str(exc)[:500],
                            "stages": stages,
                        }

                report["finished_at"] = datetime.now(UTC).isoformat()
                report["status"] = (
                    "completed"
                    if not report["failures"]
                    and set(report["outputs"]) == set(requested_targets)
                    else "completed_with_failures"
                )
                report_path = temp_dir / "open-specialist-report.json"
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
        output_dir: str = "benchmarks/specialist_open",
        job_id: str = "",
    ) -> None:
        _load_env_file(ROOT_DIR / ".env.local")
        from splitter.object_storage import object_store_from_config

        input_path = Path(input).expanduser().resolve()
        if not input_path.exists() or input_path.suffix.lower() not in AUDIO_SUFFIXES:
            raise OpenSpecialistWorkerError(f"invalid_audio_input:{input_path}")
        store = object_store_from_config()
        if store is None:
            raise OpenSpecialistWorkerError("object_storage_not_configured")

        resolved_job_id = _safe_job_id(job_id)
        input_key = (
            f"{store.prefix}/research/open-specialists/{resolved_job_id}/"
            f"input/{input_path.name}"
        )
        input_ref = store.upload(input_path, input_key, _content_type(input_path))
        result = OpenSpecialist().separate.remote(
            {
                "job_id": resolved_job_id,
                "input_object": input_ref.as_dict(),
            }
        )

        local_output_dir = Path(output_dir).expanduser().resolve() / resolved_job_id
        local_output_dir.mkdir(parents=True, exist_ok=True)
        for stem_name, payload in result["outputs"].items():
            store.download(payload["object"], local_output_dir / f"{stem_name}.wav")
        report_path = local_output_dir / "open-specialist-report.json"
        report_path.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"status={result['status']}")
        print(f"outputs={','.join(sorted(result['outputs']))}")
        print(f"failures={','.join(sorted(result['failures']))}")
        print(f"report={report_path}")

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
CONFIG_PATH = ROOT_DIR / "models" / "mvsep_mega53_research.yaml"
CONTAINER_CONFIG_PATH = Path("/root/models/mvsep_mega53_research.yaml")
CONTAINER_MSST_PATH = Path("/root/msst")
MODEL_VOLUME_PATH = Path("/models")
AUDIO_SUFFIXES = {".flac", ".m4a", ".mp3", ".ogg", ".wav"}


class Mega53WorkerError(RuntimeError):
    """Raised when the isolated Mega 53 qualification worker is misconfigured."""


def load_mega53_config(path: Path | None = None) -> dict[str, Any]:
    payload = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise Mega53WorkerError("mega53_config_must_be_mapping")
    model = payload.get("model")
    runtime = payload.get("runtime")
    targets = payload.get("target_stems")
    if not isinstance(model, dict) or not model.get("checkpoint"):
        raise Mega53WorkerError("mega53_checkpoint_missing")
    if not isinstance(runtime, dict) or not runtime.get("source_revision"):
        raise Mega53WorkerError("mega53_runtime_revision_missing")
    if not isinstance(targets, dict) or len(targets) != 6:
        raise Mega53WorkerError("mega53_six_target_mapping_required")
    if any(
        not isinstance(model_stems, list)
        or not model_stems
        or any(not isinstance(stem, str) or not stem for stem in model_stems)
        for model_stems in targets.values()
    ):
        raise Mega53WorkerError("mega53_target_mapping_must_use_nonempty_lists")
    return payload


def _safe_job_id(value: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
    return normalized[:96] or f"mega53q-{uuid.uuid4().hex[:12]}"


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
    config = load_mega53_config(CONFIG_PATH if modal.is_local() else CONTAINER_CONFIG_PATH)
    model_config = config["model"]
    runtime_config = config["runtime"]
    target_stems = config["target_stems"]

    app = modal.App(os.getenv("MEGA53_MODAL_APP_NAME", "stemsplitter-mvsep-mega53"))
    model_volume = modal.Volume.from_name(
        "stemsplitter-mvsep-mega53-models",
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
            "models/mvsep_mega53_research.yaml",
            str(CONTAINER_CONFIG_PATH),
        )
    )

    @app.cls(
        image=image,
        gpu=os.getenv("MEGA53_MODAL_GPU", "A100-80GB"),
        cpu=float(os.getenv("MEGA53_MODAL_CPU", "8")),
        memory=int(os.getenv("MEGA53_MODAL_MEMORY_MB", "32768")),
        timeout=int(os.getenv("MEGA53_MODAL_TIMEOUT", "7200")),
        max_containers=int(os.getenv("MEGA53_MODAL_MAX_CONTAINERS", "1")),
        scaledown_window=int(os.getenv("MEGA53_MODAL_SCALEDOWN_WINDOW", "300")),
        volumes={str(MODEL_VOLUME_PATH): model_volume},
        secrets=[
            modal.Secret.from_name(
                os.getenv("OBJECT_STORAGE_MODAL_SECRET", "stemsplitter-b2")
            )
        ],
    )
    class Mega53Specialist:
        @modal.enter()
        def load_model(self) -> None:
            import torch

            sys.path.insert(0, str(CONTAINER_MSST_PATH))
            from utils.settings import get_model_from_config

            checkpoint_path = MODEL_VOLUME_PATH / str(model_config["checkpoint"])
            architecture_path = MODEL_VOLUME_PATH / str(
                model_config["architecture_config"]
            )
            if not checkpoint_path.exists() or not architecture_path.exists():
                raise Mega53WorkerError("mega53_model_volume_incomplete")

            model, architecture = get_model_from_config(
                str(model_config["architecture"]),
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
                raise Mega53WorkerError(
                    "mega53_checkpoint_incompatible:"
                    f"missing={len(incompatible.missing_keys)},"
                    f"unexpected={len(incompatible.unexpected_keys)}"
                )

            self.torch = torch
            self.device = torch.device("cuda")
            torch.backends.cuda.matmul.allow_tf32 = True
            self.model = model.eval().to(self.device)
            self.architecture = architecture
            self.output_stems = list(architecture.training.instruments)
            if len(self.output_stems) != int(model_config["output_count"]):
                raise Mega53WorkerError("mega53_output_count_mismatch")
            mapped_stems = {
                model_stem
                for model_stems in target_stems.values()
                for model_stem in model_stems
            }
            unknown = sorted(mapped_stems - set(self.output_stems))
            if unknown:
                raise Mega53WorkerError(
                    "mega53_target_mapping_invalid:" + ",".join(unknown)
                )

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
                "model_parameter_count": sum(
                    parameter.numel() for parameter in self.model.parameters()
                ),
                "model_dtype": str(next(self.model.parameters()).dtype),
                "output_count": len(self.output_stems),
                "target_stems": dict(target_stems),
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
                raise Mega53WorkerError("mega53_input_object_missing")
            store = object_store_from_config()
            if store is None:
                raise Mega53WorkerError("object_storage_not_configured")

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

                started = time.perf_counter()
                separated = demix(
                    self.architecture,
                    self.model,
                    mix,
                    self.device,
                    str(model_config["architecture"]),
                    pbar=False,
                )
                report["inference_seconds"] = round(time.perf_counter() - started, 4)
                report["model_output_count"] = len(separated)

                for product_stem, model_stems in target_stems.items():
                    target_path = temp_dir / f"{product_stem}.wav"
                    try:
                        waveform = separated[model_stems[0]].copy()
                        for model_stem in model_stems[1:]:
                            waveform += separated[model_stem]
                        sf.write(
                            target_path,
                            waveform.T,
                            sample_rate,
                            subtype="PCM_24",
                        )
                        key = store.artifact_key(
                            job_id,
                            "mega53_specialists",
                            target_path.name,
                        )
                        reference = store.upload(target_path, key, "audio/wav")
                        report["outputs"][product_stem] = {
                            "model_stems": list(model_stems),
                            "object": reference.as_dict(),
                            "channels": int(waveform.shape[0]),
                            "sample_rate": sample_rate,
                            "duration_seconds": round(
                                waveform.shape[-1] / sample_rate,
                                4,
                            ),
                            "encoding": "PCM_24",
                        }
                    except Exception as exc:
                        report["failures"][product_stem] = {
                            "error_type": type(exc).__name__,
                            "reason": str(exc)[:500],
                        }

                report["finished_at"] = datetime.now(UTC).isoformat()
                report["status"] = (
                    "completed" if not report["failures"] else "completed_with_failures"
                )
                report_path = temp_dir / "mega53-report.json"
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
        output_dir: str = "benchmarks/mvsep_mega53",
        job_id: str = "",
    ) -> None:
        _load_env_file(ROOT_DIR / ".env.local")
        from splitter.object_storage import object_store_from_config

        input_path = Path(input).expanduser().resolve()
        if not input_path.exists() or input_path.suffix.lower() not in AUDIO_SUFFIXES:
            raise Mega53WorkerError(f"invalid_audio_input:{input_path}")
        store = object_store_from_config()
        if store is None:
            raise Mega53WorkerError("object_storage_not_configured")

        resolved_job_id = _safe_job_id(job_id)
        input_key = (
            f"{store.prefix}/research/mvsep-mega53/{resolved_job_id}/"
            f"input/{input_path.name}"
        )
        input_ref = store.upload(input_path, input_key, _content_type(input_path))
        result = Mega53Specialist().separate.remote(
            {
                "job_id": resolved_job_id,
                "input_object": input_ref.as_dict(),
            }
        )

        local_output_dir = Path(output_dir).expanduser().resolve() / resolved_job_id
        local_output_dir.mkdir(parents=True, exist_ok=True)
        for stem_name, payload in result["outputs"].items():
            store.download(payload["object"], local_output_dir / f"{stem_name}.wav")
        report_path = local_output_dir / "mega53-report.json"
        report_path.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"status={result['status']}")
        print(f"outputs={','.join(sorted(result['outputs']))}")
        print(f"failures={','.join(sorted(result['failures']))}")
        print(f"report={report_path}")

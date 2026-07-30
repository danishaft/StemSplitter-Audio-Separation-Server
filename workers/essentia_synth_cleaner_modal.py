from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "models" / "synth_cleaner.yaml"
CONTAINER_CONFIG_PATH = Path("/root/project/models/synth_cleaner.yaml")
MODEL_ROOT = Path("/tmp/essentia-models")


class SynthCleanerError(RuntimeError):
    """Raised when the pinned synth scorer cannot run as configured."""


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SynthCleanerError("synth_config_must_be_mapping")
    if payload.get("status") != "score_only_calibration_required":
        raise SynthCleanerError("synth_config_status_invalid")
    classes = payload.get("classes")
    scoring = payload.get("scoring")
    decision = payload.get("decision")
    if not isinstance(classes, list) or len(classes) != 40:
        raise SynthCleanerError("synth_class_contract_invalid")
    if not isinstance(scoring, dict) or not isinstance(decision, dict):
        raise SynthCleanerError("synth_scoring_contract_invalid")
    positive_classes = set(scoring.get("positive_classes", []))
    confuser_classes = set(scoring.get("confuser_classes", []))
    if (
        positive_classes & confuser_classes
        or positive_classes | confuser_classes != set(classes)
    ):
        raise SynthCleanerError("synth_binary_class_partition_invalid")
    if decision.get("mode") != "calibration_required":
        raise SynthCleanerError("synth_decision_mode_invalid")
    if any(
        decision.get(field) is not None
        for field in (
            "automatic_accept_threshold",
            "automatic_reject_threshold",
            "minimum_margin",
        )
    ):
        raise SynthCleanerError("synth_uncalibrated_threshold_present")
    return payload


def load_batch_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise SynthCleanerError("synth_batch_candidates_missing")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise SynthCleanerError("synth_batch_candidate_invalid")
        if not candidate.get("id") or not candidate.get("path"):
            raise SynthCleanerError("synth_batch_candidate_identity_missing")
    return candidates


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download_model(url: str, destination: Path, expected_sha256: str) -> None:
    if not destination.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        urllib.request.urlretrieve(url, temporary)
        temporary.replace(destination)
    if _file_digest(destination) != expected_sha256:
        destination.unlink(missing_ok=True)
        raise SynthCleanerError("synth_model_checksum_mismatch")


try:
    import modal
except ImportError:  # pragma: no cover - Modal is a deployment dependency
    modal = None
    app = None
else:
    config = load_config(CONFIG_PATH if modal.is_local() else CONTAINER_CONFIG_PATH)
    runtime_config = config["runtime"]
    model_configs = config["models"]
    scoring_config = config["scoring"]
    class_names = [str(value) for value in config["classes"]]

    app = modal.App(
        os.getenv("SYNTH_CLEANER_MODAL_APP_NAME", "stemsplitter-synth-cleaner")
    )
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "libsndfile1")
        .pip_install(
            "essentia-tensorflow==2.1b6.dev1110",
            "librosa==0.11.0",
            "numpy<2.0",
            "pyyaml",
            "soundfile",
        )
        .add_local_file(
            "models/synth_cleaner.yaml",
            str(CONTAINER_CONFIG_PATH),
        )
    )

    @app.cls(
        image=image,
        cpu=float(os.getenv("SYNTH_CLEANER_MODAL_CPU", "4")),
        memory=int(os.getenv("SYNTH_CLEANER_MODAL_MEMORY_MB", "8192")),
        timeout=int(os.getenv("SYNTH_CLEANER_MODAL_TIMEOUT", "1800")),
        max_containers=1,
        scaledown_window=300,
    )
    class EssentiaSynthCleaner:
        @modal.enter()
        def load_models(self) -> None:
            from essentia.standard import (
                TensorflowPredict2D,
                TensorflowPredictEffnetDiscogs,
            )

            self.model_paths: dict[str, Path] = {}
            for model_name, model_config in model_configs.items():
                model_path = MODEL_ROOT / str(model_config["filename"])
                _download_model(
                    str(model_config["url"]),
                    model_path,
                    str(model_config["sha256"]),
                )
                self.model_paths[model_name] = model_path

            self.embedder = TensorflowPredictEffnetDiscogs(
                graphFilename=str(self.model_paths["embedding"]),
                output=str(runtime_config["embedding_output"]),
            )
            self.classifier = TensorflowPredict2D(
                graphFilename=str(self.model_paths["classifier"]),
                input=str(runtime_config["classifier_input"]),
                output=str(runtime_config["classifier_output"]),
                dimensions=1280,
            )

        @modal.method()
        def preflight(self) -> dict[str, Any]:
            return {
                "status": "ready_for_calibration",
                "decision_mode": config["decision"]["mode"],
                "sample_rate": int(runtime_config["sample_rate"]),
                "prediction_hz": float(runtime_config["prediction_hz"]),
                "class_count": len(class_names),
                "positive_classes": scoring_config["positive_classes"],
                "confuser_classes": scoring_config["confuser_classes"],
                "models": {
                    model_name: {
                        "filename": path.name,
                        "sha256": _file_digest(path),
                    }
                    for model_name, path in sorted(self.model_paths.items())
                },
            }

        @modal.method()
        def score(self, audio_bytes: bytes) -> dict[str, Any]:
            import librosa
            import numpy as np
            import soundfile as sf

            audio, source_rate = sf.read(
                io.BytesIO(audio_bytes),
                always_2d=True,
                dtype="float32",
            )
            mono = audio.mean(axis=1)
            sample_rate = int(runtime_config["sample_rate"])
            if source_rate != sample_rate:
                mono = librosa.resample(
                    mono,
                    orig_sr=source_rate,
                    target_sr=sample_rate,
                )
            embeddings = self.embedder(
                np.ascontiguousarray(mono, dtype="float32")
            )
            predictions = self.classifier(embeddings)
            if (
                predictions.ndim != 2
                or predictions.shape[0] == 0
                or predictions.shape[1] != len(class_names)
            ):
                raise SynthCleanerError("synth_prediction_shape_invalid")

            indexes = {name: index for index, name in enumerate(class_names)}
            positive_names = scoring_config["positive_classes"]
            confuser_names = scoring_config["confuser_classes"]
            prediction_hz = float(runtime_config["prediction_hz"])
            windows = []
            for index, prediction in enumerate(predictions):
                class_scores = {
                    name: float(prediction[indexes[name]])
                    for name in positive_names + confuser_names
                }
                positive_score = max(class_scores[name] for name in positive_names)
                confuser_score = max(class_scores[name] for name in confuser_names)
                windows.append(
                    {
                        "index": index,
                        "start_seconds": index / prediction_hz,
                        "positive_score": positive_score,
                        "confuser_score": confuser_score,
                        "margin": positive_score - confuser_score,
                        "class_scores": class_scores,
                    }
                )

            return {
                "status": "scored",
                "decision": "calibration_required",
                "source_sample_rate": int(source_rate),
                "sample_rate": sample_rate,
                "prediction_hz": prediction_hz,
                "window_count": len(windows),
                "summary": {
                    "mean_positive_score": float(
                        np.mean(
                            [window["positive_score"] for window in windows]
                        )
                    ),
                    "max_positive_score": float(
                        max(window["positive_score"] for window in windows)
                    ),
                    "mean_confuser_score": float(
                        np.mean(
                            [window["confuser_score"] for window in windows]
                        )
                    ),
                    "mean_margin": float(
                        np.mean([window["margin"] for window in windows])
                    ),
                },
                "windows": windows,
            }

    @app.local_entrypoint()
    def main(
        action: str = "preflight",
        input: str = "",
        output: str = "",
    ) -> None:
        if action == "preflight":
            result = EssentiaSynthCleaner().preflight.remote()
        elif action == "score":
            input_path = Path(input).expanduser().resolve()
            if not input_path.is_file():
                raise SynthCleanerError(f"synth_input_missing:{input_path}")
            result = EssentiaSynthCleaner().score.remote(input_path.read_bytes())
        elif action == "batch":
            manifest_path = Path(input).expanduser().resolve()
            if not manifest_path.is_file():
                raise SynthCleanerError(
                    f"synth_batch_manifest_missing:{manifest_path}"
                )
            candidates = load_batch_manifest(manifest_path)
            cleaner = EssentiaSynthCleaner()
            receipts = []
            for candidate in candidates:
                candidate_path = Path(candidate["path"]).expanduser().resolve()
                receipt = {
                    "candidate_id": candidate["id"],
                    "path": str(candidate_path),
                    "metadata": candidate.get("metadata", {}),
                }
                try:
                    audio_bytes = candidate_path.read_bytes()
                    scoring = cleaner.score.remote(audio_bytes)
                    receipt.update(
                        {
                            "audio_sha256": hashlib.sha256(
                                audio_bytes
                            ).hexdigest(),
                            "decision": "calibration_required",
                            "scoring": scoring,
                        }
                    )
                except Exception as exc:
                    receipt.update(
                        {
                            "decision": "error",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                receipts.append(receipt)
            result = {
                "schema_version": "1.0",
                "cleaner": "essentia_mtg_jamendo_instrument",
                "candidate_count": len(receipts),
                "decision_counts": {
                    decision: sum(
                        receipt["decision"] == decision for receipt in receipts
                    )
                    for decision in ("calibration_required", "error")
                },
                "candidates": receipts,
            }
        else:
            raise SynthCleanerError(f"synth_action_invalid:{action}")

        rendered = json.dumps(result, indent=2, sort_keys=True)
        if output:
            output_path = Path(output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
            print(f"receipt={output_path}")
        if action == "batch":
            print(
                json.dumps(
                    {
                        "candidate_count": result["candidate_count"],
                        "decision_counts": result["decision_counts"],
                    },
                    sort_keys=True,
                )
            )
        else:
            print(rendered)

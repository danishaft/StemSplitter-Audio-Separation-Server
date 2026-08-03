from __future__ import annotations

import hashlib
import io
import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "models" / "acmid_cleaner.yaml"
CONTAINER_CONFIG_PATH = Path("/root/project/models/acmid_cleaner.yaml")
VOLUME_ROOT = Path("/training")


class ACMIDCleanerError(RuntimeError):
    """Raised when the pinned ACMID cleaner cannot run exactly as configured."""


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ACMIDCleanerError("acmid_config_must_be_mapping")
    if payload.get("status") != "official_reproduction_under_validation":
        raise ACMIDCleanerError("acmid_config_status_invalid")
    runtime = payload.get("runtime")
    classifiers = payload.get("classifiers")
    if not isinstance(runtime, dict) or float(runtime.get("threshold", 0)) != 0.995:
        raise ACMIDCleanerError("acmid_runtime_invalid")
    expected = {
        "acoustic_guitar",
        "bass",
        "drums",
        "electric_guitar",
        "piano",
        "strings",
        "wind",
    }
    if not isinstance(classifiers, dict) or set(classifiers) != expected:
        raise ACMIDCleanerError("acmid_classifier_contract_invalid")
    return payload


def load_batch_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise ACMIDCleanerError("acmid_batch_candidates_missing")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ACMIDCleanerError("acmid_batch_candidate_invalid")
        if not candidate.get("id") or not candidate.get("path"):
            raise ACMIDCleanerError("acmid_batch_candidate_identity_missing")
        if not candidate.get("instrument"):
            raise ACMIDCleanerError("acmid_batch_candidate_instrument_missing")
    return candidates


def load_synth_training_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or not candidates:
        raise ACMIDCleanerError("synth_training_candidates_missing")
    for candidate in candidates:
        metadata = candidate.get("metadata", {})
        if not candidate.get("id") or not candidate.get("path"):
            raise ACMIDCleanerError("synth_training_candidate_identity_missing")
        if metadata.get("label") not in {
            "positive",
            "confuser",
            "target_absent",
        }:
            raise ACMIDCleanerError("synth_training_candidate_label_invalid")
        if metadata.get("split") not in {"calibration", "validation"}:
            raise ACMIDCleanerError("synth_training_candidate_split_invalid")
        if not metadata.get("song_id"):
            raise ACMIDCleanerError("synth_training_candidate_song_missing")
    return candidates


def _file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


try:
    import modal
except ImportError:  # pragma: no cover - Modal is a deployment dependency
    modal = None
    app = None
else:
    config = load_config(CONFIG_PATH if modal.is_local() else CONTAINER_CONFIG_PATH)
    runtime_config = config["runtime"]
    classifier_configs = config["classifiers"]

    app = modal.App(os.getenv("ACMID_MODAL_APP_NAME", "stemsplitter-acmid-cleaner"))
    training_volume = modal.Volume.from_name(
        "stemsplitter-specialist-training",
        create_if_missing=False,
    )
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("ffmpeg", "libsndfile1")
        .pip_install(
            "dasheng==0.0.9",
            "einops==0.8.1",
            "librosa==0.11.0",
            "numpy<2.0",
            "pyyaml",
            "soundfile",
            "torch==2.10.0",
            "torchaudio==2.10.0",
        )
        .run_commands(
            "python -c \"import torch; "
            "torch.hub.load_state_dict_from_url("
            "'https://zenodo.org/records/11511780/files/"
            "dasheng_base.pt?download=1', map_location='cpu', progress=False)\""
        )
        .add_local_file(
            "models/acmid_cleaner.yaml",
            str(CONTAINER_CONFIG_PATH),
        )
    )

    @app.cls(
        image=image,
        gpu=os.getenv("ACMID_MODAL_GPU", "T4"),
        cpu=float(os.getenv("ACMID_MODAL_CPU", "4")),
        memory=int(os.getenv("ACMID_MODAL_MEMORY_MB", "16384")),
        timeout=int(os.getenv("ACMID_MODAL_TIMEOUT", "1800")),
        max_containers=1,
        scaledown_window=300,
        volumes={str(VOLUME_ROOT): training_volume},
    )
    class ACMIDCleaner:
        @modal.enter()
        def load_models(self) -> None:
            import numpy as np
            import torch
            from dasheng.pretrained.pretrained import Dasheng
            from torch import nn

            self.torch = torch
            self.device = torch.device("cuda")
            encoder_config = config["encoder"]
            architecture_config = encoder_config["architecture"]
            weights_config = encoder_config["weights"]
            self.encoder_architecture_source = str(
                architecture_config["source"]
            )
            self.encoder_weights_sha256 = str(weights_config["sha256"])
            weights_path = VOLUME_ROOT / str(weights_config["path"])
            if not weights_path.is_file():
                raise ACMIDCleanerError("acmid_encoder_weights_missing")
            if _file_digest(weights_path, "sha256") != str(
                weights_config["sha256"]
            ):
                raise ACMIDCleanerError(
                    "acmid_encoder_weights_checksum_mismatch"
                )

            # The ACMID AudioSet checkpoint is a raw state dict. Dasheng's
            # implementation first constructs the official base architecture.
            architecture_dump = torch.hub.load_state_dict_from_url(
                str(architecture_config["download_url"]),
                map_location="cpu",
                progress=False,
            )
            model_parameters = architecture_dump["model"]
            model_config = architecture_dump["config"]
            self.encoder = Dasheng(**model_config)
            self.encoder.load_state_dict(model_parameters, strict=True)
            encoder_state = torch.load(
                weights_path,
                map_location="cpu",
                weights_only=True,
            )
            model_keys = set(self.encoder.state_dict())
            checkpoint_keys = set(encoder_state)
            matched_key_ratio = len(model_keys & checkpoint_keys) / len(model_keys)
            if matched_key_ratio < 0.95:
                raise ACMIDCleanerError("acmid_encoder_weights_incompatible")
            self.encoder.load_state_dict(encoder_state, strict=False)
            self.encoder_matched_key_ratio = matched_key_ratio
            self.encoder.eval().to(self.device)
            for parameter in self.encoder.parameters():
                parameter.requires_grad = False

            hidden_dimensions = [int(value) for value in runtime_config["hidden_dimensions"]]
            self.heads: dict[str, Any] = {}
            self.head_parameter_counts: dict[str, int] = {}
            for instrument, head_config in classifier_configs.items():
                head_path = VOLUME_ROOT / str(head_config["path"])
                if not head_path.is_file():
                    raise ACMIDCleanerError(f"acmid_head_missing:{instrument}")
                if _file_digest(head_path, "sha256") != str(head_config["sha256"]):
                    raise ACMIDCleanerError(f"acmid_head_checksum_mismatch:{instrument}")

                layers: list[tuple[str, Any]] = []
                previous = int(self.encoder.embed_dim)
                for index, width in enumerate(hidden_dimensions):
                    layers.append((f"linear_{index}", nn.Linear(previous, width)))
                    layers.append((f"relu_{index}", nn.ReLU()))
                    previous = width
                layers.append(("final_output", nn.Linear(previous, 1)))
                head = nn.Sequential(OrderedDict(layers))
                with torch.serialization.safe_globals(
                    [
                        np.core.multiarray.scalar,
                        np.dtype,
                        type(np.dtype(np.float64)),
                    ]
                ):
                    checkpoint = torch.load(
                        head_path,
                        map_location="cpu",
                        weights_only=True,
                    )
                state = checkpoint.get("model_state_dict", checkpoint)
                head.load_state_dict(state, strict=True)
                head.eval().to(self.device)
                self.heads[instrument] = head
                self.head_parameter_counts[instrument] = sum(
                    parameter.numel() for parameter in head.parameters()
                )

        @modal.method()
        def preflight(self) -> dict[str, Any]:
            device = self.torch.cuda.get_device_properties(self.device)
            return {
                "status": "ready",
                "source_revision": config["source"]["revision"],
                "device_name": device.name,
                "threshold": float(runtime_config["threshold"]),
                "sample_rate": int(runtime_config["sample_rate"]),
                "chunk_seconds": float(runtime_config["chunk_seconds"]),
                "encoder_architecture_source": self.encoder_architecture_source,
                "encoder_weights_sha256": self.encoder_weights_sha256,
                "encoder_matched_key_ratio": self.encoder_matched_key_ratio,
                "classifiers": {
                    instrument: {
                        "sha256": classifier_configs[instrument]["sha256"],
                        "parameter_count": self.head_parameter_counts[instrument],
                    }
                    for instrument in sorted(self.heads)
                },
            }

        @modal.method()
        def classify(
            self,
            audio_bytes: bytes,
            instrument: str,
        ) -> dict[str, Any]:
            import librosa
            import numpy as np
            import soundfile as sf

            if instrument not in self.heads:
                raise ACMIDCleanerError(f"acmid_instrument_invalid:{instrument}")
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
            chunk_samples = round(float(runtime_config["chunk_seconds"]) * sample_rate)
            chunk_count = len(mono) // chunk_samples
            if chunk_count == 0:
                raise ACMIDCleanerError("acmid_audio_shorter_than_one_chunk")
            chunks = np.stack(
                [
                    mono[index * chunk_samples : (index + 1) * chunk_samples]
                    for index in range(chunk_count)
                ]
            ).astype("float32", copy=False)

            probabilities: list[float] = []
            batch_size = int(runtime_config["batch_size"])
            with self.torch.inference_mode():
                for offset in range(0, chunk_count, batch_size):
                    batch = self.torch.from_numpy(chunks[offset : offset + batch_size])
                    batch = batch.to(self.device)
                    batch = batch / (
                        batch.abs().amax(dim=1, keepdim=True) + 1e-9
                    )
                    embeddings = self.encoder(batch).mean(dim=1)
                    logits = self.heads[instrument](embeddings).squeeze(1)
                    probabilities.extend(
                        self.torch.sigmoid(logits).cpu().tolist()
                    )

            threshold = float(runtime_config["threshold"])
            accepted = [
                index for index, probability in enumerate(probabilities)
                if probability >= threshold
            ]
            return {
                "status": "completed",
                "instrument": instrument,
                "source_sample_rate": int(source_rate),
                "sample_rate": sample_rate,
                "chunk_seconds": float(runtime_config["chunk_seconds"]),
                "threshold": threshold,
                "chunk_count": chunk_count,
                "accepted_chunk_indexes": accepted,
                "accepted_chunk_count": len(accepted),
                "probabilities": probabilities,
            }

        @modal.method()
        def train_synth_head(
            self,
            candidates: list[dict[str, Any]],
            seed: int = 20260729,
        ) -> dict[str, Any]:
            import hashlib
            import random

            import librosa
            import numpy as np
            import soundfile as sf
            from torch import nn
            from torch.utils.data import DataLoader, TensorDataset

            random.seed(seed)
            np.random.seed(seed)
            self.torch.manual_seed(seed)
            self.torch.cuda.manual_seed_all(seed)

            sample_rate = int(runtime_config["sample_rate"])
            chunk_seconds = float(runtime_config["chunk_seconds"])
            chunk_samples = round(chunk_seconds * sample_rate)
            hop_samples = sample_rate
            rows = []
            for candidate in candidates:
                metadata = candidate["metadata"]
                audio, source_rate = sf.read(
                    io.BytesIO(candidate["audio_bytes"]),
                    always_2d=True,
                    dtype="float32",
                )
                mono = audio.mean(axis=1)
                if source_rate != sample_rate:
                    mono = librosa.resample(
                        mono,
                        orig_sr=source_rate,
                        target_sr=sample_rate,
                    )
                starts = range(
                    0,
                    max(0, len(mono) - chunk_samples + 1),
                    hop_samples,
                )
                chunks = np.stack(
                    [
                        mono[start : start + chunk_samples]
                        for start in starts
                    ]
                ).astype("float32", copy=False)
                with self.torch.inference_mode():
                    batch = self.torch.from_numpy(chunks).to(self.device)
                    batch = batch / (
                        batch.abs().amax(dim=1, keepdim=True) + 1e-9
                    )
                    embeddings = self.encoder(batch).mean(dim=1).cpu()
                for embedding in embeddings:
                    rows.append(
                        {
                            "embedding": embedding,
                            "label": int(metadata["label"] == "positive"),
                            "source_label": metadata["label"],
                            "split": metadata["split"],
                            "song_id": metadata["song_id"],
                        }
                    )

            calibration_rows = [
                row for row in rows if row["split"] == "calibration"
            ]
            validation_rows = [
                row for row in rows if row["split"] == "validation"
            ]
            if (
                sum(row["label"] for row in calibration_rows) < 200
                or sum(not row["label"] for row in calibration_rows) < 400
            ):
                raise ACMIDCleanerError(
                    "synth_training_calibration_examples_missing"
                )

            songs_by_label: dict[int, list[str]] = {0: [], 1: []}
            for label in (0, 1):
                songs_by_label[label] = sorted(
                    {
                        row["song_id"]
                        for row in calibration_rows
                        if row["label"] == label
                    },
                    key=lambda song_id: hashlib.sha256(
                        f"{seed}:{label}:{song_id}".encode()
                    ).hexdigest(),
                )
            fold_by_song = {}
            for label, songs in songs_by_label.items():
                for index, song_id in enumerate(songs):
                    fold_by_song[(label, song_id)] = index % 5

            hidden_dimensions = [256, 128, 64]

            def build_head() -> nn.Sequential:
                layers: list[tuple[str, Any]] = []
                previous = int(self.encoder.embed_dim)
                for index, width in enumerate(hidden_dimensions):
                    layers.append((f"linear_{index}", nn.Linear(previous, width)))
                    layers.append((f"relu_{index}", nn.ReLU()))
                    previous = width
                layers.append(("final_output", nn.Linear(previous, 1)))
                return nn.Sequential(OrderedDict(layers)).to(self.device)

            def train_head(training_rows: list[dict[str, Any]]) -> nn.Sequential:
                head = build_head()
                features = self.torch.stack(
                    [row["embedding"] for row in training_rows]
                )
                labels = self.torch.tensor(
                    [row["label"] for row in training_rows],
                    dtype=self.torch.float32,
                )
                positives = float(labels.sum())
                negatives = float(len(labels) - positives)
                loss_function = nn.BCEWithLogitsLoss(
                    pos_weight=self.torch.tensor(
                        negatives / positives,
                        device=self.device,
                    )
                )
                optimizer = self.torch.optim.AdamW(
                    head.parameters(),
                    lr=5e-4,
                    weight_decay=1e-4,
                )
                generator = self.torch.Generator().manual_seed(seed)
                loader = DataLoader(
                    TensorDataset(features, labels),
                    batch_size=64,
                    shuffle=True,
                    generator=generator,
                )
                head.train()
                for _ in range(50):
                    for batch_features, batch_labels in loader:
                        optimizer.zero_grad(set_to_none=True)
                        logits = head(
                            batch_features.to(self.device)
                        ).squeeze(1)
                        loss = loss_function(
                            logits,
                            batch_labels.to(self.device),
                        )
                        loss.backward()
                        optimizer.step()
                return head.eval()

            def predict(
                head: nn.Sequential,
                prediction_rows: list[dict[str, Any]],
            ) -> list[float]:
                features = self.torch.stack(
                    [row["embedding"] for row in prediction_rows]
                ).to(self.device)
                with self.torch.inference_mode():
                    return (
                        self.torch.sigmoid(head(features).squeeze(1))
                        .cpu()
                        .tolist()
                    )

            out_of_fold = []
            for fold in range(5):
                fold_training = [
                    row
                    for row in calibration_rows
                    if fold_by_song[(row["label"], row["song_id"])] != fold
                ]
                fold_holdout = [
                    row
                    for row in calibration_rows
                    if fold_by_song[(row["label"], row["song_id"])] == fold
                ]
                head = train_head(fold_training)
                for row, probability in zip(
                    fold_holdout,
                    predict(head, fold_holdout),
                    strict=True,
                ):
                    out_of_fold.append(
                        {
                            "label": row["label"],
                            "probability": probability,
                        }
                    )

            def acceptance_metrics(
                predictions: list[dict[str, Any]],
                threshold: float,
            ) -> dict[str, float | int]:
                accepted = [
                    row
                    for row in predictions
                    if row["probability"] >= threshold
                ]
                true_positive = sum(row["label"] for row in accepted)
                positive_count = sum(row["label"] for row in predictions)
                return {
                    "accepted": len(accepted),
                    "true_positive": true_positive,
                    "false_positive": len(accepted) - true_positive,
                    "precision": (
                        true_positive / len(accepted) if accepted else 0.0
                    ),
                    "recall": (
                        true_positive / positive_count
                        if positive_count
                        else 0.0
                    ),
                }

            threshold = None
            threshold_metrics = None
            for candidate_threshold in sorted(
                {row["probability"] for row in out_of_fold}
            ):
                metrics = acceptance_metrics(
                    out_of_fold,
                    candidate_threshold,
                )
                if metrics["precision"] < 0.99 or metrics["recall"] < 0.5:
                    continue
                if (
                    threshold_metrics is None
                    or metrics["recall"] > threshold_metrics["recall"]
                ):
                    threshold = candidate_threshold
                    threshold_metrics = metrics
            if threshold is None or threshold_metrics is None:
                return {
                    "status": "failed",
                    "reason": "synth_oof_acceptance_target_unreachable",
                    "calibration_example_count": len(calibration_rows),
                    "validation_example_count": len(validation_rows),
                }

            positive_probabilities = sorted(
                row["probability"]
                for row in out_of_fold
                if row["label"]
            )
            allowed_false_rejects = int(
                len(positive_probabilities) * 0.01
            )
            reject_threshold = float(
                np.nextafter(
                    positive_probabilities[allowed_false_rejects],
                    -np.inf,
                )
            )

            final_head = train_head(calibration_rows)
            validation_predictions = []
            for row, probability in zip(
                validation_rows,
                predict(final_head, validation_rows),
                strict=True,
            ):
                validation_predictions.append(
                    {"label": row["label"], "probability": probability}
                )
            validation_metrics = acceptance_metrics(
                validation_predictions,
                threshold,
            )
            validation_positive = [
                row for row in validation_predictions if row["label"]
            ]
            false_reject_rate = (
                sum(
                    row["probability"] <= reject_threshold
                    for row in validation_positive
                )
                / len(validation_positive)
            )
            passed = (
                validation_metrics["precision"] >= 0.99
                and validation_metrics["recall"] >= 0.5
                and false_reject_rate <= 0.01
            )
            result = {
                "status": "passed" if passed else "failed",
                "seed": seed,
                "architecture": {
                    "encoder": "dasheng_base_audioset_mAP497",
                    "head_hidden_dimensions": hidden_dimensions,
                    "encoder_frozen": True,
                },
                "calibration_example_count": len(calibration_rows),
                "validation_example_count": len(validation_rows),
                "thresholds": {
                    "automatic_accept_threshold": threshold,
                    "automatic_reject_threshold": reject_threshold,
                },
                "out_of_fold": threshold_metrics,
                "validation": {
                    **validation_metrics,
                    "positive_false_reject_rate": false_reject_rate,
                },
            }
            if passed:
                checkpoint_path = (
                    VOLUME_ROOT
                    / "acmid/models/Instruments_cleaner_dasheng_synth.pth"
                )
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                self.torch.save(
                    {
                        "model_state_dict": final_head.cpu().state_dict(),
                        "thresholds": result["thresholds"],
                        "training_receipt": result,
                    },
                    checkpoint_path,
                )
                result["checkpoint_path"] = str(checkpoint_path)
                result["checkpoint_sha256"] = _file_digest(
                    checkpoint_path,
                    "sha256",
                )
            return result

    @app.local_entrypoint()
    def main(
        action: str = "preflight",
        input: str = "",
        instrument: str = "electric_guitar",
        output: str = "",
    ) -> None:
        if action == "preflight":
            result = ACMIDCleaner().preflight.remote()
        elif action == "classify":
            input_path = Path(input).expanduser().resolve()
            if not input_path.is_file():
                raise ACMIDCleanerError(f"acmid_input_missing:{input_path}")
            result = ACMIDCleaner().classify.remote(
                input_path.read_bytes(),
                instrument,
            )
        elif action == "batch":
            manifest_path = Path(input).expanduser().resolve()
            if not manifest_path.is_file():
                raise ACMIDCleanerError(
                    f"acmid_batch_manifest_missing:{manifest_path}"
                )
            candidates = load_batch_manifest(manifest_path)
            cleaner = ACMIDCleaner()
            receipts = []
            for candidate in candidates:
                candidate_path = Path(candidate["path"]).expanduser().resolve()
                receipt = {
                    "candidate_id": candidate["id"],
                    "instrument": candidate["instrument"],
                    "path": str(candidate_path),
                    "metadata": candidate.get("metadata", {}),
                }
                try:
                    audio_bytes = candidate_path.read_bytes()
                    classification = cleaner.classify.remote(
                        audio_bytes,
                        candidate["instrument"],
                    )
                    receipt.update(
                        {
                            "audio_sha256": hashlib.sha256(
                                audio_bytes
                            ).hexdigest(),
                            "decision": (
                                "accepted"
                                if classification["accepted_chunk_count"] > 0
                                else "rejected"
                            ),
                            "classification": classification,
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
                "cleaner": "acmid_dasheng",
                "candidate_count": len(receipts),
                "decision_counts": {
                    decision: sum(
                        receipt["decision"] == decision for receipt in receipts
                    )
                    for decision in ("accepted", "rejected", "error")
                },
                "candidates": receipts,
            }
        elif action == "train_synth_head":
            manifest_path = Path(input).expanduser().resolve()
            if not manifest_path.is_file():
                raise ACMIDCleanerError(
                    f"synth_training_manifest_missing:{manifest_path}"
                )
            candidates = load_synth_training_manifest(manifest_path)
            result = ACMIDCleaner().train_synth_head.remote(
                [
                    {
                        "id": candidate["id"],
                        "audio_bytes": Path(candidate["path"]).read_bytes(),
                        "metadata": candidate["metadata"],
                    }
                    for candidate in candidates
                ]
            )
        else:
            raise ACMIDCleanerError(f"acmid_action_invalid:{action}")

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

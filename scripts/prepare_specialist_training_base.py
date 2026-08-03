from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
)

DEFAULT_SPECS = ROOT / "training" / "base_specs.yaml"
DEFAULT_OUTPUT = ROOT / "training" / "generated" / "bases"


class BasePreparationError(RuntimeError):
    """Raised when a specialist base cannot be reproduced safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare hash-verified BS-RoFormer specialist bases."
    )
    parser.add_argument(
        "base_id",
        choices=SPECIALIST_BASE_IDS,
    )
    parser.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_repo_path(value: object) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else ROOT / path


def verify_file(path: Path, expected_sha256: object) -> str:
    if not path.is_file():
        raise BasePreparationError(f"required file is missing: {path}")
    actual = file_sha256(path)
    if actual != str(expected_sha256 or ""):
        raise BasePreparationError(f"SHA-256 mismatch: {path}")
    return actual


def load_specs(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(
        payload.get("bases"),
        dict,
    ):
        raise BasePreparationError("base specification must contain bases")
    return payload


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.FullLoader)
    if not isinstance(payload, dict):
        raise BasePreparationError("base model config must be a mapping")
    return payload


def prepare_config(
    source: dict[str, Any],
    output_instruments: list[str],
    training_instruments: list[str],
    *,
    trainer_defaults: dict[str, Any],
    cumulative_epochs: int,
    num_steps: int,
) -> dict[str, Any]:
    config = dict(source)
    config["audio"] = dict(source["audio"])
    config["model"] = dict(source["model"])
    config["training"] = {
        **trainer_defaults,
        **dict(source["training"]),
    }
    config["model"]["num_stems"] = len(output_instruments)
    config["audio"]["chunk_size"] = 441_000
    config["audio"]["min_mean_abs"] = 0.0001
    config["training"].update(
        {
            "instruments": training_instruments,
            "target_instrument": output_instruments[0],
            "num_epochs": cumulative_epochs,
            "num_steps": num_steps,
            "optimizer": "adamw",
            "max_class_presence_ratio": 1.0,
            "augmentation": True,
            "augmentation_mix": True,
            "augmentation_loudness": True,
            "use_amp": True,
        }
    )
    config["augmentations"] = {
        "enable": True,
        "loudness": True,
        "loudness_min": 0.5,
        "loudness_max": 1.5,
        "mixup": True,
        "mixup_probs": (0.5, 0.25, 0.1),
        "all": {
            "channel_shuffle": 0.5,
            "random_polarity": 0.5,
        },
    }
    return config


def remap_single_head(
    checkpoint_path: Path,
    source_head_index: int,
) -> OrderedDict[str, Any]:
    import torch

    state = torch.load(
        checkpoint_path,
        map_location="cpu",
        mmap=True,
        weights_only=True,
    )
    if not isinstance(state, dict):
        raise BasePreparationError("checkpoint must contain a state dictionary")
    source_prefix = f"mask_estimators.{source_head_index}."
    result: OrderedDict[str, Any] = OrderedDict()
    remapped = 0
    for key, value in state.items():
        if key.startswith("mask_estimators."):
            if not key.startswith(source_prefix):
                continue
            key = f"mask_estimators.0.{key[len(source_prefix):]}"
            remapped += 1
        if key in result:
            raise BasePreparationError(f"checkpoint key collision: {key}")
        result[key] = value
    if remapped == 0:
        raise BasePreparationError("requested source head was not found")
    return result


def main() -> int:
    args = parse_args()
    try:
        specs_path = args.specs.expanduser().resolve()
        specs = load_specs(specs_path)
        spec = specs["bases"][args.base_id]
        checkpoint_path = resolve_repo_path(spec["checkpoint_path"])
        config_path = resolve_repo_path(spec["config_path"])
        checkpoint_sha256 = verify_file(
            checkpoint_path,
            spec["checkpoint_sha256"],
        )
        config_sha256 = verify_file(config_path, spec["config_sha256"])
        output_instruments = list(spec["output_instruments"])
        training_instruments = list(spec["training_instruments"])
        source_config = load_config(config_path)
        if list(source_config["training"]["instruments"]) != list(
            spec["source_instruments"]
        ):
            raise BasePreparationError("source instrument order mismatch")
        source_head_index = spec.get("source_head_index")
        source_head_name = None
        if source_head_index is not None:
            source_head_index = int(source_head_index)
            source_instruments = list(spec["source_instruments"])
            if not 0 <= source_head_index < len(source_instruments):
                raise BasePreparationError("source head index is out of range")
            source_head_name = source_instruments[source_head_index]
            if source_head_name != spec.get("source_head_name"):
                raise BasePreparationError("source head name mismatch")

        output_root = args.output_root.expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        output_checkpoint = output_root / str(spec["output_checkpoint"])

        if source_head_index is not None:
            import torch

            state = remap_single_head(
                checkpoint_path,
                source_head_index,
            )
            torch.save(state, output_checkpoint)
        else:
            shutil.copyfile(checkpoint_path, output_checkpoint)

        schedule = specs["training_schedule"]
        num_steps = int(schedule["num_steps_per_epoch"])
        output_config_template = Path(str(spec["output_config"]))
        output_configs: dict[str, dict[str, Any]] = {}
        for stage in (25, 50, 100):
            cumulative_epochs = int(
                schedule["stages"][stage]["cumulative_epochs"]
            )
            output_config = output_root / (
                f"{output_config_template.stem}_stage_{stage}"
                f"{output_config_template.suffix}"
            )
            prepared_config = prepare_config(
                source_config,
                output_instruments,
                training_instruments,
                trainer_defaults=dict(specs["trainer_defaults"]),
                cumulative_epochs=cumulative_epochs,
                num_steps=num_steps,
            )
            output_config.write_text(
                yaml.dump(
                    prepared_config,
                    Dumper=yaml.Dumper,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            output_configs[str(stage)] = {
                "path": str(output_config.relative_to(ROOT)),
                "sha256": file_sha256(output_config),
                "cumulative_epochs": cumulative_epochs,
                "num_steps_per_epoch": num_steps,
            }
        receipt = {
            "schema_version": "1.0",
            "base_id": args.base_id,
            "allowed_profile": spec["allowed_profile"],
            "license_status": spec["license_status"],
            "trainer_revision": specs["trainer"]["revision"],
            "source_checkpoint": str(checkpoint_path.relative_to(ROOT)),
            "source_checkpoint_sha256": checkpoint_sha256,
            "source_config": str(config_path.relative_to(ROOT)),
            "source_config_sha256": config_sha256,
            "source_head_index": source_head_index,
            "source_head_name": source_head_name,
            "initialization_strategy": spec["initialization_strategy"],
            "output_instruments": output_instruments,
            "output_checkpoint": str(output_checkpoint.relative_to(ROOT)),
            "output_checkpoint_sha256": file_sha256(output_checkpoint),
            "output_configs": output_configs,
        }
        receipt_path = output_root / f"{args.base_id}.receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        BasePreparationError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        yaml.YAMLError,
    ) as exc:
        print(f"specialist base preparation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
)


class TrainingStageError(RuntimeError):
    """Raised when a specialist training stage is not reproducible."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one provenance-locked specialist training stage."
    )
    parser.add_argument(
        "base_id",
        choices=SPECIALIST_BASE_IDS,
    )
    parser.add_argument("stage", type=int, choices=(25, 50, 100))
    parser.add_argument("run_id")
    parser.add_argument(
        "--profile",
        choices=("research_all", "release_eligible"),
        default="research_all",
    )
    parser.add_argument(
        "--trainer-root",
        type=Path,
        default=ROOT / "external_repos" / "Music-Source-Separation-Training",
    )
    parser.add_argument(
        "--base-root",
        type=Path,
        default=ROOT / "training" / "generated" / "bases",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=ROOT / "training" / "trainer_datasets",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=ROOT / "training" / "runs",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TrainingStageError(f"required receipt is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TrainingStageError(f"receipt is not an object: {path}")
    return payload


def _previous_stage(stage: int) -> int | None:
    return {25: None, 50: 25, 100: 50}[stage]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    try:
        trainer_root = args.trainer_root.expanduser().resolve()
        train_script = trainer_root / "train.py"
        if not train_script.is_file():
            raise TrainingStageError(
                f"pinned trainer is unavailable: {trainer_root}"
            )
        base_root = args.base_root.expanduser().resolve()
        base_receipt = _load_json(base_root / f"{args.base_id}.receipt.json")
        dataset_dir = (
            args.dataset_root.expanduser().resolve()
            / args.profile
            / args.base_id
            / f"stage_{args.stage}"
        )
        dataset = _load_json(dataset_dir / "dataset.json")
        if dataset.get("base_id") != args.base_id:
            raise TrainingStageError("trainer dataset base mismatch")
        if int(dataset.get("stage_percent") or 0) != args.stage:
            raise TrainingStageError("trainer dataset stage mismatch")
        if dataset.get("profile") != args.profile:
            raise TrainingStageError("trainer dataset profile mismatch")

        config_record = base_receipt["output_configs"][str(args.stage)]
        config_path = ROOT / str(config_record["path"])
        if _sha256(config_path) != str(config_record["sha256"]):
            raise TrainingStageError("stage config checksum mismatch")

        previous_stage = _previous_stage(args.stage)
        runs_root = args.runs_root.expanduser().resolve()
        run_root = runs_root / args.run_id / args.base_id
        results_path = run_root / f"stage_{args.stage}"
        results_path.mkdir(parents=True, exist_ok=True)
        if previous_stage is None:
            checkpoint_path = ROOT / str(
                base_receipt["output_checkpoint"]
            )
            if _sha256(checkpoint_path) != str(
                base_receipt["output_checkpoint_sha256"]
            ):
                raise TrainingStageError("base checkpoint checksum mismatch")
        else:
            checkpoint_path = (
                run_root
                / f"stage_{previous_stage}"
                / "last_bs_roformer.ckpt"
            )
            if not checkpoint_path.is_file():
                raise TrainingStageError(
                    f"previous stage checkpoint is missing: {checkpoint_path}"
                )

        command = [
            args.python,
            str(train_script),
            "--model_type",
            "bs_roformer",
            "--config_path",
            str(config_path),
            "--start_check_point",
            str(checkpoint_path),
            "--results_path",
            str(results_path),
            "--data_path",
            str(dataset_dir / "train"),
            "--valid_path",
            str(dataset_dir / "validation"),
            "--dataset_type",
            str(dataset["dataset_type"]),
            "--num_workers",
            str(max(0, args.num_workers)),
            "--seed",
            str(args.seed),
            "--device_ids",
            "0",
            "--metrics",
            "sdr",
            "bleedless",
            "fullness",
            "--metric_for_scheduler",
            "sdr",
            "--pin_memory",
            "--save_weights_every_epoch",
        ]
        if args.num_workers > 0:
            command.extend(
                [
                    "--persistent_workers",
                    "--prefetch_factor",
                    "4",
                ]
            )
        if previous_stage is None:
            command.append("--load_only_compatible_weights")
        else:
            command.extend(
                [
                    "--load_optimizer",
                    "--load_scheduler",
                    "--load_epoch",
                    "--load_best_metric",
                    "--load_all_metrics",
                    "--load_all_losses",
                ]
            )

        launch_receipt = {
            "schema_version": "1.0",
            "status": "planned" if not args.execute else "running",
            "created_at": datetime.now(UTC).isoformat(),
            "run_id": args.run_id,
            "base_id": args.base_id,
            "stage_percent": args.stage,
            "profile": args.profile,
            "dataset_receipt": str(dataset_dir / "dataset.json"),
            "dataset_recipe_set_sha256": dataset["recipe_set_sha256"],
            "base_receipt": str(base_root / f"{args.base_id}.receipt.json"),
            "config_path": str(config_path),
            "config_sha256": config_record["sha256"],
            "start_checkpoint": str(checkpoint_path),
            "start_checkpoint_sha256": _sha256(checkpoint_path),
            "command": command,
        }
        launch_path = results_path / "launch.json"
        _atomic_json(launch_path, launch_receipt)
        if not args.execute:
            print(json.dumps(launch_receipt, sort_keys=True))
            return 0

        completed = subprocess.run(
            command,
            cwd=trainer_root,
            check=False,
        )
        if completed.returncode != 0:
            launch_receipt["status"] = "failed"
            launch_receipt["returncode"] = completed.returncode
            _atomic_json(launch_path, launch_receipt)
            raise TrainingStageError(
                f"trainer exited with status {completed.returncode}"
            )
        output_checkpoint = results_path / "last_bs_roformer.ckpt"
        if not output_checkpoint.is_file():
            raise TrainingStageError(
                "trainer completed without a resumable checkpoint"
            )
        launch_receipt.update(
            {
                "status": "completed",
                "completed_at": datetime.now(UTC).isoformat(),
                "output_checkpoint": str(output_checkpoint),
                "output_checkpoint_sha256": _sha256(output_checkpoint),
            }
        )
        _atomic_json(launch_path, launch_receipt)
    except (
        KeyError,
        OSError,
        TrainingStageError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"specialist training stage failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(launch_receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

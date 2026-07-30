from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import modal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
)

APP_NAME = "stemsplitter-specialist-training"
DATASET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit work to the deployed specialist-training app."
    )
    parser.add_argument(
        "--action",
        choices=("prepare", "train", "export"),
        required=True,
    )
    parser.add_argument(
        "--base-id",
        choices=SPECIALIST_BASE_IDS,
        default=SPECIALIST_BASE_IDS[0],
    )
    parser.add_argument("--run-id", default="sprint-v1")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--resume-checkpoint", default="")
    parser.add_argument(
        "--resume-mode",
        choices=("state", "weights"),
        default="state",
    )
    parser.add_argument("--max-examples", type=int, default=3)
    parser.add_argument("--dataset-id", default="complete-source-pools")
    parser.add_argument("--validation-set-id", default="")
    parser.add_argument(
        "--adaptation-mode",
        choices=("full", "head"),
        default="full",
    )
    parser.add_argument(
        "--training-recipe",
        choices=("legacy", "recovery_v1"),
        default="legacy",
    )
    return parser


def _function_call(arguments: argparse.Namespace) -> tuple[str, Any]:
    if arguments.steps < 1 or arguments.epochs < 1:
        raise ValueError("steps and epochs must be positive")
    if arguments.max_examples < 1:
        raise ValueError("max_examples must be positive")
    if not DATASET_ID_PATTERN.fullmatch(arguments.dataset_id):
        raise ValueError("invalid dataset_id")

    if arguments.action == "prepare":
        function_name = "prepare_source_archives"
        function_args: tuple[Any, ...] = ()
    elif arguments.action == "train":
        function_name = "train_specialist"
        function_args = (
            arguments.base_id,
            arguments.run_id,
            arguments.steps,
            arguments.epochs,
            arguments.resume_checkpoint,
            arguments.resume_mode,
            arguments.dataset_id,
            arguments.adaptation_mode,
            arguments.validation_set_id,
            arguments.training_recipe,
        )
    else:
        function_name = "export_specialist"
        function_args = (
            arguments.base_id,
            arguments.run_id,
            arguments.max_examples,
            arguments.dataset_id,
            arguments.validation_set_id,
        )

    function = modal.Function.from_name(APP_NAME, function_name)
    return function_name, function.spawn(*function_args)


def main() -> None:
    arguments = _parser().parse_args()
    function_name, function_call = _function_call(arguments)
    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "app_name": APP_NAME,
                "action": arguments.action,
                "function_name": function_name,
                "function_call_id": function_call.object_id,
                "dashboard_url": function_call.get_dashboard_url(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

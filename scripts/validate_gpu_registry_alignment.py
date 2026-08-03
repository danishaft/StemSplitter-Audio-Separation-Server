from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.model_registry import load_model_registry  # noqa: E402

WORKER_PATH = ROOT / "workers" / "audio_separator_gpu_worker.py"
QUALITY_PROFILE = "quality_gpu_experimental"


def _literal_assignment(module: ast.Module, name: str):
    for node in module.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise RuntimeError(f"assignment not found: {name}")


def main() -> int:
    tree = ast.parse(WORKER_PATH.read_text(encoding="utf-8"))
    worker_registry = _literal_assignment(tree, "LOCAL_MODEL_REGISTRY")
    worker_profiles = _literal_assignment(tree, "PROFILE_MODEL_PLANS")
    worker_quarantine = _literal_assignment(tree, "QUARANTINED_MODELS")
    registry = load_model_registry()

    quality_plan_ids = list(worker_profiles[QUALITY_PROFILE])
    quality_model_ids: list[str] = []
    for plan_id in quality_plan_ids:
        members = worker_registry[plan_id].get("members")
        quality_model_ids.extend(members if isinstance(members, dict) else [plan_id])
    immediate_ids = {
        model.model_id
        for model in registry.models.values()
        if model.download_policy == "immediate"
    }
    if set(quality_model_ids) != immediate_ids:
        missing = sorted(immediate_ids - set(quality_model_ids))
        extra = sorted(set(quality_model_ids) - immediate_ids)
        raise SystemExit(f"quality profile mismatch: missing={missing} extra={extra}")

    for plan_id in quality_plan_ids:
        plan = worker_registry[plan_id]
        members = plan.get("members")
        if isinstance(members, dict):
            for model_id, worker_model in members.items():
                registry_model = registry.get_model(model_id)
                declared_model = (
                    registry_model.raw.get("model_filename")
                    or registry_model.raw.get("audio_separator_model_filename")
                )
                if worker_model != declared_model:
                    raise SystemExit(
                        f"model filename mismatch for {model_id}: "
                        f"worker={worker_model!r} registry={declared_model!r}"
                    )
            continue

        model_id = plan_id
        worker_model = plan["model"]
        registry_model = registry.get_model(model_id)
        declared_model = (
            registry_model.raw.get("model_filename")
            or registry_model.raw.get("audio_separator_model_filename")
        )
        if worker_model != declared_model:
            raise SystemExit(
                f"model filename mismatch for {model_id}: "
                f"worker={worker_model!r} registry={declared_model!r}"
            )

    for model_id in worker_quarantine:
        if registry.get_model(model_id).download_policy != "quarantined_replaced":
            raise SystemExit(f"quarantined worker model not quarantined in registry: {model_id}")

    print(
        f"ok: {QUALITY_PROFILE} has {len(quality_model_ids)} registry-aligned checkpoints "
        f"across {len(quality_plan_ids)} execution branches "
        f"and {len(worker_quarantine)} quarantined replacement"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

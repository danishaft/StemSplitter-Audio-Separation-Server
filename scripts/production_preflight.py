#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from urllib.parse import urljoin

import requests

from splitter.config import APP_ENV, GPU_WORKER_CONFIG
from splitter.jobs import control_plane_health
from splitter.product_contract import load_product_contract
from splitter.runtime import RuntimeConfigurationError, validate_runtime_config


def _gpu_worker_health() -> bool:
    base_url = str(GPU_WORKER_CONFIG.get("base_url") or "").rstrip("/") + "/"
    headers = {}
    if GPU_WORKER_CONFIG.get("api_key"):
        headers["Authorization"] = f"Bearer {GPU_WORKER_CONFIG['api_key']}"
    response = requests.get(
        urljoin(base_url, "health"),
        headers=headers,
        timeout=min(30, int(GPU_WORKER_CONFIG["timeout"])),
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("status", "")).lower() in {"healthy", "ok", "ready"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the production control plane.")
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="validate configuration without contacting dependencies",
    )
    args = parser.parse_args()

    checks: dict[str, object] = {}
    try:
        if APP_ENV != "production":
            raise RuntimeConfigurationError("production_preflight_requires_app_env_production")
        validate_runtime_config()
        checks["configuration"] = True
        contract = load_product_contract()
        target_stems = set(contract.target_stems)
        supported_stems = set(contract.model_supported_stems)
        candidate_stems = set(contract.specialist_candidate_stems)
        checks["product_contract"] = (
            len(target_stems) == 12
            and supported_stems.isdisjoint(candidate_stems)
            and supported_stems | candidate_stems == target_stems
        )
        if not args.config_only:
            checks.update(control_plane_health())
            checks["gpu_worker"] = _gpu_worker_health()
    except (RuntimeConfigurationError, requests.RequestException, RuntimeError) as exc:
        checks["error"] = str(exc)
        print(json.dumps(checks, sort_keys=True))
        return 1

    healthy = all(value is True for value in checks.values())
    print(json.dumps(checks, sort_keys=True))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())

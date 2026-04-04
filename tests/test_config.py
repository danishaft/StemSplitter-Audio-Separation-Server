from __future__ import annotations

import importlib

import splitter.config as config


def test_mvsep_config_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("MVSEP_API_KEY", "fixture-key")
    monkeypatch.setenv("MVSEP_TIMEOUT", "123")
    monkeypatch.setenv("MVSEP_MAX_RETRIES", "7")

    reloaded = importlib.reload(config)
    try:
        assert reloaded.MVSEP_CONFIG["api_key"] == "fixture-key"
        assert reloaded.MVSEP_CONFIG["timeout"] == 123
        assert reloaded.MVSEP_CONFIG["max_retries"] == 7
    finally:
        monkeypatch.delenv("MVSEP_API_KEY")
        monkeypatch.delenv("MVSEP_TIMEOUT")
        monkeypatch.delenv("MVSEP_MAX_RETRIES")
        importlib.reload(config)

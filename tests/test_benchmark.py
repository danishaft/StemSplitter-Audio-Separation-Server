from __future__ import annotations

import json
from pathlib import Path
import pytest

from splitter.benchmark import BenchmarkReport, BenchmarkResult, BenchmarkRunner, BenchmarkSong, compare_benchmarks


def test_benchmark_save_report_includes_specialist_metrics(tmp_path: Path) -> None:
    runner = BenchmarkRunner([], tmp_path)
    report = BenchmarkReport(
        benchmark_id="bench-001",
        created_at="2026-03-24T00:00:00Z",
        corpus_size=1,
        avg_broad_quality=0.9,
        avg_derived_quality=0.7,
        avg_specialist_quality=0.8,
        publish_rate_broad=1.0,
        publish_rate_derived=0.5,
        publish_rate_specialist=0.25,
    )
    report.easy_results.append(
        BenchmarkResult(
            song_name="fixture",
            difficulty="easy",
            success=True,
            published_broad_stems=["vocals"],
            published_derived_stems=["kick"],
            published_specialist_substems=["lead_vocals"],
            published_midi=["melody"],
            pipeline_mode="local_plus_mvsep_experimental",
            remote_adapter_status="used",
        )
    )

    runner._save_report(report)

    data = json.loads((tmp_path / "benchmark_bench-001.json").read_text())
    assert data["avg_specialist_quality"] == 0.8
    assert data["publish_rate_specialist"] == 0.25
    assert data["results"][0]["published_specialist_substems"] == ["lead_vocals"]
    assert data["results"][0]["pipeline_mode"] == "local_plus_mvsep_experimental"
    assert (tmp_path / "benchmark_bench-001.md").exists()


def test_compare_benchmarks_reports_specialist_deltas(tmp_path: Path) -> None:
    current = tmp_path / "current.json"
    previous = tmp_path / "previous.json"
    current.write_text(json.dumps({
        "benchmark_id": "current",
        "success_rate": 1.0,
        "avg_broad_quality": 0.9,
        "avg_derived_quality": 0.7,
        "avg_specialist_quality": 0.8,
        "publish_rate_broad": 1.0,
        "publish_rate_derived": 0.6,
        "publish_rate_specialist": 0.3,
    }))
    previous.write_text(json.dumps({
        "benchmark_id": "previous",
        "success_rate": 0.9,
        "avg_broad_quality": 0.85,
        "avg_derived_quality": 0.65,
        "avg_specialist_quality": 0.2,
        "publish_rate_broad": 0.95,
        "publish_rate_derived": 0.55,
        "publish_rate_specialist": 0.1,
    }))

    comparison = compare_benchmarks(current, previous)

    assert comparison["metrics"]["avg_specialist_quality"]["delta"] == pytest.approx(0.6)
    assert comparison["metrics"]["publish_rate_specialist"]["delta"] == pytest.approx(0.2)


def test_benchmark_surfaces_job_error_when_manifest_is_missing(monkeypatch, tmp_path: Path) -> None:
    runner = BenchmarkRunner([], tmp_path)

    monkeypatch.setattr(
        "splitter.benchmark.create_job",
        lambda name, file_bytes, profile="quality": {"job_id": "fixture-job"},
    )
    monkeypatch.setattr("splitter.benchmark.run_job", lambda job_id: None)
    monkeypatch.setattr(
        "splitter.benchmark.get_job_status",
        lambda job_id: {"status": "error", "error": "fixture demucs failure"},
    )
    monkeypatch.setattr("splitter.benchmark.get_manifest", lambda job_id: None)

    song_path = tmp_path / "fixture.wav"
    song_path.write_bytes(b"fixture")
    result = runner._run_single_song(
        BenchmarkSong(name="fixture", path=song_path, difficulty="easy"),
        "quality",
    )

    assert result.success is False
    assert result.error_message == "fixture demucs failure"


def test_benchmark_publish_rate_broad_counts_only_core_stems(tmp_path: Path) -> None:
    runner = BenchmarkRunner([], tmp_path)
    report = BenchmarkReport(
        benchmark_id="bench-core",
        created_at="2026-03-24T00:00:00Z",
        corpus_size=1,
    )
    result = BenchmarkResult(
        song_name="fixture",
        difficulty="easy",
        success=True,
        published_broad_stems=["vocals", "drums", "bass", "other", "instrumental", "guitar"],
    )

    runner._calculate_aggregates(report, [result])

    assert report.publish_rate_broad == pytest.approx(1.0)

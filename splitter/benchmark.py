"""Benchmark and evaluation layer for Phase 4.

Provides tools for:
- Running the full quality pipeline on a curated song corpus
- Recording quality metrics, timings, and publish rates
- Generating benchmark reports with per-stem-family averages
- Regression checking across changes
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PUBLISH_THRESHOLDS, QUALITY_8_SPECIALIST_STEMS
from .jobs import create_job, get_job_status, get_manifest, run_job
from .util import ensure_dir

CORE_BROAD_BENCHMARK_STEMS = {"vocals", "drums", "bass", "other", "instrumental"}


@dataclass
class BenchmarkSong:
    """A single song in the benchmark corpus."""
    name: str
    path: Path
    difficulty: str  # "easy", "mixed", "hard", "failure_cases"
    genre: str | None = None
    bpm: float | None = None
    duration: float | None = None
    notes: str = ""


@dataclass
class BenchmarkResult:
    """Results from running benchmark on a single song."""
    song_name: str
    difficulty: str
    success: bool
    error_message: str | None = None
    
    # Published stems
    published_broad_stems: list[str] = field(default_factory=list)
    published_derived_stems: list[str] = field(default_factory=list)
    published_specialist_substems: list[str] = field(default_factory=list)
    published_midi: list[str] = field(default_factory=list)
    
    # Rejected candidates
    rejected_extended: list[str] = field(default_factory=list)
    rejected_derived: list[str] = field(default_factory=list)
    rejected_specialist: list[str] = field(default_factory=list)
    
    # Quality scores (averaged per family)
    avg_broad_quality: float = 0.0
    avg_derived_quality: float = 0.0
    avg_specialist_quality: float = 0.0
    
    # Timing
    total_duration_seconds: float = 0.0
    broad_split_duration: float = 0.0
    derived_split_duration: float = 0.0
    midi_duration: float = 0.0
    
    # Metadata
    pipeline_mode: str = "unknown"
    remote_adapter_status: str = "not_requested"
    manifest: dict[str, Any] | None = None


@dataclass
class BenchmarkReport:
    """Complete benchmark report across the corpus."""
    benchmark_id: str
    created_at: str
    corpus_size: int
    evidence_level: str = "internal_heuristic_not_ground_truth"
    release_claim_eligible: bool = False
    total_duration_seconds: float = 0.0
    
    # Per-difficulty breakdown
    easy_results: list[BenchmarkResult] = field(default_factory=list)
    mixed_results: list[BenchmarkResult] = field(default_factory=list)
    hard_results: list[BenchmarkResult] = field(default_factory=list)
    failure_case_results: list[BenchmarkResult] = field(default_factory=list)
    
    # Aggregated metrics
    success_rate: float = 0.0
    avg_broad_quality: float = 0.0
    avg_derived_quality: float = 0.0
    avg_specialist_quality: float = 0.0
    publish_rate_broad: float = 0.0
    publish_rate_derived: float = 0.0
    publish_rate_specialist: float = 0.0
    
    # Per-stem-family averages
    stem_family_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    
    # Failure analysis
    failure_reasons: dict[str, int] = field(default_factory=dict)
    
    # Comparison to previous benchmark (if available)
    previous_benchmark_id: str | None = None
    quality_delta: float | None = None


class BenchmarkRunner:
    """Runs benchmark evaluation on a song corpus."""
    
    def __init__(self, corpus: list[BenchmarkSong], output_dir: Path):
        self.corpus = corpus
        self.output_dir = ensure_dir(output_dir)
        self.results_dir = ensure_dir(output_dir / "results")
        
    def run(self, benchmark_id: str, profile: str = "quality") -> BenchmarkReport:
        """Run full benchmark on all songs in the corpus."""
        report = BenchmarkReport(
            benchmark_id=benchmark_id,
            created_at=datetime.utcnow().isoformat() + "Z",
            corpus_size=len(self.corpus),
        )
        
        all_results: list[BenchmarkResult] = []
        start_time = time.time()
        
        for song in self.corpus:
            print(f"Benchmarking: {song.name} ({song.difficulty})")
            result = self._run_single_song(song, profile)
            all_results.append(result)
            
            # Categorize by difficulty
            if song.difficulty == "easy":
                report.easy_results.append(result)
            elif song.difficulty == "mixed":
                report.mixed_results.append(result)
            elif song.difficulty == "hard":
                report.hard_results.append(result)
            else:
                report.failure_case_results.append(result)
        
        report.total_duration_seconds = time.time() - start_time
        
        # Calculate aggregated metrics
        self._calculate_aggregates(report, all_results)
        
        # Save report
        self._save_report(report)
        
        return report
    
    def _run_single_song(self, song: BenchmarkSong, profile: str) -> BenchmarkResult:
        """Run benchmark on a single song."""
        result = BenchmarkResult(
            song_name=song.name,
            difficulty=song.difficulty,
            success=False,
        )
        
        try:
            # Create and run job
            job_start = time.time()
            audio_bytes = song.path.read_bytes()
            status = create_job(song.path.name, audio_bytes, profile=profile)
            job_id = str(status["job_id"])
            
            run_job(job_id)
            
            # Get results
            status = get_job_status(job_id)
            manifest = get_manifest(job_id)
            
            if not manifest:
                if status and status.get("status") == "error" and status.get("error"):
                    result.error_message = str(status["error"])
                else:
                    result.error_message = "No manifest generated"
                return result
            
            result.manifest = manifest
            result.success = True
            result.pipeline_mode = str(manifest.get("pipeline_mode", "unknown"))
            result.remote_adapter_status = str(manifest.get("remote_adapter_status", "not_requested"))

            # Extract published stems
            result.published_broad_stems = list(manifest.get("published_broad_stems", {}).keys())
            result.published_derived_stems = list(manifest.get("published_derived_stems", {}).keys())
            result.published_specialist_substems = list(manifest.get("published_specialist_substems", {}).keys())
            result.published_midi = list(manifest.get("midi_exports", {}).keys())
            
            # Extract rejected candidates
            rejected = manifest.get("rejected_candidates", {})
            result.rejected_extended = list(rejected.get("extended_stems", {}).keys())
            result.rejected_derived = list(rejected.get("derived_stems", {}).keys())
            result.rejected_specialist = list(rejected.get("specialist_substems", {}).keys())
            
            # Calculate average quality scores
            broad_stems = manifest.get("published_broad_stems", {})
            if broad_stems:
                scores = [
                    stem.get("quality_score", 0.0)
                    for stem in broad_stems.values()
                ]
                result.avg_broad_quality = sum(scores) / len(scores) if scores else 0.0
            
            derived_stems = manifest.get("published_derived_stems", {})
            if derived_stems:
                scores = [
                    stem.get("quality_score", 0.0)
                    for stem in derived_stems.values()
                ]
                result.avg_derived_quality = sum(scores) / len(scores) if scores else 0.0

            specialist_stems = manifest.get("published_specialist_substems", {})
            if specialist_stems:
                scores = [
                    stem.get("quality_score", 0.0)
                    for stem in specialist_stems.values()
                ]
                result.avg_specialist_quality = sum(scores) / len(scores) if scores else 0.0
            
            # Timing
            result.total_duration_seconds = time.time() - job_start
            
        except Exception as e:
            result.error_message = str(e)
        
        return result
    
    def _calculate_aggregates(
        self,
        report: BenchmarkReport,
        all_results: list[BenchmarkResult],
    ) -> None:
        """Calculate aggregated metrics for the report."""
        successful = [r for r in all_results if r.success]
        
        # Success rate
        report.success_rate = len(successful) / len(all_results) if all_results else 0.0
        
        # Average quality scores
        if successful:
            report.avg_broad_quality = sum(
                r.avg_broad_quality for r in successful
            ) / len(successful)
            report.avg_derived_quality = sum(
                r.avg_derived_quality for r in successful
            ) / len(successful)
            report.avg_specialist_quality = sum(
                r.avg_specialist_quality for r in successful
            ) / len(successful)

        # Publish rates
        total_possible_broad = len(successful) * len(CORE_BROAD_BENCHMARK_STEMS)
        total_possible_derived = len(successful) * 7  # 7 derived stems
        total_possible_specialist = len(successful) * len(QUALITY_8_SPECIALIST_STEMS)
        actual_published_broad = sum(
            len([stem for stem in r.published_broad_stems if stem in CORE_BROAD_BENCHMARK_STEMS])
            for r in successful
        )
        actual_published_derived = sum(len(r.published_derived_stems) for r in successful)
        actual_published_specialist = sum(len(r.published_specialist_substems) for r in successful)
        
        report.publish_rate_broad = actual_published_broad / total_possible_broad if total_possible_broad else 0.0
        report.publish_rate_derived = actual_published_derived / total_possible_derived if total_possible_derived else 0.0
        report.publish_rate_specialist = actual_published_specialist / total_possible_specialist if total_possible_specialist else 0.0

        # Stem family metrics
        stem_families: dict[str, list[float]] = {}
        for r in successful:
            if r.manifest:
                for group_name in ("published_broad_stems", "published_derived_stems", "published_specialist_substems"):
                    for stem_name, stem_data in r.manifest.get(group_name, {}).items():
                        family = stem_data.get("family", stem_name)
                        if family not in stem_families:
                            stem_families[family] = []
                        stem_families[family].append(stem_data.get("quality_score", 0.0))
        
        report.stem_family_metrics = {
            family: {
                "avg_quality": sum(scores) / len(scores) if scores else 0.0,
                "count": len(scores),
            }
            for family, scores in stem_families.items()
        }
        
        # Failure analysis
        for r in all_results:
            if not r.success and r.error_message:
                # Categorize error
                if "manifest" in r.error_message.lower():
                    key = "manifest_generation_failure"
                elif "demucs" in r.error_message.lower():
                    key = "demucs_error"
                else:
                    key = "other_error"
                report.failure_reasons[key] = report.failure_reasons.get(key, 0) + 1
    
    def _save_report(self, report: BenchmarkReport) -> None:
        """Save benchmark report to disk."""
        report_path = self.output_dir / f"benchmark_{report.benchmark_id}.json"
        
        # Convert to serializable format
        data = {
            "benchmark_id": report.benchmark_id,
            "created_at": report.created_at,
            "corpus_size": report.corpus_size,
            "evidence_level": report.evidence_level,
            "release_claim_eligible": report.release_claim_eligible,
            "total_duration_seconds": report.total_duration_seconds,
            "success_rate": report.success_rate,
            "avg_broad_quality": report.avg_broad_quality,
            "avg_derived_quality": report.avg_derived_quality,
            "avg_specialist_quality": report.avg_specialist_quality,
            "publish_rate_broad": report.publish_rate_broad,
            "publish_rate_derived": report.publish_rate_derived,
            "publish_rate_specialist": report.publish_rate_specialist,
            "stem_family_metrics": report.stem_family_metrics,
            "failure_reasons": report.failure_reasons,
            "previous_benchmark_id": report.previous_benchmark_id,
            "quality_delta": report.quality_delta,
            "results": [
                {
                    "song_name": r.song_name,
                    "difficulty": r.difficulty,
                    "success": r.success,
                    "error_message": r.error_message,
                    "published_broad_stems": r.published_broad_stems,
                    "published_derived_stems": r.published_derived_stems,
                    "published_specialist_substems": r.published_specialist_substems,
                    "published_midi": r.published_midi,
                    "rejected_extended": r.rejected_extended,
                    "rejected_derived": r.rejected_derived,
                    "rejected_specialist": r.rejected_specialist,
                    "avg_broad_quality": r.avg_broad_quality,
                    "avg_derived_quality": r.avg_derived_quality,
                    "avg_specialist_quality": r.avg_specialist_quality,
                    "total_duration_seconds": r.total_duration_seconds,
                    "pipeline_mode": r.pipeline_mode,
                    "remote_adapter_status": r.remote_adapter_status,
                }
                for r in (
                    report.easy_results +
                    report.mixed_results +
                    report.hard_results +
                    report.failure_case_results
                )
            ],
        }
        
        report_path.write_text(json.dumps(data, indent=2, sort_keys=True))
        summary_path = self.output_dir / f"benchmark_{report.benchmark_id}.md"
        summary_path.write_text(
            "\n".join(
                [
                    f"# Benchmark {report.benchmark_id}",
                    "",
                    "This report uses internal heuristic scores for regression checks.",
                    "It is not a ground-truth quality benchmark or a commercial claim.",
                    "",
                    f"- Evidence level: {report.evidence_level}",
                    f"- Release claim eligible: {report.release_claim_eligible}",
                    f"- Corpus size: {report.corpus_size}",
                    f"- Success rate: {report.success_rate:.3f}",
                    f"- Avg broad quality: {report.avg_broad_quality:.3f}",
                    f"- Avg derived quality: {report.avg_derived_quality:.3f}",
                    f"- Avg specialist quality: {report.avg_specialist_quality:.3f}",
                    f"- Publish rate broad: {report.publish_rate_broad:.3f}",
                    f"- Publish rate derived: {report.publish_rate_derived:.3f}",
                    f"- Publish rate specialist: {report.publish_rate_specialist:.3f}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )


def compare_benchmarks(
    current_path: Path,
    previous_path: Path,
) -> dict[str, Any]:
    """Compare two benchmark reports."""
    current_data = json.loads(current_path.read_text())
    previous_data = json.loads(previous_path.read_text())
    
    comparison = {
        "current_benchmark_id": current_data["benchmark_id"],
        "previous_benchmark_id": previous_data["benchmark_id"],
        "metrics": {
            "success_rate": {
                "current": current_data["success_rate"],
                "previous": previous_data["success_rate"],
                "delta": current_data["success_rate"] - previous_data["success_rate"],
            },
            "avg_broad_quality": {
                "current": current_data["avg_broad_quality"],
                "previous": previous_data["avg_broad_quality"],
                "delta": current_data["avg_broad_quality"] - previous_data["avg_broad_quality"],
            },
            "avg_derived_quality": {
                "current": current_data["avg_derived_quality"],
                "previous": previous_data["avg_derived_quality"],
                "delta": current_data["avg_derived_quality"] - previous_data["avg_derived_quality"],
            },
            "avg_specialist_quality": {
                "current": current_data.get("avg_specialist_quality", 0.0),
                "previous": previous_data.get("avg_specialist_quality", 0.0),
                "delta": current_data.get("avg_specialist_quality", 0.0) - previous_data.get("avg_specialist_quality", 0.0),
            },
            "publish_rate_broad": {
                "current": current_data["publish_rate_broad"],
                "previous": previous_data["publish_rate_broad"],
                "delta": current_data["publish_rate_broad"] - previous_data["publish_rate_broad"],
            },
            "publish_rate_derived": {
                "current": current_data["publish_rate_derived"],
                "previous": previous_data["publish_rate_derived"],
                "delta": current_data["publish_rate_derived"] - previous_data["publish_rate_derived"],
            },
            "publish_rate_specialist": {
                "current": current_data.get("publish_rate_specialist", 0.0),
                "previous": previous_data.get("publish_rate_specialist", 0.0),
                "delta": current_data.get("publish_rate_specialist", 0.0) - previous_data.get("publish_rate_specialist", 0.0),
            },
        },
    }
    
    return comparison

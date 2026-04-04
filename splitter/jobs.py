from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any
import shutil
import subprocess as sp
import uuid

from .analysis import (
    create_tempo_locked_copy,
    detect_sections,
    detect_tempo_and_beats,
    estimate_key,
    write_chord_guide_midi,
    write_sections_analysis,
    write_tempo_key_analysis,
)
from .config import DEFAULT_PROFILE, JOBS_DIR, PROFILE_CONFIG, PUBLISH_THRESHOLDS
from .packaging import package_directories, write_manifest
from .separation import build_broad_stems, build_derived_stems
from .specialist import (
    build_drum_substems_mvsep,
    build_instrument_substems_mvsep,
    build_local_derived_candidates,
    build_vocal_substems_mvsep,
    local_specialist_runtime_status,
    mvsep_runtime_status,
)
from .scoring import score_audio_candidate, validate_midi_candidate
from .util import dump_json, ensure_dir, file_sha256, load_json, now_iso

try:
    from audio2midi.librosa_pitch_detector import Normal_Pitch_Det
except Exception:  # pragma: no cover - dependency can be absent during import
    Normal_Pitch_Det = None


EXECUTOR = ThreadPoolExecutor(max_workers=1)
JOBS_LOCK = Lock()
JOB_FUTURES: dict[str, object] = {}


def _job_root(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _status_path(job_root: Path) -> Path:
    return job_root / "status.json"


def _update_status(job_root: Path, **fields: Any) -> dict[str, Any]:
    path = _status_path(job_root)
    current = load_json(path) if path.exists() else {}
    current.update(fields)
    current["updated_at"] = now_iso()
    dump_json(path, current)
    return current


def _run_audio2midi(input_path: Path, output_path: Path) -> bool:
    if Normal_Pitch_Det is None:
        return False
    ensure_dir(output_path.parent)
    try:
        detector = Normal_Pitch_Det()
        detector.predict(str(input_path), output_file=str(output_path))
    except Exception:
        return False
    return output_path.exists()


def create_job(upload_name: str, file_bytes: bytes, *, profile: str | None = None) -> dict[str, Any]:
    resolved_profile = profile if profile in PROFILE_CONFIG else DEFAULT_PROFILE
    job_id = uuid.uuid4().hex
    ensure_dir(JOBS_DIR)
    job_root = ensure_dir(_job_root(job_id))
    input_dir = ensure_dir(job_root / "input")
    upload_path = input_dir / upload_name
    upload_path.write_bytes(file_bytes)

    status = {
        "job_id": job_id,
        "profile": resolved_profile,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "input_name": upload_name,
        "input_path": str(upload_path.resolve()),
    }
    dump_json(_status_path(job_root), status)
    return status


def submit_job(job_id: str) -> None:
    with JOBS_LOCK:
        JOB_FUTURES[job_id] = EXECUTOR.submit(run_job, job_id)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    path = _status_path(_job_root(job_id))
    if not path.exists():
        return None
    return load_json(path)


def get_manifest(job_id: str) -> dict[str, Any] | None:
    manifest_path = _job_root(job_id) / "analysis" / "manifest.json"
    if not manifest_path.exists():
        return None
    return load_json(manifest_path)


def _collect_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for item in sorted(root.glob("**/*")):
            if item.is_file():
                files.append(item)
    return files


def _audio_duration(audio_path: Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(audio_path))
        return float(info.frames / max(info.samplerate, 1))
    except Exception:
        return 0.0


def _publish_audio_candidates(
    candidates: dict[str, dict[str, object]],
    *,
    threshold: float,
    publish_dir: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    published: dict[str, dict[str, object]] = {}
    rejected: dict[str, dict[str, object]] = {}
    if not candidates:
        return published, rejected

    ensure_dir(publish_dir)
    for stem_name, candidate in candidates.items():
        scored = score_audio_candidate(candidate, threshold)
        if scored["publish_status"] == "published":
            target = publish_dir / f"{stem_name}.wav"
            shutil.copy2(Path(str(scored["path"])), target)
            published[stem_name] = {
                **scored,
                "path": str(target.resolve()),
                "confidence": scored["quality_score"],
            }
        else:
            rejected[stem_name] = scored
    return published, rejected


def _publish_midi_candidate(
    candidate_path: Path,
    *,
    name: str,
    source_name: str,
    source_path: Path,
    audio_duration: float,
    publish_dir: Path,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    scored = validate_midi_candidate(
        candidate_path,
        source_name=source_name,
        source_path=source_path,
        audio_duration=audio_duration,
        threshold=PUBLISH_THRESHOLDS["midi"],
    )
    if scored["publish_status"] != "published":
        return None, scored

    ensure_dir(publish_dir)
    target = publish_dir / f"{name}.mid"
    shutil.copy2(candidate_path, target)
    return {**scored, "path": str(target.resolve())}, None


def _candidate_winner_entry(
    payload: dict[str, object],
    *,
    published_group: str,
    fallback_used: bool = False,
) -> dict[str, object]:
    return {
        "published_group": published_group,
        "winning_source": payload.get("source_model", "unknown"),
        "quality_score": payload.get("quality_score"),
        "fallback_used": fallback_used,
    }


def _collect_specialist_candidates(
    broad_outputs: dict[str, dict[str, object]],
    job_root: Path,
) -> tuple[dict[str, dict[str, object]], list[str], str, str | None]:
    available, reason = mvsep_runtime_status()
    if not available:
        return {}, [reason] if reason else [], "skipped", reason

    candidates: dict[str, dict[str, object]] = {}
    errors: list[str] = []

    if "vocals" in broad_outputs:
        outputs, branch_errors = build_vocal_substems_mvsep(
            Path(str(broad_outputs["vocals"]["path"])),
            job_root,
        )
        candidates.update(outputs)
        errors.extend(branch_errors)

    if "drums" in broad_outputs:
        outputs, branch_errors = build_drum_substems_mvsep(
            Path(str(broad_outputs["drums"]["path"])),
            job_root,
        )
        candidates.update(outputs)
        errors.extend(branch_errors)

    if "other" in broad_outputs:
        outputs, branch_errors = build_instrument_substems_mvsep(
            Path(str(broad_outputs["other"]["path"])),
            job_root,
        )
        candidates.update(outputs)
        errors.extend(branch_errors)

    if candidates and errors:
        return candidates, errors, "partial", ";".join(errors)
    if candidates:
        return candidates, [], "used", None
    if errors:
        return {}, errors, "failed", ";".join(errors)
    return {}, [], "skipped", "mvsep_no_outputs"


def run_job(job_id: str) -> None:
    job_root = _job_root(job_id)
    status = get_job_status(job_id)
    if not status:
        return

    input_path = Path(str(status["input_path"]))
    profile = str(status["profile"])
    profile_cfg = PROFILE_CONFIG[profile]
    models_used = list(profile_cfg["run_models"])

    try:
        _update_status(job_root, status="running", stage="broad_split")
        broad_outputs, extended_candidates, run_info, missing = build_broad_stems(
            input_path, job_root, profile, profile_cfg["run_models"]
        )
        rejected_candidates: dict[str, dict[str, dict[str, object]]] = {
            "extended_stems": {},
            "derived_stems": {},
            "specialist_substems": {},
            "midi": {},
        }
        missing_features = list(missing)
        candidate_winners: dict[str, dict[str, object]] = {}
        remote_adapter_status = "not_requested"
        remote_adapter_reason: str | None = None
        pipeline_mode = "local_standard" if profile == "preview" else "local_fallback"

        if profile_cfg["publish_extended"]:
            published_extended, rejected_extended = _publish_audio_candidates(
                extended_candidates,
                threshold=PUBLISH_THRESHOLDS["extended_stems"],
                publish_dir=job_root / "broad_stems",
            )
            broad_outputs.update(published_extended)
            rejected_candidates["extended_stems"] = rejected_extended
            for stem_name, payload in published_extended.items():
                candidate_winners[stem_name] = _candidate_winner_entry(
                    payload,
                    published_group="broad_stems",
                    fallback_used=False,
                )

        derived_outputs: dict[str, dict[str, object]] = {}
        if profile_cfg["publish_derived"]:
            _update_status(job_root, stage="derived_split")
            heuristic_candidates = build_derived_stems(
                broad_outputs,
                job_root,
                use_specialist=False,
            )
            derived_candidates = dict(heuristic_candidates)
            local_specialist_available, local_specialist_reason = local_specialist_runtime_status()
            if profile_cfg.get("prefer_local_specialists") and local_specialist_available:
                local_candidates, local_errors = build_local_derived_candidates(broad_outputs, job_root)
                derived_candidates.update(local_candidates)
                pipeline_mode = "local_specialist"
                for error in local_errors:
                    if error not in missing_features:
                        missing_features.append(error)
            elif profile_cfg.get("prefer_local_specialists") and local_specialist_reason:
                if local_specialist_reason not in missing_features:
                    missing_features.append(local_specialist_reason)
            derived_outputs, rejected_derived = _publish_audio_candidates(
                derived_candidates,
                threshold=PUBLISH_THRESHOLDS["derived_stems"],
                publish_dir=job_root / "derived_stems",
            )
            rejected_candidates["derived_stems"] = rejected_derived
            for stem_name, payload in derived_outputs.items():
                candidate_winners[stem_name] = _candidate_winner_entry(
                    payload,
                    published_group="derived_stems",
                    fallback_used=str(payload.get("source_model", "")).startswith("heuristic:"),
                )
                source_model = str(payload.get("source_model", ""))
                if source_model.startswith("local_specialist:"):
                    model_name = source_model.split(":", 1)[1]
                    if model_name not in models_used:
                        models_used.append(model_name)

        specialist_outputs: dict[str, dict[str, object]] = {}
        if profile_cfg.get("use_mvsep"):
            _update_status(job_root, stage="specialist_substems")
            specialist_candidates, specialist_errors, remote_adapter_status, remote_adapter_reason = _collect_specialist_candidates(
                broad_outputs,
                job_root,
            )
            specialist_outputs, rejected_specialist = _publish_audio_candidates(
                specialist_candidates,
                threshold=PUBLISH_THRESHOLDS["specialist_substems"],
                publish_dir=job_root / "specialist_substems",
            )
            rejected_candidates["specialist_substems"] = rejected_specialist
            if specialist_outputs:
                pipeline_mode = "local_plus_mvsep_experimental"
            for stem_name, payload in specialist_outputs.items():
                candidate_winners[stem_name] = _candidate_winner_entry(
                    payload,
                    published_group="specialist_substems",
                    fallback_used=False,
                )
            if specialist_errors:
                for error in specialist_errors:
                    if error not in missing_features:
                        missing_features.append(error)
            if remote_adapter_status in {"skipped", "failed"} and remote_adapter_reason and remote_adapter_reason not in missing_features:
                missing_features.append(remote_adapter_reason)
        else:
            specialist_outputs = {}

        analysis: dict[str, Any] = {}
        tempo_locked: dict[str, str] = {}
        analysis_exports: dict[str, str] = {}
        if profile_cfg["tempo_lock"] and broad_outputs:
            analysis = detect_tempo_and_beats(Path(str(broad_outputs["instrumental"]["path"])))
            analysis.update(estimate_key(Path(str(broad_outputs["instrumental"]["path"]))))
            analysis_dir = ensure_dir(job_root / "analysis")
            tempo_key_path = write_tempo_key_analysis(analysis_dir / "tempo_key.json", analysis)
            analysis_exports["tempo_key"] = str(tempo_key_path.resolve())
            sections = detect_sections(
                Path(str(broad_outputs["instrumental"]["path"])),
                analysis.get("beat_times"),
            )
            sections_path = write_sections_analysis(analysis_dir / "sections.json", sections)
            analysis_exports["sections"] = str(sections_path.resolve())
            tempo_dir = ensure_dir(job_root / "tempo_locked_wavs")
            for stem_name, payload in {**broad_outputs, **derived_outputs, **specialist_outputs}.items():
                source = Path(str(payload["path"]))
                target = tempo_dir / f"{stem_name}.wav"
                create_tempo_locked_copy(
                    source,
                    target,
                    float(analysis.get("first_beat_seconds", 0.0)),
                )
                tempo_locked[stem_name] = str(target.resolve())

        midi_exports: dict[str, dict[str, object]] = {}
        if profile_cfg["generate_midi"]:
            _update_status(job_root, stage="midi")
            midi_dir = ensure_dir(job_root / "midi")
            midi_candidate_dir = ensure_dir(job_root / "midi_candidates")
            melody_sources = []
            if profile_cfg.get("use_mvsep"):
                melody_sources.append(("lead_vocals", specialist_outputs.get("lead_vocals")))
            melody_sources.extend(
                [
                    ("vocals", broad_outputs.get("vocals")),
                    ("keys_synth", specialist_outputs.get("keys_synth") or derived_outputs.get("keys_synth")),
                    ("piano", specialist_outputs.get("piano") or broad_outputs.get("piano")),
                ]
            )
            for source_name, payload in melody_sources:
                if not payload:
                    continue
                candidate_target = midi_candidate_dir / "melody.mid"
                if not _run_audio2midi(Path(str(payload["path"])), candidate_target):
                    continue
                published_midi, rejected_midi = _publish_midi_candidate(
                    candidate_target,
                    name="melody",
                    source_name=source_name,
                    source_path=Path(str(payload["path"])),
                    audio_duration=_audio_duration(Path(str(payload["path"]))),
                    publish_dir=midi_dir,
                )
                if published_midi:
                    midi_exports["melody"] = published_midi
                    candidate_winners["midi:melody"] = {
                        "published_group": "midi",
                        "winning_source": source_name,
                        "quality_score": published_midi.get("quality_score"),
                        "fallback_used": False,
                    }
                    break
                if rejected_midi:
                    rejected_candidates["midi"][f"melody_from_{source_name}"] = rejected_midi

            bass_source = broad_outputs.get("bass")
            if bass_source:
                bass_candidate = midi_candidate_dir / "bass.mid"
                if _run_audio2midi(Path(str(bass_source["path"])), bass_candidate):
                    published_midi, rejected_midi = _publish_midi_candidate(
                        bass_candidate,
                        name="bass",
                        source_name="bass",
                        source_path=Path(str(bass_source["path"])),
                        audio_duration=_audio_duration(Path(str(bass_source["path"]))),
                        publish_dir=midi_dir,
                    )
                    if published_midi:
                        midi_exports["bass"] = published_midi
                        candidate_winners["midi:bass"] = {
                            "published_group": "midi",
                            "winning_source": "bass",
                            "quality_score": published_midi.get("quality_score"),
                            "fallback_used": False,
                        }
                    elif rejected_midi:
                        rejected_candidates["midi"]["bass"] = rejected_midi

            chord_source = specialist_outputs.get("keys_synth") or derived_outputs.get("keys_synth") or broad_outputs.get("other")
            if chord_source:
                chord_target = midi_candidate_dir / "chords_guide.mid"
                try:
                    write_chord_guide_midi(
                        Path(str(chord_source["path"])),
                        chord_target,
                        analysis.get("beat_times"),
                    )
                except Exception:
                    pass
                else:
                    chord_source_name = (
                        "keys_synth"
                        if specialist_outputs.get("keys_synth") or derived_outputs.get("keys_synth")
                        else "other"
                    )
                    published_midi, rejected_midi = _publish_midi_candidate(
                        chord_target,
                        name="chords_guide",
                        source_name=chord_source_name,
                        source_path=Path(str(chord_source["path"])),
                        audio_duration=_audio_duration(Path(str(chord_source["path"]))),
                        publish_dir=midi_dir,
                    )
                    if published_midi:
                        midi_exports["chords_guide"] = published_midi
                        candidate_winners["midi:chords_guide"] = {
                            "published_group": "midi",
                            "winning_source": chord_source_name,
                            "quality_score": published_midi.get("quality_score"),
                            "fallback_used": False,
                        }
                    elif rejected_midi:
                        rejected_candidates["midi"]["chords_guide"] = rejected_midi

        _update_status(job_root, stage="package")
        manifest = {
            "job_id": job_id,
            "profile": profile,
            "status": "completed",
            "input_name": status["input_name"],
            "input_path": str(input_path.resolve()),
            "input_hash": file_sha256(input_path),
            "runtime_env": {
                "engine": "local-cpu",
                "created_at": status["created_at"],
            },
            "models_used": models_used + (["mvsep"] if specialist_outputs else []),
            "runs_root": run_info["runs_root"],
            "published_broad_stems": broad_outputs,
            "published_derived_stems": derived_outputs,
            "published_specialist_substems": specialist_outputs,
            "tempo_locked_exports": tempo_locked,
            "midi_exports": midi_exports,
            "analysis": analysis,
            "analysis_exports": analysis_exports,
            "pipeline_mode": pipeline_mode,
            "candidate_winners": candidate_winners,
            "rejected_candidates": rejected_candidates,
            "missing_features": missing_features,
            "remote_adapter_status": remote_adapter_status,
            "remote_adapter_reason": remote_adapter_reason,
            "timings": {"completed_at": now_iso()},
        }
        manifest_path = write_manifest(job_root, manifest)

        package_groups = {
            "stems": _collect_files(job_root / "broad_stems", job_root / "derived_stems", job_root / "specialist_substems"),
            "midi": _collect_files(job_root / "midi"),
            "wav_plus_midi": _collect_files(
                job_root / "broad_stems",
                job_root / "derived_stems",
                job_root / "specialist_substems",
                job_root / "midi",
                job_root / "tempo_locked_wavs",
                job_root / "analysis",
            ),
        }
        bundles = package_directories(job_root, package_groups)
        manifest["bundle_exports"] = bundles
        write_manifest(job_root, manifest)
        _update_status(
            job_root,
            status="completed",
            stage="done",
            manifest_path=str(manifest_path.resolve()),
            bundles=bundles,
        )
    except sp.CalledProcessError as exc:
        _update_status(job_root, status="error", stage="failed", error=str(exc))
    except Exception as exc:  # pragma: no cover - integration path
        _update_status(job_root, status="error", stage="failed", error=str(exc))

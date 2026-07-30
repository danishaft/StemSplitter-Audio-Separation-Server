from __future__ import annotations

import argparse
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf


EXPECTED_STEMS = (
    "vocals",
    "instrumental",
    "drums",
    "bass",
    "guitar",
    "piano",
    "kick",
    "snare",
)
RECONSTRUCTION_PARTS = ("vocals", "drums", "bass", "other")


def _db(value: float) -> float | None:
    if value <= 0:
        return None
    return round(20.0 * math.log10(value), 3)


def _audio_metrics(path: Path, source_info: sf.SoundFile) -> dict[str, object]:
    info = sf.info(path)
    audio, _ = sf.read(path, always_2d=True, dtype="float32")
    finite = bool(np.isfinite(audio).all())
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))) if audio.size else 0.0
    silent_frame_ratio = float(np.mean(np.max(np.abs(audio), axis=1) < 1e-5)) if len(audio) else 1.0
    clipped_samples = int(np.count_nonzero(np.abs(audio) >= 0.999999))
    duration_delta = abs(float(info.duration) - float(source_info.duration))
    checks = {
        "finite": finite,
        "has_audio_frames": bool(info.frames),
        "sample_rate_matches": info.samplerate == source_info.samplerate,
        "channels_match": info.channels == source_info.channels,
        "duration_matches": duration_delta <= 0.05,
        "no_clipped_samples": clipped_samples == 0,
    }
    return {
        "path": str(path.resolve()),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "duration_seconds": round(float(info.duration), 6),
        "duration_delta_seconds": round(duration_delta, 6),
        "format": info.format,
        "subtype": info.subtype,
        "peak_dbfs": _db(peak),
        "rms_dbfs": _db(rms),
        "signal_presence": "present" if rms > 1e-4 else "absent_or_below_detection_floor",
        "silent_frame_ratio": round(silent_frame_ratio, 6),
        "clipped_samples": clipped_samples,
        "checks": checks,
        "technical_pass": all(checks.values()),
    }


def _reconstruction(job_root: Path, source_path: Path) -> dict[str, object]:
    paths = {
        "vocals": job_root / "candidate_stems" / "broad_stems" / "vocals.wav",
        "drums": job_root / "candidate_stems" / "broad_stems" / "drums.wav",
        "bass": job_root / "candidate_stems" / "broad_stems" / "bass.wav",
        "other": job_root / "candidate_stems" / "broad_stems" / "other.wav",
    }
    if not all(path.exists() for path in paths.values()):
        return {"available": False, "technical_pass": False, "reason": "broad_candidate_missing"}

    source, source_rate = sf.read(source_path, always_2d=True, dtype="float32")
    parts = []
    for name in RECONSTRUCTION_PARTS:
        audio, sample_rate = sf.read(paths[name], always_2d=True, dtype="float32")
        if sample_rate != source_rate:
            return {"available": False, "technical_pass": False, "reason": "sample_rate_mismatch"}
        parts.append(audio)
    length = min([len(source), *(len(part) for part in parts)])
    reference = source[:length]
    reconstructed = np.sum([part[:length] for part in parts], axis=0)
    error = reference - reconstructed
    reference_rms = float(np.sqrt(np.mean(np.square(reference, dtype=np.float64))))
    error_rms = float(np.sqrt(np.mean(np.square(error, dtype=np.float64))))
    snr_db = 20.0 * math.log10(reference_rms / max(error_rms, 1e-12))
    return {
        "available": True,
        "parts": list(RECONSTRUCTION_PARTS),
        "snr_db": round(snr_db, 3),
        "error_rms_dbfs": _db(error_rms),
        "error_peak_dbfs": _db(float(np.max(np.abs(error)))),
        "minimum_snr_db": 15.0,
        "technical_pass": snr_db >= 15.0,
        "interpretation": "Consistency check only; this does not measure stem isolation quality.",
    }


def _bundle_check(job_root: Path, manifest: dict[str, object]) -> dict[str, object]:
    main = manifest.get("published_main_stems", {})
    expected_members = {
        str(Path(str(payload["path"])).resolve().relative_to(job_root.resolve()))
        for payload in main.values()
    }
    results: dict[str, object] = {}
    for name, raw_path in manifest.get("bundle_exports", {}).items():
        path = Path(str(raw_path))
        with zipfile.ZipFile(path) as archive:
            members = {item for item in archive.namelist() if item.lower().endswith(".wav")}
        results[name] = {
            "path": str(path.resolve()),
            "wav_members": sorted(members),
            "missing": sorted(expected_members - members),
            "unexpected": sorted(members - expected_members),
            "technical_pass": members == expected_members,
        }
    return results


def run(job_root: Path, output_path: Path) -> dict[str, object]:
    manifest_path = job_root / "analysis" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_path = Path(str(manifest["input_path"]))
    source_info = sf.info(source_path)
    main = manifest.get("published_main_stems", {})
    contract = manifest.get("stem_contract", {})
    contract_checks = {
        "exact_stem_set": set(main) == set(EXPECTED_STEMS),
        "contract_complete": contract.get("status") == "complete",
        "no_missing_stems": not contract.get("missing_stems"),
    }
    stems = {
        stem: _audio_metrics(Path(str(main[stem]["path"])), source_info)
        for stem in EXPECTED_STEMS
        if stem in main
    }
    reconstruction = _reconstruction(job_root, source_path)
    bundles = _bundle_check(job_root, manifest)
    technical_pass = (
        all(contract_checks.values())
        and len(stems) == len(EXPECTED_STEMS)
        and all(item["technical_pass"] for item in stems.values())
        and reconstruction["technical_pass"]
        and bool(bundles)
        and all(item["technical_pass"] for item in bundles.values())
    )
    report = {
        "schema_version": 1,
        "job_id": manifest["job_id"],
        "profile": manifest["profile"],
        "source": {
            "path": str(source_path.resolve()),
            "duration_seconds": round(float(source_info.duration), 6),
            "sample_rate": source_info.samplerate,
            "channels": source_info.channels,
            "subtype": source_info.subtype,
        },
        "contract_checks": contract_checks,
        "stems": stems,
        "reconstruction": reconstruction,
        "bundles": bundles,
        "technical_verdict": "pass" if technical_pass else "fail",
        "perceptual_quality_verdict": "pending_producer_review",
        "limitations": [
            "This song has no isolated ground-truth stems, so SDR, SIR, and SAR cannot be measured.",
            "Passing technical checks does not prove that bleed, warble, or missing musical content is acceptable.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local friend-test technical stem gate.")
    parser.add_argument("job_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = run(args.job_root.resolve(), args.output.resolve())
    print(json.dumps({"job_id": report["job_id"], "technical_verdict": report["technical_verdict"]}))


if __name__ == "__main__":
    main()

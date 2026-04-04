from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

from splitter.config import ALLOWED_EXTENSIONS, JOBS_DIR, MAX_CONTENT_LENGTH
from splitter.jobs import create_job, get_job_status, get_manifest, run_job, submit_job

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _index_path() -> str:
    return os.path.join(os.path.dirname(__file__), "index.html")


def _job_root(job_id: str) -> Path:
    return (JOBS_DIR / job_id).resolve()


def _artifact_payload(job_id: str) -> dict[str, object]:
    manifest = get_manifest(job_id) or {}
    bundles = manifest.get("bundle_exports", {})
    broad = manifest.get("published_broad_stems", {})
    derived = manifest.get("published_derived_stems", {})
    specialist = manifest.get("published_specialist_substems", {})
    tempo_locked = manifest.get("tempo_locked_exports", {})
    midi = manifest.get("midi_exports", {})
    analysis = manifest.get("analysis_exports", {})

    def _make_urls(payload: dict[str, object]) -> dict[str, str]:
        urls: dict[str, str] = {}
        for name, meta in payload.items():
            path = meta["path"] if isinstance(meta, dict) else meta
            rel = Path(str(path)).resolve().relative_to(_job_root(job_id))
            urls[name] = f"/artifacts/{job_id}/{rel.as_posix()}"
        return urls

    def _bundle_urls(payload: dict[str, str]) -> dict[str, str]:
        urls: dict[str, str] = {}
        for name, path in payload.items():
            rel = Path(str(path)).resolve().relative_to(_job_root(job_id))
            urls[name] = f"/artifacts/{job_id}/{rel.as_posix()}"
        return urls

    return {
        "broad_stems": _make_urls(broad),
        "derived_stems": _make_urls(derived),
        "specialist_substems": _make_urls(specialist),
        "tempo_locked_wavs": _make_urls(tempo_locked),
        "midi": _make_urls(midi),
        "analysis": _make_urls(analysis),
        "bundles": _bundle_urls(bundles),
    }


@app.route("/")
def index():
    return send_file(_index_path())


@app.route("/jobs", methods=["POST"])
def create_job_route():
    if "file" not in request.files:
        return jsonify(error="No audio file in request"), 400

    audio_file = request.files["file"]
    if not audio_file.filename:
        return jsonify(error="No file selected"), 400
    if not allowed_file(audio_file.filename):
        return jsonify(error="Invalid format. Use MP3, WAV, FLAC, OGG, or M4A."), 400

    profile = request.form.get("profile", "quality").strip() or "quality"
    status = create_job(audio_file.filename, audio_file.read(), profile=profile)
    submit_job(str(status["job_id"]))
    response = dict(status)
    response["artifacts"] = {}
    return jsonify(response), 202


@app.route("/jobs/<job_id>", methods=["GET"])
def job_status(job_id: str):
    status = get_job_status(job_id)
    if not status:
        return jsonify(error="Job not found"), 404

    response = dict(status)
    if response.get("status") == "completed":
        manifest = get_manifest(job_id) or {}
        response["artifacts"] = _artifact_payload(job_id)
        response["rejected_candidates"] = manifest.get("rejected_candidates", {})
        response["remote_adapter_status"] = manifest.get("remote_adapter_status")
        response["remote_adapter_reason"] = manifest.get("remote_adapter_reason")
    return jsonify(response)


@app.route("/jobs/<job_id>/manifest", methods=["GET"])
def job_manifest(job_id: str):
    manifest = get_manifest(job_id)
    if not manifest:
        return jsonify(error="Manifest not found"), 404
    return jsonify(manifest)


@app.route("/artifacts/<job_id>/<path:artifact_path>", methods=["GET"])
def serve_artifact(job_id: str, artifact_path: str):
    job_root = _job_root(job_id)
    target = (job_root / artifact_path).resolve()
    if not str(target).startswith(str(job_root)) or not target.exists():
        return jsonify(error="Artifact not found"), 404
    mimetype, _ = mimetypes.guess_type(target.name)
    return send_file(target, mimetype=mimetype or "application/octet-stream", as_attachment=True)


@app.route("/separate", methods=["POST"])
def separate_audio_file():
    """
    Compatibility endpoint that preserves the original flat stem response.
    It runs the lightweight preview profile synchronously.
    """

    if "file" not in request.files:
        return jsonify(error="No audio file in request"), 400

    audio_file = request.files["file"]
    if not audio_file.filename:
        return jsonify(error="No file selected"), 400
    if not allowed_file(audio_file.filename):
        return jsonify(error="Invalid format. Use MP3, WAV, FLAC, OGG, or M4A."), 400

    status = create_job(audio_file.filename, audio_file.read(), profile="preview")
    job_id = str(status["job_id"])
    try:
        run_job(job_id)
    except RuntimeError as exc:
        return jsonify(error=f"Separation failed: {exc}"), 500

    manifest = get_manifest(job_id)
    if not manifest:
        return jsonify(error="No manifest was produced"), 500

    broad = manifest.get("published_broad_stems", {})
    stems = {}
    for stem_name, payload in broad.items():
        stem_path = Path(str(payload["path"])).resolve()
        rel = stem_path.relative_to(_job_root(job_id))
        stems[stem_name] = f"/artifacts/{job_id}/{rel.as_posix()}"
    return jsonify(job_id=job_id, stems=stems, manifest=f"/jobs/{job_id}/manifest")


@app.route("/stems/<job_id>/<stem_file>", methods=["GET"])
def serve_stem(job_id: str, stem_file: str):
    stem_name = stem_file.rsplit(".", 1)[0]
    manifest = get_manifest(job_id)
    if not manifest:
        return jsonify(error="Job not found"), 404
    payload = manifest.get("published_broad_stems", {}).get(stem_name)
    if not payload:
        return jsonify(error="Stem not found"), 404
    stem_path = Path(str(payload["path"])).resolve()
    return send_file(stem_path, mimetype="audio/wav", as_attachment=True, download_name=stem_path.name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

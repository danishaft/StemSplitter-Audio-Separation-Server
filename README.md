# Stem Splitter Audio Separation Server

This project is a local, CPU-first package builder for music separation. It
starts with broad stems, then adds higher-value production artifacts such as
tempo-locked WAV exports, MIDI guide files, section analysis, and downloadable
bundles. The server keeps the original `/separate` endpoint for compatibility,
but the main workflow is now job-based.

## What the server produces

Each completed job writes a working session package under `jobs/<job_id>/`.
The package focuses on reliable outputs first, then publishes extra artifacts
only when the pipeline has enough confidence to make them useful.

- Guaranteed broad stems in `quality` mode:
  - `vocals`
  - `drums`
  - `bass`
  - `other`
  - `instrumental`
- Extended broad stems when confidence passes the threshold:
  - `piano`
  - `guitar`
- Derived stems when confidence passes the threshold:
  - `kick`
  - `snare_clap`
  - `hats_cymbals`
  - `percussion`
  - `keys_synth`
  - `pads_strings`
  - `fx`
- Experimental specialist sub-stems when the optional MVSEP adapter is
  configured and the outputs pass the threshold:
  - `lead_vocals`
  - `backing_vocals`
  - `vocal_reverb`
  - `kick`
  - `snare`
  - `hi_hats`
  - `cymbals`
  - `toms`
  - `piano`
  - `guitar`
  - `keys_synth`
  - `strings`
- Tempo-locked WAV exports
- MIDI guide files:
  - `melody.mid`
  - `bass.mid`
  - `chords_guide.mid`
- Analysis exports:
  - `tempo_key.json`
  - `sections.json`
  - `manifest.json`
- Bundle downloads:
  - `stems.zip`
  - `midi.zip`
  - `wav_plus_midi.zip`

## Profiles

The server exposes three runtime profiles so you can choose speed, local depth,
or the experimental remote specialist path.

- `quality` runs a multi-model pipeline and publishes the full package when
  artifacts pass confidence checks. This profile stays fully local.
- `preview` keeps the run lighter and returns only the broad-stem layer.
- `quality_mvsep_experimental` keeps the local broad/derived pipeline, then
  optionally adds scored MVSEP specialist sub-stems when `MVSEP_API_KEY` is
  configured. If MVSEP is unavailable, the job still completes locally and the
  manifest records the skip reason.

The `quality` and `quality_mvsep_experimental` profiles now also prefer a local
specialist runner for derived stems. By default they use the bundled
`tools/local_specialist_runner.py`; `LOCAL_SPECIALIST_RUNNER` can override that
path. If no runner is available, the job falls back to the heuristic derived
path and records the fallback in the manifest.

## Quality scoring and rejected candidates

The server scores every non-core artifact before it publishes the file. That
includes extended stems, derived stems, specialist sub-stems, and MIDI guide
files.

- Core broad stems always publish when the model produces them:
  - `vocals`
  - `drums`
  - `bass`
  - `other`
  - `instrumental`
- Extended stems publish only when they reach the extended threshold.
- Derived stems publish only when they reach the derived threshold.
- Specialist sub-stems publish only when they reach the specialist threshold.
- MIDI files publish only when they pass both the MIDI score threshold and the
  MIDI sanity checks.

When a non-core artifact fails the gate, the server does not expose a download
link for it. Instead, it records the candidate in `rejected_candidates` inside
`analysis/manifest.json` with:

- `quality_score`
- `publish_status`
- `publish_reason`
- `warnings`
- `metrics`

This behavior lets you see what the pipeline attempted without polluting the
download surface with weak stems.

The manifest also records:

- `pipeline_mode`
- `candidate_winners`
- `remote_adapter_status`
- `remote_adapter_reason`

Those fields make it clear whether a job used local specialists, fell back to
heuristics, or layered in the experimental MVSEP branch.

## Requirements

You need a local Python environment with CPU PyTorch support and Demucs
installed in the shared project virtual environment. The current setup targets
Ubuntu 24.04 and Python 3.12.

- Python 3.12 or newer
- `ffmpeg`
- `libsndfile`
- The shared virtual environment at
  `/home/ayodele/Desktop/marlon-music/venv`

## Run the server locally

Use the bundled startup script to launch the Flask app with the shared virtual
environment.

1. Change into the repository root.
2. Run `./start.sh`.
3. Open `http://localhost:5000` if the browser does not open automatically.

The UI lets you upload a song, choose a profile, poll job status, and download
artifacts as they become available.

## API overview

The API now centers on jobs. Each job stores its own inputs, outputs, status,
and manifest on disk.

### `POST /jobs`

Create a new job by uploading one audio file and an optional `profile` form
field. The server returns `202 Accepted` with the queued job metadata.

### `GET /jobs/<job_id>`

Fetch the current job status. Once the job completes, this response includes
artifact URLs grouped by type.

### `GET /jobs/<job_id>/manifest`

Fetch the canonical manifest for a completed job. The manifest records model
choices, published stems, derived outputs, analysis data, bundle exports, and
missing features. It also records rejected candidates and the reasons they were
not published.

### `GET /artifacts/<job_id>/<relative_path>`

Download one generated file from the job directory.

### `POST /separate`

Use the legacy compatibility endpoint if you need the older flat broad-stem
response. This route runs the lighter `preview` profile synchronously.

## Job directory layout

Each job uses the same on-disk structure so artifacts are easy to inspect or
script against.

- `input/`
- `broad_stems/`
- `derived_stems/`
- `tempo_locked_wavs/`
- `midi/`
- `analysis/`
- `package/`

The `analysis/` directory includes the quality-scored manifest, `tempo_key`,
the lightweight `sections.json` export for `quality` jobs, and any structured
remote-adapter status for the experimental profile.

## Run tests

The Phase 2 test suite covers the scoring layer, section analysis, job
orchestration, and the HTTP contract without forcing large model downloads.

1. Activate the shared virtual environment.
2. Change into the repository root.
3. Run `pytest -q`.

The tests use synthetic fixtures and monkeypatched separation steps so you can
verify the pipeline behavior quickly on CPU.

## Docker

The repository still includes a Dockerfile for local packaging. The image uses
Python 3.12, installs audio dependencies, and launches `audio_api.py`.

1. Build the image with `docker build -t stem-splitter-local .`
2. Run the container with `docker run -p 5000:5000 stem-splitter-local`

The container ships the same job-based API and static UI as the local script.

## Limits and design choices

This pipeline does not claim to recover Suno's hidden original session. It
builds a practical local working package instead.

- Broad stems are prioritized over brittle ultra-fine splits.
- Extended and derived stems are confidence-gated.
- MIDI files are guide-quality for rebuilding and arrangement, not guaranteed
  note-perfect transcriptions.
- Specialist sub-stems are optional and experimental, not part of the default
  local product contract.

## Next steps

If you want to push the local stack further, the next sensible upgrades are:

- Add stronger recursive specialist splitters for drum and music-family stems.
- Add a benchmark harness for real-song evaluation.
- Add richer section labeling and candidate-quality diagnostics.

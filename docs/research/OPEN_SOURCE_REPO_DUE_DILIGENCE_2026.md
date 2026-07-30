# Open-source repository due diligence

This audit determines which reference projects are worth studying before the
next architecture revision. It separates reusable engineering from model
quality claims and records evidence at the audited commit instead of relying on
README marketing.

Audit date: July 18, 2026.

## Decision summary

The six projects do not provide one complete architecture that we can copy.
Use `python-audio-separator` as the model-runtime reference, StemDeck as the
local product and pipeline reference, and UVR as a historical algorithm and
model-configuration reference. None of the six is a production cloud control
plane or media data plane reference.

| Repository | Audited commit | Decision | Primary value |
| --- | --- | --- | --- |
| [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) | `ee1fcee` | Deep dive | Model runtime, registry, architecture adapters, ensembles, and inference parameters |
| [StemDeck](https://github.com/stemdeckapp/stemdeck) | `89717d2` | Deep dive selectively | Local job lifecycle, cancellation, recovery, SSE, audio preparation, streaming, and desktop packaging |
| [Ultimate Vocal Remover](https://github.com/anjok07/ultimatevocalremovergui) | `5517e0c` | Deep dive selectively | UVR model semantics, signal processing, ensembles, and model configuration |
| [StemRoller](https://github.com/stemrollerapp/stemroller) | `ea70ff9` | Quick reference only | Electron packaging, subprocess progress, cancellation, and local queue UX |
| [MISST](https://github.com/Frikallo/MISST) | `c7ea17f` | Performance clue only | Historical Demucs GPU timing and direct model invocation |
| [StemLab](https://github.com/sunsetsacoustic/StemLab) | `7aa9774` | Ignore | No production-quality implementation to reuse |

## Critical finding about our current models

Our current eight-stem profile uses `BS-Roformer-SW.ckpt` for the broad stems
and `MDX23C-DrumSep-aufr33-jarredou.ckpt` for drum sub-stems. The current
`python-audio-separator` benchmark database has no entry for BS-Roformer-SW.
Its DrumSep entry lists the six output names but contains zero evaluated tracks
and no median scores.

This means both models are runtime-validated but not quality-validated by that
benchmark database. Our local full-song check proves file integrity,
reconstruction consistency, and packaging only. It does not prove that these
are the best models or that their eight outputs beat commercial systems.

Do not label the current eight-stem profile as benchmark-proven until it passes
our ground-truth corpus and producer listening gates against selected
comparators.

## Benchmark capability audit

None of these repositories provides a reproducible eight-stem benchmark or an
apples-to-apples comparison with commercial services. Product completeness,
successful file creation, and model catalog scores are not substitutes for
ground-truth evaluation of our published stem contract.

`python-audio-separator` contains a MUSDB18-HQ script that runs `museval` and
records SDR, SIR, SAR, ISR, and processing speed. However, its paths are tied to
the author's local machine, and it only evaluates standard two-output
vocals/instrumental models. For non-standard and multi-stem models, the script
explicitly skips `museval` and records speed only. Its score database therefore
cannot validate our broad six-output model, DrumSep specialist, or eight-stem
product profile.

The remaining repositories do not close this gap:

- StemDeck and StemRoller test local product behavior, not separation quality.
- UVR provides model execution and ensemble semantics, not a reproducible
  multi-dataset benchmark suite.
- StemLab provides neither credible benchmark results nor reusable evaluation
  infrastructure.

Keep our benchmark implementation as an independent subsystem. It must support
dataset adapters, per-stem ground-truth alignment, SI-SDR and SDR-family
metrics, runtime and cost accounting, checkpoint hashes, aggregate confidence
intervals, and imported outputs from commercial comparators.

## Deep dive: python-audio-separator

This is the most important technical reference because our worker already uses
version `0.44.3` and its Python `Separator` API. The project supports Demucs,
MDX, MDXC/RoFormer, and VR architectures behind one runtime, model metadata,
model downloading, output normalization, bit-depth handling, chunking, and
ensemble algorithms.

Keep and verify these patterns:

- Use the Python API rather than launching a fresh CLI process per model.
- Cache loaded model instances in warm GPU containers.
- Validate architecture-specific configuration before loading checkpoints.
- Benchmark autocast, segment size, overlap, and batch size per model and GPU.
- Evaluate its FFT, waveform, max-spec, and min-spec ensemble implementations.
- Reuse its bit-depth, chunking, stem-name, and model-configuration tests where
  their licenses and behavior fit our runtime.
- Import model scores only with dataset, metric implementation, checkpoint
  hash, and evaluation commit recorded.

Do not copy these deployment patterns:

- The Modal endpoint reads the complete upload into memory and passes audio
  bytes into a spawned function.
- Modal Volume and Modal Dict are used as the primary output and status stores.
- Download endpoints read complete output files into memory before responding.
- Multiple models run sequentially without dependency-aware scheduling.

The Cloud Run implementation's Firestore job-store and GCS output-store
abstractions are useful references, but returning complete file bytes through
the API is still not our target architecture. Browser playback and downloads
must use signed object-storage or CDN URLs.

## Deep dive: StemDeck

StemDeck is actively maintained, Apache-2.0 licensed, and thoughtfully
engineered for a local single-machine product. Its separation model is only
Demucs `htdemucs_6s`, so it is not a model-quality reference for our stack.

The changes between the previous audited commit `5615fb0` and current commit
`89717d2` cover release UI and Windows GPU packaging. They do not add benchmark,
cloud queue, object-storage, or specialist-model infrastructure.

Adopt or adapt these ideas:

- Normalize unusual uploads to 44.1 kHz stereo before expensive inference.
- Reject oversized and over-duration files before queue admission.
- Apply explicit pending-job backpressure.
- Send progress through Server-Sent Events instead of aggressive polling.
- Support immediate subprocess cancellation and delete partial audio safely.
- Persist completed jobs and recover valid orphaned results after a crash.
- Quarantine small failure evidence while deleting large partial artifacts.
- Record stage timings and compute stem-presence statistics in one streamed
  pass.
- Serve audio with HTTP range support for responsive seeking.
- Apply TTL cleanup and protect active jobs from deletion.

Do not copy its in-memory registry or single-process semaphore for the cloud
service. Those choices are appropriate for a desktop application, not a
multi-instance service.

## Selective reference: Ultimate Vocal Remover

UVR remains the historical source for much of the MDX, VR, Demucs, and ensemble
logic that `python-audio-separator` packages for programmatic use. Study UVR to
understand model semantics, complement stems, spectrogram inversion, TTA,
post-processing, and ensemble behavior.

Do not adopt the Tkinter application architecture, pinned legacy dependency
stack, bundled fork of Demucs, or monolithic orchestration. The audited tree's
README claims MIT licensing but the shallow tree did not contain the referenced
`LICENSE` file, so legal verification is required before copying code directly.
Prefer the maintained MIT-licensed `python-audio-separator` implementation.

## Quick reference: StemRoller

StemRoller is an Electron and Svelte desktop wrapper around Demucs. Its local
process queue, subprocess cancellation, progress parsing, FFmpeg mixing, and
self-contained packaging are useful UI references. It explicitly warns that
separation takes several minutes and contributes no cloud queue, specialist
model routing, quality benchmark, or production storage design.

Do not use it as a backend or inference architecture reference.

## Performance clue: MISST

MISST is a GPL-3.0 local Tkinter and Demucs application last substantively
updated in 2023. Its published benchmark reports a 4-minute-9-second song in
28 seconds on an RTX 2070 Super using `htdemucs`. That is useful evidence that
our current latency is not explained by audio duration alone.

The comparison is not direct: MISST produces four broad stems with one Demucs
model, while our profile runs a broad six-output model and a dependent six-way
drum specialist. Use the result as a hardware/runtime baseline, not a quality
or eight-stem benchmark. Do not copy GPL code into our project.

## Ignore: StemLab

StemLab has no license file in the audited tree and does not implement several
features advertised in its README. The de-reverb path is a placeholder, the
"ensemble" is an unvalidated waveform average, sample-rate mismatch handling
contains a no-op, and subprocess commands use unsafe shell construction.

Do not copy its architecture, ensemble logic, queue, model selection, or audio
post-processing.

## Confirmed architecture decision

The comparison confirms that the cloud architecture must retain separate
control, execution, and media planes:

- Flask itself is not the principal latency problem.
- Keep `ThreadPoolExecutor` and JSON status files as development fallbacks
  only. Production configuration fails closed unless PostgreSQL and RQ are
  selected.
- Keep Modal `.spawn()` in the execution plane, but use PostgreSQL for canonical
  state, Redis and RQ for dispatch, and renewable database leases for
  idempotent execution.
- Send direct uploads, worker inputs, stems, and ZIP files through private B2
  object storage instead of relaying media through Flask.
- Apply atomic global and per-owner admission limits before creating a job.
- Keep cancellation in `cancelling` until queued work or Modal acknowledges
  termination.
- Expose durable job events through polling before adding SSE based on measured
  product need.
- Give terminal deletion and retention sweeps one explicit application owner.
- GPU model execution takes about 108 seconds of the measured 330-second run;
  upload, artifact transfer, and local packaging dominate the remaining path.

This design is stronger for a multi-user cloud service than the local lifecycle
architectures in the audited repositories. Managed PostgreSQL, Redis, and
identity are configured and live-verified, but the design is not
production-proven until the failure drills pass.

## Remaining gates before production promotion

Complete these gates before promoting the isolated production path:

1. Build an evidence matrix for every architectural claim, including source,
   benchmark, license, and applicability.
2. Benchmark our two selected models and credible alternatives on ground-truth
   data for all eight published stems.
3. Run the same 102-second file on T4, L4, and A10G with warm and cold starts.
4. Benchmark `python-audio-separator` autocast, chunk, overlap, and model-cache
   settings without changing quality thresholds blindly.
5. Validate ZIP publication, temporary-object cleanup, hard deletion, and
   abandoned-upload lifecycle rules against B2.
6. Run admission, lease takeover, retry, cancellation, reconciliation,
   cross-tenant, and restore drills against the activated services.
7. Create a dependency and license bill of materials for code and checkpoint
   redistribution.

The architecture is locked. These gates determine promotion, not another
rewrite.

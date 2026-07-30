# Commercial-grade stem splitter implementation plan

This document is the execution plan for moving this project from a useful
local stem splitter into a benchmarked, commercial-grade separation pipeline.
It turns the current architecture findings into concrete tasks, subtasks,
acceptance gates, and source references.

> **Warning:** This plan supersedes optimistic claims in older planning files
> when those claims are not backed by ground-truth evaluation. A stem is not
> considered commercial-grade because it exists as a file. It is considered
> commercial-grade only when it passes objective metrics and listening review.

## Canonical plan rules

This file is the canonical implementation plan until it is explicitly replaced
by a newer file. It is not a loose v1 brainstorm. All implementation work must
map back to one of the phases or tasks in this file.

- Do not create a new hidden roadmap in chat.
- Do not skip Phase 0 and Phase 1 to chase model integrations.
- Do not add new stem claims without adding the model, route, score, and gate.
- Do not replace this plan without writing the replacement file and explaining
  what changed.
- If implementation uncovers new work, add it to the discovered work log near
  the bottom of this file before continuing.
- If a task is partially implemented, update its status in this file or in a
  linked tracker file before moving to another task.
- At the start of each new work session, read the resume checkpoint and the
  next incomplete task.

## Diagnosis

The current project has a useful job pipeline, manifests, packaging, broad stem
separation, experimental remote adapters, and a ground-truth evaluator. The
main gap is the separation engine layer. The project does not yet have enough
specialist models, routing, ensemble selection, or cleanup to compete with
commercial services such as LALAL.AI, Logic Pro Stem Splitter, or
SpectraLayers.

The current broad stems are the strongest part of the system. The current
specialist stems are the weakest part. Piano, lead/back vocals, drum
sub-stems, strings, synth, wind, and reverb cleanup must not be presented as
pro outputs until they pass stricter gates.

## Guiding policies

These rules govern all implementation decisions in this plan.

- Publish fewer stems if that is the truthful output.
- Prefer proven open-source model runners before writing custom model code.
- Keep broad, derived, specialist, remote, and rejected outputs separate.
- Treat heuristics as experimental derived outputs, not real source stems.
- Run every candidate through a scoring gate before publishing it.
- Keep model licenses, checkpoints, versions, and checksums explicit.
- Compare against commercial tools only with the same source audio.
- Avoid one giant splitter. Use a routed model graph by stem family.
- Make every claim testable through a report file.
- Keep remote services optional, isolated, and clearly labeled.

## Current asset inventory

This inventory records what already exists in the repository and what must be
added before the product can be called commercial-grade.

| Area | Current status | Gap |
| --- | --- | --- |
| Job pipeline | Mostly present | Needs model-graph execution planning |
| Manifests | Mostly present | Needs stricter verification status fields |
| Broad stems | Partly strong | Needs BS-RoFormer comparison and gating |
| Specialist stems | Weak | Needs real specialist models |
| Derived stems | Experimental | Must be pulled out of pro path |
| Ground-truth eval | Started | Needs more datasets and per-stem suites |
| Candidate comparison | Started for piano/guitar | Needs all target stems |
| Model registry | Missing | Needs model metadata, licenses, and routing |
| Commercial comparator | Missing | Needs LALAL, Logic, and SpectraLayers outputs |
| Post-processing | Minimal | Needs bleed, phase, loudness, and artifact cleanup |

## Target stem families

The target is not a fixed number of files. The target is a verified set of
usable stems where each stem has a known source model, score, and status.

- Core broad stems: `vocals`, `drums`, `bass`, `other`, `instrumental`.
- Extended broad stems: `piano`, `guitar`.
- Vocal specialist stems: `lead_vocals`, `backing_vocals`, `dry_vocals`,
  `vocal_reverb_residual`.
- Drum specialist stems: `kick`, `snare`, `hi_hats`, `cymbals`, `toms`,
  `ride`, `crash`, `percussion`.
- Instrument specialist stems: `keys_synth`, `strings`, `wind_brass`,
  `pads`, `fx`.

## Standard kit

This project must use a limited standard kit first. Add new tools only when the
standard kit cannot cover a required stem family.

- Use `python-audio-separator` for UVR-style model catalog execution.
- Use `bs-roformer-infer` for BS-RoFormer models.
- Use `melband-roformer-infer` for MelBand-RoFormer models.
- Use DrumSep models for drum sub-stems.
- Use ZFTurbo/MVSep tooling for training, validation, and ensembles.
- Use a ComfyUI-like graph model for routing design, not as a required
  dependency.

## Reference projects

These projects contain engineering patterns this project can reuse.

- [Ultimate Vocal Remover GUI](https://github.com/Anjok07/ultimatevocalremovergui)
  provides the local splitter product pattern, model categories, and user
  workflow.
- [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)
  provides CLI execution, model listing, model download, and model cache
  patterns.
- [bs-roformer-infer](https://github.com/openmirlab/bs-roformer-infer)
  provides a clean BS-RoFormer model registry and inference runner.
- [melband-roformer-infer](https://github.com/openmirlab/melband-roformer-infer)
  provides a MelBand-RoFormer registry, karaoke models, denoise models, and
  dereverb models.
- [DrumSep on MVSep](https://mvsep.com/algorithms/29) documents drum models for
  kick, snare, cymbals, toms, ride, hi-hat, and crash.
- [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)
  provides training, inference, validation, and ensemble patterns.
- [ComfyUI](https://github.com/comfy-org/comfyui) provides the graph, node,
  plugin, and workflow orchestration reference pattern.
- `/home/ayodele/Desktop/Yard` provides the research operating-system pattern:
  selection rubrics, eval-plan templates, result notes, kill/continue logs,
  provenance discipline, score-card design, and drift monitoring.

## Phase 0: Stop the weak product path

This phase removes misleading behavior before adding more models. It prevents
the project from wasting time validating stems that the architecture already
knows are weak.

### Task A: Freeze unverified claims

This task makes the product language match the evidence.

- Mark older plan files as historical or superseded.
- Remove any claim that current 12-stem or 16-stem output is pro-grade.
- Add a clear definition for `verified`, `experimental`, `derived`, and
  `rejected`.
- Add a `commercial_grade` field only when a stem passes objective and human
  review gates.

Acceptance criteria:

- No default UI, API, or manifest field implies that weak specialist stems are
  professional outputs.
- Historical docs remain available but are clearly labeled as superseded.

### Task B: Pull heuristic stems out of pro outputs

This task keeps useful experiments without mislabeling them.

- Move EQ-derived kick, snare, hats, cymbals, percussion, keys, pads, and fx
  into a `published_derived_experimental` or equivalent bucket.
- Keep derived stems out of commercial packages by default.
- Add rejected reasons for derived stems that fail artifact or leakage checks.
- Keep derived stems accessible for research and debugging.

Acceptance criteria:

- `stems.zip` does not include weak derived stems as official stems unless an
  explicit experimental option is selected.
- The manifest tells users exactly which stems are derived.

### Task C: Define the release profiles

This task prevents one profile from trying to serve all use cases.

- Keep `preview` local, fast, and broad-stem-only.
- Keep `quality` local and benchmark-safe.
- Keep `quality_mvsep_experimental` remote and optional.
- Add `research_specialist` for local specialist model experiments.
- Add `commercial_candidate` only after strict gates exist.

Acceptance criteria:

- Remote models never run in default local profiles.
- Experimental profiles are clearly named and documented.

## Phase 1: Build the model registry foundation

This phase creates the source of truth for models, stems, licenses, runtime
requirements, and routing.

### Task D: Create `models/registry.yaml`

This task creates the first version of the model registry.

- Use `../research/SPECIALIST_MODEL_SELECTION.md` and
  `models/selected_specialist_models.yaml` as the registry seed.
- Add model entries for Demucs, audio-separator, BS-RoFormer, MelBand-RoFormer,
  DrumSep, MVSEP, and commercial comparator outputs.
- Track model name, source project, checkpoint URL, config path, license,
  expected stems, input stem, output stems, hardware requirements, and checksum.
- Track whether a model is local, remote, proprietary, or comparator-only.
- Track whether a model is approved for product use.

Acceptance criteria:

- Every model runner reads metadata from the registry.
- No checkpoint is used without a registry entry.

### Task E: Add model license audit fields

This task prevents accidental use of unsafe model weights.

- Add `code_license`, `weights_license`, `commercial_use`, and
  `attribution_required` fields.
- Add `license_status` values: `unknown`, `research_only`,
  `commercial_candidate`, and `commercial_approved`.
- Block `commercial_candidate` profile from using models with unknown license
  status.

Acceptance criteria:

- The pipeline refuses to publish commercial outputs from unknown-license
  checkpoints.
- Reports include model license status.

### Task F: Add model download and cache management

This task makes local model setup repeatable.

- Store models under `.cache/stem-models` or another ignored cache path.
- Add checksums for downloaded configs and checkpoints.
- Add a model download command that can fetch one model, one category, or all
  approved models.
- Add cache status reporting for missing, present, corrupt, and outdated
  models.

Acceptance criteria:

- A clean machine can reproduce the model environment from the registry.
- Corrupt or missing checkpoints fail with structured errors.

## Phase 2: Integrate core open-source model runners

This phase replaces baseline-only separation with stronger local model
families.

### Task G: Integrate BS-RoFormer runner

This task adds the main candidate for six-stem commercial-quality broad
separation.

- Create `tools/bs_roformer_runner.py`.
- Support input audio, output directory, model slug, target stems, and device.
- Download or locate `BS-RoFormer-SW` through the registry.
- Normalize outputs to `vocals`, `drums`, `bass`, `guitar`, `piano`, `other`,
  and `instrumental`.
- Add unit tests with a fake runner.
- Add an integration test that is skipped unless the model is present.

Acceptance criteria:

- The runner can produce normalized six-stem outputs.
- The benchmark harness can compare BS-RoFormer against current Demucs outputs.

### Task H: Integrate MelBand-RoFormer runner

This task adds vocal, karaoke, denoise, and dereverb model execution.

- Create `tools/melband_roformer_runner.py`.
- Support vocals, instrumental, karaoke, denoise, and dereverb categories.
- Normalize outputs to known stem names.
- Add lead/back vocal candidate support where the selected model provides it.
- Add dry vocal and reverb residual outputs for dereverb workflows.

Acceptance criteria:

- Vocal and dereverb candidates can be generated without changing the main job
  contract.
- Karaoke and lead/back outputs are stored as specialist candidates.

### Task I: Integrate DrumSep runner

This task replaces EQ-derived drum sub-stems with real drum specialist
separation.

- Create `tools/drumsep_runner.py`.
- Accept a drum stem or full mix depending on model mode.
- Prefer `drums -> DrumSep` routing to reduce non-drum leakage.
- Normalize outputs to `kick`, `snare`, `hi_hats`, `cymbals`, `toms`, `ride`,
  and `crash`.
- Add fallback behavior when a selected model provides fewer drum outputs.

Acceptance criteria:

- Drum sub-stems come from a trained model, not EQ filters.
- The manifest records the parent input stem and DrumSep model used.

### Task J: Extend the existing audio-separator runner

This task turns the current piano/guitar runner into a general UVR catalog
runner.

- Add registry-driven model selection instead of hardcoded model names.
- Support `--list_models` JSON ingestion for catalog discovery.
- Support single-stem and multi-stem model execution.
- Normalize output names through registry mappings.
- Keep this runner isolated in `.venvs/audio-separator`.

Acceptance criteria:

- The runner can execute any approved audio-separator model from the registry.
- New UVR-style models do not require custom Python code unless output naming
  is unusual.

## Phase 3: Build the routed model graph

This phase turns the system into a multi-stage pipeline instead of independent
script calls.

### Task K: Define the routing graph schema

This task describes how audio moves through models.

- Add `routing/profile_name.yaml` files for each profile.
- Define nodes for input mix, broad separation, vocal specialists, drum
  specialists, instrument specialists, cleanup, scoring, packaging, and reject
  buckets.
- Define node inputs, outputs, required models, optional models, and timeouts.
- Define whether each node is local, remote, or comparator-only.

Acceptance criteria:

- A profile can be inspected before execution to know every planned model run.
- Routing can be changed without editing job orchestration code.

### Task L: Implement graph execution

This task executes the routing graph safely.

- Add a graph planner that expands profile configuration into runnable steps.
- Add dependency ordering for parent stems and child stems.
- Add step-level status: `pending`, `running`, `complete`, `skipped`,
  `failed`, and `rejected`.
- Add retry policy only where retry is safe.
- Add structured errors for missing model, missing input, timeout, and bad
  output.

Acceptance criteria:

- A failed specialist branch does not fail the whole job unless the profile
  marks it as required.
- The manifest records every planned, skipped, failed, and completed step.

### Task M: Separate artifact groups permanently

This task keeps artifact semantics clean.

- Keep `published_broad_stems` for broad stems.
- Keep `published_specialist_substems` for trained specialist model outputs.
- Keep `published_derived_experimental` for heuristics and DSP-derived stems.
- Keep `commercial_comparator_outputs` for imported LALAL, Logic, or
  SpectraLayers outputs.
- Keep rejected candidates grouped by stem family.

Acceptance criteria:

- A user can tell exactly how every stem was created.
- Weak stems cannot silently enter the pro artifact group.

## Phase 4: Build candidate generation and ensemble selection

This phase runs multiple candidates per stem and promotes only the best
candidate.

### Task N: Generalize candidate collection

This task expands current piano/guitar comparison to all target stems.

- Create a generic `StemCandidate` data model.
- Record stem name, candidate path, parent path, model, profile, source group,
  runtime, license status, and quality status.
- Collect candidates from broad, specialist, derived, remote, and comparator
  sources.

Acceptance criteria:

- Any stem can have multiple candidates before publishing.
- Candidate reports are stable JSON files.

### Task O: Add objective scoring per stem family

This task makes scoring stem-aware.

- Use SI-SDR, SDR, correlation, and error loudness when ground truth exists.
- Add leakage score against sibling stems.
- Add silence and energy sanity checks.
- Add spectral artifact checks for musical usability.
- Keep scoring thresholds per stem family.

Acceptance criteria:

- A candidate can fail because it is silent, leaky, distorted, or worse than
  the current winner.
- Score reports explain why a stem was published or rejected.

### Task P: Add ensemble and blend strategies

This task tests whether combining candidates improves quality.

- Add `winner_take_all` selection.
- Add average-wave ensemble for similar-quality candidates.
- Add conservative frequency-domain ensemble for complementary candidates.
- Add rejection if any ensemble performs worse than the best single model.

Acceptance criteria:

- Ensembles are used only when they improve measured quality.
- Bad candidates cannot drag down an ensemble silently.

## Phase 5: Build benchmark and comparator coverage

This phase stops testing only the songs that make the system look good.

### Task Q: Expand ground-truth datasets

This task adds stronger objective benchmarks.

- Add MUSDB18 or MUSDB-HQ where available.
- Add Slakh and BabySlakh splits for instrument-heavy evaluation.
- Add drum-specific datasets for DrumSep evaluation.
- Add vocal lead/back datasets where licensing permits.
- Add a curated Suno-style test set for no-ground-truth listening review.

Acceptance criteria:

- Broad, specialist, vocal, drum, and instrument families each have a benchmark
  set.
- Results are stored under `benchmarks/ground_truth`.

### Task R: Build the commercial comparator harness

This task lets the project measure against paid tools without pretending.

- Add an import format for LALAL.AI outputs.
- Add an import format for Logic Pro exports.
- Add an import format for SpectraLayers exports.
- Add comparator metadata: tool name, version, settings, date, and source
  file.
- Compare our outputs and commercial outputs on the same ground-truth tracks
  where possible.

Acceptance criteria:

- Reports can say whether our output beats a commercial output for the same
  song and stem.
- Comparator files are never mixed into model training data by accident.

### Task S: Add human listening review

This task covers cases where objective metrics do not tell the full story.

- Add a review form or JSON schema for artifact, bleed, clarity, tone, and
  usefulness.
- Require blind A/B/C comparisons where possible.
- Store listening notes beside objective reports.
- Use human review as a gate for commercial-profile stems.

Acceptance criteria:

- A high metric score is not enough if the stem sounds unusable.
- Listening review is repeatable and stored.

## Phase 6: Add cleanup and mastering-aware post-processing

This phase makes raw model outputs more usable.

### Task T: Add stem consistency checks

This task catches common separation failures.

- Check that reconstructed stems do not wildly exceed input loudness.
- Check for excessive phase cancellation.
- Check for impossible energy distribution.
- Check whether a child stem contains more energy than its parent.

Acceptance criteria:

- Broken model outputs are rejected before packaging.
- Reports include consistency warnings.

### Task U: Add audio cleanup modules

This task improves stem usability after separation.

- Add loudness normalization per stem.
- Add optional bleed suppression.
- Add optional transient repair for drum stems.
- Add optional dereverb or deecho for vocal stems.
- Add optional noise and artifact reduction.
- Keep cleanup reversible by storing pre-cleanup candidates.

Acceptance criteria:

- Cleanup never overwrites the raw candidate.
- Cleanup must improve score or pass listening review before publishing.

## Phase 7: Productize the truth layer

This phase makes the API and UI communicate exactly what happened.

### Task V: Add verification statuses to API responses

This task makes quality visible to users and clients.

- Add `quality_status` values: `verified`, `candidate`, `experimental`,
  `rejected`, `skipped`, and `not_available`.
- Add `quality_reason` for every non-verified stem.
- Add `model_source`, `model_license_status`, and `score_summary`.
- Add `comparison_rank` when commercial comparator outputs exist.

Acceptance criteria:

- The completed job payload can explain every missing or rejected stem.
- Clients do not need to parse logs to understand quality.

### Task W: Update UI grouping and labels

This task prevents users from mistaking experiments for pro stems.

- Show broad stems separately from specialist stems.
- Show derived experimental stems in a separate collapsed group.
- Show rejected candidates only when debug mode is enabled.
- Label remote and commercial comparator outputs clearly.
- Show model, score, and status for each stem.

Acceptance criteria:

- The UI never presents weak outputs as commercial-grade stems.
- Users can still access experimental outputs deliberately.

### Task X: Update packaging profiles

This task makes downloads match the selected quality contract.

- Keep `stems.zip` for verified and accepted published stems only.
- Add `experimental_stems.zip` for derived and research outputs.
- Add `candidate_report.zip` for scores, manifests, and logs.
- Add `commercial_comparison.zip` only when comparator outputs exist.

Acceptance criteria:

- A normal user download contains no mislabeled weak stems.
- Researchers can still download all candidates and reports.

## Phase 8: Hardening and release gates

This phase makes the system dependable enough to use repeatedly.

### Task Y: Add operational controls

This task prevents model execution from breaking the machine.

- Add GPU and CPU device selection.
- Add per-model timeout and memory limits.
- Add batch queue controls.
- Add model warmup and cache status checks.
- Add retry rules for network-only adapters.

Acceptance criteria:

- Heavy model jobs do not hang indefinitely.
- The system can explain whether failure is model, cache, hardware, or input
  related.

### Task Z: Define commercial-candidate release criteria

This task defines what must be true before claiming commercial parity.

- Require model license audit completion.
- Require benchmark results across at least three dataset families.
- Require commercial comparator runs on selected tracks.
- Require listening review on representative genres.
- Require no default publication of experimental stems.
- Require full regression tests to pass.

Acceptance criteria:

- The project cannot claim LALAL, Logic, or SpectraLayers parity without a
  written report.
- Every release has reproducible benchmark artifacts.

## Phase 9: Evidence operating system

This phase comes from the Yard audit. Yard is not a better splitter engine, but
it has stronger research governance than this plan originally captured. These
tasks prevent the project from drifting into untracked experiments.

### Task AA: Add experiment templates and result notes

This task makes every model or architecture experiment reproducible.

- Add `benchmarks/templates/eval_plan_template.md`.
- Add `benchmarks/templates/result_note_template.md`.
- Require objective, metrics, data, experiment matrix, success criteria, kill
  criteria, runtime notes, and next action.
- Store one result note beside every benchmark report.

Acceptance criteria:

- Every non-trivial model experiment has a written eval plan before execution.
- Every benchmark run ends with a decision: `continue`, `pivot`, or `kill`.

### Task AB: Add kill/continue and model selection rubric

This task prevents endless testing of weak directions.

- Add a weighted model-selection rubric covering recency, benchmark evidence,
  stem coverage, license safety, runtime feasibility, integration complexity,
  and commercial relevance.
- Add `benchmarks/KILL_CONTINUE_LOG.md`.
- Require a kill/continue decision after each model family sprint.
- Archive weak models instead of leaving them in active routing plans.

Acceptance criteria:

- New model integrations cannot start without passing the selection rubric.
- Failed or weak directions have an explicit kill/pivot reason.

### Task AC: Add dataset and comparator provenance

This task makes benchmark and comparator data defensible.

- Add fingerprints for benchmark input files and commercial comparator outputs.
- Store source URL, license, date accessed, tool version, settings, and
  checksum.
- Store license snapshots where licensing matters.
- Keep train, validation, test, and comparator data separated.
- Add a removal path for mislicensed or contaminated data.

Acceptance criteria:

- Every benchmark input and comparator output has provenance metadata.
- Commercial comparator outputs cannot be used as training data by accident.

### Task AD: Add score-card, calibration, and drift monitoring

This task keeps quality measurements trustworthy over time.

- Add per-run score cards with separation metrics, artifact metrics, loudness
  metrics, perceptual quality metrics, and listening-review summaries.
- Separate source-separation quality from production/audio-quality scores.
- Track model version, runner version, hardware, runtime, and profile.
- Track score drift across benchmark slices by genre, stem family, and model.
- Add calibration notes for any AI judge or human-review aggregate score.

Acceptance criteria:

- A new model version cannot silently change benchmark quality.
- Reports show whether a regression is separation quality, artifact quality,
  loudness, or reviewer disagreement.

## Execution order

This sequence keeps the work focused on the highest-risk gaps first.

1. Complete Phase 0 to stop misleading outputs.
2. Complete Phase 1 to make model use reproducible and license-aware.
3. Complete Phase 2 for BS-RoFormer, MelBand-RoFormer, DrumSep, and expanded
   audio-separator execution.
4. Complete Phase 3 so profile routing is graph-based and auditable.
5. Complete Phase 4 so every stem has candidate selection and rejection.
6. Complete Phase 5 so progress is measured against datasets and paid tools.
7. Complete Phase 6 so raw outputs become usable production stems.
8. Complete Phase 7 so users see verified truth, not marketing language.
9. Complete Phase 8 before any commercial-grade claim.
10. Complete Phase 9 so experiments, data, and score drift remain auditable.

## Dependency map

This map prevents circular work and skipped foundations. Later tasks can start
only when their required upstream tasks are complete or deliberately stubbed.

| Task | Depends on | Unlocks |
| --- | --- | --- |
| A | None | Honest docs, API, and UI language |
| B | A | Clean artifact separation |
| C | A, B | Safe profile behavior |
| D | A | Registry-driven runners |
| E | D | Commercial-safe model use |
| F | D, E | Reproducible model setup |
| G | D, F | BS-RoFormer candidates |
| H | D, F | MelBand vocal and dereverb candidates |
| I | D, F | Real drum sub-stem candidates |
| J | D, F | General UVR-style model execution |
| K | C, D | Profile routing files |
| L | K | Graph-based execution |
| M | B, L | Permanent artifact contract |
| N | M | Generic candidate collection |
| O | N | Objective quality gates |
| P | O | Ensemble and blend selection |
| Q | O | Larger ground-truth coverage |
| R | Q | Commercial tool comparison |
| S | O, R | Listening review gate |
| T | L, O | Consistency rejection |
| U | T | Cleanup candidate generation |
| V | M, O | Truthful API responses |
| W | V | Truthful UI grouping |
| X | M, V | Correct download packages |
| Y | F, L | Reliable heavy model execution |
| Z | A through Y | Commercial-candidate release |
| AA | O, Q | Reproducible experiment records |
| AB | AA | Kill/continue governance |
| AC | Q, R | Defensible benchmark provenance |
| AD | O, S, AC | Long-term score-card and drift monitoring |

## Completion tracker

Use this tracker to prevent losing the next step. Update the status when a task
is completed, blocked, or deliberately deferred.

| Task | Status | Evidence |
| --- | --- | --- |
| A: Freeze unverified claims | Pending | Needs docs and API language audit |
| B: Pull heuristic stems out of pro outputs | Pending | Needs manifest and packaging changes |
| C: Define release profiles | Pending | Needs config and tests |
| D: Create `models/registry.yaml` | Started | Added `models/registry.yaml`, `splitter/model_registry.py`, and `tests/test_model_registry.py`; runner wiring still belongs to later tasks |
| E: Add model license audit fields | Pending | Needs registry fields and blockers |
| F: Add model download and cache management | Pending | Needs CLI and checksum tests |
| G: Integrate BS-RoFormer runner | Pending | Needs runner, fake tests, real benchmark |
| H: Integrate MelBand-RoFormer runner | Pending | Needs runner and vocal tests |
| I: Integrate DrumSep runner | Pending | Needs runner and drum tests |
| J: Extend audio-separator runner | Started | Basic piano/guitar bridge exists |
| K: Define routing graph schema | Pending | Needs route YAML schema |
| L: Implement graph execution | Pending | Needs planner and execution states |
| M: Separate artifact groups permanently | Started | Broad/specialist separation partly exists |
| N: Generalize candidate collection | Started | Piano/guitar candidate comparison exists |
| O: Add objective scoring per stem family | Started | Ground-truth scoring exists for some stems |
| P: Add ensemble and blend strategies | Pending | Needs candidate ensemble module |
| Q: Expand ground-truth datasets | Started | BabySlakh support exists |
| R: Build commercial comparator harness | Pending | Needs import formats |
| S: Add human listening review | Pending | Needs review schema |
| T: Add stem consistency checks | Pending | Needs consistency module |
| U: Add audio cleanup modules | Pending | Needs cleanup candidates |
| V: Add verification statuses to API responses | Pending | Needs API payload changes |
| W: Update UI grouping and labels | Pending | Needs UI changes |
| X: Update packaging profiles | Pending | Needs package contract changes |
| Y: Add operational controls | Pending | Needs device, timeout, and cache controls |
| Z: Define commercial-candidate release criteria | Pending | Needs release report template |
| AA: Add experiment templates and result notes | Pending | Needs benchmark templates |
| AB: Add kill/continue and model selection rubric | Pending | Needs rubric and log |
| AC: Add dataset and comparator provenance | Pending | Needs metadata schema |
| AD: Add score-card, calibration, and drift monitoring | Pending | Needs score-card schema |

## First implementation sprint

The first sprint must create the base that all later work uses.

1. Add a `models/registry.yaml` schema and loader.
2. Add model license and cache fields.
3. Mark current derived stems as experimental in manifests and API responses.
4. Add a BS-RoFormer runner behind the registry.
5. Run BS-RoFormer against BabySlakh Track00011 and compare to current Demucs.
6. Add a generic `StemCandidate` model.
7. Extend candidate comparison beyond piano and guitar.
8. Update tests to prove default `quality` remains local and honest.

### First sprint detailed task list

Use this detailed list for the next implementation pass.

1. Add status labels to existing plan files.
   - Mark `16_STEM_PLAN.md`, `STEM_ROADMAP.md`, and
     `../research/PRETRAINED_MODELS.md` as
     historical planning artifacts.
   - Point each file to this canonical plan.
   - Remove or qualify unsupported `pro` claims.

2. Change derived stem publication behavior.
   - Add `published_derived_experimental` to manifests.
   - Move EQ-derived sub-stems into the experimental bucket.
   - Keep existing broad stems unchanged.
   - Update `stems.zip` to exclude experimental stems by default.
   - Add `experimental_stems.zip` only when experimental output exists.

3. Add verification status fields.
   - Add `quality_status`.
   - Add `quality_reason`.
   - Add `model_source`.
   - Add `model_license_status`.
   - Add `score_summary`.

4. Add model registry foundation.
   - Create `models/registry.yaml`.
   - Seed it from `models/selected_specialist_models.yaml`.
   - Create `splitter/model_registry.py`.
   - Validate required fields.
   - Add tests for valid, missing, and unsafe license entries.

5. Add model cache foundation.
   - Create `scripts/model_cache.py`.
   - Add `status`, `verify`, and `download` commands.
   - Use checksums from the registry.
   - Keep model files out of Git.

6. Add BS-RoFormer runner.
   - Create `tools/bs_roformer_runner.py`.
   - Add fake-runner tests.
   - Add skipped real-model integration test.
   - Benchmark BabySlakh Track00011 when the model is available.

7. Generalize candidate data.
   - Create a generic candidate model.
   - Keep the existing piano/guitar report working.
   - Add room for drum, vocal, and instrument candidates.

8. Run verification.
   - Run focused tests for registry, packaging, and candidate reports.
   - Run the full local test suite.
   - Save benchmark reports under `benchmarks/`.

9. Add Yard-derived evidence templates.
   - Add eval-plan and result-note templates under `benchmarks/templates`.
   - Add a kill/continue log.
   - Add the model-selection rubric.
   - Require each benchmark report to link to its result note.

## Immediate stop list

These actions must stop until the relevant gates exist.

- Stop calling file count a quality milestone.
- Stop publishing heuristic sub-stems as official pro stems.
- Stop using publishability scores as ground-truth quality.
- Stop adding UI claims before model and benchmark work.
- Stop treating MVSEP or audio-separator adapters as proof of local quality.
- Stop benchmarking only the current weak stack when the missing model layer is
  already known.
- Stop using unlicensed or unknown-license checkpoints in product profiles.

## Resume checkpoint

When resuming this project, start here.

1. Read this file.
2. Check the completion tracker.
3. Run `git status --short`.
4. Continue the first pending task in the tracker.
5. If new work is discovered, add it to the discovered work log before coding.
6. Run the narrowest useful test after each non-trivial implementation task.
7. Update the tracker evidence before ending the session.

The current next task is Task A: freeze unverified claims.

## Discovered work log

Use this section for new tasks discovered during implementation. Do not create
side plans in chat. Add the work here, map it to a phase, and then continue.

| Date | Phase | Discovery | Action |
| --- | --- | --- | --- |
| July 10, 2026 | All | Initial completeness audit added canonical rules, dependency map, tracker, and resume checkpoint. | Use this file as the source of truth. |
| July 10, 2026 | Phase 9 | Yard audit found useful research-governance patterns: eval plans, result notes, kill/continue logs, provenance, score cards, and drift monitoring. | Added Phase 9 and Tasks AA-AD. |
| July 10, 2026 | Phase 1 | Specialist model candidates were selected across broad, vocal, drum, cleanup, instrument, remote, and comparator categories. | Use `../research/SPECIALIST_MODEL_SELECTION.md` and `models/selected_specialist_models.yaml` as Task D input. |
| July 10, 2026 | Phase 1 | Runtime registry foundation was added and validates the selected model seed. | Next model-layer task is Task F: model download and cache management. |
| July 11, 2026 | Phase 2 | Cocktail Fork MRX was isolated into a standalone Modal worker and produced `speech_dialog`, `music`, and `sfx` on a 20-second smoke job. | Treat it as an external-runner experimental candidate; benchmark it before any SFX or speech production claim. |
| July 11, 2026 | Phase 5 | Added the speech/music/SFX external-stem benchmark harness and ran Cocktail Fork on the 20-second `booty2` sample. | Current evidence is no-reference sanity only: it passed with no warnings, but production quality still requires ground-truth or comparator scoring. |
| July 11, 2026 | Phase 5 | Added the speech/music/SFX corpus runner and ran Cocktail Fork on the two-song `local-small` corpus with 20-second excerpts. | Two of two jobs completed and two of two no-reference sanity checks passed; next gate is MVSep, CDX, LALAL, or ground-truth comparison. |
| July 11, 2026 | Phase 5 | Added music-only negative-control references for BabySlakh. | Cocktail Fork scored `music` at `31.23 dB` SDR and kept false `speech_dialog` and `sfx` leakage below `-44 dB`; this does not replace real speech/SFX evaluation. |
| July 12, 2026 | Phase 5 | MVSep DnR v3 comparator outputs were collected for the 20-second `booty2` sample and benchmarked against Cocktail Fork MRX. | Music alignment is strong and speech alignment is moderate, but SFX fails the comparator gate. Keep Cocktail Fork experimental and prioritize CDX23, BandIt v2, or another DnR-style SFX runner. |
| July 12, 2026 | Phase 5 | Added a no-spend gate for SFX model candidates. | Do not spend Modal GPU, paid API, or long external queue time until the candidate has exact target stems, public weights, a runnable inference entry point, known license status, local dry-run success, and output-name validation. CDX23 is the first target; BandIt v2 is second after weight and runner preflight. |
| July 12, 2026 | Phase 5 | Ran the CDX23 no-spend preflight. | Technical gates passed: exact stems, release weights, dependency imports, `inference.py --help`, and output naming. Commercial use is blocked because the repository has no license file and GitHub reports `licenseInfo: null`; do not spend GPU until license status is verified. |

## Success definition

The project reaches commercial-candidate status when it can produce a report
like this for each target stem family:

- The source model and checkpoint are known.
- The model license is known.
- The stem was scored against ground truth where available.
- The stem was compared against at least one commercial output where possible.
- The stem passed listening review.
- The manifest explains every published, rejected, skipped, and missing stem.
- The download package contains only stems that match the selected profile.
- The benchmark has a result note and kill/continue decision.
- The benchmark and comparator data have provenance metadata.
- Score cards separate separation quality from production/audio quality.

## Next steps

Start with the first implementation sprint. Do not add more visible stem claims
until the registry, routing, candidate scoring, and experimental-stem separation
are in place.

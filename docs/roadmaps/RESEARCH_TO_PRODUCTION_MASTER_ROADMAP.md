# Research-to-production master roadmap

> **Superseded:** Use [`FINAL_STEMSPLITTER_RELEASE_PLAN.md`](FINAL_STEMSPLITTER_RELEASE_PLAN.md)
> as the single active implementation authority. This file remains preserved
> as research and execution history.

This document preserves the detailed research-to-production execution history
for dataset completion, specialist training, model qualification, inference
integration, cloud delivery, self-hosted delivery, and release. The final
release plan supersedes it as the active execution authority. Older documents
remain evidence and history.

Status: **Approved for Phase 0 execution**

Last updated: July 29, 2026

## How to use this roadmap

Work through the phases in dependency order. Mark a task complete only when its
named evidence exists. A completed command, generated file, or successful model
load is not evidence of audio quality.

Use these status markers:

- `[ ]` means not started.
- `[~]` means started but the exit gate has not passed.
- `[x]` means complete with evidence.
- `[!]` means blocked and names the blocking condition.
- `[N/A]` means deliberately excluded with a recorded reason.

No phase may be called complete because work took a long time or consumed GPU
credit. Only its exit gate determines completion.

## Mission and success definition

The product goal is a trustworthy hierarchical 12-stem splitter for artists
and producers. The research goal is to meet or exceed the quality of the
corresponding LALAL.AI output on the same songs. The project may claim that it
beats LALAL.AI only after a matched, blinded comparison passes the claim gate
defined in this roadmap.

The final public stem contract is:

1. Vocals
2. Instrumental
3. Drums
4. Bass
5. Kick
6. Snare
7. Piano
8. Acoustic guitar
9. Electric guitar
10. Synth
11. Strings
12. Wind and brass

This is a hierarchy, not twelve mutually exclusive signals. Vocals and
instrumental are parents. Kick and snare are children of drums. The remaining
instrument stems are children of instrumental. Users must not be told that
summing all twelve outputs reconstructs the song.

## Current truth

The project has useful infrastructure and several strong pretrained models, but
it does not yet have a qualified 8-stem or 12-stem release. The current
qualification ledger is rejected after nine valid songs. Piano is weak on the
internal corpus, and broad guitar has an internal domain mismatch.

| Stem | Current owner | Current evidence | Current status |
| --- | --- | --- | --- |
| Vocals | Mel-Band RoFormer | 11.01 dB external SDR | Candidate, release benchmark incomplete |
| Instrumental | Vocal complement | 17.32 dB external SDR | Candidate, release benchmark incomplete |
| Drums | BS-RoFormer SW | 14.11 dB external, 16.699 dB internal | Strong candidate |
| Bass | BS-RoFormer SW | 14.62 dB external, 10.682 dB internal | Strong candidate |
| Kick | MDX23C DrumSep | 14.54 dB external SDR | Candidate, internal benchmark incomplete |
| Snare | MDX23C DrumSep | 9.79 dB external SDR | Candidate, internal benchmark incomplete |
| Piano | BS-RoFormer SW | 7.83 dB external, 2.459 dB internal | Domain mismatch under investigation |
| Acoustic guitar | None | No qualified checkpoint | Missing |
| Electric guitar | None | Prior 1,000-step specialist failed | Missing |
| Synth | None | Released X-LANCE chain failed local gate | Missing |
| Strings | None | Prior short specialist was marginal | Missing |
| Wind and brass | None | Prior short specialist retained bleed | Missing |

The data status also has two different meanings. The research manifest records
catalogued or recoverable material, while only about 6.98 GB is currently
retained locally. RawStems selections and suspended B2 objects are not
training-ready until byte read-back succeeds.

| Specialist | Real train hours catalogued | Synthetic train hours | Planning range | Current gap |
| --- | ---: | ---: | ---: | ---: |
| Acoustic guitar | 0 | 0 | 70-100+ real hours | No prepared corpus |
| Electric guitar | 54.143 | 0 | 70-100+ real hours | Below planning range |
| Synth | 0 | 0 | 70-100+ real hours | No prepared corpus |
| Strings | 9.368 | 50.051 | 70-100+ real hours | Synthetic-majority |
| Wind and brass | 8.917 | 50.089 | 70-100+ real hours | Synthetic-majority |

The 70-100 hour values are acquisition planning ranges derived from the scale
of ACMID's seven-class cleaned corpus. They are not scientific pass thresholds.
The final sufficiency decision also requires source diversity, label precision,
held-out coverage, and a learning-curve analysis. Synthetic exposure does not
replace real multitrack diversity.

## Diagnosis

The main blocker is no longer broad model discovery. The blocker is freezing a
valid real-audio benchmark and model-input contract, then converting
recoverable audio into five clean, balanced, reproducible corpora and running a
research-faithful specialist training and qualification process. Piano becomes
a sixth specialist only if the frozen benchmark rejects its current owner.

Previous work lost time for four reasons:

- It changed architecture before closing the data and benchmark contracts.
- It treated short training runs as evidence of final model quality.
- It mixed catalogued data, locally available data, and training-ready data.
- It allowed several roadmap files to make incompatible claims.

## Guiding policies

These policies govern every decision in the roadmap.

- Use ACMID's high-confidence data-cleaning lesson with X-LANCE's independent
  single-target BS-RoFormer training pattern.
- Keep pretrained owners when they pass the same benchmark. Don't retrain a
  strong stem merely to make the architecture look uniform.
- Train one specialist per missing target: acoustic guitar, electric guitar,
  synth, strings, and wind and brass.
- Train piano as a sixth specialist only if the frozen benchmark rejects its
  current owner.
- Match training input to runtime input. The original mixture is the safe
  default because it cannot discard target energy and matches the released
  X-LANCE training pattern. A predicted parent requires a later, separately
  versioned dataset, model, benchmark, and release.
- Freeze evaluation data before full training and never tune against the test
  set.
- Require real multitrack data to be the majority of every full corpus.
- Keep research-only rights separate from redistributable and commercial
  rights. Rights don't block private experiments, but unresolved rights block
  public checkpoint or commercial product release.
- Resolve initialization-checkpoint use and redistribution rights before full
  training so the project doesn't produce a checkpoint it cannot ship.
- Make every dataset, training run, checkpoint, benchmark, and model release
  immutable and content-addressed.
- Spend GPU credit only after data, model initialization, one-batch execution,
  and resume behavior pass no-spend or minimal-spend preflight.
- Reject or hide a weak stem. Never publish a plausible filename as a
  successful separation.
- Use one cloud and self-hosted API contract. Change providers behind
  interfaces, not in the user contract.

## Locked research architecture

The target Pro-12 runtime provisionally uses eight checkpoints. It uses nine if
the frozen benchmark rejects the current piano owner. This decision remains
locked until higher-level evidence on the frozen benchmark disproves it.

| Checkpoint role | Outputs owned |
| --- | --- |
| Mel-Band RoFormer | Vocals and instrumental |
| BS-RoFormer SW | Drums, bass, piano, and internal routing parents |
| MDX23C DrumSep | Kick and snare |
| Conditional piano BS-RoFormer specialist | Piano, only if the current owner fails |
| Acoustic-guitar BS-RoFormer specialist | Acoustic guitar |
| Electric-guitar BS-RoFormer specialist | Electric guitar |
| Synth BS-RoFormer specialist | Synth |
| Strings BS-RoFormer specialist | Strings |
| Wind-and-brass BS-RoFormer specialist | Wind and brass |

The new specialists use single-target heads and receive the original mixture
for the first release. ACMID's joint seven-output SCNet is not the production
architecture because ACMID did not compare it against X-LANCE-style
specialists. ACMID remains the reference for classifier-based cleaning and
data-scale evidence.

## Evidence hierarchy

Use evidence in this order when resolving a disagreement.

1. A reproducible result on the frozen project benchmark.
2. A primary paper result reproduced from its pinned official repository.
3. A primary paper result that has not yet been reproduced locally.
4. A released checkpoint with a documented dataset and license.
5. A community report or listening impression.
6. A hypothesis.

Lower-level evidence may justify an experiment. It may not overturn higher-level
evidence or qualify a production model.

## Phase 0: Freeze decisions and preserve the research state

This phase prevents another architecture reset while work is running. It
records exactly what is being built, what is historical, and what can spend
money.

- [ ] `P0-01` Approve this roadmap as the sole execution authority.
- [ ] `P0-02` Mark `PROVEN_12_STEM_MODEL_PLAN.md` as superseded because it
  selects a joint ACMID SCNet.
- [ ] `P0-03` Mark the model sections of
  `ROAD_TO_SERIES_A_PLAN.md` as subordinate to this roadmap.
- [ ] `P0-04` Record the final 12-stem hierarchy in the product contract and
  API capability schema.
- [ ] `P0-05` Preserve failed checkpoints, logs, and benchmark reports as
  negative evidence outside production selection.
- [ ] `P0-06` Create a clean source snapshot for research reproducibility
  without deleting or reverting the current dirty worktree.
- [ ] `P0-07` Pin the exact commits of X-LANCE, ACMID, the training framework,
  model architecture code, and metric implementations.
- [ ] `P0-08` Create one decision record for the provisional eight-checkpoint
  architecture and the benchmark-triggered ninth piano specialist.
- [ ] `P0-09` Create a budget envelope for data transfer, storage, training,
  benchmark inference, and commercial comparison.
- [ ] `P0-10` Define the maximum automatic spend per run and require a new
  approval when a run would exceed it.
- [ ] `P0-11` Freeze current rejected profiles so they cannot enter the default
  API or UI through configuration drift.
- [ ] `P0-12` Resolve use, derivative-work, redistribution, and commercial
  rights for every current runtime and initialization checkpoint. Record
  `allowed`, `research_only`, or `blocked`; don't leave `unknown`.
- [ ] `P0-13` Classify each dataset source separately for private research,
  checkpoint redistribution, and commercial service use.
- [ ] `P0-14` Freeze a model-input contract. Use the original mixture by
  default, and list every proposed predicted-parent route as unqualified.
- [ ] `P0-15` Defer predicted-parent routing until after the first
  original-mixture specialist release. Any later parent route requires a new
  dataset, model, benchmark, and release rather than an in-place switch.
- [ ] `P0-16` Record that Pro-12 cannot release unless the current piano owner
  passes Phase 1 or a qualified piano specialist replaces it.

**Exit gate:** One approved contract, one model architecture, one research
snapshot, one budget, resolved checkpoint rights, one model-input contract, and
no contradictory active plan.

**Stop condition:** If reviewers cannot agree on the stem hierarchy, evidence
standard, or model ownership, stop before acquiring more data or running GPUs.

## Phase 1: Freeze the benchmark before training

This phase creates the test that decides whether training succeeded. Training
must not begin until the benchmark is immutable and leakage-free.

- [ ] `P1-00` Recover, checksum, read back, and protect the benchmark source
  audio before attempting baseline or commercial-service inference.
- [ ] `P1-01` Define a composition-disjoint benchmark from real stereo
  44.1 or 48 kHz multitrack songs. Keep 16 kHz BabySlakh as a smoke fixture,
  not the release benchmark.
- [ ] `P1-02` Perform a sample-size and power analysis for objective and
  listening comparisons. Use at least 30 songs and expand until every target
  has enough positive and absent examples for the declared confidence rule.
- [ ] `P1-03` Balance genres, production styles, recording quality, instrument
  prominence, polyphony, and acoustic versus electronic timbres.
- [ ] `P1-04` Record exact source projects, song identifiers, licenses,
  checksums, sample rates, channels, and target mappings.
- [ ] `P1-05` Fingerprint every composition and prohibit related performances,
  stems, renders, or excerpts from entering training.
- [ ] `P1-06` Keep validation and test sets separate. Use validation for
  checkpoint selection and test only for final qualification.
- [ ] `P1-07` Freeze current model outputs as baselines before new training.
- [ ] `P1-08` Acquire matched LALAL.AI outputs for the same test excerpts under
  a documented comparison protocol.
- [ ] `P1-09` Define stem-specific primary and secondary metrics before seeing
  new model results.
- [ ] `P1-10` Replace mono truncation scoring with delay-aligned stereo SDR and
  SI-SDR improvement. Record alignment policy and reject invalid length or
  channel mismatches.
- [ ] `P1-11` Add hierarchy checks for vocals plus instrumental, drums versus
  kick and snare, and specialist outputs versus their parent.
- [ ] `P1-12` Define blind listening forms with randomized model identity,
  loudness matching, and no visual clues.
- [ ] `P1-13` Validate the entire benchmark pipeline against synthetic fixtures
  with known perfect, silent, copied-mixture, and swapped-stem failures.
- [ ] `P1-14` Generate a signed benchmark manifest and prevent later mutation.
- [ ] `P1-15` Measure a full target-to-output bleed matrix, target retention,
  artifact severity, lower-tail performance, and reconstruction error.
- [ ] `P1-16` Include target-absent songs and measure false-positive energy for
  every optional specialist output.
- [ ] `P1-17` Report confidence intervals and paired per-song deltas instead of
  treating songs as unrelated aggregate samples.
- [ ] `P1-18` Freeze original-mixture input for the first specialist dataset,
  training, qualification, and inference release.
- [ ] `P1-19` Decide the piano owner. If current BS-RoFormer piano fails the
  frozen internal gate, add a piano specialist corpus and training run.
- [ ] `P1-20` Hash the scorer container, dependency versions, resampling
  implementation, alignment implementation, and metric configuration.

The release threshold for every new specialist must include all of these
conditions:

- Positive median and aggregate SI-SDR improvement over the input baseline.
- No catastrophic lower-tail regression beyond the frozen stem-specific floor.
- Improvement over the strongest available open baseline on the same songs.
- No material regression in parent reconstruction or adjacent-stem leakage.
- Majority blind preference over the open baseline.

The public claim "better than LALAL.AI" additionally requires a matched blind
producer study. Each advertised stem must exceed 50 percent preference with a
predeclared confidence rule. Aggregate preference cannot hide a failed stem.

**Exit gate:** Real benchmark assets, the benchmark manifest, stereo metric
code, baseline outputs, listening protocol, input-routing decision, piano-owner
decision, and promotion thresholds are frozen and reproducible.

**Stop condition:** If fewer than 15 real positives exist for a target, add
test material. Don't weaken the gate or reuse training songs.

## Phase 2: Recover and secure the data plane

This phase turns catalogued data into readable, checksum-verified source
material. A manifest entry is not a usable training asset.

- [ ] `P2-01` Choose durable training-data storage independent of the suspended
  B2 account, or restore B2 and prove byte read-back.
- [ ] `P2-02` Reconcile local, Modal Volume, object-store, and provider copies
  into one inventory without deleting unique files.
- [ ] `P2-03` Reacquire selected RawStems archives and verify provider and local
  checksums.
- [ ] `P2-04` Reacquire locally removed QuartSet, TinySOL, ChoraleBricks, and
  other accepted sources needed by active manifests.
- [ ] `P2-05` Resolve MoisesDB and MedleyDB research access or mark them
  unavailable with evidence.
- [ ] `P2-06` Materialize only selected source subsets when full archives add
  no training value.
- [ ] `P2-07` Record provider, version, retrieval date, checksum, byte count,
  rights status, and local/object URI for every source object.
- [ ] `P2-08` Run read-back verification before deleting any local source.
- [ ] `P2-09` Define retention, backup, and restore behavior for irreplaceable
  source data, cleaned corpora, checkpoints, and benchmark assets.
- [ ] `P2-10` Complete one restore drill from the selected durable store.

**Exit gate:** Every item referenced by an active corpus manifest is readable,
checksum-verified, recoverable, and associated with provenance and rights
metadata.

**Stop condition:** Don't upload the same unverified archive repeatedly. Fix
the provider, credential, lifecycle, or storage failure first.

## Phase 3: Complete the specialist corpora

This phase fills the actual data deficits. Dataset completion is based on
target-active audio, verified label precision, source diversity, and benchmark
coverage, not archive size. The hour ranges are acquisition budgets based on
ACMID-scale evidence, not automatic pass conditions.

### Locked acquisition order

Use one fixed source ladder. Do not search random dataset marketplaces before
exhausting these sources.

1. Recover the X-LANCE-curated RawStems lists for all five families. The pinned
   lists contain 167 acoustic-guitar songs, 414 electric-guitar songs, 254
   synth songs, 109 string songs, and 93 wind-and-brass songs.
2. Add MoisesDB and MedleyDB 2.0 as high-precision taxonomy anchors and
   real-production diversity. They contain source tracks and instrument labels,
   but they aren't individually large enough to supply every 70-hour target.
3. Add real specialist corpora: GAPS and GuitarSet for acoustic guitar;
   Guitar-TECHS, EG-IPT, GOAT, and AlbumDB for electric guitar; and URMP,
   Spheres, QuartSet, and ChoraleBricks for orchestral families.
4. Measure accepted target-active hours after decoding, deduplication, label
   cleaning, and split assignment. Measure the remaining deficit instead of
   estimating it from archive size.
5. Fill only the measured deficit with the ACMID multilingual web-crawl
   workflow. Use pinned queries and per-item provenance. Clean acoustic guitar,
   electric guitar, strings, and wind and brass with the pinned ACMID Dasheng
   heads. Clean synth with the locked Essentia MTG-Jamendo instrument model and
   the human-review policy in Phase 4.
6. Use Slakh2100, SynthSOD, CocoChorales, NSynth, TinySOL, and rendered sample
   libraries only for train-set augmentation. Never count them toward accepted
   clean real hours or independent real projects.

This order follows the strongest reproducible evidence available to the
project. X-LANCE used manually cleaned RawStems plus MoisesDB. ACMID showed that
multilingual web collection followed by classifier cleaning can turn 4,643.51
raw hours into 737.35 accepted hours. That observed aggregate yield is about
15.9 percent, so a remaining 70-hour deficit can require roughly 440 raw
candidate hours before class-specific variation. The crawler must therefore
budget from the measured accepted-hour gap, not from download volume.

- [ ] `P3-SRC-01` Extend the RawStems curation manifest from the old
  three-family selection to the pinned acoustic-guitar and synth lists.
- [ ] `P3-SRC-02` Download and verify RawStems, MoisesDB, MedleyDB, and the
  specialist real-recording sources before starting a new web crawl.
- [ ] `P3-SRC-03` Produce an accepted-hour deficit report for all five families.
- [ ] `P3-SRC-04` Generate frozen multilingual query manifests sized from each
  measured deficit and the observed cleaner yield.
- [ ] `P3-SRC-05` Stop acquisition for a family only after its accepted hours,
  project diversity, hard-negative coverage, and held-out split gates pass.

### Acoustic-guitar corpus

The acoustic-guitar corpus starts from zero prepared hours and is a critical
path blocker.

- [ ] `P3-AG-01` Build toward the 70-100+ clean real target-active-hour
  planning range while tracking marginal source and timbre coverage.
- [ ] `P3-AG-02` Include at least 30 independent recording projects and at
  least 20 performers where source metadata permits.
- [ ] `P3-AG-03` Balance steel-string, nylon-string, strummed, picked, solo,
  ensemble, miked, pickup, dry, and reverberant examples.
- [ ] `P3-AG-04` Include hard negatives such as clean electric guitar, harp,
  piano, and bright percussion.

### Electric-guitar corpus

Electric guitar is closest to full scale but still requires more real songs and
high-confidence cleaning.

- [ ] `P3-EG-01` Recover all 54.143 catalogued real train hours.
- [ ] `P3-EG-02` Add clean real data toward the 70-100+ hour planning range
  without weakening source diversity or label precision.
- [ ] `P3-EG-03` Balance clean, distorted, lead, rhythm, DI, amplified,
  effects-heavy, muted, and sustained playing.
- [ ] `P3-EG-04` Prevent synchronized microphone and DI views from being
  counted as independent compositions.
- [ ] `P3-EG-05` Keep articulation datasets from one performer or studio as
  train-only augmentation.

### Conditional piano corpus

This corpus is required only if `P1-19` rejects the current piano owner.

- [ ] `P3-PI-01` If triggered, build a clean real piano corpus toward the
  ACMID-scale planning range.
- [ ] `P3-PI-02` Balance acoustic grand, upright, electric piano, dry, room,
  solo, ensemble, percussive, and sustained material.
- [ ] `P3-PI-03` Add hard negatives from mallet percussion, guitar, harp,
  organ, and harmonically dense synths.

### Synth corpus

The synth corpus starts from zero prepared hours and must follow the
RawStems-plus-MoisesDB lesson rather than the rejected inference chain.

- [ ] `P3-SY-01` Build toward the 70-100+ clean real target-active-hour
  planning range while tracking timbre and production coverage.
- [ ] `P3-SY-02` Cover pads, leads, bass-like synths, arpeggios, plucks,
  sustained chords, effects, analog, digital, and heavily processed timbres.
- [ ] `P3-SY-03` Define and enforce the boundary between synth, keyboard,
  electric piano, organ, and sound effects.
- [ ] `P3-SY-04` Include hard negatives from piano, strings, distorted guitar,
  and electronic percussion.
- [ ] `P3-SY-05` Create a manually verified cleaner-calibration set with diverse
  synth positives, target-absent songs, and confusable negatives. Keep it
  separate from separation validation and test songs.

### Strings corpus

The current strings corpus is synthetic-majority. Full training requires real
multitrack expansion.

- [ ] `P3-ST-01` Recover all 9.368 catalogued real train hours.
- [ ] `P3-ST-02` Add clean real data toward the 70-100+ hour planning range.
- [ ] `P3-ST-03` Balance solo and ensemble violin, viola, cello, double bass,
  pizzicato, bowed, sustained, and orchestral textures.
- [ ] `P3-ST-04` Keep real multitracks as the sampling majority for the first
  release. Defer synthetic-ratio ablations until after the faithful baseline
  qualifies or fails.
- [ ] `P3-ST-05` Add hard negatives from synth pads, choir, and sustained
  guitar.

### Wind-and-brass corpus

The current wind-and-brass corpus is also synthetic-majority and contains
several acoustically distinct families.

- [ ] `P3-WB-01` Recover all 8.917 catalogued real train hours.
- [ ] `P3-WB-02` Add clean real data toward the 70-100+ hour planning range.
- [ ] `P3-WB-03` Balance trumpet, trombone, horn, tuba, saxophone, flute,
  clarinet, oboe, bassoon, solo, section, and ensemble recordings.
- [ ] `P3-WB-04` Prevent one synthetic library or one ensemble from dominating
  sampled exposure.
- [ ] `P3-WB-05` Add hard negatives from vocals, strings, synth leads, and
  distorted guitar.

**Exit gate:** Each required specialist has a recoverable real-majority corpus,
passes the predeclared label-precision and diversity matrix, has no dominant
duplicate source, and uses only the Phase 1 composition-disjoint held-out set.
The report must explain any corpus below or above the planning range.

**Stop condition:** Don't start a full training run for a family whose real
data target, diversity matrix, or held-out set is incomplete.

## Phase 4: Clean, split, and release the training datasets

This phase converts source audio into immutable dataset releases. It applies
machine cleaning and human auditing without silently discarding difficult but
correct examples.

- [ ] `P4-01` Finish the official Dasheng base checkpoint plus AudioSet overlay
  sequence required by ACMID's cleaners.
- [ ] `P4-02` Reproduce the released ACMID classifier behavior on known
  positives and negatives before using it as a filter.
- [ ] `P4-03` Reproduce ACMID's published 0.995 operating point, then calibrate
  and report precision and recall separately for every source and target.
  Don't assume one threshold transfers unchanged.
- [ ] `P4-04` Use the pretrained Essentia MTG-Jamendo instrument classifier as
  the only synth cleaner. Don't evaluate or train another synth classifier in
  this research cycle.
- [ ] `P4-04A` Define the synth-family score from the published
  `synthesizer`, `pad`, `sampler`, and approved related outputs, while treating
  `keyboard`, `organ`, `electricpiano`, percussion, and effects as explicit
  confusable categories.
- [ ] `P4-04B` Calibrate automatic-accept, automatic-reject, and manual-review
  thresholds once on `P3-SY-05`. Calibration routes uncertainty; it does not
  select between models.
- [ ] `P4-04C` Automatically accept only high-confidence synth chunks,
  automatically reject clear negatives, and manually review every uncertain or
  conflicting chunk.
- [ ] `P4-04D` Manually audit a stratified sample of automatic accepts and
  rejects to detect systematic subtype errors before freezing the corpus.
- [ ] `P4-04E` Record Essentia's `CC BY-NC-SA 4.0` restriction, attribution,
  model hash, thresholds, and cleaner configuration. Keep the cleaned dataset
  and resulting synth checkpoint research-only until commercial rights are
  resolved.
- [ ] `P4-05` Decode every accepted file and reject unreadable, truncated,
  silent, clipped beyond tolerance, or invalid-channel audio.
- [ ] `P4-06` Normalize metadata and channel layout without destructively
  loudness-normalizing the source waveform.
- [ ] `P4-07` Verify target and mixture alignment when both are supplied.
- [ ] `P4-08` Detect exact and near-duplicate audio before splitting.
- [ ] `P4-09` Group alternate renders, excerpts, stems, microphone views, and
  performances of one composition before assigning splits.
- [ ] `P4-10` Separate real multitracks, isolated-note augmentation, synthetic
  renders, and hard negatives in the manifest.
- [ ] `P4-11` Generate mixtures online or from a versioned recipe so the same
  random seed reproduces each example.
- [ ] `P4-12` Use original mixtures for the first specialist dataset release.
  Don't generate predicted-parent training data in this research cycle.
- [ ] `P4-13` Prevent target leakage, source-target swaps, and validation or
  test compositions from entering training or augmentation pools.
- [ ] `P4-14` Manually audit a statistically useful stratified sample of
  accepted, rejected, and borderline items for every source and class.
- [ ] `P4-15` Measure classifier precision, rejection error, source balance,
  performer balance, target-active duration, and synthetic sampling share.
- [ ] `P4-16` Publish one immutable dataset card, JSONL or CSV index, split
  manifest, checksums, source receipt set, and cleaning report per specialist.
- [ ] `P4-17` Materialize one GPU-readable cache per dataset release and prove
  deterministic restoration from the canonical source objects.

**Exit gate:** Five mandatory and any triggered piano dataset releases pass
integrity, calibrated purity, diversity, split-leakage, materialization, and
restore checks.

**Stop condition:** If manual precision is below the predeclared threshold,
fix labels or the cleaner. Don't compensate by increasing hours with noisy
data.

## Phase 5: Lock the training system

This phase proves that the training implementation matches the selected
research pattern before expensive runs begin.

- [ ] `P5-01` Pin and use the official X-LANCE trainer. If the existing MSST
  worker remains, prove data, forward, loss, optimizer, scheduler, checkpoint,
  and validation parity before using it.
- [ ] `P5-02` Define the exact initialization checkpoint for each specialist:
  SW guitar for acoustic and electric guitar, first-stage X-LANCE synth for
  synth, first-stage orchestra for strings and wind and brass, and a pinned
  piano owner if `P1-19` triggers it. Record checkpoint hashes and rights.
- [ ] `P5-03` Prove state-dict key, tensor-shape, stem-head, sample-rate, and
  channel compatibility for every initialization.
- [ ] `P5-04` Extract and hash one per-stem config from the pinned official
  source. Preserve each model's sample rate, segment length, effective batch
  size, precision, optimizer, and L1 plus multi-resolution STFT settings rather
  than imposing one universal recipe.
- [ ] `P5-05` Freeze learning rate, scheduler, gradient accumulation, clipping,
  augmentation, validation cadence, checkpoint cadence, and random seeds in
  versioned configs.
- [ ] `P5-06` Use original mixtures exactly as frozen by `P1-18`.
- [ ] `P5-07` Build a reproducible container with pinned CUDA, PyTorch, audio
  libraries, architecture code, and metric versions.
- [ ] `P5-08` Run a CPU or minimal-GPU one-batch forward, loss, backward,
  optimizer, validation, checkpoint, and resume test for every required config.
- [ ] `P5-09` Overfit four to eight examples as a wiring test. Use this only to
  prove the model can learn and the target isn't swapped.
- [ ] `P5-10` Verify interrupted-job resume without resetting optimizer,
  scheduler, scaler, global step, best-checkpoint state, random generators, or
  sampler and data-loader cursor.
- [ ] `P5-11` Record GPU memory, examples per second, estimated full-run hours,
  storage growth, and cost for each family.
- [ ] `P5-12` Set failure alerts for NaN loss, silent targets, zero gradients,
  exploding gradients, data starvation, corrupt batches, and stalled
  checkpoints.
- [ ] `P5-13` Produce one signed preflight report covering every required
  family.
- [ ] `P5-14` Create an immutable run specification keyed by code, container,
  dataset, initialization, config, seed, and run hash.
- [ ] `P5-15` Add exclusive run leases and retry-safe attempt identifiers so
  two workers cannot write the same run.
- [ ] `P5-16` Write checkpoints atomically to object storage and never overwrite
  a completed step or run configuration.

The overfit test and one-batch test are wiring tests, not pilot quality
experiments. There will be no repeated 25-step or 1,000-step quality loop.

**Exit gate:** Every required configuration passes official-trainer or parity,
one-batch, overfit, checkpoint, immutable-attempt, exact-resume, metric, memory,
and cost preflight using the production dataset format.

**Stop condition:** Any mismatch, NaN, resume error, target swap, or unexpected
memory estimate blocks all full runs until the root cause is fixed.

## Phase 6: Run full specialist training

This phase executes the evidence-backed full runs. Runs may execute in parallel
only when the budget and GPU quota permit it.

- [ ] `P6-01` Train acoustic guitar with its frozen per-stem schedule.
- [ ] `P6-02` Train electric guitar with its frozen per-stem schedule.
- [ ] `P6-03` Train synth with its frozen per-stem schedule.
- [ ] `P6-04` Train strings with its frozen per-stem schedule.
- [ ] `P6-05` Train wind and brass with its frozen per-stem schedule.
- [ ] `P6-05A` If `P1-19` triggered it, train piano with its frozen per-stem
  schedule.
- [ ] `P6-06` Persist configs, code commit, dataset release, initialization
  hash, environment digest, seed, logs, metrics, checkpoints, and cost receipt
  for every run.
- [ ] `P6-07` Evaluate on validation at the frozen cadence without touching
  the final test set.
- [ ] `P6-08` Keep best-validation and latest-resumable checkpoints separate.
- [ ] `P6-09` Monitor loss components, SDR trend, leakage, silence rate,
  throughput, VRAM, data-loader utilization, and cost.
- [ ] `P6-10` Resume interrupted runs from the last complete checkpoint rather
  than restarting and charging twice.
- [ ] `P6-11` Run a second seed only when the first result is near the promotion
  boundary or shows unexplained instability.

Use the pinned source schedules to define a minimum, maximum, and
validation-based stopping rule per stem. The current planning envelope is
200,000 to 1,000,000 optimizer steps, not a promise that every model stops at
200,000. Replace all GPU-hour and cost estimates with measured Phase 5
throughput before launching.

**Exit gate:** Every required model has a complete reproducible training
receipt, immutable attempts, and a best-validation checkpoint.

**Stop condition:** Stop a run only for numerical failure, corrupt data,
persistent validation collapse, exhausted budget, or a predeclared early-stop
rule. Don't stop because early audio sounds imperfect.

## Phase 7: Qualify every trained specialist

This phase determines which models are good enough to own a public stem. It
does not assume that completing training guarantees promotion.

- [ ] `P7-01` Evaluate every eligible checkpoint on the frozen validation set.
- [ ] `P7-02` Select one checkpoint per family using only predeclared
  validation criteria.
- [ ] `P7-03` Evaluate the selected checkpoint once on the frozen test set.
- [ ] `P7-04` Compare each specialist with the input baseline, current open
  candidates, relevant ACMID result, and matched LALAL.AI output.
- [ ] `P7-05` Report median, mean, aggregate, lower decile, worst segment, and
  positive-song win rate instead of one headline average.
- [ ] `P7-06` Measure target retention, non-target bleed, musical-noise
  artifacts, transient damage, stereo image, and parent consistency.
- [ ] `P7-07` Run loudness-matched blind listening with at least three trained
  listeners during internal qualification.
- [ ] `P7-08` Investigate genre and instrumentation slices so one dominant
  domain cannot hide failures elsewhere.
- [ ] `P7-09` Mark every stem `accepted`, `experimental`, or `rejected` with
  evidence and a reason.
- [ ] `P7-10` Update the qualification ledger atomically with checkpoint hashes
  and benchmark report hashes.
- [ ] `P7-11` Calibrate target-presence confidence on positive and absent songs;
  report precision, recall, and false-positive energy for the selected
  threshold.
- [ ] `P7-12` Measure sibling duplication for acoustic versus electric guitar
  and synth versus strings versus wind and brass.
- [ ] `P7-13` Require the piano owner, whether current or newly trained, to pass
  the same internal and listening gates as every other Pro stem.

**Exit gate:** Every specialist has a signed qualification decision. Only
accepted checkpoints may proceed to product integration.

**Stop condition:** Don't patch routing or post-processing to hide a rejected
model. Diagnose whether the failure is data, initialization, optimization, or
architecture, then open a new evidence-backed research cycle.

## Phase 8: Create immutable model releases

This phase converts accepted research checkpoints into deployable model
releases with traceable ownership.

- [ ] `P8-01` Register each accepted checkpoint with its model family, stem,
  parent input, code commit, config, dataset release, metrics, license, hash,
  size, VRAM, and runtime.
- [ ] `P8-02` Export or package checkpoints without changing numerical output.
- [ ] `P8-03` Verify full-song chunking, overlap, windowing, and stitching
  against direct short-clip inference.
- [ ] `P8-04` Run CPU metadata loading and target GPU numerical parity checks.
- [ ] `P8-05` Scan model artifacts and containers for secrets or unexpected
  executable content.
- [ ] `P8-06` Upload models to durable private storage and verify read-back.
- [ ] `P8-07` Define model cache eviction, warm-start, rollback, and previous
  release retention.
- [ ] `P8-08` Sign one release manifest for the complete eight- or
  nine-checkpoint graph.
- [ ] `P8-09` Pin `release_id`, graph version, container digest, preprocessing
  version, metric version, and every checkpoint hash on each job.
- [ ] `P8-10` Implement rollback by changing one active-release pointer for new
  jobs. Existing jobs remain pinned to their original release.

**Exit gate:** One immutable model release manifest can recreate every
production checkpoint and identify its evidence.

**Stop condition:** A checkpoint with unknown hash, source dataset, license,
or qualification report cannot enter production storage.

## Phase 9: Integrate the hierarchical inference graph

This phase wires accepted models into one coherent audio graph. It avoids
running unrelated models or mixing independent outputs without ownership.

The intended graph is:

```text
input song
  -> Mel-Band RoFormer
     -> vocals
     -> instrumental
  -> BS-RoFormer SW
     -> drums
     -> bass
     -> piano
  -> MDX23C DrumSep
     -> kick
     -> snare
  -> acoustic-guitar specialist
  -> electric-guitar specialist
  -> synth specialist
  -> strings specialist
  -> wind-and-brass specialist
```

This is a semantic hierarchy, not an assumption that every child consumes a
predicted parent. The original mixture is the default input for each branch.
Predicted-parent routing is outside the first specialist release.

The integration tasks are:

- [ ] `P9-01` Make the release manifest, not ad hoc worker code, select model
  owners and checkpoint versions.
- [ ] `P9-02` Run each first-release specialist on the original mixture used
  during training.
- [ ] `P9-03` Preserve the broad instrumental parent so unresolved instruments
  are never discarded.
- [ ] `P9-04` Define and test sibling-overlap handling for acoustic and electric
  guitar without assuming an unreliable broad-guitar parent.
- [ ] `P9-05` Define and test sibling-overlap handling for synth, strings, and
  wind and brass without assuming an unreliable `other` parent.
- [ ] `P9-06` Apply phase-consistent parent constraints only when the frozen
  benchmark proves they improve quality.
- [ ] `P9-07` Attach confidence, qualification status, model release, parent,
  timings, and warnings to every artifact.
- [ ] `P9-08` Suppress or label outputs below the release confidence floor.
- [ ] `P9-09` Keep experimental remote adapters and rejected models outside the
  default graph.
- [ ] `P9-10` Cache only qualified shared computations. Key caches by job,
  source hash, release, graph, preprocessing, and model hash.
- [ ] `P9-11` Parallelize independent branches within measured GPU memory and
  provider concurrency limits.
- [ ] `P9-12` Verify chunk boundaries, phase, sample count, channel count,
  sample rate, clipping, silence, and file integrity.
- [ ] `P9-13` Generate hierarchical metadata that tells users which stems may
  be recombined.
- [ ] `P9-14` Benchmark cold, warm, short-song, long-song, and concurrent
  latency plus actual provider cost.
- [ ] `P9-15` Specify any residual projection equation, reconstruction-error
  limit, clipping limit, and rollback rule before enabling it.
- [ ] `P9-16` Keep intermediate caches job-scoped and encrypted by default.
  Define ownership, expiration, invalidation, and deletion behavior.
- [ ] `P9-17` Make the Phase 9 latency-and-cost harness the sole measurement
  implementation reused by cloud and beta qualification.

**Exit gate:** The complete graph reproduces offline checkpoint quality,
publishes correct hierarchy metadata, and passes latency, cost, and integrity
gates.

**Stop condition:** If integration quality is lower than standalone quality,
fix parent routing, chunking, normalization, or overlap handling before adding
another model.

## Phase 10: Complete the user-facing API and artifact contract

This phase exposes the qualified graph without leaking internal model
complexity into the user experience.

- [ ] `P10-01` Expose three truthful modes: Fast Split, Studio Split, and Pro
  Split.
- [ ] `P10-02` Define Fast Split as vocals, instrumental, drums, and bass.
- [ ] `P10-03` Define Studio Split as Fast Split plus kick and snare.
- [ ] `P10-04` Enable Pro Split only when all required specialist gates pass.
- [ ] `P10-05` Keep piano or broad guitar in Labs if their internal benchmark
  remains weak.
- [ ] `P10-06` Accept direct upload and approved song-import sources through
  one normalized input contract.
- [ ] `P10-07` Validate format, duration, size, decodeability, and ownership
  before queue admission.
- [ ] `P10-08` Return durable job identifiers, truthful state transitions,
  progress, cancellation, and failure reasons.
- [ ] `P10-09` Publish individual WAVs, a manifest, playback metadata, and ZIP
  archives through signed artifact URLs.
- [ ] `P10-10` Include hierarchy, model release, confidence, quality status,
  duration, sample rate, and channel metadata in the manifest.
- [ ] `P10-11` Preserve backward compatibility or provide a versioned API
  migration for existing clients.
- [ ] `P10-12` Generate and validate OpenAPI plus typed frontend clients.
- [ ] `P10-13` Prevent an unqualified release from becoming user-selectable.
- [ ] `P10-14` Give Fast, Studio, and Pro independent release flags so missing
  Pro specialists cannot block a qualified Fast or Studio release.

**Exit gate:** One upload or import produces a truthful, cancellable job and
the correct qualified artifacts through both API and UI contracts.

**Stop condition:** Don't expose profile names, checkpoint names, or rejected
stems as product features.

## Phase 11: Finish the cloud execution path

This phase makes the existing FastAPI, PostgreSQL, queue, object storage, and
Modal boundaries safe for real users.

- [ ] `P11-01` Add explicit PostgreSQL schemas for jobs, attempts, artifacts,
  model releases, usage ledger, audit events, outbox records, and deletion
  sagas. Keep FastAPI stateless and PostgreSQL authoritative.
- [ ] `P11-02` Create jobs and outbox records in one transaction. Treat Redis
  and RQ as replaceable transport, not canonical state.
- [ ] `P11-03` Make Modal authentication mandatory and fail closed in every
  non-local environment.
- [ ] `P11-04` Allow credentials only for configured trusted artifact origins.
  Reject or fetch untrusted absolute URLs without authorization headers.
- [ ] `P11-05` Use private object storage for inputs and outputs with
  least-privilege credentials and short-lived signed URLs.
- [ ] `P11-06` Define unique idempotency and completion keys for job creation,
  dispatch, artifact publication, usage charging, retries, and callbacks.
- [ ] `P11-07` Add attempt leases and monotonic fencing tokens. Reject
  completion, heartbeat, or publication from a superseded attempt.
- [ ] `P11-08` Prove cancellation while queued, dispatching, running,
  finalizing, retrying, reconciling, and recovering.
- [ ] `P11-09` Implement deletion as a durable tombstoned saga across
  PostgreSQL, object storage, temporary uploads, Modal Volumes, manifests,
  archives, and caches.
- [ ] `P11-10` Enforce per-user concurrency, global backpressure, duration,
  upload-size, and spend limits.
- [ ] `P11-11` Use the Phase 9 harness to measure real warm and cold p50, p95,
  and p99 latency and cost for each product mode.
- [ ] `P11-12` Set autoscaling and concurrency from measured VRAM and provider
  quota rather than assumed 50,000-user demand.
- [ ] `P11-13` Reconcile provider invoices with per-job usage receipts.
- [ ] `P11-14` Define and test every allowed job and attempt transition,
  including terminal-state immutability.
- [ ] `P11-15` Make outbox delivery at-least-once and worker effects idempotent;
  prove duplicate messages cannot duplicate GPU work or charges.
- [ ] `P11-16` Clean abandoned direct uploads and objects that never acquired a
  valid job owner.
- [ ] `P11-17` Cancel or fence reconciliation and recovery work when the owning
  job is cancelled or deleted.

Initial target service levels are:

| Mode | Four-minute p95 target | Variable cost target |
| --- | ---: | ---: |
| Fast Split | Under 90 seconds | Under $0.05 |
| Studio Split | Under 150 seconds | Under $0.12 |
| Pro Split | Set after required-specialist profiling | Must support positive margin |

**Exit gate:** Managed-provider drills prove secure, idempotent, recoverable,
bounded-cost processing under the agreed concurrency model.

**Stop condition:** Don't replace RQ, PostgreSQL, Modal, or object storage
because another tool appears fashionable. Replace a component only after a
measured failure and a passing migration proof.

## Phase 12: Finish the self-hosted execution path

This phase gives local users the same separation and artifact contract without
depending on Modal or the cloud control plane.

- [ ] `P12-01` Provide a versioned Docker Compose deployment for API, worker,
  PostgreSQL, queue, and optional S3-compatible storage.
- [ ] `P12-02` Provide a local CUDA execution provider that implements the same
  worker contract as Modal.
- [ ] `P12-03` Define supported Linux, NVIDIA driver, CUDA, GPU architecture,
  VRAM, RAM, disk, and CPU requirements.
- [ ] `P12-04` Provide checksum-verified model download, cache, resume, and
  offline import behavior.
- [ ] `P12-05` Support local files and S3-compatible object storage behind the
  same artifact interface.
- [ ] `P12-06` Document GPU-specific concurrency and low-VRAM degradation.
- [ ] `P12-07` Prove install, first run, restart, upgrade, rollback, backup, and
  uninstall on a clean supported machine.
- [ ] `P12-08` Publish model and source licenses plus redistribution
  restrictions.
- [ ] `P12-09` Run the same golden audio and API contract tests used by cloud.

**Exit gate:** A clean supported machine can reproduce the qualified model
release and API contract without hidden cloud dependencies.

**Stop condition:** Don't create a separate self-hosted product fork. Provider
adapters may differ; contracts and release evidence must remain shared.

## Phase 13: Complete security, reliability, and operations

This phase covers the failures that don't appear in a successful local demo.

- [ ] `P13-01` Enforce authentication and tenant ownership on jobs, artifacts,
  events, cancellation, deletion, and imported sources.
- [ ] `P13-02` Run cross-tenant read, write, cancel, delete, and signed-URL
  abuse tests with two managed identities.
- [ ] `P13-03` Validate MIME type by decoding, not filename alone.
- [ ] `P13-04` Scan dependencies, images, secrets, and exposed endpoints.
- [ ] `P13-05` Define retention and deletion policies for source audio,
  artifacts, logs, backups, and training data.
- [ ] `P13-06` Schedule expired-job cleanup and object-store lifecycle rules.
- [ ] `P13-07` Back up PostgreSQL and critical manifests, then pass restoration
  drills.
- [ ] `P13-08` Instrument queue depth, job age, stage latency, GPU utilization,
  errors, retries, cost, artifact failures, and model-release distribution.
- [ ] `P13-09` Add alerts with owners and runbooks for stuck jobs, provider
  outages, elevated failure rate, cost spikes, and storage growth.
- [ ] `P13-10` Add structured logs and correlation identifiers across API,
  queue, worker, object store, and billing.
- [ ] `P13-11` Load-test admission, polling or event delivery, cancellation,
  database transitions, and artifact downloads separately from GPU capacity.
- [ ] `P13-12` Define availability, recovery-time, recovery-point, latency, and
  support objectives appropriate to the current rollout stage.
- [ ] `P13-13` Produce a reproducible signed source and container release from a
  clean repository state.

**Exit gate:** Security and recovery drills pass, observability covers every
job stage, and an operator can diagnose and recover the documented failures.

**Stop condition:** Don't claim 50,000-user readiness from a request-count load
test that excludes GPU capacity, storage, queueing, provider quotas, and cost.

## Phase 14: Run product qualification and beta

This phase verifies that objective model improvements create better outcomes
for artists and producers.

- [ ] `P14-01` Complete the frozen 30-50 song objective benchmark for every
  advertised stem and mode.
- [ ] `P14-02` Run matched LALAL.AI comparisons on the same source excerpts.
- [ ] `P14-03` Run a blinded producer study with at least 20 participants for
  competitive claims.
- [ ] `P14-04` Test full-song workflow with artists and producers, including
  upload, preview, playback, download, import into a DAW, and recombination.
- [ ] `P14-05` Collect stem-level quality, usefulness, failure, latency, and
  willingness-to-pay feedback.
- [ ] `P14-06` Verify users understand the stem hierarchy and don't sum parent
  and child stems together.
- [ ] `P14-07` Measure real per-song compute, storage, egress, support, retry,
  and refund cost.
- [ ] `P14-08` Set pricing and quotas from measured unit economics.
- [ ] `P14-09` Publish truthful limitations and suppress failed specialist
  outputs.
- [ ] `P14-10` Record a release decision for Fast, Studio, and Pro separately.

**Exit gate:** The selected release is objectively qualified, preferred by
target users, understandable, supportable, and economically viable.

**Stop condition:** Don't delay a strong six-stem product because an
unqualified Pro-12 stem failed. Release modes have independent gates.

## Phase 15: Release, monitor, and improve

This phase turns the qualified candidate into an operated product without
weakening the evidence standard after launch.

- [ ] `P15-01` Deploy to staging from the signed release artifact.
- [ ] `P15-02` Run smoke, golden audio, migration, rollback, security, and
  provider-failure tests in staging.
- [ ] `P15-03` Release to a small controlled cohort with explicit capacity and
  spend limits.
- [ ] `P15-04` Monitor quality complaints by stem and model release rather than
  as one generic failure category.
- [ ] `P15-05` Monitor latency, queue age, retries, cost, storage, conversion,
  retention, and cancellation.
- [ ] `P15-06` Roll back automatically or manually when predeclared quality,
  reliability, security, or cost thresholds fail.
- [ ] `P15-07` Expand capacity only after measured demand and provider quotas
  justify it.
- [ ] `P15-08` Maintain a model and dataset improvement backlog grounded in
  failed benchmark slices and user evidence.
- [ ] `P15-09` Re-run the frozen release benchmark for every model, routing,
  preprocessing, chunking, or post-processing change.
- [ ] `P15-10` Publish the LALAL.AI comparison claim only if the matched claim
  gate passes.

**Exit gate:** The product operates within its quality, reliability, security,
latency, and cost objectives over a representative observation period.

**Stop condition:** Don't scale marketing or GPU reservations ahead of observed
retention, quality, and unit economics.

## Critical path and parallel work

The roadmap has four connected but independently releasable paths. A missing
Pro specialist must not block a qualified Fast or Studio release.

The Pro research path is:

```text
P0 decision freeze
  -> P1 benchmark-asset recovery, frozen benchmark, and input decision
  -> P2 recoverable storage
  -> P3 required complete real corpora
  -> P4 immutable cleaned datasets
  -> P5 training preflight
  -> P6 required full training runs
  -> P7 qualification
  -> P8 model release
  -> P9 inference integration
  -> P10 product contract
  -> P14 product qualification
  -> P15 release
```

The Fast and Studio release path is:

```text
P0 contract and rights
  -> P1 qualification of existing owners
  -> P8 immutable release
  -> P9 integration
  -> P10 Fast and Studio contract
  -> P11 cloud control plane
  -> P13 security and operations
  -> P14 product qualification
  -> P15 release
```

The cloud path is:

```text
P8 release manifest
  -> P9 inference contract
  -> P10 API contract
  -> P11 cloud control plane
  -> P13 security, recovery, and operations
  -> P14 cloud beta
  -> P15 cloud release
```

The self-hosted path is:

```text
P8 release manifest
  -> P9 inference contract
  -> P10 API contract
  -> P12 self-hosted provider
  -> P13 shared security and release checks
  -> P14 self-hosted beta
  -> P15 self-hosted release
```

The following work may run in parallel without changing the research decision:

- Platform security, idempotency, cancellation, deletion, and recovery work in
  Phase 11.
- Self-hosted packaging work that uses current qualified models in Phase 12.
- Observability, runbooks, load harnesses, and clean release automation in
  Phase 13.
- Acoustic-guitar, synth, strings, wind-and-brass, and electric-guitar data
  acquisition after Phase 1 freezes composition exclusions.
- The required full training jobs after their individual Phase 4 and Phase 5
  gates pass and the total budget is approved.

## Rabbit-hole prevention rules

These rules stop attractive work that doesn't advance a release gate.

- Don't search for more models while the selected architecture lacks complete
  datasets or a full faithful training run.
- Don't change losses, add LoRA, add ensembles, or invent post-processing
  before the exact baseline recipe completes.
- Don't repeat tiny quality runs. Use one-batch and tiny-overfit tests only for
  wiring, then run the approved full schedule.
- Don't count synthetic hours, isolated-note exposure, alternate microphones,
  or duplicate renders as independent real-song hours.
- Don't improve scores by modifying the test set, excluding hard genres, or
  tuning thresholds after test results are visible.
- Don't make a new stem public because it sounds good on one song.
- Don't wire rejected remote or open models into the default route.
- Don't fine-tune already strong stems until the frozen benchmark proves a
  stem-specific deficiency worth the cost.
- Don't rewrite the platform stack while the current standard kit can pass the
  required safety and scale drills.
- Don't optimize for 50,000 users before the per-job latency and cost model is
  measured, but don't introduce architecture that prevents horizontal scale.
- Don't delete negative results. Record why they failed so the project doesn't
  repeat them.

## Required evidence register

Completion requires these durable artifacts. Paths may be finalized during
implementation, but every artifact must be versioned and referenced here.

| Evidence | Required before |
| --- | --- |
| Approved architecture decision | Data acquisition and training |
| Frozen benchmark manifest and metric protocol | Dataset finalization |
| Source receipts and restore report | Dataset release |
| Required dataset cards, indexes, and cleaning reports | Full training |
| Required training preflight reports | Full training |
| Required full training receipts | Qualification |
| Required signed qualification reports | Model release |
| Eight-checkpoint release manifest | Product integration |
| Inference quality, latency, and cost report | Beta |
| Cross-tenant, recovery, deletion, and billing drills | Public cloud release |
| Clean self-hosted install and upgrade report | Self-hosted release |
| Matched LALAL.AI benchmark and blind study | Competitive claim |

## Final release checklist

The complete project is ready only when every applicable item below is true.

- [ ] The final stem contract and hierarchy are stable.
- [ ] Every public stem has one qualified model owner.
- [ ] Every model owner has an immutable checkpoint and release record.
- [ ] Every trained checkpoint traces to a reproducible dataset and run.
- [ ] Every benchmark is composition-disjoint and reproducible.
- [ ] Fast, Studio, and Pro modes have independent release decisions.
- [ ] Weak stems are hidden or labelled rather than fabricated.
- [ ] Cloud jobs are secure, idempotent, cancellable, recoverable, and
  deletable.
- [ ] Self-hosted jobs use the same API, model release, and artifact contract.
- [ ] Actual latency and cost satisfy the selected service and pricing model.
- [ ] Rights and redistribution status permit the intended release.
- [ ] Monitoring, alerts, runbooks, backups, restore, and rollback are proven.
- [ ] Artists and producers complete the workflow successfully.
- [ ] Any claim of beating LALAL.AI is supported by the matched claim gate.

## Review sign-off

This section records the two required loophole audits. The roadmap remains a
draft until both audits are resolved in the document.

- [x] ML research audit: Athena approved the corrected architecture, data,
  benchmark, training, and inference sequence on July 29, 2026.
- [x] Systems and product audit: Forge approved the corrected platform,
  security, cost, release, cloud, and self-hosted sequence on July 29, 2026.
- [x] Final reconciliation: all blockers and major findings from both audits
  are incorporated. Neither reviewer reported a remaining blocker.

## Primary references

The research decision depends on these primary sources and pinned local
reproductions:

- X-LANCE, Music Source Restoration Challenge system:
  <https://arxiv.org/abs/2602.09042>
- Local X-LANCE revision:
  `external_repos/xlance-msr` at
  `7f55df1f84b127aaa27f57f9436538529ad09643`
- ACMID dataset cleaning and seven-stem study:
  <https://arxiv.org/abs/2510.07840>
- Local ACMID revision:
  `external_repos/ACMID` at
  `ac7b55f86d5b53c85a7739acb9e47f64fdfb7b59`
- CP-JKU multi-output BS-RoFormer comparison:
  <https://arxiv.org/abs/2603.04032>
- RawStems:
  <https://arxiv.org/abs/2505.21827>
- Current stem qualification:
  `models/stem_qualification.yaml`
- Current specialist corpus gates:
  `datasets/status/specialist-corpus-gates.json`
- Current training-data status:
  `datasets/status/training-data-status.json`
- Current production boundary:
  `../architecture/PRODUCTION_ARCHITECTURE.md`

## Next steps

Run the two independent loophole audits. Revise this document from their
findings, approve Phase 0, and then execute the benchmark and data-recovery
critical path without starting new model or GPU experiments.

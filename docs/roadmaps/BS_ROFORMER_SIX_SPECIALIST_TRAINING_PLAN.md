# BS-RoFormer six-specialist fast qualification and adaptation plan

> **Warning:** This plan is superseded by
> `PROVEN_12_STEM_MODEL_PLAN.md`. Keep it only as historical context for the
> experiments already performed. Don't use it to start new training runs.

This document is the complete execution plan for resolving the six specialist
stem families that the current product cannot yet publish honestly:

1. Kick
2. Snare
3. Piano
4. Electric guitar
5. Strings
6. Wind and brass

The original version assumed that all six needed two newly trained models.
Local evidence and current open-source research disprove that assumption. The
fast path is to qualify existing specialists first, use LoRA or head expansion
only for actual failures, and add a second refiner only when one measured
failure requires it.

The expected result is zero new checkpoints for kick and snare, zero or one for
piano, one for electric guitar, and one shared two-head orchestra adapter for
strings and wind/brass. The twelve-checkpoint design remains a fallback, not
the default.

## Product decision

The product will not claim that all twelve stems are production-ready merely
because twelve WAV files exist. The current four broad stems remain:

- Vocals
- Instrumental
- Drums
- Bass

The existing X-LANCE synth checkpoint remains the preferred synth candidate.
The Mega53 acoustic-guitar checkpoint remains a candidate until its license and
full-corpus benchmark are complete.

Current evidence for the six targets is:

- Kick: MDX23C DrumSep has an external SDR of 14.54 dB.
- Snare: MDX23C DrumSep has an external SDR of 9.79 dB.
- Piano: BS-RoFormer SW has an external SDR of 7.83 dB and an internal median
  SI-SDR of 2.459 dB on the incomplete local corpus.
- Electric guitar: Mega53 failed the local smoke segment at -17.4588 dB
  SI-SDR.
- Strings: Mega53 failed the positive-source smoke segment at -16.8305 dB
  SI-SDR.
- Wind: Mega53's saxophone proxy failed the local smoke segment at -0.7698 dB
  SI-SDR.

External metrics use different MVSep datasets and are not directly comparable
across families. They are enough to prioritize qualification, not enough to
claim release readiness.

The primary decision is:

1. Do not retrain kick or snare unless the existing DrumSep model fails the
   internal release corpus.
2. Benchmark piano before training it.
3. Adapt the inherited guitar head for electric guitar.
4. Expand the inherited orchestra head into strings and wind/brass outputs.
5. Add a sequential refiner only to a stem that still has measured bleed or
   target damage.

## What X-LANCE actually did

X-LANCE did not create a completely new separator architecture. It reused
BS-RoFormer and trained derivative checkpoints for under-served stem families.
Its public inference code applies specialist checkpoints sequentially: the
output of the first model becomes the input to the second model.

The public training loader also shows two useful stages:

1. A target-head stage keeps most of the inherited network frozen and trains
   the mask estimator associated with the desired family.
2. A second single-target RoFormer loads the inherited backbone, creates a new
   target head, and refines the first model's estimate.

The published recipe uses ten-second clips, L1 plus multi-resolution STFT loss,
AdamW, mixed precision, a batch size of four, and long training runs exceeding
200,000 steps. Those values are starting points, not proof that they are
optimal for our data.

Primary references:

- <https://github.com/ModistAndrew/xlance-msr>
- <https://huggingface.co/chenxie95/xlance-msr-ckpt>
- <https://arxiv.org/abs/2602.09042>

## Fast target architecture

The fast architecture reuses accepted checkpoints and shares adaptation work.
Any adapter must still learn from the imperfect parent signal it receives in
production.

- **Kick and snare:** Predicted drums enter the existing MDX23C DrumSep model.
- **Piano:** The existing BS-RoFormer SW piano head remains unless a same-song
  bakeoff proves that Mega53 or a short LoRA adaptation is stronger.
- **Electric guitar:** Predicted guitar or other enters a LoRA-adapted
  BS-RoFormer guitar head.
- **Strings and wind/brass:** Predicted orchestra or other enters one
  LoRA-adapted BS-RoFormer with two expanded output heads.

This design follows two published shortcuts. X-LANCE initializes from existing
ZFTurbo BS-RoFormer weights instead of starting from random weights. CP-JKU
demonstrates LoRA warm-starting and output-head expansion for an eight-stem
BS-RoFormer. ZFTurbo's mature trainer already supports old-weight loading,
LoRA, generated mixtures, validation, multi-GPU training, and export.

References:

- <https://github.com/ZFTurbo/Music-Source-Separation-Training>
- <https://arxiv.org/abs/2603.04032>
- <https://msrchallenge.com/>

## Gate 0: model and data rights

No GPU training begins until every input checkpoint and every audio item has a
recorded right to the selected profile's intended use. "Available online" is
not permission, but a known non-commercial research grant is sufficient for
the internal `research_all` profile.

The authoritative source list and acquisition procedure are defined in
`../research/SPECIALIST_DATASET_ACQUISITION_MAP.md`. The machine-readable
authority is
`datasets/registry/specialist_sources.yaml`.

The first specialist run uses `research_all`, including quality-approved
MoisesDB, RawStems, GOAT, MedleyDB, MUSDB, and permission-pending sources. Its
checkpoints remain internal. A checkpoint can enter public or paid inference
only when it was trained from a `release_eligible` manifest. If a source owner
denies permission, deleting the source files is insufficient; retrain from the
uncontaminated base checkpoint.

The rights ledger must contain:

- Source name and immutable source identifier
- Download URI or contributor agreement
- Track and stem identifiers
- Copyright owner or authorized contributor
- License name and exact license text or agreement version
- Permission for machine-learning training
- Permission for commercial hosted inference
- Permission to distribute derived weights
- Required attribution
- SHA-256 checksum
- Date acquired and reviewer

The legal status of known sources is:

- **Slakh2100, CC BY 4.0:** Candidate for commercial training after
  attribution and provenance review.
- **MoisesDB, CC BY-NC-SA 4.0:** Include in `research_all`; obtain permission
  before release training.
- **MedleyDB, CC BY-NC-SA 4.0:** Include in `research_all`; obtain permission
  before release training.
- **MUSDB family:** Research and evaluation unless a track-specific commercial
  grant exists.
- **RawStems:** Include label-reviewed material in `research_all`; each
  original track still requires an item-level audit for release training.
- **GOAT:** Include in `research_all`; its non-commercial terms require a
  separate grant for release training.
- **ACMID or YouTube-derived audio:** Research only unless every recording has
  explicit training rights.
- **First-party artist multitracks:** Commercial training after a signed
  model-training release.
- **MIDI and sample-library renders:** Allowed only when both licenses permit
  ML training and derived weights.

MoisesDB's official dataset card describes it as non-commercial:

- [MoisesDB dataset card][moisesdb-card]

[moisesdb-card]: https://huggingface.co/datasets/wearemusicai/moisesdb

This document is an engineering policy, not legal advice. Before a public paid
launch, counsel must review the completed rights ledger and weight licenses.

## Training-data specification

Data quality is the largest determinant of whether this work succeeds. Each
target needs exact isolated labels, diverse mixtures, and real production
conditions. The test set must contain music that was never used for training,
augmentation design, threshold tuning, or model selection.

### Minimum pilot corpus

Each stem may enter pilot training only when it has:

- At least 20 hours of target-active audio after removing silence
- At least 1,000 unique arrangements or source combinations
- At least 100 distinct songs or generated compositions
- At least 20 real multitracks lawfully available for the selected profile
- At least 30 fully held-out songs for final evaluation
- No shared song, artist, MIDI arrangement, or source recording across splits

These are pilot minimums, not release guarantees.

### Release-candidate corpus

Before a full-training fallback, each stem should have:

- At least 100 hours of target-active audio
- At least 500 distinct compositions
- Multiple recording styles, keys, tempos, dynamics, and mix positions
- At least 25 percent real licensed recordings by active target duration
- A dedicated Afrobeats and African-pop subset
- A hard-song subset with dense arrangements, effects, and overlapping timbre

Augmentation may increase effective exposure, but it does not increase the
number of independent songs. Reports must show original and augmented hours
separately.

### Stem-specific acquisition

Kick and snare data should come from MIDI drum arrangements rendered into
separate kit channels plus licensed real drum multitracks. The corpus must
cover acoustic kits, electronic drums, layered samples, rimshots, claps,
Afrobeats percussion, side-chain processing, saturation, room microphones,
reverb, and mastered drum buses.

Piano data should cover acoustic grand, upright, felt, processed piano,
electric piano where correctly labeled, solo passages, chordal accompaniment,
and piano mixed against guitars, strings, and synths.

Electric-guitar data should cover clean, distorted, muted, lead, rhythm,
chorused, delayed, reverberant, DI, and amplified recordings. Acoustic guitar
must be an explicit interferer so the model learns the boundary.

Strings data should cover solo and ensemble violin, viola, cello, double bass,
legato, staccato, pizzicato, synthetic string patches, and strings overlapping
with pads and orchestra.

Wind and brass data should cover saxophone, flute, clarinet, oboe, trumpet,
trombone, horn, tuba, ensembles, breath noise, mutes, and instruments processed
with common studio effects. The product label must remain `wind_brass` unless
the data supports reliable subfamilies.

## Dataset construction

The dataset builder must create training inputs that match production. It must
not simply add clean sources together at fixed volume.

For every training example, the builder will:

1. Select a target stem and several legal interferers.
2. Apply gain, pan, EQ, compression, saturation, reverb, and delay within
   bounded, recorded augmentation ranges.
3. Build the full mixture and the clean parent bus.
4. Run the current production broad separator to create the predicted parent.
5. Select clean, predicted, or contamination-augmented parent input according
   to the configured curriculum.
6. Preserve the exact clean target as ground truth.
7. Reject clips with insufficient target energy, clipping, broken alignment,
   duplicate content, or invalid reconstruction.
8. Record every source and transform in the sample manifest.

The initial curriculum should use:

- 25 percent clean parent buses for learnability
- 50 percent production-predicted parent buses for serving realism
- 25 percent parent buses with controlled leakage and codec damage

The ratio becomes an experiment parameter. It must not be silently changed.

Audio preparation requirements are:

- Stereo
- The sample rate required by the selected base checkpoint
- Ten-second target-active clips for the first experiments
- Peak below -1 dBFS after mixture construction
- No loudness normalization that destroys natural target-to-mixture ratios
- Sample-accurate alignment
- Deterministic split and augmentation seeds

The implementation must read the sample rate from checkpoint metadata. It must
not assume that all public X-LANCE checkpoints use the same rate.

## Training implementation

The repository should not reimplement a mature trainer. Pin ZFTurbo's
Music-Source-Separation-Training repository at a reviewed commit and add only
the project-specific data, configuration, Modal, and registry integration:

```text
external_repos/
  music-source-separation-training/
training/
  __init__.py
  manifests.py
  parent_inputs.py
  configs/
    electric_guitar_lora.yaml
    strings_wind_lora.yaml
    piano_lora.yaml
scripts/
  build_training_manifest.py
  audit_training_rights.py
  render_training_mixtures.py
  evaluate_specialist.py
  export_specialist.py
workers/
  specialist_training_modal.py
models/
  training_registry.yaml
```

Every run must record:

- Experiment ID
- Git commit
- Container digest
- Python and CUDA versions
- GPU type
- Configuration hash
- Dataset-manifest hash
- Parent-separator checkpoint hash
- Base-checkpoint hash and license
- Random seed
- Training and validation curves
- Checkpoint hashes
- Wall-clock duration and billed cost

## Fast adaptation recipe

The recipe begins with existing-model qualification. New training starts only
for a measured failure.

### Phase A: qualify inherited models

Run DrumSep kick/snare, BS-RoFormer SW piano, and Mega53 piano against the same
ground-truth clips. This phase can eliminate three training targets in one day.

### Phase B: LoRA and head expansion

Initialize electric guitar from the inherited guitar head. Initialize the
strings and wind/brass model from the X-LANCE orchestra or BS-RoFormer other
head. Freeze the base weights and train LoRA adapters plus the new output heads.

The starting configuration is:

- Architecture: BS-RoFormer compatible with the selected base
- Segment: 10 seconds
- Batch size: 4, or an equivalent effective batch through accumulation
- Precision: BF16 when supported, otherwise FP16
- Optimizer: AdamW
- Initial learning rate: `5e-4` for new heads
- Initial LoRA learning rate: determine with a short `1e-4` to `5e-4` sweep
- Warmup: 500 steps for pilots and up to 2,000 for an accepted full run
- Loss: waveform L1 plus multi-resolution STFT
- Checkpoint interval: 1,000 steps
- Validation interval: 1,000 steps

The inherited FFT, hop, band, depth, and normalization settings must come from
the base checkpoint's exact configuration. We must not create a nominally
compatible model that cannot faithfully load its weights.

### Phase C: optional sequential refinement

A second model is not automatic. Add one only when the adapted output beats the
baseline but still has a repeatable bleed or restoration failure. Its input is
the Phase B estimate, and its target remains the clean isolated source.

The default production paths are:

```text
song -> drums -> existing DrumSep -> kick and snare
song -> existing BS-RoFormer SW -> piano
song -> guitar/other -> electric-guitar LoRA adapter
song -> orchestra/other -> two-head strings/wind LoRA adapter
```

## Experiment ladder

Each new adapter must pass the following ladder before consuming a full GPU
budget.

### E0: loader reproduction

Load the exact base checkpoint, run one reference file, and verify shape,
sample rate, output scale, and deterministic inference. A mismatched state
dictionary or silent output blocks the target.

### E1: tiny-set overfit

Train on 32 to 64 examples and prove that the loss falls sharply and the model
can reconstruct those targets. Failure means the labels, loader, loss, or
architecture is wrong.

### E2: 1,000-step throughput calibration

Run 1,000 steps on the intended GPU. Record step time, peak VRAM, checkpoint
size, interruption recovery, and actual Modal cost. This run establishes the
budget for every later stage.

### E3: 2,000-step pilot

Train the LoRA adapter and new head. Compare it against the inherited baseline
on the held-out development set. Stop if it does not improve target quality or
only learns silence.

### E4: 10,000-step adapter pilot

Run objective metrics and a small blind listening check. Only targets with a
credible improvement proceed.

### E5: full candidate

Train to a maximum of 50,000 LoRA steps, selecting checkpoints by held-out
validation quality rather than final-step loss. Escalation to partial or full
fine-tuning requires evidence that LoRA reached a quality ceiling and that the
larger run is likely to recover the remaining gap.

### E6: independent release evaluation

Freeze the model and run the untouched test corpus, commercial comparators,
latency measurement, cost measurement, and failure analysis.

## Compute and storage plan

Training should run in a reproducible CUDA container on Modal or an equivalent
GPU platform. Data and checkpoints must survive worker termination.

The initial hardware policy is:

- Use an RTX 4090 or L40S for loader tests and small pilots when memory permits.
- Use an A100 80 GB, H100, or H200 for full runs after measured comparison.
- Use BF16 on hardware that supports it.
- Use a persistent Modal volume for active checkpoints and run state.
- Archive immutable manifests, datasets, and accepted checkpoints in B2.
- Resume from the last verified checkpoint after preemption.
- Never use spot capacity until checkpoint resume has passed E2.

We will not guess the final cost. The E2 calibration produces:

```text
estimated_hours = measured_seconds_per_step * planned_steps / 3600
estimated_gpu_cost = estimated_hours * current_gpu_hourly_rate
estimated_total_cost = gpu_cost + storage + data_transfer
```

Each configuration must include a hard maximum step count, maximum runtime,
maximum retry count, and maximum approved cost. A retry resumes the same run;
it must not silently create a second billable experiment.

## Evaluation protocol

A file-exists check is not a quality benchmark. Every candidate must be scored
against exact ground truth and compared on the same songs.

The objective report must include:

- SI-SDR and SDR, per song and median
- Target energy recall
- Interferer rejection and bleed energy
- Spectral distance
- Transient preservation for kick and snare
- Mixture consistency
- Silent-output and near-silent-output rate
- Clipping and non-finite sample rate
- Real-time factor, wall time, peak VRAM, and cost per song

Reports must separate synthetic, real multitrack, Afrobeats, and hard-song
subsets. An excellent synthetic score cannot hide poor real-recording results.

The blind listening report must include at least:

- Fifteen short excerpts per target
- Three producers or experienced listeners
- Randomized model labels
- Current product output, new candidate, and a commercial comparator
- Ratings for isolation, target damage, artifacts, and usability
- Recorded severe-failure examples

Public benchmark numbers from another paper do not prove our pipeline's score.
We may cite them as context, but comparisons must use the same audio, stem
definition, preprocessing, and metric implementation.

## Release gates

A specialist may replace the current candidate only when all gates pass:

1. Rights ledger permits commercial hosted inference and weight distribution.
2. Median SI-SDR improves by at least 1 dB over the current product candidate
   on the untouched test corpus.
3. It does not regress any protected broad stem by more than 0.5 dB.
4. It reduces severe bleed or silent-output failures, not only average loss.
5. At least 80 percent of blind comparisons prefer it to the current output.
6. It reconstructs and exports valid audio for every release-corpus song.
7. Its measured latency and cost fit the product budget.
8. The inference worker can resume, retry, and produce the same model hash.

Commercial-comparator parity is a product goal, not a gate we can fake with a
single subjective song. A candidate that beats the current model but not the
comparator may ship only as `experimental`.

## Product integration

Accepted checkpoints or adapters must enter the existing model registry with
immutable versions and checksums. The router must invoke them only after the
required broad parent exists.

For every output, the manifest must record:

- Target family
- Parent stem
- Base-model and adapter IDs
- Model hashes
- Quality score and threshold
- Published or rejected status
- Rejection reason
- Inference duration and cost

The API, UI, and archives may expose a specialist only after the same artifact
is present in the manifest. Rejected or absent specialists must be shown as
unavailable or experimental, never replaced with a fabricated silent or
residual file.

## Execution order

The work should proceed in four short waves. Full two-stage training is used
only after this route fails.

### Wave 1: one-day reuse audit

- [ ] Pin the existing ZFTurbo trainer instead of rebuilding it.
- [ ] Verify licenses and hashes for DrumSep, BS-RoFormer SW, and X-LANCE.
- [ ] Freeze one same-song qualification corpus and metric implementation.
- [ ] Run kick, snare, and piano candidates on that corpus.
- [ ] Record accept, adapt, or reject decisions.

### Wave 2: existing-model integration

- [ ] Qualify DrumSep kick and snare on production-parent drums.
- [ ] Qualify BS-RoFormer SW and Mega53 piano on identical clips.
- [ ] Wire the winners without retraining.
- [ ] Reject models that preserve the drum bus but fail isolation.

### Wave 3: electric-guitar adaptation

- [ ] Generate and freeze the `research_all` source manifest.
- [ ] Select every quality-approved electric-guitar source in that manifest.
- [ ] Add acoustic guitar, keys, synth, and strings as hard interferers.
- [ ] Build production-parent guitar and other inputs.
- [ ] Train and qualify one electric-guitar LoRA adapter.
- [ ] Train piano LoRA only if both inherited candidates fail.
- [ ] Reject outputs that merely copy the parent or erase the target.

### Wave 4: shared orchestra adaptation

- [ ] Select every quality-approved strings and wind/brass source in the
      frozen `research_all` manifest.
- [ ] Build orchestra/other production-parent inputs.
- [ ] Train one LoRA adapter with strings and wind/brass output heads.
- [ ] Split the model only if measured negative transfer requires it.
- [ ] Test orchestra, synth-pad, guitar, and vocal-overlap failure cases.
- [ ] Keep the broad `wind_brass` label until narrower labels pass
      independently.

### Final integration

- [ ] Run all six outputs on the untouched release corpus.
- [ ] Run the blind producer panel.
- [ ] Measure warm and cold latency and cost.
- [ ] Select, reject, or mark each output experimental.
- [ ] Register accepted immutable checkpoints.
- [ ] Wire accepted checkpoints and adapters into the production router.
- [ ] Update API, UI, ZIP, and manifest contracts.
- [ ] Publish benchmark cards and known limitations.

## Stop conditions

The team must stop a run rather than spend through a known failure.

Stop immediately when:

- A model or dataset does not permit the selected profile's intended use.
- An item has unknown provenance or no recorded research permission.
- The target and input are misaligned.
- The tiny-set overfit test fails.
- Training learns silence or an unchanged parent copy.
- The 10,000-step adapter pilot does not beat the inherited baseline.
- Validation worsens while training loss continues falling.
- Synthetic gains disappear on real licensed recordings.
- The estimated full-run cost exceeds the approved budget.
- A checkpoint cannot resume deterministically after interruption.

After a stop, fix the data, labels, architecture, or evaluation. Do not hide the
failure with post-processing, renamed residuals, or lower publication
thresholds.

## Expected schedule

The accelerated target is seven to fourteen calendar days:

- Day 1: pin the trainer, audit checkpoint licenses, and freeze evaluation.
- Days 1 to 2: qualify kick, snare, and piano candidates.
- Days 2 to 5: prepare immediate Slakh and licensed adaptation examples.
- Days 3 to 7: train and select the electric-guitar LoRA adapter.
- Days 4 to 9: train and select the shared strings/wind adapter.
- Days 8 to 12: run same-song benchmarks and blind listening.
- Days 12 to 14: integrate accepted outputs and publish limitations.

A three-to-five-day friend-test build is possible if DrumSep and piano pass and
we expose the three remaining stems as experimental. A production claim for
all six still requires the evidence gates; the schedule must not be shortened
by relabeling failed outputs.

## Definition of done

This plan is complete only when each of the six rows has one explicit outcome:

- Kick: accepted, experimental with evidence, or rejected with evidence
- Snare: accepted, experimental with evidence, or rejected with evidence
- Piano: accepted, experimental with evidence, or rejected with evidence
- Electric guitar: accepted, experimental with evidence, or rejected with
  evidence
- Strings: accepted, experimental with evidence, or rejected with evidence
- Wind and brass: accepted, experimental with evidence, or rejected with
  evidence

"Trained" is not done. Done means a legally usable, reproducible checkpoint or
adapter with ground-truth metrics, blind listening evidence, known cost, known
latency, immutable hashes, and correct production integration.

## Immediate next actions

The first implementation pass should complete these items in order:

1. Pin and smoke-test ZFTurbo's existing trainer.
2. Audit the three inherited checkpoint families.
3. Run DrumSep and both piano candidates on the same ground-truth inputs.
4. Remove kick, snare, and piano from training when they pass.
5. Prepare electric-guitar and orchestra LoRA configurations.
6. Calibrate 1,000 steps before approving either full adapter run.

No full specialist run should begin before those six actions pass.

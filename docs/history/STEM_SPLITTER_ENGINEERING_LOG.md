# Stem splitter engineering and research log

This document is the chronological source of truth for the stem splitter
project. It records what was attempted, what evidence was produced, what
failed, what changed, and what remains uncertain. Planning documents describe
the intended future; this log describes observed reality.

## Documentation map

The project uses separate documents for product plans, research decisions,
architecture, and execution evidence. Use this log to find the relevant
authority without treating a plan as proof of implementation.

| Document | Purpose |
| --- | --- |
| `README.md` | Current user-facing product contract and operating instructions |
| `../roadmaps/ROAD_TO_SERIES_A_PLAN.md` | Product and platform delivery roadmap |
| `../architecture/PRODUCTION_ARCHITECTURE.md` | Target production system architecture |
| `../research/SPECIALIST_MODEL_SELECTION.md` | Model inventory and selection decisions |
| `../research/SPECIALIST_DATASET_ACQUISITION_MAP.md` | Dataset sources, rights, and acquisition policy |
| `../roadmaps/BS_ROFORMER_SIX_SPECIALIST_TRAINING_PLAN.md` | Specialist qualification and training plan |
| `STEM_SPLITTER_ENGINEERING_LOG.md` | Executed work, evidence, incidents, and current state |

## Current state

As of July 28, 2026, the product exposes an honest eight-stem contract. Work is
in progress on new electric-guitar, strings, and wind/brass specialists. The
research dataset is materialized and indexed on Modal, all metadata caches are
complete, and the first 1,000-step electric-guitar training run has completed.

The completed run is evidence that the dataset and trainer connect correctly.
It is not evidence that the checkpoint is production quality.

## System architecture

The application and the research trainer are separate systems that share model
artifacts only after qualification.

```text
Product path
Browser -> FastAPI -> durable job boundary -> Modal inference worker
        -> quality contract -> object storage -> signed artifacts

Research path
Curated source manifests -> Modal training volume -> indexed corpus
        -> BS-RoFormer trainer -> checkpoint -> held-out evaluation
        -> listening review -> model registry -> product qualification
```

The product must not load a research checkpoint merely because training
completed. A checkpoint enters the runtime only after objective evaluation,
listening review, provenance review, and a recorded publication decision.

## Dataset DNA

The `complete-source-pools` dataset contains 95.7 GB of isolated source audio
from 11 collections. Audio remains organized by source. Three CSV indexes
create logical target-versus-other views without duplicating the audio.

```text
/training/
├── source_audio/datasets/staging/<source>/<version>/...
├── indexes/complete-source-pools/
│   ├── index.json
│   ├── electric_guitar.csv
│   ├── strings.csv
│   ├── wind_brass.csv
│   ├── electric_guitar.metadata.pkl
│   ├── strings.metadata.pkl
│   ├── wind_brass.metadata.pkl
│   └── metadata-receipt.json
├── datasets/sprint-clean-v1/research_all/<family>/stage_25/validation/
├── bases/<family>_bsroformer_base.ckpt
└── runs/<run-id>/<family>/
```

Each CSV row contains `instrum`, `path`, `sha256`, `source_id`, and
`composition_id`. The label is the requested family or `other`. The checksum
identifies the audio, the source identifies its provenance, and the
composition groups stems from the same recording.

| Family index | Target rows | Other rows | Total rows |
| --- | ---: | ---: | ---: |
| Electric guitar | 10,542 | 23,448 | 33,990 |
| Strings | 11,868 | 22,122 | 33,990 |
| Wind/brass | 11,424 | 22,566 | 33,990 |

The three indexes contain 101,970 references to 33,990 unique audio files.
Modal verification found zero missing references. Training samples random
ten-second segments and constructs mixtures at runtime instead of storing
millions of rendered training mixtures.

## Dataset execution record

The following sequence records the completed dataset work. It distinguishes
necessary preparation from repeated investigation that did not improve the
corpus.

1. Defined electric guitar, strings, and wind/brass as target families.
2. Registered AlbumDB, Chorale Bricks, CocoChorales, EG-IPT, Guitar-TECHS,
   MedleyDB Sample, QuartSet, RawStems, SPHERES, TinySOL, and URMP.
3. Downloaded source archives and materialized remotely stored archive members.
4. Audited audio decoding, activity, clipping, channels, checksums, labels, and
   provenance.
5. Classified accepted items as a target family or `other`.
6. Recorded source and composition identifiers for split control and
   traceability.
7. Built three immutable online-mixing indexes.
8. Stored 95.7 GB of source audio on the persistent Modal training volume.
9. Verified all index paths, row counts, family counts, and semantic digests.
10. Exported a 12-clip representative listening bundle for a fast sanity check.
11. Built the three MSST metadata caches from curated item-manifest frame
    counts.

Repeated sample audits were useful only until they established basic corpus
integrity. They did not prove full-corpus label accuracy and must not be
repeated as a substitute for model training and held-out evaluation.

## Metadata-cache incident

The initial Modal trainer launch exposed a preventable cost problem. MSST
attempted to open all 33,990 audio files from inside each H100 function before
performing its first optimization step.

Three H100 runs were stopped before training because each was independently
scanning file headers. A first correction moved the scan to a 16-CPU Modal
function, but random reads against the Modal volume remained too slow and the
job was stopped after about one hour.

The acquisition item manifests already contained exact frame counts for every
indexed checksum. A local coverage check found:

```text
manifest audio records: 36,311
required unique checksums: 33,990
covered checksums: 33,990
missing checksums: 0
frame-count conflicts: 0
```

The final cache builder reads those curated manifests instead of reopening the
audio corpus. It produced all three cache files and a receipt in under one
Modal invocation. This cache changes no audio. It maps each path to its frame
count so MSST can select valid ten-second offsets.

## First training-segment evidence

The first actual specialist runs used `run_id=specialists-20260728` and the
`complete-source-pools` dataset. Each H100 loaded its cache groups without
rescanning audio and completed 1,000 optimization steps.

| Family | Modal app | Seconds | Seconds/step | Initial SDR | Post-run SDR | Change |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Electric guitar | `ap-gFVMpOwgPPM7On2ClGECjZ` | 534.601 | 0.534601 | 0.9561 | 1.5770 | +0.6209 |
| Strings | `ap-fwhubpurj7Px6c4HKnQaII` | 799.528 | 0.799528 | 5.0572 | 5.0820 | +0.0248 |
| Wind/brass | `ap-tLkVheDsYwGPiHscjrDRBP` | 1,130.050 | 1.130050 | -8.0231 | -8.1371 | -0.1140 |

The resumable checkpoints and their identities are:

| Family | Checkpoint SHA-256 |
| --- | --- |
| Electric guitar | `bc6116eaa82ebb0535228509079cdb680b6479f1fb52a9bb2f0e6194efe774ce` |
| Strings | `e800ab2156b5759a333d699cb6f4d60b38419833bcc5c5601d0f75b0a3d6946e` |
| Wind/brass | `5dc0d09c657f17d6ddd121cfc152d927b396e54b140ca8f2d8553f786edab77e` |

The validation sets are small. The reported changes are therefore directional
evidence, not release benchmarks. Electric guitar improved enough to justify
checkpoint evaluation. Strings was effectively flat. Wind/brass regressed
slightly and must not enter a long run until its target construction, starting
checkpoint, and validation examples are diagnosed.

## First checkpoint quality gate

The independent exporter originally scored the raw model weights in
`last_bs_roformer.ckpt`, while the trainer validates the EMA-smoothed weights
stored in `ema_model_state_dict`. The resumable checkpoint was correct, but
the evaluation boundary was not. The exporter now extracts and labels the EMA
weights explicitly as `trained_ema_1000`. The corrected values exactly
reproduce the training-time validation values.

| Family | Base SDR | EMA SDR | Mean delta | Median delta | SDR wins | Bleedless delta | Fullness delta | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Electric guitar | 0.9561 | 1.5770 | +0.6208 | -0.0906 | 1/6 | +3.8009 | -5.6241 | Stop long continuation; the mean gain is one-example-driven and content retention fell. |
| Strings | 5.0572 | 5.0820 | +0.0248 | +0.0210 | 5/5 | +1.0934 | -0.8765 | Stop long continuation; direction is consistent but too small to justify 199,000 more steps. |
| Wind/brass | -8.0231 | -8.1371 | -0.1140 | -0.0036 | 2/4 | -0.0298 | +1.1618 | Reject this training direction; quality is poor and did not improve. |

The corrected W&B comparison runs are:

- Electric guitar:
  `https://wandb.ai/daniel-ejeh-auralith/stemsplitter-specialists/runs/3oc9dyml`
- Strings:
  `https://wandb.ai/daniel-ejeh-auralith/stemsplitter-specialists/runs/856wselp`
- Wind/brass:
  `https://wandb.ai/daniel-ejeh-auralith/stemsplitter-specialists/runs/o0kj99gn`

The earlier runs `tuydiqfb`, `a2lmp272`, and `ezgijwih` scored raw weights and
must not be used for model-quality decisions. Their outputs remain historical
debug evidence only.

The accepted item manifests were also checked for split leakage. No accepted
audio hash and no accepted composition identifier occurs in both train and
validation/test. Rejected duplicate records can carry different split labels,
but `load_audited_items` excludes them before the online indexes are built.

All base, EMA, reference audio, and JSON receipts are preserved locally under
`benchmarks/specialist_training/specialists-20260728/`. These are listening and
directional training artifacts, not a release benchmark.

## Expanded specialist gate

The first tiny validation splits were replaced by the immutable
`specialists-validation-30-v1` set. It contains 30 held-out mixtures and target
references for each specialist family, 180 FLAC files in total. The builder
round-robins compositions, rejects targets below -50 dBFS, reuses already
rendered clips, and records the complete selection in
`training/validation_sets/specialists-validation-30-v1/validation-set.json`.
The installed archive SHA-256 is
`36bb18f067cb574ad7be50e938964c084f976173f4f06c89c2be782dc7b44cad`.

The expanded EMA gates produced these results:

| Family | Mean SDR delta | Median SDR delta | SDR wins | Mean bleedless delta | Mean fullness delta | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Electric guitar | -0.7711 dB | -0.1046 dB | 7/30 | not promoted | negative | Reject the 1,000-step checkpoint; retain the original guitar base. |
| Strings | +0.3046 dB | +0.0122 dB | 19/30 | +0.7900 dB | -0.7208 dB | Preserve for research, but stop continuation because the gain is marginal and target retention declines. |
| Wind/brass, corrected harmonic base | +0.0994 dB | +0.1575 dB | 20/30 | -1.7564 dB | +6.0315 dB | Reject the 1,000-step fine-tune because its small SDR gain trades away bleed cleanliness. |

Electric and strings receipts are
`benchmarks/specialist_training/electric_guitar-ema1000-expanded-gate-v1.json`
and
`benchmarks/specialist_training/strings-ema1000-expanded-gate-v1.json`.
The corrected wind receipt is
`benchmarks/specialist_training/wind-harmonic-ema1000-expanded-gate-v1.json`;
its W&B comparison is
`https://wandb.ai/daniel-ejeh-auralith/stemsplitter-specialists/runs/vc90vnub`.

Wind/brass had been initialized from source head 1 of the bowed-strings model,
which is the residual `other` head. A 30-clip bake-off proved that this was a
semantic initialization error. Cloning the model's actual `strings` head
improved mean SDR by 7.2812 dB and bleedlessness by 6.2264 dB relative to the
old residual head, although fullness fell by 16.4146 dB. The residual base is
archived under `training/generated/archive/wind-brass-residual-v1/`; the
corrected harmonic base SHA-256 is
`921b3e75c465dff98c2f9518ccf26a5ec64e165f970253de8388c39a47461433`.

One controlled full-adaptation wind run was then allowed:
`wind-harmonic-full-20260728`, 1,000 steps, learning rate 5e-6, effective batch
12, on an H100. It completed in 848.498 seconds and produced checkpoint
SHA-256
`c8d3a608914d6e461d1f0488eb631f24f5c42e73ae2d4277a4c15fc978f56b25`.
The independent gate rejected that trained checkpoint. The corrected harmonic
base remains the wind/brass research starting point; no specialist checkpoint
from this sprint is approved for production.

## Known discrepancies and risks

The first run also revealed differences between the written X-LANCE-inspired
plan and the active trainer configuration. These must be resolved before a
long 200,000-step commitment.

- The plan describes a target-head or LoRA adaptation stage, but the run
  reported 51,049,420 trainable parameters out of 51,049,484. That indicates
  almost full-model fine-tuning.
- The plan references batch size four, but the run reported an effective batch
  size of two.
- The validation corpus is too small to support a production-quality claim.
- The training receipt reported zero peak GPU memory because memory was
  measured in the parent process instead of the trainer subprocess.
- The `research_all` corpus includes sources that cannot automatically support
  a public commercial checkpoint. Any public release requires a separately
  proven `release_eligible` dataset lineage.
- Electric-guitar loss varied sharply between mixtures. The first checkpoint
  needs audio export and held-out evaluation before its direction is trusted.

These are measured gaps, not reasons to discard the architecture. They define
the work required before expensive full training.

## Experiment monitoring

Subsequent training segments report live research metrics to the W&B project
`daniel-ejeh-auralith/stemsplitter-specialists`. Modal remains the source for
infrastructure status, while W&B is the source for training curves and run
comparisons.

The monitoring boundary is:

```text
Modal dashboard -> container, GPU, duration, failure, and billing evidence
W&B dashboard   -> loss, SDR, bleed, fullness, learning rate, and run config
Modal Volume    -> checkpoint, receipt, and local W&B backup files
Jupyter         -> held-out tables, spectrograms, and listening comparisons
```

The W&B API key is stored only in the Modal secret `stemsplitter-wandb`.
Training configuration sent to W&B excludes the key. Runs use the project
`stemsplitter-specialists`, the group name matching the training `run_id`, and
the specialist family as the W&B job type.

The CPU-only verification run
`https://wandb.ai/daniel-ejeh-auralith/stemsplitter-specialists/runs/avj4soi1`
confirmed authentication, metric upload, summary upload, and dashboard access
on July 28, 2026. The first three 1,000-step checkpoints predate this
connection, so their metrics remain in receipts and this log rather than W&B.

## Decision log

The decision log records changes that affect cost, quality, data lineage, or
the product contract.

| Date | Observation | Decision |
| --- | --- | --- |
| July 27, 2026 | Three specialist families lacked accepted open checkpoints. | Fine-tune inherited BS-RoFormer specialists for electric guitar, strings, and wind/brass. |
| July 28, 2026 | The complete Modal corpus passed path and index verification. | Stop acquiring more data and enter training. |
| July 28, 2026 | Three H100 workers began repeated metadata scans. | Stop the workers before optimization and remove GPU-side scanning. |
| July 28, 2026 | CPU reads from the Modal volume remained too slow. | Build cache files from existing curated frame metadata. |
| July 28, 2026 | All 33,990 required checksums had conflict-free frame metadata. | Mark the dataset training-ready. |
| July 28, 2026 | Electric-guitar training completed 1,000 steps. | Evaluate the checkpoint and correct configuration discrepancies before long runs. |
| July 28, 2026 | Strings remained flat and wind/brass regressed after 1,000 steps. | Preserve both checkpoints but stop automatic continuation until diagnosis. |
| July 28, 2026 | W&B monitoring passed an authenticated CPU-only smoke run. | Require live W&B tracking and persistent local logs for subsequent training segments. |
| July 28, 2026 | Independent export initially scored raw weights while training validated EMA weights. | Extract EMA weights explicitly for quality evaluation and retain raw weights only for resume. |
| July 28, 2026 | Corrected robust statistics showed no family ready for a long continuation. | Stop all three at 1,000 steps and correct model/data/training choices before spending more GPU credit. |
| July 28, 2026 | Accepted manifests had zero cross-split hash or composition overlap. | Keep the current split boundary; rejected duplicate records are not training leakage. |
| July 28, 2026 | The original wind/brass base cloned the bowed-strings residual `other` head. | Archive it and promote the semantically closer strings-head clone as the research base. |
| July 28, 2026 | The corrected wind base beat the residual base by 7.2812 dB SDR but lost 16.4146 dB fullness. | Treat it as a stronger warm start, not a shippable model. |
| July 28, 2026 | Full wind adaptation gained only 0.0994 dB SDR while losing 1.7564 dB bleedlessness on 30 clips. | Reject the trained checkpoint and stop this training path before another paid run. |
| July 28, 2026 | Recovery-v1 balanced source families, bounded target/background SNR to 0-10 dB, disabled uncontrolled augmentation, and used staged adaptation. | Use this recipe as the controlled research baseline, not as automatic proof of model quality. |
| July 28, 2026 | Electric recovery lost 0.2453 dB SDR and 1.4187 fullness, with SDR improving on 4/30 clips. | Reject checkpoint `dd2bc41e`; retain the stronger original electric base. |
| July 28, 2026 | Strings recovery gained 0.0439 dB SDR and 0.2407 fullness, with SDR improving on 23/30 clips. | Keep checkpoint `ce7bfdf8` as a research candidate; do not label the marginal gain production-qualified. |
| July 28, 2026 | Wind recovery gained 0.1048 dB SDR and 7.4165 fullness but lost 2.7601 bleedlessness, with bleed improving on 8/30 clips. | Keep checkpoint `f6d2c351` only as an experimental fullness candidate; do not promote it to production. |
| July 28, 2026 | Head-to-full continuation initially restored incompatible epoch and optimizer semantics. | Add explicit `state` and `weights` resume modes; stage transitions load model weights into fresh training state. |
| July 28, 2026 | X-LANCE synth v2 scored -1.6873 dB SI-SDR on the immutable positive-source fixture, ahead of X-LANCE v1 at -4.4494 and Oulianov at -5.3454. | Keep X-LANCE v2 as the next synth research candidate, but do not product-promote or fine-tune it until a multi-clip ground-truth corpus exists. |
| July 28, 2026 | The independent 9-track BabySlakh gate superseded the single-clip ranking: X-LANCE v1 won 6/9 clips with median SI-SDR -1.5793 dB, v2 won 3/9 at -2.3959 dB, and Oulianov won none at -7.5339 dB. | Keep X-LANCE v1 as the strongest current synth research candidate, but reject all three for production because aggregate and median SI-SDR remain negative. |
| July 28, 2026 | A source-level review found that X-LANCE used two sequential synth checkpoints and that ACMID trained one exact seven-stem SCNet after high-precision Dasheng cleaning. Our short, separate specialist adaptations copied neither complete system. | Supersede the six-specialist plan with `../roadmaps/PROVEN_12_STEM_MODEL_PLAN.md`; reproduce the released X-LANCE synth chain, then reproduce ACMID cleaning and seven-stem SCNet without custom losses or short-run quality decisions. |
| July 28, 2026 | The official X-LANCE synth chain scored -1.5191 dB aggregate SI-SDR on the full mixture and -1.4828 dB on a BS-RoFormer `other` parent. The parent reduced the worst segment from -28.4177 dB to -16.2193 dB but did not fix generalization. | Reject the released chain for production. Stop routing and ensemble patches; use the published X-LANCE training recipe for a stronger synth checkpoint. Require positive aggregate and median SI-SDR with no catastrophic tail failure. |

## Next steps

Do not spend more GPU credit on the old specialist path.

1. Apply ACMID's seven released cleaners at the published `0.995` threshold.
2. Measure clean hours for all seven ACMID classes.
3. Reproduce ACMID's seven-output SCNet only after the corpus and trainer
   preflight pass.
4. Rebuild synth with X-LANCE's published data, objective, and sequential
   specialist recipe.
5. Run a product-song listening bake-off only after a candidate clears the
   immutable held-out gate.

Update this log whenever a run changes model status, consumes meaningful cloud
credit, fails after dispatch, changes dataset lineage, or modifies the product
contract. Record exact run identifiers, hashes, metrics, costs, and the
resulting decision.

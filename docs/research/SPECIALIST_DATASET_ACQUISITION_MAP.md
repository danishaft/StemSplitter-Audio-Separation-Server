# Specialist dataset acquisition map

This document combines Athena's research audit and Clio's music-industry
acquisition plan. It is the dataset authority for electric guitar, strings,
wind/brass, piano, kick, and snare specialist work.

The internet contains abundant audio, but very little of it simultaneously has
correct isolated labels, useful recording quality, genre diversity, and
commercial training rights. The fastest route is not indiscriminate scraping.
It is a hybrid of public research datasets, verified open datasets, controlled
rendering, and directly licensed real producer sessions.

## Executive decision

On July 26, 2026, we locked a two-profile corpus policy. The `research_all`
profile uses every source that passes audio, label, and provenance validation,
including MoisesDB, RawStems, GOAT, MedleyDB, MUSDB, and other non-commercial
or permission-pending sources. The `release_eligible` profile contains only
sources whose commercial training rights are resolved.

This distinction is mandatory. Removing a dataset after training does not
remove its influence from a checkpoint. If a source owner denies permission,
we must retrain the release checkpoint from an uncontaminated base using the
`release_eligible` manifest. The unrestricted research checkpoint remains
internal and cannot serve public or paid inference.

The corpus has three layers:

1. Real, openly licensed instrument recordings for timbre and articulation.
2. Large synthetic multitracks for mixture diversity and exact labels.
3. Directly licensed Afrobeats and African-pop sessions for production realism.

All three layers can start in parallel. Dataset licensing outreach must not
delay the internal research run, but unresolved rights block release rather
than being treated as paperwork.

The machine-readable authority is
`datasets/registry/specialist_sources.yaml`. Generate immutable source
selections with `scripts/build_specialist_source_manifest.py`.

## What we already have

The local machine already contains:

- A 2.6 GB, 20-track BabySlakh archive at 16 kHz
- Ten prepared BabySlakh ground-truth tracks
- DrumSep, BS-RoFormer SW, X-LANCE, Mega53, and open specialist checkpoints
- Benchmark, quality-gate, Modal, and B2 infrastructure

BabySlakh is useful for smoke tests but not a full 44.1 kHz training corpus.
Resampling 16 kHz audio does not restore missing high-frequency information.

## Implementation status

As of July 27, 2026, the acquisition work has moved beyond source research:

- Provider inventories cover 417,887,247,102 bytes across the automatically
  accessible sources.
- Backblaze B2 stores eight uploaded files totaling 2,911,497,942 bytes under
  `stemsplitter/training-data/raw/`, but the account is suspended for billing
  and warns that data deletion may occur. These objects are not recoverable
  while the account remains suspended.
- Ten provider archives totaling 5,291,450,726 bytes are currently available
  from verified local copies. Every receipt records its provider checksum,
  SHA-256 checksum, byte count, and rights status. The status report separates
  local availability, verified remote storage, and unverified remote storage.
- The X-LANCE curation manifest is pinned to commit
  `7f55df1f84b127aaa27f57f9436538529ad09643`.
- That curation contains 479 unique RawStems songs: 414 electric-guitar,
  109 strings, and 93 wind/brass candidates.
- QuartSet contributes 538 unique accepted string clips from 56 compositions.
  It contains 2.18 target-active hours after rejecting 22 exact duplicates.
- TinySOL contributes 1,188 strings and 1,031 wind/brass files. It contains
  3.23 target-active hours after rejecting 254 non-target instruments and 15
  nearly silent files.
- ChoraleBricks contributes 199 original-dynamics wind/brass performances from
  13 chorales. It contains 1.99 target-active hours after rejecting 193
  normalized mirror files.
- Guitar-TECHS contributes 208 accepted DI and mic-amplifier WAV views across
  104 performance groups. The audit rejects all 208 lossy video-reference
  copies.
- Guitar-TECHS contains 10.05 hours of accepted file exposure and 7.49
  target-active hours across both synchronized views. Counting each paired
  performance once gives 5.02 timeline hours and 3.75 target-active hours.
- Guitar-TECHS is train-only augmentation because its three players use
  distinct gear and rooms, and Player 3 contains only musical excerpts.
  Validation and test must use independent multitrack songs.
- The EG-IPT remote ZIP inventory contains 52,317 real WAV files across six
  simultaneous recording views, three pickup positions, and 19 techniques.
  The full archive would require 23.8 GB compressed and 29.67 GB extracted.
- The selected EG-IPT corpus keeps the `dyn` close-mic amplifier view for every
  available take. This reduces transfer to 4.00 GB and extracted storage to
  4.94 GB without multiplying simultaneous views.
- EG-IPT contributes 8,628 accepted electric-guitar takes, 4.65 hours of file
  exposure, and 3.27 target-active hours. The audit rejects 89 near-silent
  takes, including one file that is also too short.
- EG-IPT is train-only articulation augmentation because all recordings use
  one professional guitarist in one studio setup. Independent songs and
  performers must supply validation and test data.

These numbers are measured from item manifests. They are not estimated source
durations or augmented exposure. The complete three-family corpus is not yet
ready because the remaining archives still require acquisition and audit.
QuartSet and TinySOL item manifests are measured, but their local archives were
removed before B2 read access was tested. Restore the B2 account or reacquire
those archives before training.

> **Warning:** Don't use `--cleanup` until the configured object store passes
> remote byte read-back. The audit command now rejects cleanup when its receipt
> lacks that proof.

Use these commands to reproduce the current state:

```bash
.venvs/training-data/bin/python3 scripts/acquire_training_source.py \
  inventory quartset

receipt=datasets/manifests/acquisition/quartset/\
zenodo-15708701/QuartSet.zip.receipt.json
.venvs/training-data/bin/python3 scripts/audit_training_archive.py \
  quartset "$receipt"

python3 scripts/report_training_data_status.py
```

## What X-LANCE actually used

X-LANCE combined RawStems and MoisesDB. It manually removed incorrectly
labelled RawStems examples and initialized its models from the pretrained
six-stem BS-RoFormer SW checkpoint.

The public paper and configurations show:

- RawStems contains 578 songs, eight broad groups, 17 finer groups, and 354.13
  hours of total annotated stem audio.
- MoisesDB contains 240 songs, 14 hours 24 minutes of mixtures, and hierarchical
  fine-grained instrument labels.
- X-LANCE trained four new broad specialists: synth, orchestra, percussion,
  and refined drums.
- It did not train separate kick, snare, strings, wind, or electric-guitar
  models.
- The synth specialist used RawStems `Synth` plus MoisesDB synth data.
- The orchestra specialist used RawStems `Orch` plus MoisesDB orchestra data.
- The percussion specialist used RawStems `Rhy_PERC` plus MoisesDB percussion.
- The drums specialist used RawStems `Rhy_DK` plus MoisesDB drums.
- Synth, orchestra, and percussion used ten-second clips without random
  cross-song mixing in the selected final configuration.
- Drums used ten-second clips with random mixture augmentation.
- Every final specialist trained for more than 200,000 steps on an H200 with
  batch size four.

At 200,000 steps, batch size four, and ten-second clips, each model receives at
least 2,222 sampled hours of training exposure. This does not mean it has 2,222
unique hours. The finite source corpus is sampled repeatedly with different
segments and mixtures.

X-LANCE did not publish the filtered song count or active hours for each target
after cleaning. No honest source can therefore state its exact per-stem data
quantity. RawStems also states that each audio file retains its original
creator's license, while MoisesDB is non-commercial. Their dataset recipe is
useful research evidence but is not our commercial data license.

Primary sources:

- <https://arxiv.org/abs/2602.09042>
- <https://github.com/ModistAndrew/xlance-msr>
- <https://arxiv.org/abs/2505.21827>
- <https://huggingface.co/datasets/yongyizang/RawStems>
- <https://arxiv.org/abs/2307.15913>

## What the Audio Separation community evidence adds

The Audio Separation Discord contains a useful first-hand account from a
strings-model author. On April 21 and 22, 2026, the author reported using about
45 MoisesDB songs, personal released songs, stems from industry contacts, and
roughly 400 one-minute arrangements created in FL Studio with virtual
instruments. The author varied key, EQ, effects, and wet/dry balance and said
the 400 arrangements took about 12 hours to create.

This is evidence that a producer can bootstrap labelled arrangements quickly.
It is not evidence that 400 arrangements are sufficient for a commercial
model:

- Four hundred one-minute arrangements contain at most 6 hours 40 minutes of
  audio before removing silence or measuring target-active time.
- The author said the strings dataset was difficult to source, described the
  resulting model as not the greatest, and reported a training mistake.
- Another strings researcher in the same discussion reported only 3.50 and
  3.60 dB SDR on the MVSep strings benchmark.
- A separate user's 15 to 20 hours of copyright-free recordings appeared as a
  question about sufficiency, not as a successful training result.
- A January 2026 community comment said the X-LANCE-related restoration system
  had not been tested thoroughly. Treat that as anecdotal caution, not a
  benchmark result.

The reproducible lesson is to automate short, varied arrangements and combine
them with real stems. We will reproduce the useful X-LANCE data direction in
`research_all`, including MoisesDB, while preserving enough provenance to
build a separate release checkpoint. Commercial sample-library terms may
prohibit machine-learning training or redistribution, so generated material
must still record every sample, MIDI source, license, and transformation.

Community source:

- <https://discord.com/channels/708579735583588363/1226334240250269797>

## Our data-sufficiency rule

We will not guess one universal number of hours. We will prove sufficiency with
a scaling curve for every trained target.

Before a full adapter run, each hard stem must have:

- At least 20 hours of target-active, commercially usable training audio
- At least 200 independent compositions or performances
- At least ten hours of real recordings rather than synthetic-only material
- At least 30 genre-matched real projects
- At least 20 untouched real songs for validation and final evaluation
- No shared song, MIDI arrangement, performer take, or recording across splits

For electric guitar, strings, and wind/brass, run the same short adapter on 25,
50, and 100 percent of the available corpus. Plot held-out SI-SDR, bleed, and
listening preference against data size.

The corpus is insufficient when the 100-percent run still improves by more than
0.5 dB over the 50-percent run or when real-song listening continues to improve
materially. Acquire more data before a long run.

The corpus may proceed when the scaling curve has flattened, synthetic and real
results agree, and the model beats the inherited candidate on untouched real
songs. This is stronger evidence than copying an unpublished X-LANCE hour
count.

## Immediate open-data sources

Every source must enter the rights ledger before training. CC BY and CC0 are
promising on their face, but we must archive the exact license, version,
attribution, source URL, and checksum.

### Electric guitar

The electric-guitar corpus should begin with real isolated performances and
then place them inside licensed mixtures.

- **Guitar-TECHS:** More than five hours of synchronized electric-guitar
  recordings from direct input, amplifier, egocentric, and exocentric
  microphones. It includes techniques, chords, scales, original solos, and
  MIDI. The publisher states CC BY 4.0.
- **AlbumDB:** Ten real multitrack songs with 13 to 35 tracks per song. It
  includes electric guitar, piano, kick, snare, and some additional instrument
  families. The dataset publication states CC BY 4.0.
- **Slakh2100:** Synthetic multitracks with aligned MIDI and electric-guitar
  classes. It provides mixture diversity but not enough real timbral diversity.
- **NSynth:** CC BY 4.0 isolated notes for augmentation only. Its 16 kHz
  monophonic clips cannot replace complete guitar performances.

Primary sources:

- <https://guitar-techs.github.io/>
- <https://doi.org/10.5281/zenodo.19683000>
- <https://www.slakh.com/>
- <https://magenta.tensorflow.org/datasets/nsynth>

### Strings

The strings corpus needs real bowing and ensemble interactions plus synthetic
scale.

- **QuartSet:** Real recordings for 56 string-quartet compositions, covering
  violin, viola, and cello. The dataset is approximately 795 MB.
- **Slakh2100:** Synthetic bowed-string and ensemble examples inside complete
  arrangements.
- **CocoChorales:** More than 1,400 hours of generated source-separated
  ensembles under CC BY 4.0. The full audio is 16 kHz and approximately 2.9 TB
  compressed, so we should not download it blindly.
- **VSCO Community:** A CC0 orchestral sample library that can render new
  44.1/48 kHz performances when paired with properly licensed MIDI.
- **TinySOL:** CC BY 4.0 isolated orchestral notes for articulation and timbre
  augmentation, not complete mixture training by itself.

Primary sources:

- <https://zenodo.org/records/15708701>
- <https://www.slakh.com/>
- <https://magenta.tensorflow.org/datasets/cocochorales>
- <https://versilian-studios.com/vsco-community/>
- <https://zenodo.org/records/3659365>

### Wind and brass

The wind/brass corpus should use real separated performances as anchors and
rendered arrangements for scale.

- **ChoraleBricks:** CC BY 4.0 multitracks from 11 musicians playing 13 wind
  and brass instruments. It contains 193 tracks and supports 4,582 ensemble
  combinations.
- **CocoChorales:** Separate violin, viola, cello, double bass, flute, oboe,
  clarinet, bassoon, saxophone, trumpet, horn, trombone, and tuba sources.
- **Slakh2100:** Synthetic mixtures and aligned MIDI for instrument-class
  diversity.
- **VSCO Community and TinySOL:** Permissive isolated samples for rendering
  additional arrangements at the required sample rate.

Primary sources:

- <https://www.audiolabs-erlangen.de/resources/MIR/2025-ChoraleBricks>
- <https://doi.org/10.5281/zenodo.15081741>
- <https://magenta.tensorflow.org/datasets/cocochorales>
- <https://www.slakh.com/>

### Kick and snare

Kick and snare already have a strong model candidate. These sources strengthen
qualification and provide fallback adaptation data.

- **Groove MIDI Dataset:** 13.6 hours of human-performed drums, aligned MIDI,
  and synthesized audio under CC BY 4.0. It includes Afrobeat and Highlife.
- **Expanded Groove MIDI Dataset:** 444.5 hours across 43 drum kits under CC
  BY 4.0. Its audio is a drum mixture, so isolated kick/snare targets should be
  rendered from MIDI using a training-safe sample library.
- **AlbumDB:** Real kick and snare tracks inside full production sessions.
- **Slakh2100:** Additional synthetic drum parts and complete mixtures.

Primary sources:

- <https://magenta.tensorflow.org/datasets/groove>
- <https://magenta.tensorflow.org/datasets/e-gmd>
- <https://doi.org/10.5281/zenodo.19683000>

### Piano

Piano should be benchmarked before new training. If it fails, use:

- Slakh2100 for aligned synthetic piano inside full mixtures
- AlbumDB for real multitrack context
- Directly licensed producer sessions for Afrobeats piano and keys

MAESTRO is valuable research data but is not the first commercial-training
choice because its license includes non-commercial restrictions.

## Dataset use profiles

The pipeline enforces two explicit profiles rather than relying on memory.
Rights status never substitutes for quality review: both profiles reject
corrupt audio, wrong labels, duplicates, split leakage, and unusable
recordings.

### Research all

Use every quality-approved source whose terms permit internal research,
including:

- Guitar-TECHS, EG-IPT, GOAT, AlbumDB, Slakh2100, and NSynth
- MoisesDB, MedleyDB, MUSDB, and label-reviewed RawStems
- SynthSOD, EnsembleSet, The Spheres Dataset, and QuartSet
- ChoraleBricks, CocoChorales, VSCO Community, TinySOL, URMP, and OrchideaSOL
- Quality-reviewed Freesound Loop Dataset items

This profile maximizes the evidence available for electric guitar, strings,
and wind/brass. Its checkpoints are research artifacts and are not eligible
for public or paid inference.

### Release eligible

These sources currently present permissive licenses suitable for a commercial
candidate on their face:

- Guitar-TECHS
- EG-IPT
- AlbumDB
- Slakh2100
- NSynth
- SynthSOD
- The Spheres Dataset
- ChoraleBricks
- CocoChorales
- VSCO Community
- TinySOL

Final release still requires attribution and legal review of the stored rights
ledger.

### Permission or item review required

These sources enter `research_all` now, but enter `release_eligible` only after
written permission or per-item review:

- Freesound items marked CC0 or CC BY, with uploader AI preference respected
- URMP
- OrchideaSOL
- Cambridge Multitrack Library contributors
- RawStems
- EnsembleSet RWC-derived items
- MoisesDB
- MedleyDB
- MUSDB
- GOAT
- StemGMD
- Commissioned session musicians
- Producer DAW sessions
- Gramosynth/Rightsify and MassiveMusic licensed-data offerings

When permission is granted, create a new immutable registry version. Do not
edit the provenance of an already trained checkpoint.

### Excluded from both profiles

These inputs remain excluded because they are not reliable labelled training
datasets, lack defensible provenance, or create circular pseudo-ground truth:

- Telefunken educational multitracks
- Remix-contest stems
- YouTube or streaming-service audio
- Splice samples
- LALAL.AI, Moises, or MVSep outputs used as pseudo-ground truth
- Any DAW project containing undisclosed third-party loops or samples

Research access, public download, or a repository license does not override the
audio rightsholder's terms. A source with a known non-commercial research grant
belongs in `research_all`; a source with no defensible provenance belongs in
neither profile.

## Exact pilot corpus

The first adapter pilots do not need every dataset on the internet. They need a
small, high-density corpus with exact labels.

### Electric-guitar pilot

Use:

- All accepted Guitar-TECHS performance material
- AlbumDB electric-guitar tracks
- A stratified Slakh electric-guitar subset
- At least ten directly licensed producer or session-musician projects

Create mixtures containing hard interferers such as acoustic guitar, synth,
piano, strings, and vocals. At least half of training inputs should use the
same predicted guitar/other parent produced by the product router.

### Strings pilot

Use:

- QuartSet real performances
- A strings-only CocoChorales subset
- A stratified Slakh strings subset
- Additional CC0 orchestral renders
- At least ten directly licensed pop or Afrobeats string sessions

Generate an initial batch of at least 400 one-minute arrangements with
rights-cleared samples and MIDI. Randomize orchestration, key, register,
articulation, tempo, dynamics, room response, EQ, and wet/dry balance. Preserve
the dry target before effects so each mixture has exact ground truth. Treat
this batch as bootstrap coverage, not as the 20-hour sufficiency gate.

Do not let repeated movements or MIDI arrangements cross the train and
evaluation split.

### Wind/brass pilot

Use:

- ChoraleBricks real performances
- A wind/brass CocoChorales subset
- A stratified Slakh wind/brass subset
- Additional CC0 orchestral renders
- At least ten directly licensed horn, saxophone, or wind sessions

Include synth brass, vocals, distorted guitar, and strings as hard interferers.

## Real-session acquisition program

Synthetic data teaches labels and coverage. Direct contributor sessions teach
the production domain.

### Outreach channels

Contact:

- Existing producer and artist relationships through WhatsApp and Instagram
- Nigerian, Ghanaian, Kenyan, and South African studios in the Music In Africa
  directory
- Session musicians on SoundBetter, AirGigs, and Fiverr
- Music schools, church bands, horn sections, string quartets, and university
  recording programs
- Cambridge MT artists and producers individually, not the library as a whole

Useful directories:

- <https://www.musicinafrica.net/directory-categories/recording-studios>
- <https://soundbetter.com/>
- <https://www.airgigs.com/>
- <https://www.fiverr.com/>

### Contributor offer

An initial low-cash offer can include:

- `$25` for one accepted existing project
- `$100` for five accepted projects
- `$10` referral reward
- One year of the product's Pro plan
- Optional public credit and contributor badge
- `$50` to `$150` for commissioned specialist packs

Payment occurs only after rights and technical quality checks pass.

### Required contributor rights

A lawyer-reviewed release must explicitly grant rights to:

- Reproduce, clean, edit, remix, annotate, and store the submitted audio
- Train, evaluate, fine-tune, and validate machine-learning models
- Use cloud processors and contractors
- Commercialize and distribute derived model weights
- Offer paid and free inference using the trained models
- Retain derived weights after the raw-data agreement ends

The contributor must confirm control of the master, composition, performances,
and all included samples. The agreement should prohibit redistribution of the
raw audio while allowing contributors to retain and release their songs.

### Required technical delivery

Every accepted session must provide:

- 24-bit WAV where available
- Native 44.1 or 48 kHz sample rate
- All files consolidated from the same start time
- Dry stems where available
- A reference mix
- No clipping or lossy source files
- Exact instrument labels
- BPM, key, genre, and production year
- Performer and recording-chain metadata
- Complete sample and loop disclosure

The stems must reconstruct the reference mix within a documented tolerance.

## Storage and provenance

Raw data must be immutable. Processing creates new versions rather than
changing source files.

```text
datasets/
  registry/specialist_sources.yaml
  raw/<source>/<version>/
  licenses/<source>/<version>/
  manifests/<source>-<version>.jsonl
  corpora/research_all/<corpus-version>.json
  corpora/release_eligible/<corpus-version>.json
  processed/<recipe-version>/<split>/
  evaluations/<corpus-version>/
```

Every manifest row must contain:

- Dataset and version
- Source URL and source record ID
- Track, stem, and contributor IDs
- Instrument taxonomy
- Original and normalized sample rates
- Audio checksum
- License and archived license checksum
- Attribution text
- Commercial-training decision
- Reviewer and review date
- Train, validation, or test split
- Every processing and augmentation step

Downloads should use official APIs or repository clients and verify publisher
checksums. Do not build a generic web scraper.

## The first 48 hours

The acquisition sprint should run in parallel.

### Hours 0 to 8

- [ ] Create the rights-ledger and dataset-manifest schema.
- [ ] Snapshot licenses and metadata for all green sources.
- [ ] Start Guitar-TECHS, QuartSet, ChoraleBricks, AlbumDB, and Groove MIDI
      downloads.
- [ ] Start a full-resolution Slakh transfer directly into B2.
- [ ] Send the contributor release for legal review.

### Hours 8 to 20

- [ ] Hash and inventory every downloaded file.
- [ ] Normalize the product instrument taxonomy.
- [ ] Reserve composition-level validation and evaluation splits.
- [ ] Select only required CocoChorales subsets or MIDI; do not fetch 2.9 TB.
- [ ] Send outreach to 50 producers, 30 studios, and 20 session musicians.

### Hours 20 to 34

- [ ] Render Groove MIDI and selected orchestral MIDI at 44.1/48 kHz.
- [ ] Generate the first 400 rights-cleared, one-minute strings arrangements.
- [ ] Build electric-guitar, strings, and wind/brass target/interferer mixtures.
- [ ] Generate production-parent inputs using the current product router.
- [ ] Reject silence, clipping, misalignment, duplicates, and mislabeled stems.

### Hours 34 to 48

- [ ] Run tiny-set overfit checks for the two planned adapters.
- [ ] Run the 1,000-step cost and throughput calibration.
- [ ] Compare pilot outputs against inherited checkpoints.
- [ ] Record permission requests for every useful yellow source.
- [ ] Accept, repair, or reject the corpus before a longer run.

## Fourteen-day acquisition target

By day 14, target:

- 60 to 100 accepted real projects
- At least 30 Afrobeats or African-pop projects
- At least ten real target-active hours for each trained hard stem
- Complete synthetic coverage for every target family
- At least 30 independent real projects per trained hard stem
- A frozen, song-disjoint evaluation corpus
- Zero release-training items with unknown or unresolved commercial rights

This is enough for credible adapters and an honest product decision. It is not
the final data moat. Contributor acquisition should continue after launch.

## Decision rule

The data problem is solved for the first release when:

1. Each target has exact, aligned, commercially usable labels.
2. The training split contains synthetic scale and real timbral diversity.
3. The evaluation split contains untouched real songs.
4. No composition, recording, performer take, or source MIDI crosses splits.
5. Every item has an immutable rights and processing record.
6. The adapters improve real held-out songs, not only synthetic benchmarks.

If a model fails after these conditions hold, the next problem is model
adaptation. Before these conditions hold, more GPU time is not the solution.

For `research_all`, replace the first condition with exact, aligned labels and
a recorded right to internal research use. That profile can determine the
quality ceiling while permission work continues.

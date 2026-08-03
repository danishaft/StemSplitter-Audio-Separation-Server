# Proven 12-stem model implementation plan

This document replaces the experimental six-specialist training strategy with
one evidence-backed model path. The project will copy released research
systems at pinned revisions before introducing any project-specific training
change.

## Final decision

The final product contract remains:

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

The runtime will use six checkpoints across four proven model families:

- Mel-Band RoFormer for vocals and instrumental.
- BS-RoFormer SW for drums, bass, piano, and the internal `other` parent.
- MDX23C DrumSep for kick and snare.
- The two released X-LANCE synth checkpoints as a sequential synth refiner.
- One ACMID-compatible seven-output SCNet for acoustic guitar, electric
  guitar, strings, and wind and brass.

The broad `guitar` and `other` outputs remain internal routing artifacts. They
aren't part of the final 12-stem download.

## Why this path is proven

X-LANCE won the 2025 Music Source Restoration challenge with sequential
BS-RoFormer models. Its published system starts with a frozen six-stem
BS-RoFormer, then applies specialist refiners. It uses cleaned RawStems and
MoisesDB data, 10-second clips for selected specialists, L1 plus
multi-resolution STFT loss, mixed precision, and more than 200,000 training
steps per specialist.

ACMID addresses our exact unresolved classes: acoustic guitar, electric
guitar, strings, and wind and brass. Its best seven-stem SCNet reached these
test SDR values:

| Stem | Published SDR |
| --- | ---: |
| Piano | 6.07 dB |
| Drums | 8.05 dB |
| Bass | 6.84 dB |
| Acoustic guitar | 5.49 dB |
| Electric guitar | 5.72 dB |
| Strings | 5.93 dB |
| Wind and brass | 4.24 dB |

ACMID also measured a 2.39 dB average gain from cleaning web data and a
1.16 dB gain from adding the cleaned corpus to MoisesDB and MedleyDB. This
means target purity and dataset scale are required parts of the model recipe.

Banquet isn't the production replacement for these classes. Its released
MoisesDB result files average approximately -0.13 dB for bowed strings and
0.17 dB for wind. SIREN-SEPARATE has no published benchmark or research paper
that verifies its granular claims. Mega53 provides many output names but no
comparable published per-stem benchmark or clear checkpoint license.

## Runtime graph

The final routing graph is:

```text
song
├── Mel-Band RoFormer
│   ├── vocals
│   └── instrumental
├── BS-RoFormer SW
│   ├── drums
│   │   └── MDX23C DrumSep
│   │       ├── kick
│   │       └── snare
│   ├── bass
│   ├── piano
│   └── other
│       └── X-LANCE synth v1 -> X-LANCE synth v2
│           └── synth
└── instrumental
    └── ACMID-compatible seven-stem SCNet
        ├── acoustic_guitar
        ├── electric_guitar
        ├── strings
        └── wind
```

SCNet also predicts drums, bass, and piano. Those duplicate predictions are
benchmark comparators until they beat the current owners on the same held-out
corpus.

## Work to stop

Stop the following work immediately:

- Don't continue the 25-step or 1,000-step specialist checkpoints.
- Don't train a strings head as a proxy for wind and brass.
- Don't add SI-SDR, bleed, fullness, LoRA, head-freezing, or custom residual
  losses to the first reproduction.
- Don't treat a file-created check, one song, or one short run as model
  qualification.
- Don't use Banquet, SIREN, Mega53, or unlicensed community checkpoints as the
  production owner for the unresolved stems.
- Don't spend GPU credit until the exact published data and model preflight
  passes locally or on CPU.

Keep the old checkpoints, receipts, and benchmark files as negative research
evidence. Remove them from product-selection logic, not from history.

## Phase 1: reproduce X-LANCE synth

Copy the released X-LANCE path without modification:

1. Pin `ModistAndrew/xlance-msr` at commit
   `7f55df1f84b127aaa27f57f9436538529ad09643`.
2. Acquire `syn_mss.pth` and `syn_mss1.pth` from the official MIT-licensed
   `chenxie95/xlance-msr-ckpt` repository.
3. Generate BS-RoFormer SW `other` parents for the existing nine-track
   BabySlakh gate.
4. Run `syn_mss.pth` followed by `syn_mss1.pth`, matching the released
   sequential inference behavior.
5. Score the complete chain against ground-truth synth stems.
6. Publish synth only if the complete released chain beats each individual
   checkpoint, has positive aggregate and median SI-SDR, and has no segment
   below the family-specific catastrophic-failure floor.

This phase corrects the previous qualification, which tested individual
checkpoints rather than the published two-checkpoint system.

The July 28, 2026 reproduction rejected the released chain. It reached
`-1.5191 dB` aggregate SI-SDR on the full mixture and `-1.4828 dB` on the
BS-RoFormer `other` parent. Parent routing reduced the worst failure from
`-28.4177 dB` to `-16.2193 dB`, but it did not produce release-quality synth.
Do not add routing heuristics around this checkpoint pair. Use X-LANCE's
published data and training recipe to produce a stronger checkpoint.

## Phase 2: reproduce ACMID data cleaning

Use ACMID's released cleaners before building another training batch:

1. Pin `scottishfold0621/ACMID` at commit
   `ac7b55f86d5b53c85a7739acb9e47f64fdfb7b59`.
2. Use the seven released frozen-Dasheng classifier heads.
3. Convert candidates to 16 kHz mono and split them into 3-second segments.
4. Retain segments at the published inference threshold of `0.995`.
5. Reassemble retained segments by source and preserve source, composition,
   license, split, classifier, and checksum metadata.
6. Keep composition-level train, validation, and test boundaries.
7. Combine cleaned sources with MoisesDB and MedleyDB using their official
   train, validation, and test partitions.

The first reproduction corpus must cover all seven ACMID classes. It must not
train from the existing three-family indexes alone.

Use the published corpus floor as the scale target:

- At least 70 clean hours for each of the seven classes.
- At least 737 clean hours in total across all seven classes.
- No composition overlap between train, validation, and test.
- A manual purity review of a fixed random sample from every class.

The current project corpus is useful input, but it doesn't yet reproduce this
scale. It has about 54 hours of electric guitar, 59 hours of strings, and
59 hours of wind and brass before ACMID's `0.995` purity filter.

## Phase 3: reproduce ACMID SCNet

Create one seven-output SCNet with the paper's settings:

- Input: stereo, 48 kHz, 10 seconds.
- Outputs: piano, drums, bass, acoustic guitar, electric guitar, strings, and
  wind and brass.
- FFT: 4096.
- Hop size: 1024.
- Window size: 4096.
- Band sample-rate ratios: `0.230`, `0.370`, and `0.400`.
- Band convolution depths: `3`, `2`, and `1`.
- Downsampling layers: 8.
- Compression factor: 4.
- Optimizer: Adam.
- Learning rate: `1e-4`.
- Batch size: 8.
- Precision: mixed.
- Maximum epochs: 1,000.
- Learning-rate reduction: factor `0.95`, patience `2`, based on validation
  loss.

Use the pinned ZFTurbo SCNet implementation and its standard SCNet loss. Don't
add project-specific loss terms during reproduction.

Run a complete preflight before paid training:

1. Materialize one batch with all seven targets.
2. Verify mixture reconstruction and tensor shapes.
3. Run forward, backward, optimizer, scheduler, save, and resume operations.
4. Overfit a tiny fixed set to prove the data/model contract.
5. Compare one validation pass against untouched references.

Only then start the full run. Select checkpoints by validation loss and report
SDR on untouched MoisesDB and MedleyDB test songs.

## Phase 4: qualification and product wiring

Use one immutable evaluation corpus for every candidate. Qualification must
produce per-song and per-stem SDR, SI-SDR, bleed/interference measurements,
silent-target behavior, listening examples, inference time, VRAM, and cost.

The ACMID reproduction target is at least the paper's reported SDR for each
published stem. A model that misses one target remains experimental for that
stem even if its average passes.

After qualification:

1. Assign the strongest verified model owner to each of the 12 outputs.
2. Keep duplicate SCNet outputs internal unless they beat the current owner.
3. Add the four accepted SCNet outputs and synth to the manifest, API, UI, and
   ZIP package.
4. Preserve `other` and broad `guitar` only as internal parent stems.
5. Record checkpoint source, revision, hash, license, scorecard, and runtime
   cost in the model registry.

## Acceptance criteria

The model program is complete only when:

- The released X-LANCE synth chain has been reproduced and measured on both
  documented input routes.
- The seven ACMID classifiers have cleaned every training source.
- The seven-stem SCNet configuration matches the paper.
- The full training corpus meets the published scale floor.
- The held-out benchmark contains no training compositions.
- Every published stem meets its own quality threshold.
- All six runtime checkpoints have pinned sources, hashes, and acceptable
  licenses.
- One end-to-end job returns exactly the 12 contracted stems.

## Primary references

- ACMID paper: <https://arxiv.org/abs/2510.07840>
- ACMID code and cleaner weights:
  <https://github.com/scottishfold0621/ACMID>
- X-LANCE paper: <https://arxiv.org/abs/2602.09042>
- X-LANCE code: <https://github.com/ModistAndrew/xlance-msr>
- Official X-LANCE checkpoints:
  <https://huggingface.co/chenxie95/xlance-msr-ckpt>
- ZFTurbo training framework:
  <https://github.com/ZFTurbo/Music-Source-Separation-Training>
- Banquet code and released result files:
  <https://github.com/kwatcharasupat/query-bandit>

## Next steps

Implement Phase 1 first because it uses released checkpoints and requires no
training. In parallel, add ACMID classifier inference to the existing corpus
pipeline and measure the clean hours that remain after the `0.995` filter.

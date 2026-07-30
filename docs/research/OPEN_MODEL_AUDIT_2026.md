# Open model audit 2026

This audit records the current Hugging Face and GitHub model evidence for the
local stem splitter. The goal is to avoid guessing: a model only moves forward
when it has a clear role, accessible weights, a plausible runner, and a license
status that we can reason about.

## Bottom line

There is active 2026 work in open stem separation. The current registry is
missing several useful candidates, but most of them are not drop-in runtime
models yet because they require new runner support.

- `StemSplitio/htdemucs-6s-onnx` is a real local 6-stem ONNX candidate for
  drums, bass, other, vocals, guitar, and piano.
- `HiDolen/Mini-BS-RoFormer-V2-46.8M` is a compact local BS-RoFormer candidate
  with public HF weights, but the license is non-commercial.
- `gridshiftstudio/drumsep-onnx` is a local drum-element ONNX candidate for
  kick, snare, cymbals, and toms.
- `anvuew/dereverb_bs_roformer` is a stronger local dereverb candidate than the
  current MelBand dereverb entry, but its GPL-3.0 license needs an explicit
  product decision.
- `hilarl/siren-separate` is promising for query-based granular extraction, but
  it is gated and cannot be counted as locally available yet.

This is not the full universe of current research. It is the first
downloadable-weight pass. A second pass must audit challenge systems, SCNet
families, SFX models, and training-code pretrained checkpoints before we call
the model map complete.

## Availability decisions

Use this table as the decision source before adding models to the runtime
registry.

| Candidate | Role | Access | Runner gap | License | Decision |
| --- | --- | --- | --- | --- | --- |
| `StemSplitio/htdemucs-6s-onnx` | Six-stem broad model with guitar and piano | Public HF weights, 394.6 MB dry-run | Needs ONNX runner | MIT | Acquire as benchmark candidate |
| `StemSplitio/htdemucs-ft-onnx` | Strong four-stem Demucs FT ONNX package | Public HF weights, 1.9 GB dry-run | Needs ONNX runner | MIT | Hold unless ONNX runner proves useful |
| `StemSplitio/htdemucs-ft-vocals-onnx` | Vocal specialist ONNX fallback | Public HF weights, 482.1 MB dry-run | Needs ONNX runner | MIT | Hold; current RoFormer vocal bench is stronger |
| `HiDolen/Mini-BS-RoFormer-V2-46.8M` | Compact four-stem BS-RoFormer candidate | Public HF weights, 94 MB dry-run | Needs Transformers/custom-code runner | CC-BY-NC-4.0 | Acquire for research benchmark only |
| `gridshiftstudio/drumsep-onnx` | Drum element split: kick, snare, cymbals, toms | Public HF weights, 335.1 MB dry-run | Needs ONNX drum runner | MIT | Acquire as local DrumSep replacement candidate |
| `splitzo/drumsep` | DrumSep ONNX mirror | Public HF weights, 335.1 MB dry-run | Needs ONNX drum runner | MIT | Do not duplicate; prefer Gridshift manifest |
| `anvuew/BS-RoFormer` | BS-RoFormer vocal/instrumental candidates | Public HF weights, 409 MB dry-run | Needs BS-RoFormer runner | GPL-3.0 | Hold; overlaps current Viperx RoFormers |
| `anvuew/dereverb_bs_roformer` | Strong dereverb candidate | Public HF weights, 736.8 MB repo dry-run | Needs BS-RoFormer runner | GPL-3.0 | Acquire only selected top checkpoint |
| `mlx-community/mel-roformer-zfturbo-vocals-v1-mlx` | Lightweight vocal model for Apple MLX | Public HF weights, 67.4 MB dry-run | MLX-only path, not Linux-first | MIT | Hold for Apple-specific path |
| `hilarl/siren-separate` | Query-based granular extraction from other stem | Gated HF repo; approval required | Needs query runner and access approval | Apache-2.0 stated | Blocked until access approved |

## Impact on the eight remote-only gaps

The audit changes the drum strategy, but it does not fully close strings,
synth, wind, SFX, or lead/back vocal separation.

- Drum sub-stems now have another local path: `gridshiftstudio/drumsep-onnx`.
- Guitar and piano get another local path through `StemSplitio/htdemucs-6s-onnx`.
- Strings still need MVSEP, SIREN access, or a newly found local model.
- Synth and keys still need MVSEP, SIREN access, or a newly found local model.
- Wind and brass still rely on the weak `17_HP-Wind_Inst-UVR.pth` fallback.
- SFX still needs MVSEP, BandIt/DnR-style local work, or SIREN access.
- Lead and backing vocals still need MVSEP karaoke, verified local karaoke
  weights, or a better public model.

## Second-pass audit backlog

These areas are explicitly not closed yet. They may contain stronger models
than the first-pass list, or training code that can produce the missing local
specialists.

| Area | Why it matters | Current status | Next action |
| --- | --- | --- | --- |
| ZFTurbo pretrained ecosystem | MVSep-linked training code for RoFormer, MelBand, SCNet, BandIt, and ensembles | Training repo confirmed; pretrained-model map not fully extracted | Audit `docs/pretrained_models.md` and matching HF links |
| Music Demixing Challenge / SDX systems | Competition submissions expose serious architectures and benchmark practice | Challenge papers and starter kits confirmed | Extract winning architectures and public weights |
| SCNet and Band-SCNet | Lightweight strong four-stem architecture; relevant for local speed and quality | Papers confirmed; local weights still need search | Find maintained inference repo and downloadable checkpoints |
| Moises-Light | Resource-efficient band-split U-Net direction from commercial-adjacent research | Paper found; public weights not confirmed | Check author/project release status |
| BandIt / DnR / SFX separation | Most relevant path for music, speech, and SFX separation | UVR discussion points to ZFTurbo/MVSep BandIt path | Verify current weights and runner path |
| Lead/back vocal local karaoke models | Required for LALAL-style vocal split parity | Current local source is blocked/unverified | Search UVR/audio-separator catalog and HF for verified weights |
| Strings/synth/wind local replacements | Required to reduce MVSEP dependency | Still remote-led or weak local fallback | Search HF/GitHub by stem family and benchmark terms |

## Second-pass discoveries

The second search pass found several concrete local-weight sources that reduce
the remote-only gap. These entries still need runner integration and listening
tests before promotion.

| Candidate | Role | Access | Size | Decision |
| --- | --- | --- | --- | --- |
| `oulianov/BS-Roformer-BowedStrings-Duality` | Strings and bowed strings local candidate | Public HF weights | 303.5 MB | Acquire |
| `oulianov/bsroformer-lead-synth` | Lead/synth local candidate | Public HF weights | 170.8 MB | Acquire |
| `oulianov/MelBandRoformer-Duet` | Duet or lead/back vocal experiment | Public HF weights | 630.2 MB | Acquire |
| `oulianov/BS-Roformer-DrumsOther-Duality` | Drums versus other candidate | Public HF weights | 303.5 MB | Acquire if disk and time allow |
| `oulianov/mvsep_mega_53` | Very broad 53-stem experimental model | Public HF weights | 1.4 GB | Acquire for research; do not default |
| `oulianov/denoise_debleed_gabox` | Denoise/debleed candidate | Public HF weights | 913.0 MB | Hold unless current denoise/debleed fails |
| `oulianov/mel_band_roformer_crowd_aufr33_viperx` | Crowd/no-crowd candidate | Public HF weights | 913.1 MB | Hold unless crowd cleanup becomes priority |
| Audio-separator karaoke models | Karaoke and vocal/instrumental fallback | Public catalog filenames | Varies | Acquire selected strongest only |
| ZFTurbo pretrained model list | RoFormer, SCNet, BandIt, SFX, DrumSep, denoise, crowd, dereverb | Public documentation list | Varies | Extract exact current HF URLs next |

## Second-pass acquisition queue

Acquire these after the first open-model audit queue is complete.

1. `oulianov/BS-Roformer-BowedStrings-Duality`.
2. `oulianov/bsroformer-lead-synth`.
3. `oulianov/MelBandRoformer-Duet`.
4. `oulianov/BS-Roformer-DrumsOther-Duality`.
5. `oulianov/mvsep_mega_53`.
6. `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt` from the
   audio-separator catalog.
7. `UVR_MDXNET_KARA_2.onnx` from the audio-separator catalog.
8. `UVR-MDX-NET_Crowd_HQ_1.onnx` from the audio-separator catalog if crowd
   cleanup becomes part of the near-term benchmark.

## Acquisition queue

Acquire these as local benchmark candidates after the current audio-separator
cache is stable.

1. Download `gridshiftstudio/drumsep-onnx`.
2. Download `HiDolen/Mini-BS-RoFormer-V2-46.8M`.
3. Download `StemSplitio/htdemucs-6s-onnx`.
4. Download only `dereverb_bs_roformer_anvuew_sdr_22.5050.ckpt` and
   `config.yaml` from `anvuew/dereverb_bs_roformer`.
5. Retry `BS-Roformer-SW.ckpt`; the previous audio-separator download failed
   at 608 MB of 699 MB due to an incomplete network read.

## Registry actions

Do not add these candidates to `models/selected_specialist_models.yaml` as
runtime models until the runner set is expanded. The current registry accepts
`audio_separator`, `bs_roformer_infer`, `melband_roformer_infer`,
`mvsep_remote`, and `commercial_comparator`. The audited candidates need new
runner types:

- `onnx_demucs_runner`
- `onnx_drumsep_runner`
- `transformers_bs_roformer_runner`
- `bs_roformer_checkpoint_runner`

## Sources

- StemSplitio Music Source Separation Toolkit 2026:
  https://huggingface.co/collections/StemSplitio/music-source-separation-toolkit-2026
- StemSplitio benchmark dataset:
  https://huggingface.co/datasets/StemSplitio/stem-separation-benchmark-2026
- StemSplitio htdemucs 6-stem ONNX:
  https://huggingface.co/StemSplitio/htdemucs-6s-onnx
- HiDolen Mini-BS-RoFormer V2:
  https://huggingface.co/HiDolen/Mini-BS-RoFormer-V2-46.8M
- Gridshift DrumSep ONNX:
  https://huggingface.co/gridshiftstudio/drumsep-onnx
- Splitzo DrumSep ONNX mirror:
  https://huggingface.co/splitzo/drumsep
- anvuew BS-RoFormer:
  https://huggingface.co/anvuew/BS-RoFormer
- anvuew dereverb BS-RoFormer:
  https://huggingface.co/anvuew/dereverb_bs_roformer
- ZFTurbo Music Source Separation Training:
  https://github.com/ZFTurbo/Music-Source-Separation-Training
- python-audio-separator:
  https://github.com/nomadkaraoke/python-audio-separator
- BS-RoFormer-Infer:
  https://pypi.org/project/bs-roformer-infer/
- SIREN-SEPARATE:
  https://huggingface.co/hilarl/siren-separate

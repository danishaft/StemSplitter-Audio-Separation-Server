# Specialist model selection

This document chooses the first specialist model stack for the commercial-grade
stem splitter plan. The selections are candidates, not final approvals. A model
becomes product-approved only after license audit, local runner integration,
benchmark scoring, and listening review.

## Selection rules

The model stack must cover the LALAL-style product gap without pretending that
every downloadable checkpoint is safe or useful. Each selected model has a
specific role, a runner path, and a verification requirement.

- Use benchmark-leading models where they are available.
- Use local models first when they have a credible runner.
- Use remote or commercial tools as comparator targets when local weights are
  unavailable.
- Keep fallback models for every major stem family.
- Do not mark any model as commercial-approved until license status is known.

## Current runtime status

The Modal GPU worker now has a validated 15-model local runtime profile. The
current product contract is `quality_8_stems`: vocals, instrumental, drums,
bass, guitar, piano, kick, and snare. The worker can produce extra broad,
derived, and specialist files, but lead/back vocals, strings, synth, wind, and
SFX remain candidate or comparator work until they pass direct scoring and
listening review.

The follow-up 2026 open-model audit is recorded in
`OPEN_MODEL_AUDIT_2026.md`. That audit found additional public local candidates,
including `StemSplitio/htdemucs-6s-onnx`, `HiDolen/Mini-BS-RoFormer-V2-46.8M`,
`gridshiftstudio/drumsep-onnx`, and `anvuew/dereverb_bs_roformer`. They remain
outside the runtime registry until a runner path and benchmark result are
verified.

| Item | Status |
| --- | --- |
| `audio-separator 0.44.3` | Installed in `.venvs/audio-separator` |
| `quality_gpu_experimental` | 15 validated local/cacheable models |
| Remote-only comparator models | 8 planned models |
| Local smoke-passed candidate queue | 5 planned candidates |
| External runner sanity-passed candidates | 1 planned candidate |
| Downloaded external research candidates | 2 planned candidates |
| Blocked external research candidates | 2 planned candidates |
| Quarantined replaced models | 1 replaced model |
| BS-RoFormer SW | Validated in the Modal worker |
| MelBand-RoFormer vocal models | Validated in the Modal worker |
| MDX23C DrumSep | Validated in the Modal worker |
| Dereverb, deecho, and denoise models | Validated with RoFormer DeEcho replacement |
| Strings, synth, and SFX specialists | Remote/comparator only |

## Download policy

The selected stack uses explicit download policies. These policies prevent the
model cache from becoming an untracked junk drawer.

| Policy | Meaning |
| --- | --- |
| `immediate` | Download during the first relevant model pack. |
| `later_if_needed` | Download only if primary models fail or a benchmark needs the fallback. |
| `external_runner_experimental` | Run through an isolated external Python worker only; do not include in the default GPU profile. |
| `remote_only` | Do not download locally; call through MVSEP or use as a remote benchmark target. |
| `blocked_until_source_verified` | Do not download until the exact local source and runner are verified. |
| `quarantined_replaced` | Keep a failed model visible after it has been replaced. |
| `comparator_only` | Do not download as a model; import outputs from a commercial/manual tool. |

## Chosen model matrix

This matrix is the source of truth for the first registry seed. The selected
models are ordered by expected value, not by implementation difficulty.

| Stem family | Primary selected model | Fallbacks | Runner path | Status |
| --- | --- | --- | --- | --- |
| Broad six-stem: vocals, drums, bass, guitar, piano, other | `BS-RoFormer SW` / `roformer-model-bs-roformer-sw-by-jarredou` | `htdemucs_ft`, `htdemucs_6s`, `MDX23C-InstVoc`, `MelBand Inst` | `audio-separator` in the Modal worker | Validated runtime model; license audit still needed |
| Vocals / instrumental | `vocals_mel_band_roformer.ckpt` / `melband-roformer-kim-vocals` | `model_bs_roformer_ep_368_sdr_12.9628.ckpt`, `model_bs_roformer_ep_317_sdr_12.9755.ckpt`, `MDX23C-8KFFT-InstVoc_HQ_2.ckpt`, `Kim_Vocal_2.onnx` | `melband-roformer-infer` and `audio-separator` | Selected, needs benchmark |
| Lead/back vocals | `Mel-RoFormer Karaoke / Duet`, `UVR-BVE-4B_SN-44100-1.pth`, and `MVSep Karaoke BS-RoFormer Team` | `mel_band_roformer_karaoke_gabox.ckpt`, `mel_band_roformer_karaoke_becruily.ckpt`, `UVR_MDXNET_KARA_2.onnx` | `audio-separator`, MVSEP adapter, or external runner | Runtime has BVE for backing vocals and derives lead as `vocals - backing_vocals`; remaining candidates passed smoke tests and need benchmark review |
| Dry vocal / vocal reverb residual | `dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt` | `dereverb_mel_band_roformer_less_aggressive_anvuew_sdr_18.8050.ckpt`, `deverb_bs_roformer_8_384dim_10depth.ckpt`, `Reverb_HQ_By_FoxJoy.onnx`, `UVR-DeEcho-DeReverb.pth` | `audio-separator` | Validated runtime model |
| Echo removal | `dereverb-echo_mel_band_roformer_sdr_13.4843_v2.ckpt` | `UVR-De-Echo-Normal.pth` is quarantined | `audio-separator` | Validated local replacement |
| Noise removal | `UVR-DeNoise.pth` | `UVR-DeNoise-Lite.pth` | `audio-separator` | Validated runtime model |
| Broad drums | `BS-RoFormer SW` | `htdemucs_ft`, `MVSep Drums MelBand + SCNet XL Ensemble` | `bs-roformer-infer`, Demucs, MVSEP adapter | Selected |
| Drum sub-stems: kick, snare, toms, hi-hat, ride, crash | `MDX23C-DrumSep-aufr33-jarredou.ckpt` for first local pass | `DrumSep MelBand RoFormer v2`, `DrumSep SCNet XL 5-stem`, `DrumSep SCNet XL 6-stem` | `audio-separator` first, MVSEP/DrumSep runner later | Selected |
| Bass | `BS-RoFormer SW` | `hdemucs_mmi`, `htdemucs_ft`, `kuielab_a_bass.onnx` | `bs-roformer-infer`, Demucs, audio-separator | Selected |
| Guitar | `BS-RoFormer SW` | `htdemucs_6s`, `MLSLABS WCJ` as comparator | `bs-roformer-infer`; comparator import for MLSLABS/Logic | Selected, not from audio-separator guitar filter |
| Piano | `BS-RoFormer SW` | `htdemucs_6s`, `MLSLABS WCJ` and Logic as comparators | `bs-roformer-infer`; comparator import for Logic/MLSLABS | Selected, not from audio-separator piano filter |
| Strings | `MVSep Strings BSRoformer (2025.09)` | `Loom of Time BSRoFormer`; accept access for `SIREN-SEPARATE` or replace it | MVSEP adapter, external Python runner | Remote benchmark selected; Loom checkpoint and runner load are verified, but code-license and quality gates remain open; SIREN access is requested |
| Wind / brass | `MVSep Wind BS-RoFormer` | `MelBand + SCNet Ensemble`, `SCNet Large`, `17_HP-Wind_Inst-UVR.pth` | MVSEP adapter first, audio-separator rough fallback | Selected as remote benchmark; local fallback weak |
| Synth / keys | `MVSep Synth BS-RoFormer` | `other` from BS-RoFormer SW as parent candidate; accept access for `SIREN-SEPARATE` or replace it | MVSEP adapter or external Python runner | Remote benchmark selected; no available local synth specialist is verified |
| Pads / FX / SFX | `Cocktail Fork MRX`, `BandIt v2`, and `TUSS medium` as rejected SFX evidence | `MVSep music/sfx/speech ensemble`, CDX23, and stronger future local replacements | Standalone Modal workers for external runners; MVSEP adapter as comparator | TUSS directly supports `speech`, `sfxbg`, and `musicbg`, but its comparator benchmark still rejects production `sfx`. Cocktail Fork and BandIt also fail the production SFX comparator. CDX23 remains license-blocked |
| Crowd / room noise cleanup | `UVR-MDX-NET_Crowd_HQ_1.onnx` | `UVR-DeNoise.pth` | `audio-separator` | Optional cleanup candidate |

## Download priority packs

The models must be downloaded in controlled packs so the benchmark can tell us
which family improved the product.

### Pack 1: Broad and instrument foundation

This pack addresses the biggest quality gap first.

- `BS-RoFormer SW` / `roformer-model-bs-roformer-sw-by-jarredou`.
- `model_bs_roformer_ep_368_sdr_12.9628.ckpt`.
- `model_bs_roformer_ep_317_sdr_12.9755.ckpt`.
- `MDX23C-8KFFT-InstVoc_HQ_2.ckpt`.

Expected impact:

- Better vocals, instrumental, drums, bass, piano, guitar, and other.
- Direct comparison against Demucs on BabySlakh and current local jobs.

### Pack 2: Vocal specialist and cleanup

This pack targets LALAL-style vocal tools.

- `vocals_mel_band_roformer.ckpt`.
- `melband_roformer_big_beta4.ckpt`.
- `Kim_Vocal_2.onnx`.
- `Mel-RoFormer Karaoke / Duet`.
- `dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt`.
- `dereverb-echo_mel_band_roformer_sdr_13.4843_v2.ckpt`.
- `UVR-DeNoise.pth`.

Expected impact:

- Better vocal/instrumental candidates.
- Dry vocal, reverb residual, echo, and noise cleanup candidates.

### Pack 3: Drum sub-stems

This pack replaces EQ-derived drum sub-stems.

- `MDX23C-DrumSep-aufr33-jarredou.ckpt`.
- `DrumSep MelBand RoFormer v2` when local source or MVSEP route is confirmed.
- `DrumSep SCNet XL 5-stem`.
- `DrumSep SCNet XL 6-stem`.

Expected impact:

- Real kick, snare, toms, hi-hat, ride, crash, and cymbal candidates.
- EQ-derived drum stems move to experimental fallback only.

### Pack 4: Remote/comparator specialists

This pack fills categories where local model source is not confirmed yet.

- `MVSep Strings BSRoformer (2025.09)`.
- `MVSep Wind BS-RoFormer`.
- `MVSep Synth BS-RoFormer`.
- `MVSep Karaoke BS-RoFormer Team`.
- `MVSep music/sfx/speech ensemble`.
- LALAL.AI, Logic, and SpectraLayers comparator outputs for the same test
  tracks.

Expected impact:

- Benchmark target for strings, wind, synth, and lead/back vocals.
- Clear gap analysis before we spend time hunting or training local weights.

### Pack 5: Validated local fallbacks

This pack contains local fallback models that are already in the validated
worker path.

- `kuielab_a_bass.onnx`.
- `17_HP-Wind_Inst-UVR.pth`.

Expected impact:

- Dedicated bass and wind-like fallback candidates for benchmark comparison.

### Pack 6: Quarantined replaced models

This pack keeps failed models visible without letting them re-enter runtime by
accident.

- `UVR-De-Echo-Normal.pth`.

Expected impact:

- No runtime impact. This model stays excluded unless a future
  `audio-separator` release validates the exact file.

### Pack 7: External research candidates

This pack tracks local-runner candidates found outside `audio-separator`. These
are not approved default runtime models.

- `MVSEP-CDX23-Cinematic-Sound-Demixing`: technical no-spend preflight passed
  on July 12, 2026, but GPU spend is blocked until license status is verified.
- `cocktail-fork-separation`: deployed as the standalone
  `stemsplitter-cocktail-fork-gpu` Modal worker and smoke-passed on July 11,
  2026. The first no-reference sanity benchmark passed with no warnings:
  `benchmarks/external_stems/cocktail_fork_booty2_20s_sanity_001.json`.
  The first two-song corpus sanity run also passed with no warnings:
  `benchmarks/external_stems/cocktail_fork_local_small_20s_001/aggregate.json`.
  The BabySlakh music-only negative control inside that run scored `music` at
  `31.23 dB` SDR and kept `speech_dialog` and `sfx` leakage below `-44 dB`
  versus the input. The MVSep DnR v3 comparator benchmark is recorded at
  `benchmarks/external_stems/cocktail_fork_vs_mvsep_dnr_v3_booty2_20s_001.json`.
  It scored Cocktail Fork at `0.9698` correlation and `11.8411 dB`
  SDR-to-comparator for `music`, `0.8362` correlation and `5.1649 dB` for
  `speech_dialog`, and only `0.2026` correlation and `-2.5874 dB` for `sfx`.
  Do not treat Cocktail Fork as a production SFX specialist.
- `BandIt v2`: no-spend preflight on July 12, 2026 confirmed the right
  speech/music/SFX task, Apache-2.0 code, output naming, and CC-BY-SA-4.0
  Zenodo weights. `checkpoint-multi.ckpt` is downloaded, MD5-verified, and
  loadable on CPU. The runner help/config gate passes after local
  compatibility patches. One isolated short Modal T4 smoke produced
  `speech_dialog`, `music`, and `sfx` WAVs. The MVSep DnR v3 comparator
  benchmark scored `music` at `0.972` correlation and `12.5659 dB` SDR,
  `speech_dialog` at `0.9661` correlation and `7.2888 dB` SDR, and `sfx` at
  `0.4518` correlation and `-4.6504 dB` SDR. Treat BandIt as useful evidence
  for speech/music separation, not as production SFX.
- `TUSS medium`: no-spend preflight on July 12, 2026 confirmed a direct
  CASS-style prompt set: `speech`, `sfxbg`, and `musicbg`. The medium
  checkpoint is downloaded, SHA-256 verified, and loads locally with zero
  missing or unexpected parameters. One isolated short Modal T4 smoke produced
  `speech_dialog`, `music`, and `sfx` WAVs. The MVSep DnR v3 comparator
  benchmark scored `music` at `0.9579` correlation and `10.6334 dB` SDR,
  `speech_dialog` at `0.8799` correlation and `2.2455 dB` SDR, and `sfx` at
  `0.5867` correlation and `-8.8516 dB` SDR with a `+10.634 dB` loudness
  mismatch. Treat TUSS as useful evidence, not as production SFX. The code is
  AGPL-3.0-or-later, so keep it as an isolated external runner unless AGPL
  obligations are accepted.
- `Loom of Time BSRoFormer`: no-spend preflight on July 12, 2026 confirmed MIT
  model weights and relevant plucked-string and wind outputs.
  `models/separator/best.pt` is downloaded, SHA-256-verified, loadable on CPU,
  and the runner help gate passes after installing `bs_roformer`. The GitHub
  runner repo still has no detected license file.
- `SIREN-SEPARATE`: no-spend preflight on July 12, 2026 found a public
  Apache-2.0 Hugging Face model card, but files are gated behind access
  acceptance. Access was requested through Peruz and is awaiting author review.
  It is not counted as an available local model.

Expected impact:

- Possible future local coverage for SFX, speech/music/effects, strings, and
  wind.
- Cocktail Fork now has isolated runtime impact only through its own worker;
  it still has no impact on `quality_gpu_experimental`, and it still needs
  a better SFX model or ground-truth-backed evidence before a production SFX
  quality claim.

### Pack 8: Local candidate queue

This pack contains `audio-separator` candidates found in the local catalog.
They passed isolated Modal smoke tests on July 11, 2026, but are not approved
runtime models yet.

- `UVR_MDXNET_KARA_2.onnx`.
- `mel_band_roformer_karaoke_gabox.ckpt`.
- `mel_band_roformer_karaoke_becruily.ckpt`.
- `mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt`.
- `UVR-MDX-NET_Crowd_HQ_1.onnx`.

Expected impact:

- Better evidence for lead/back vocal, karaoke, and crowd-cleanup quality.
- No runtime impact until benchmark comparisons and listening review pass.

## What is explicitly not approved yet

These categories are selected as targets but not approved as local
commercial-grade models.

- `MLSLABS WCJ`: use as comparator if available; local source is not confirmed.
- `Logic Pro 11.2`: use as commercial comparator, not part of our model stack.
- LALAL.AI outputs: use as commercial comparator, not training data.
- Any unknown-license checkpoint: research-only until audit completes.
- EQ-derived sub-stems: experimental fallback only, never pro output.

## Next implementation action

Use the registry as the source of truth for model planning and drift checks.

1. Run `python3 scripts/validate_gpu_registry_alignment.py` after every model
   registry or worker profile change.
2. Resolve CDX23 license status or find a stronger DnR-style SFX model before
   any more production SFX GPU spend.
3. Resolve Loom code-license status or replace the runner before promoting it
   beyond research.
4. Wait for SIREN access approval or replace it with an ungated query separator.
5. Run one full API/UI job with `quality_gpu_experimental` only after the
   source/runner blockers above are either solved or explicitly deferred.
6. Use the eight remote-only models as benchmark targets while scoring the five
   smoke-passed local candidates and validating four blocked external local
   candidates.
7. Promote future local candidates only after smoke, scoring, and listening
   review.

## Sources

- OpenMIRLab BS-RoFormer-Infer:
  https://github.com/openmirlab/bs-roformer-infer
- OpenMIRLab MelBand-RoFormer-Infer:
  https://github.com/openmirlab/melband-roformer-infer
- BS-RoFormer SW files:
  https://huggingface.co/jarredou/BS-ROFO-SW-Fixed/tree/main
- MVSep BS-RoFormer SW:
  https://mvsep.com/algorithms/77
- MVSep Karaoke:
  https://mvsep.com/algorithms/76
- SIREN-SEPARATE:
  https://huggingface.co/hilarl/siren-separate
- UVR resource model list:
  https://github.com/Politrees/UVR_resources/blob/main/UVR_resources/model_list_filenames.json
- MVSep DrumSep:
  https://mvsep.com/algorithms/29
- MVSep Strings leaderboard:
  https://mvsep.com/quality_checker/leaderboard/strings/?sort=strings
- MVSep Wind:
  https://mvsep.com/algorithms/61
- MVSep Synth leaderboard:
  https://mvsep.com/quality_checker/synth_leaderboard
- MVSEP CDX23 Cinematic Sound Demixing:
  https://github.com/ZFTurbo/MVSEP-CDX23-Cinematic-Sound-Demixing
- Cocktail Fork MRX:
  https://github.com/merlresearch/cocktail-fork-separation
- BandIt v2:
  https://github.com/kwatcharasupat/bandit-v2
- Loom of Time BSRoFormer checkpoint:
  https://huggingface.co/Haoyu123123/loom-of-time-models

# Remaining specialist model gaps

This file tracks model capabilities that are not fully solved by the validated
15-model local GPU worker. The local runtime is complete for the current
product path, but these gaps remain for commercial-grade comparison and future
local replacement work.

## Summary

The July 11, 2026 local catalog audit used the installed `audio-separator`
runner. It found local candidates for DrumSep, wind fallback, karaoke,
backing-vocal extraction, and crowd cleanup. It found no local
`audio-separator` candidates for strings, synth, or SFX separation, so those
remain external-runner or remote-comparator work.

- Local GPU runtime: 15 validated models.
- Remote/comparator models: 8 planned entries.
- Local smoke-passed candidate queue: 5 planned entries.
- External runner sanity-passed candidates: 1 planned entry.
- Downloaded external local candidates: 2 planned entries.
- Blocked external local candidates: 2 planned entries.
- Quarantined model: 1 replaced UVR DeEcho entry.

## Gap matrix

Use this matrix to decide what to search, port, or train next.

| Capability | Current local status | Remaining gap | Next action |
| --- | --- | --- | --- |
| Drum sub-stems | `MDX23C-DrumSep-aufr33-jarredou.ckpt` is validated locally. | MVSep DrumSep MelBand and SCNet XL variants remain remote benchmark targets. | Compare local MDX23C against remote outputs before adding another drum runner. |
| Strings | No local `audio-separator` string model was found. Loom now has a downloaded, SHA-256-verified MIT checkpoint and a passing runner help gate for plucked-string and wind-like stems. | `mvsep_strings_bsroformer_remote` remains the strongest benchmark target. SIREN access is requested but not approved. Loom is domain-specific and not a general strings solution yet. | Do not claim production strings yet. First resolve Loom runner code-license status or replace the runner, then run a short local smoke and benchmark. |
| Wind and brass | `17_HP-Wind_Inst-UVR.pth` is validated as a weak local fallback. Loom can emit `wind` and now passes no-GPU runner load, but it is trained for Chinese folk music. | `mvsep_wind_bsroformer_remote` remains the stronger benchmark target; Loom may become a research comparator only after smoke and benchmark checks. | Benchmark UVR wind, Loom wind, and MVSep wind only after the Loom license path is clean. |
| Synth and keys | No local `audio-separator` synth model was found. | `mvsep_synth_bsroformer_remote` remains remote-only. SIREN is the only found local query candidate. Access was requested through Peruz on July 12, 2026, and is awaiting author review. | Wait for SIREN approval or replace it with an ungated public query separator. Do not claim local synth separation yet. |
| SFX and speech | No local `audio-separator` SFX model was found. Cocktail Fork MRX, BandIt v2, and TUSS medium all run, but all fail the production SFX bar. TUSS passed smoke and scored well enough for music evidence, but its `sfx` result is not usable as a production stem. | The local SFX gap remains open. CDX23 remains the strongest exact-fit local candidate but is blocked by license status. TUSS is AGPL-3.0-or-later and must remain isolated unless AGPL obligations are accepted. | Stop spending on TUSS, BandIt, or Cocktail Fork for production SFX unless a new prompt, checkpoint, or ensemble hypothesis is defined. Resolve CDX23 license status or find a stronger DnR-style SFX model. |
| Karaoke and backing vocals | `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt` and `UVR-BVE-4B_SN-44100-1.pth` are validated locally as candidate evidence. They are not part of the current `quality_8_stems` contract. | Gabox, becruily, MDX karaoke, and MVSep Karaoke still need comparison. The residual lead stem still needs listening and comparator review. | Compare the BVE path and remaining smoke-passed candidates against MVSep Karaoke before claiming lead/back parity. |

## External candidates

These candidates are now tracked in the registry. Cocktail Fork has moved from
blocked to isolated sanity-passed status; the others remain blocked until their
runner contract, license status, and quality score are verified.

| Candidate | Covers | Why it matters | Status |
| --- | --- | --- | --- |
| [`MVSEP-CDX23-Cinematic-Sound-Demixing`](https://github.com/ZFTurbo/MVSEP-CDX23-Cinematic-Sound-Demixing) | dialog, SFX, music | Gives the most direct DnR/CDX-style path for local SFX separation. It has exact target stems, a simple inference entry point, released model weights, and published DnR metrics. | Technical preflight passed; commercial/license gate blocked |
| [`cocktail-fork-separation`](https://github.com/merlresearch/cocktail-fork-separation) | speech, music, SFX | Includes pre-trained soundtrack separation models. | Isolated Modal runner passed sanity checks; MVSep DnR v3 comparator passed music strongly, passed speech moderately, and failed SFX |
| [`BandIt v2`](https://github.com/kwatcharasupat/bandit-v2) | speech, music, effects | Matches the same DnR v3-style target, has an Apache-2.0 repository license, and is exposed by MVSep for speech/music/effects. | Downloaded and MD5-verified; isolated smoke passed; MVSep comparator benchmark is good for `music` and `speech_dialog` but rejects production `sfx` |
| [`Task-Aware Unified Source Separation`](https://github.com/merlresearch/unified-source-separation) | speech, SFX mix, music mix | Gives a prompt-conditioned CASS-capable model with direct `speech`, `sfxbg`, and `musicbg` prompts. | Medium checkpoint downloaded and SHA-256 verified; Modal smoke passed; MVSep comparator benchmark rejects production `sfx`; AGPL external-runner obligations |
| [`Loom of Time BSRoFormer`](https://huggingface.co/Haoyu123123/loom-of-time-models) | vocal, erhu, plucked strings, wind, percussion | Gives a real BSRoFormer checkpoint with strings and wind outputs, but it is domain-specific. | Downloaded and SHA-256-verified; runner help passes; blocked by undetected code repo license and quality unknowns |
| [`SIREN-SEPARATE`](https://huggingface.co/hilarl/siren-separate) | query-based guitar, piano, synth, strings | Claims granular extraction from the `other` stem. | Access requested through Peruz and awaiting author review; not counted as downloaded |

## No-spend gate

Use this gate before any Modal GPU run, paid API call, or long external queue.
The goal is to reject weak candidates before they cost time or credits.

A candidate must pass every gate below before a paid or GPU run.

1. Confirm exact stem coverage for the failed capability. For the current SFX
   gap, that means `speech` or `dialog`, `music`, and `sfx` or `effects`.
2. Confirm public weights or a documented model download path.
3. Confirm an inference command or runner entry point without modifying model
   internals.
4. Confirm license status before adding the model to any commercial-candidate
   profile.
5. Confirm expected hardware and dependency risk from the repository before
   deployment.
6. Run a local no-GPU dry-run first, such as `--help`, import checks, config
   load, and output-name validation.
7. Run one short local or free-tier smoke test before any paid GPU batch.
8. Stop immediately if the model fails to produce the exact expected stem names
   or if `sfx` is clearly weak against the MVSep comparator.

The current SFX priority order is:

1. `MVSEP-CDX23-Cinematic-Sound-Demixing`: first target because it has the
   strongest fit to the exact SFX failure mode and published DnR metrics. The
   technical preflight passed, but the license gate blocks GPU spend.
2. `Task-Aware Unified Source Separation`: useful as experimental evidence for
   speech/music/SFX, but not enough for production `sfx`. Its MVSep comparator
   benchmark scored `sfx` at `0.5867` correlation and `-8.8516 dB` SDR with a
   `+10.634 dB` loudness mismatch.
3. `BandIt v2`: useful as an experimental speech/music/effects runner, but not
   enough for production `sfx`. The MVSep comparator benchmark improved over
   Cocktail Fork on correlation, but the `sfx` SDR and loudness mismatch fail
   the production bar.
4. Any other DnR-style model: only after it passes the same gate.

## Local candidate queue

These candidates are visible to `audio-separator` and passed isolated Modal
smoke tests on July 11, 2026. They are still not runtime models because they
need benchmark comparison and listening review.

| Candidate | Covers | Status |
| --- | --- | --- |
| `UVR_MDXNET_KARA_2.onnx` | karaoke vocals/instrumental | Smoke passed; needs benchmark and listening review |
| `mel_band_roformer_karaoke_gabox.ckpt` | karaoke vocals/instrumental | Smoke passed; needs benchmark and listening review |
| `mel_band_roformer_karaoke_becruily.ckpt` | karaoke vocals/instrumental | Smoke passed; needs benchmark and listening review |
| `mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt` | crowd/other cleanup | Smoke passed; needs benchmark and listening review |
| `UVR-MDX-NET_Crowd_HQ_1.onnx` | no-crowd/crowd cleanup | Smoke passed; needs benchmark and listening review |

## Do not do

These constraints prevent the model stack from drifting into false capability
claims.

- Do not claim general local strings, synth, or SFX specialist separation yet.
- Do not put remote-only models into `quality_gpu_experimental`.
- Do not put blocked or isolated external candidates into
  `quality_gpu_experimental`.
- Do not re-enable `UVR-De-Echo-Normal.pth` unless `audio-separator` validates
  the exact model file in a future release.
- Do not promote any new model without a targeted smoke test, output-name
  verification, and benchmark comparison.

## Next steps

Run the next search in this order.

1. Resolve CDX23 license status or find a stronger DnR-style SFX model before
   spending more GPU time on production SFX.
2. Resolve Loom code-license status or replace the runner implementation before
   treating it as a local strings or wind candidate.
3. Wait for SIREN access approval or replace it before treating it as a synth,
   strings, piano, or guitar model.
4. Benchmark the five smoke-passed local candidates against the validated
   runtime outputs and MVSep comparators.
5. Compare local karaoke candidates against MVSep Karaoke output before claiming
   lead/back parity.

# GPU worker contract

This document records the current GPU worker architecture so implementation
does not drift back into hidden assumptions or patch-only fixes.

## Diagnosis

The worker must run long model jobs reliably without depending on Flask local
CPU fallback or unsafe Modal background threads. The smoke test proved that
the old background-thread design could return `200 OK` before the model job
finished, after which Modal could shut down the runner.

## Guiding policies

- Use one Modal GPU worker service for local/cacheable model execution.
- Run each submitted Modal job to completion inside the Modal request or a real
  Modal function contract, not an unmanaged background thread.
- Write completed outputs to the Modal jobs volume as the source of truth.
- Import completed results from the Modal Volume first, with HTTP artifact
  download only as a fallback.
- Keep failed models out of `quality_gpu_experimental`.
- Keep failed or suspect models in an audit-only profile until they are fixed
  and revalidated.

## Runtime profiles

`quality_gpu_experimental` is the normal GPU profile. It only includes models
that passed the July 11, 2026 smoke test.

`quality_gpu_full_audit` is for debugging the full validated worker plan. It
must not be exposed as the normal user path.

Candidate profiles such as `candidate_karaoke_gabox` and
`candidate_mdxnet_crowd_hq_1` are isolated smoke-test profiles. They must not
be treated as product runtime profiles until benchmark comparison and listening
review pass.

`stemsplitter-cocktail-fork-gpu` is a separate Modal worker for the external
Cocktail Fork MRX runner. It is not part of `quality_gpu_experimental`; it
exists to test speech, music, and SFX separation without mixing upstream Torch
dependencies into the main `audio-separator` worker.

Run `python3 scripts/validate_gpu_registry_alignment.py` after model registry
or worker profile changes. This check fails if the registry and the deployed
worker plan drift apart.

## Validated GPU model plan

The validated plan currently contains 15 model entries:

- `bs_roformer_sw`
- `melband_kim_vocals`
- `bs_roformer_viperx_1296`
- `bs_roformer_viperx_1297`
- `melband_big_beta4`
- `mdx23c_instvoc_hq_2`
- `kim_vocal_2`
- `mdx23c_drumsep_jarredou_aufr33`
- `melband_dereverb_anvuew`
- `roformer_dereverb_echo_v2`
- `uvr_denoise`
- `mel_roformer_karaoke_duet`
- `uvr_bve_4b_sn_44100_1_candidate`
- `kuielab_a_bass`
- `uvr_wind_inst`

## Quarantined models

This model is excluded from `quality_gpu_experimental`:

- `uvr_deecho_normal`: `audio-separator` rejects the model MD5 as unsupported.
  `roformer_dereverb_echo_v2` replaces it after a passing smoke test.

## Artifact import contract

The worker writes artifacts to `stemsplitter-gpu-worker-jobs`. The local API
imports the completed job folder from that Modal Volume before attempting HTTP
artifact downloads. This avoids one-request-per-WAV transfers as the default
path.

The Cocktail Fork worker writes to `stemsplitter-cocktail-fork-jobs` and
publishes outputs under the `specialist_substems` artifact group as
`speech_dialog`, `music`, and `sfx`.

The first no-reference Cocktail Fork sanity benchmark is recorded at
`benchmarks/external_stems/cocktail_fork_booty2_20s_sanity_001.json`. It passed
with no warnings, but it is not a ground-truth quality benchmark.

The first two-song corpus sanity benchmark is recorded at
`benchmarks/external_stems/cocktail_fork_local_small_20s_001/aggregate.json`.
It completed two of two worker jobs and passed two of two no-reference sanity
checks. The BabySlakh music-only negative control in that run scored the
`music` stem at `31.23 dB` SDR and kept false `speech_dialog` and `sfx`
leakage below `-44 dB` versus the input.

The MVSep DnR v3 comparator benchmark is recorded at
`benchmarks/external_stems/cocktail_fork_vs_mvsep_dnr_v3_booty2_20s_001.json`.
It passed the no-reference sanity checks and showed strong `music` alignment
and moderate `speech_dialog` alignment, but `sfx` failed the comparator gate.
Do not promote Cocktail Fork as a production SFX specialist.

## Next steps

1. Keep `uvr_deecho_normal` out of all user-facing profiles unless a future
   `audio-separator` release validates that exact model file.
2. Promote future model candidates only after a targeted smoke test passes and
   output names are correct.
3. Benchmark the five smoke-passed local candidates before promoting any of them
   into `quality_gpu_experimental`.
4. Resolve CDX23, BandIt v2, or another DnR-style SFX runner before claiming
   production SFX separation. Current no-spend status: CDX23 is technically
   runnable but license-blocked; BandIt v2 has Apache-2.0 code, CC-BY-SA-4.0
   weights, the right target stems, a downloaded and MD5-verified checkpoint,
   and a passing runner help/config gate after compatibility patches. It still
   needs one isolated short Modal smoke before runtime promotion.
5. Run a full API job through the backend and UI path, not only the direct
   Modal worker path.
6. Use the remaining remote/comparator models for benchmark targets, not as
   default local runtime models.

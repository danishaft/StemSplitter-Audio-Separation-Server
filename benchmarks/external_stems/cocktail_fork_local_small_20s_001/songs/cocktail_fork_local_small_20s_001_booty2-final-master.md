# External stem benchmark cocktail_fork_local_small_20s_001_booty2-final-master

This report records evidence for a speech, music, and SFX external
runner. It is not a production quality claim unless ground-truth
reference scores are present.

- System: `cocktail_fork_mrx`
- Evidence level: `no_reference_sanity`
- Quality claim: `not_quality_benchmark_without_ground_truth`
- Sanity pass: `True`
- Missing stems: `none`
- Warnings: `none`

## Stem metrics

| Stem | Duration | RMS dB vs input | Peak | Active ratio | Clipped ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| `music` | 20.000 | -0.261 | 0.966279 | 0.9994 | 0.00000000 |
| `sfx` | 20.000 | -18.088 | 0.805023 | 0.1282 | 0.00000000 |
| `speech_dialog` | 20.000 | -34.479 | 0.131794 | 0.0305 | 0.00000000 |

## Reconstruction

- `stem_sum_sdr_to_input`: `25.3363`
- `residual_rms_db_vs_input`: `-24.918`
- `stem_sum_rms_db_vs_input`: `0.01`

## Pairwise correlations

- `music__sfx`: `0.1778`
- `music__speech_dialog`: `0.0725`
- `sfx__speech_dialog`: `0.0072`

## Reference scores

- No ground-truth reference directory was supplied.

## Comparator scores

- No comparator directory was supplied.

# External stem benchmark bandit_vs_mvsep_dnr_v3_booty2_20s_001

This report records evidence for a speech, music, and SFX external
runner. It is not a production quality claim unless ground-truth
reference scores are present.

- System: `bandit_v2`
- Evidence level: `comparator_similarity`
- Quality claim: `not_quality_benchmark_without_ground_truth`
- Sanity pass: `True`
- Missing stems: `none`
- Warnings: `none`

## Stem metrics

| Stem | Duration | RMS dB vs input | Peak | Active ratio | Clipped ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| `music` | 20.000 | -2.156 | 0.912354 | 0.9609 | 0.00000000 |
| `sfx` | 20.000 | -31.504 | 0.288635 | 0.2017 | 0.00000000 |
| `speech_dialog` | 20.000 | -4.703 | 0.967987 | 0.5897 | 0.00000000 |

## Reconstruction

- `stem_sum_sdr_to_input`: `33.1136`
- `residual_rms_db_vs_input`: `-32.596`
- `stem_sum_rms_db_vs_input`: `-0.025`

## Pairwise correlations

- `music__sfx`: `0.1147`
- `music__speech_dialog`: `0.0487`
- `sfx__speech_dialog`: `0.0377`

## Reference scores

- No ground-truth reference directory was supplied.

## Comparator scores

- `booty2-master-v1-20s/music`: correlation `0.972`, SDR-to-comparator `12.5659`
- `booty2-master-v1-20s/sfx`: correlation `0.4518`, SDR-to-comparator `-4.6504`
- `booty2-master-v1-20s/speech_dialog`: correlation `0.9661`, SDR-to-comparator `7.2888`

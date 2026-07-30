# External stem benchmark tuss_vs_mvsep_dnr_v3_booty2_20s_001

This report records evidence for a speech, music, and SFX external
runner. It is not a production quality claim unless ground-truth
reference scores are present.

- System: `tuss_medium`
- Evidence level: `comparator_similarity`
- Quality claim: `not_quality_benchmark_without_ground_truth`
- Sanity pass: `True`
- Missing stems: `none`
- Warnings: `none`

## Stem metrics

| Stem | Duration | RMS dB vs input | Peak | Active ratio | Clipped ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| `music` | 20.000 | -2.755 | 0.907928 | 0.9557 | 0.00000000 |
| `sfx` | 20.000 | -27.378 | 0.264801 | 0.8684 | 0.00000000 |
| `speech_dialog` | 20.000 | -3.625 | 0.938660 | 0.7230 | 0.00000000 |

## Reconstruction

- `stem_sum_sdr_to_input`: `17.1482`
- `residual_rms_db_vs_input`: `-16.346`
- `stem_sum_rms_db_vs_input`: `0.556`

## Pairwise correlations

- `music__sfx`: `0.3102`
- `music__speech_dialog`: `0.1537`
- `sfx__speech_dialog`: `0.126`

## Reference scores

- No ground-truth reference directory was supplied.

## Comparator scores

- `booty2-master-v1-20s/music`: correlation `0.9579`, SDR-to-comparator `10.6334`
- `booty2-master-v1-20s/sfx`: correlation `0.5867`, SDR-to-comparator `-8.8516`
- `booty2-master-v1-20s/speech_dialog`: correlation `0.8799`, SDR-to-comparator `2.2455`

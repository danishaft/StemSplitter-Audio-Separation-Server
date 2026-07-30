# External stem benchmark cocktail_fork_vs_mvsep_dnr_v3_booty2_20s_001

This report records evidence for a speech, music, and SFX external
runner. It is not a production quality claim unless ground-truth
reference scores are present.

- System: `cocktail_fork_mrx`
- Evidence level: `comparator_similarity`
- Quality claim: `not_quality_benchmark_without_ground_truth`
- Sanity pass: `True`
- Missing stems: `none`
- Warnings: `none`

## Stem metrics

| Stem | Duration | RMS dB vs input | Peak | Active ratio | Clipped ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| `music` | 20.000 | -1.436 | 0.963962 | 0.9747 | 0.00000000 |
| `sfx` | 20.000 | -36.786 | 0.080099 | 0.2902 | 0.00000000 |
| `speech_dialog` | 20.000 | -9.263 | 0.844103 | 0.4534 | 0.00000000 |

## Reconstruction

- `stem_sum_sdr_to_input`: `19.6199`
- `residual_rms_db_vs_input`: `-19.507`
- `stem_sum_rms_db_vs_input`: `-0.231`

## Pairwise correlations

- `music__sfx`: `0.1665`
- `music__speech_dialog`: `0.1848`
- `sfx__speech_dialog`: `0.0582`

## Reference scores

- No ground-truth reference directory was supplied.

## Comparator scores

- `booty2-master-v1-20s/music`: correlation `0.9698`, SDR-to-comparator `11.8411`
- `booty2-master-v1-20s/sfx`: correlation `0.2026`, SDR-to-comparator `-2.5874`
- `booty2-master-v1-20s/speech_dialog`: correlation `0.8362`, SDR-to-comparator `5.1649`

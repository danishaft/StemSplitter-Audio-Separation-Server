# External stem benchmark cocktail_fork_booty2_20s_sanity_001

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

- No comparator directory was supplied.

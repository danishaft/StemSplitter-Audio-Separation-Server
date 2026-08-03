# External stem benchmark cocktail_fork_local_small_20s_001_babyslakh-Track00011

This report records evidence for a speech, music, and SFX external
runner. It is not a production quality claim unless ground-truth
reference scores are present.

- System: `cocktail_fork_mrx`
- Evidence level: `ground_truth_reference`
- Quality claim: `ground_truth_scored`
- Sanity pass: `True`
- Missing stems: `none`
- Warnings: `none`

## Stem metrics

| Stem | Duration | RMS dB vs input | Peak | Active ratio | Clipped ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| `music` | 20.000 | 0.008 | 0.787122 | 0.8929 | 0.00000000 |
| `sfx` | 20.000 | -44.262 | 0.027941 | 0.0703 | 0.00000000 |
| `speech_dialog` | 20.000 | -49.848 | 0.043358 | 0.0096 | 0.00000000 |

## Reconstruction

- `stem_sum_sdr_to_input`: `31.4989`
- `residual_rms_db_vs_input`: `-31.499`
- `stem_sum_rms_db_vs_input`: `0.013`

## Pairwise correlations

- `music__sfx`: `0.0822`
- `music__speech_dialog`: `0.0204`
- `sfx__speech_dialog`: `0.0227`

## Reference scores

- `music`: SI-SDR `31.235`, SDR `31.2283`, correlation `0.9996`
- `sfx`: silence target, leakage `-44.262` dB vs input, pass `True`
- `speech_dialog`: silence target, leakage `-49.848` dB vs input, pass `True`

## Comparator scores

- No comparator directory was supplied.

# Producer listening scorecard

Use this scorecard to decide whether each stem is useful in a real production
session. The technical gate passed, but this song has no isolated ground-truth
stems, so the listening session is the perceptual quality gate.

> **Note:** The piano output is below the signal detection floor, and the guitar
> output is very low-level. Mark whether those instruments are actually present
> in the original before judging either output.

## Session details

Record the listening setup and overall result before completing the stem-level
review.

- Job ID: `089b8b88d1b543868b1fb32727d29e47`
- Source: `booty2-final-master.wav`
- Technical verdict: **Pass**
- Producer:
- Date:
- Headphones or monitors:
- Overall verdict: **Pass / Needs work / Fail**

## Scoring method

Score each category from 1 to 5. A score of 5 means release-ready, 4 means
usable with minor cleanup, 3 means usable only in limited situations, 2 means
major repair is required, and 1 means unusable.

If an instrument is absent from the original, don't penalize a silent stem.
Instead, mark **Expected?** as **No** and judge whether the output correctly
stays quiet without capturing unrelated instruments.

## Stem review

Listen to the original first, then solo each stem at matched monitor volume.
Check missing musical content before focusing on bleed or artifacts.

| Stem | Expected? | Isolation | Completeness | Artifacts | Tonal quality | Production use | Verdict |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Vocals | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |
| Instrumental | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |
| Drums | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |
| Bass | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |
| Guitar | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |
| Piano | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |
| Kick | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |
| Snare | Yes / No | /5 | /5 | /5 | /5 | /5 | Pass / Work / Fail |

## Producer notes

Record exact timestamps for every issue so we can reproduce and prioritize it.

- Missing content or wrong instrument assignment:
- Bleed between stems:
- Warble, phasing, metallic sound, or transient smearing:
- Vocal consonant, breath, and reverb problems:
- Kick and snare punch or timing problems:
- Stems you would use in a real session:
- Stems you would not use:
- Most important improvement:

## Acceptance decision

Pass the friend-test gate only when the producer can use the outputs for at
least one real task and no expected stem is misleadingly empty. Treat any
score of 1 or 2 as a blocker. Record scores of 3 as specific follow-up work.

The technical measurements are in `technical-report.json` beside this file.

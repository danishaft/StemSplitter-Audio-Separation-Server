# Competitive audio-workspace teardown

This teardown defines the category conventions StemSplitter must meet before it
tries to differentiate. It focuses on the working separation experience rather
than marketing screenshots or feature-count comparisons.

For captured public-page evidence and the current V3 visual ownership model,
read the [public platform UI case studies](./public-platform-ui-case-studies.md).
This document remains the authority for audio-workspace interaction grammar.

The primary references are
[Moises Web and Desktop](https://moises.ai/products/moises-web-app/),
[Fadr Stems](https://fadr.com/help/stems), and
[BandLab Splitter](https://help.bandlab.com/hc/en-us/articles/16560236938777-Using-BandLab-Splitter).
The review used current official product pages, help material, and interface
imagery available in August 2026.

## Executive finding

The established interaction paradigm is a **multitrack audio workstation**.
The waveform is the primary content object, the transport is the persistent
control layer, and each stem behaves like a channel rather than a downloadable
card.

The rejected StemSplitter design used a long conversion-page structure. It
made upload visually dominant, delayed the musical workspace, separated stems
into independent players, and omitted a synchronized visual timeline. That
structure could not compete with products that let a musician understand the
whole song at a glance and manipulate relationships between stems.

## Shared category grammar

Moises, Fadr, and BandLab differ in brand expression, but they teach the same
mental model.

| Layer | Category convention | User value |
| --- | --- | --- |
| Project | Track title, artwork, duration, key, tempo, and export remain visible | Preserves musical context |
| Timeline | Stacked waveforms share one horizontal time scale and playhead | Makes alignment and song structure obvious |
| Channel | Every stem has a label, color, mute, solo, and level control | Supports relationship-based listening |
| Transport | Play, seek, loop, time, and speed occupy one stable control area | Prevents independent players from drifting |
| Status | Processing and partial availability appear in the workspace | Keeps completed work usable while other work continues |
| Export | Individual and grouped export remain close to the workspace | Makes the next professional action obvious |
| Responsive | Mobile preserves transport and channel identity while reducing density | Maintains the same learned model across devices |

This grammar is not a proprietary Moises composition. It is the familiar
language of digital audio workstations, practice tools, and stem mixers.

## Moises

Moises provides the strongest baseline for calm hierarchy and complete musical
context.

### What it does well

- Uses one synchronized timeline for every stem.
- Places channel controls beside each waveform instead of below unrelated
  result cards.
- Keeps title, BPM, key, time signature, transport, and export visible.
- Uses restrained dark surfaces so waveform color carries meaning.
- Supports mute, solo, volume, pan, speed, count-in, metronome, chords, and
  lyrics through progressive disclosure.
- Treats a separated song as a reusable project rather than a completed job
  receipt.
- Preserves the same project across web, desktop, and mobile.

### What StemSplitter can improve

- Quality status can sit directly on each channel without hiding uncertainty.
- Parent and specialist stems can show hierarchy more clearly.
- Original-versus-stem comparison can be more explicit.
- Export provenance and model qualification can remain available without
  entering a technical settings page.
- Dense controls can become easier to scan through stronger grouping and
  transient glass surfaces.

## Fadr

Fadr provides the strongest reference for direct manipulation and expressive
stem identity.

### What it does well

- Gives different stems vivid, persistent waveform colors.
- Represents editable audio as waveform clips rather than abstract rows.
- Supports drag alignment, edge trimming, repetition, scrolling, and zoom.
- Updates chord context during playback.
- Makes stems, MIDI, key, tempo, and remix continuation part of one workflow.
- Publishes completed outputs progressively rather than waiting for every
  secondary analysis result.
- Offers full-screen focus and contextual tooltips for denser controls.

### What StemSplitter can improve

- Reduce neon competition between controls and audio content.
- Separate evaluation status from creative controls more clearly.
- Use calmer typography and spacing for long critical-listening sessions.
- Preserve expressive stem colors while meeting contrast and color-vision
  requirements.

## BandLab Splitter

BandLab provides the strongest reference for approachable practice and
continuation into a larger creative system.

### What it does well

- Leads with the waveform and a small number of understandable controls.
- Exposes mute, solo, and channel volume without DAW knowledge.
- Keeps loop, speed, pitch, key, and tempo close to playback.
- Remembers recent sessions and preserves previous settings.
- Offers clear export to audio, MIDI, or the BandLab Studio.
- Uses the same Splitter concept on web and mobile.

### What StemSplitter can improve

- Give producers more detailed stem hierarchy and quality evidence.
- Support more stems without turning the control rail into a long slider list.
- Make partial and rejected specialist outputs understandable.
- Provide a self-hosted path without exposing infrastructure concepts in the
  musician workspace.

## Comparative matrix

The matrix distinguishes category requirements from opportunities.

| Capability | Moises | Fadr | BandLab | StemSplitter target |
| --- | --- | --- | --- | --- |
| Shared waveform timeline | Strong | Strong | Strong | Required |
| Global transport | Strong | Strong | Strong | Required |
| Per-stem mute and solo | Strong | Strong | Strong | Required |
| Per-stem volume | Strong | Strong | Strong | Required |
| Pan | Strong | Plugin | Limited | Progressive control |
| Loop and speed | Strong | Remix workflow | Strong | Required after first result |
| Key, BPM, and chords | Strong | Strong | Strong | Show when available |
| Direct clip editing | Limited | Strong | Studio handoff | Later create mode |
| Partial-result workflow | Moderate | Strong | Limited | Required |
| Quality qualification | Weak | Weak | Weak | Differentiator |
| Stem hierarchy | Moderate | Broad list | Simple list | Differentiator |
| Self-hosted mode | No | No | No | Differentiator |
| Restrained glass controls | Limited | Limited | Limited | Visual differentiator |

## Revised product composition

The first release uses three connected surfaces rather than one long page.

### Import room

The import room is compact and immersive. It contains upload and Audius input,
profile choice, honest output expectations, and one primary action. A selected
local file can display an original-mix waveform preview before submission.

### Processing workspace

Processing keeps the source waveform, project identity, and emerging channel
rows visible. Upload, queue, inference, packaging, cancellation, and recovery
appear as workspace states rather than a separate status card.

### Listening workspace

Results open into a synchronized mixer:

- compact project header;
- left channel rail with stem identity, mute, solo, level, and quality state;
- stacked waveform timeline with one playhead and time ruler;
- optional right inspector for output details and downloads;
- floating glass transport for play, seek, loop, original comparison, and
  master level;
- export action in a predictable top-right position.

## Spatial-glass policy

Glass is a functional layer, not the content background. Apple describes glass
as a control and navigation layer that floats above content and recommends
against using it throughout the content layer. StemSplitter follows that
principle on the web.

### Use glass for

- the compact top navigation;
- the persistent transport;
- floating zoom, loop, and comparison controls;
- menus, tooltips, popovers, and the mobile channel drawer;
- transient processing and recovery overlays;
- the import dock when it sits above rich artwork or media.

### Do not use glass for

- waveform lanes;
- long text surfaces;
- every stem channel;
- tables or quality evidence;
- disabled controls;
- multiple nested card layers.

### Material recipe

The regular material uses a translucent neutral fill, `20px` to `28px`
backdrop blur, slight saturation, a one-pixel light edge, an inner highlight,
and a broad low-opacity shadow. It must have an opaque fallback and a higher
contrast mode.

Clear material is reserved for icon controls over dark artwork or waveforms.
Text-heavy controls use a denser regular material. Background dimming adapts to
the luminance underneath the glass.

## Revised color architecture

The shell uses forest-black rather than flat black. Ivory and sage sections
reset attention, neutral studio surfaces recede, and stem colors carry the
musical identity.

| Role | Value | Purpose |
| --- | --- | --- |
| Canvas | `#07110D` | Deep spatial background |
| Workspace | `#0B1812` | Solid waveform content layer |
| Raised solid | `#11231A` | Channel rail and inspector |
| Paper | `#F2F3EA` | Primary editorial reset |
| Sage | `#DFE9DF` | Workflow explanation |
| Glass regular | `rgb(8 25 17 / 72%)` | Navigation and transport |
| Glass clear | `rgb(255 255 255 / 8%)` | Media-overlay controls |
| Primary text | `#F3F7F1` | High-emphasis content |
| Secondary text | `#B4C4B9` | Supporting content |
| Primary action | `#67E58B` | Main action and playhead |
| Focus | `#B9F6C8` | Keyboard focus |
| Danger | `#FF6B78` | Failure and destructive action |
| Warning | `#FFC857` | Evaluation and caution |
| Success | `#67E58B` | Completed state |

Stem colors use coral for vocals, amber for rhythm, cyan for bass, blue for
keys, mint for guitars, rose for synth, teal for strings, and a neutral silver
for the source mix. Color never replaces a label or channel position.

## Waveform data architecture

The frontend must not download every WAV file merely to draw the workspace.
The packaging stage produces a compact peak envelope for the source and every
published audio artifact.

The existing analysis artifact group can expose one versioned JSON document:

```json
{
  "schema_version": 1,
  "sample_rate": 44100,
  "duration_seconds": 212.4,
  "resolution": 2048,
  "channels": {
    "vocals": { "min": [], "max": [] },
    "drums": { "min": [], "max": [] }
  }
}
```

The browser draws waveforms from peak data, streams only the stem a person
plays, and uses one audio clock as the transport authority. A stem joins the
clock only when it is audible. This preserves synchronization without an eager
eleven-file download.

## Rejection criteria

A redesign fails even if it is attractive when any of these conditions remain:

- results are primarily independent cards;
- the page has multiple unrelated native audio players;
- waveforms are decorative or absent;
- transport moves between channels or scroll positions;
- stem colors do not stay consistent across waveform, controls, and export;
- glass reduces control contrast or appears in the waveform content layer;
- mobile becomes a generic list with no persistent transport;
- the workspace hides evaluation status to look more polished;
- the first viewport is mostly brand storytelling instead of the musical task.

## New review gate

The next Figma version must pass all of these gates before implementation:

- a musician can identify the active track, current time, audible stems, and
  export action in five seconds;
- synchronized waveform and channel behavior is clear without explanation;
- import, processing, partial result, completed, recovery, and unavailable-stem
  states share one workspace model;
- desktop and mobile preserve the same transport authority;
- glass usage follows the functional-layer policy;
- no critical action depends on color alone;
- the design is compared directly with current Moises, Fadr, and BandLab
  references at matching viewport sizes;
- the prior `93/100` score is not reused.

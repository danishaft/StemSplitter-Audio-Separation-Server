---
version: alpha
name: Emerald Studio Continuum
description: >-
  A musician-first audio workspace with cinematic entry media and a restrained
  professional studio environment.
colors:
  canvas: "#07110D"
  surface-deep: "#050B08"
  surface-input: "#0A1812"
  surface-selected: "#123021"
  surface-success: "#102A24"
  workspace: "#0B1812"
  raised: "#11231A"
  control: "#193126"
  control-hover: "#244535"
  surface-solid: "#12271C"
  paper: "#F2F3EA"
  paper-soft: "#DFE9DF"
  ink: "#102018"
  ink-muted: "#506157"
  ink-metadata: "#52705E"
  action: "#67E58B"
  action-hover: "#7BEA9A"
  action-pressed: "#55CF78"
  action-ink: "#06210F"
  focus: "#B9F6C8"
  brand-signal: "#8ED9A5"
  text: "#F3F7F1"
  muted: "#B4C4B9"
  quiet: "#778B7E"
  metadata: "#9BAEA1"
  success: "#7FC79E"
  warning: "#FFB84D"
  warning-surface: "#2B2314"
  on-warning: "#FFE0A3"
  danger: "#FF6F91"
  danger-surface: "#301822"
  on-danger: "#FFB7C8"
  line: "rgba(255, 255, 255, 0.10)"
typography:
  display-xl:
    fontFamily: Sora
    fontSize: 86px
    fontWeight: 600
    lineHeight: 1.01
    letterSpacing: -0.055em
  display-lg:
    fontFamily: Sora
    fontSize: 72px
    fontWeight: 500
    lineHeight: 1.02
    letterSpacing: -0.055em
  display-md:
    fontFamily: Sora
    fontSize: 48px
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: -0.045em
  heading-lg:
    fontFamily: Sora
    fontSize: 38px
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: -0.035em
  heading-md:
    fontFamily: Sora
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.18
    letterSpacing: -0.025em
  body-lg:
    fontFamily: Instrument Sans
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0em
  body-md:
    fontFamily: Instrument Sans
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0em
  body-sm:
    fontFamily: Instrument Sans
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0em
  label-md:
    fontFamily: Instrument Sans
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0em
  metadata:
    fontFamily: IBM Plex Mono
    fontSize: 10px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0.04em
rounded:
  none: 0px
  control: 8px
  button: 10px
  field: 12px
  panel: 16px
  stage: 28px
  editorial: 32px
  full: 9999px
spacing:
  micro: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 72px
  4xl: 112px
  desktop-gutter: 40px
  mobile-gutter: 12px
  content-max: 1440px
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.action-ink}"
    rounded: "{rounded.button}"
    height: 46px
    padding: 20px
    typography: "{typography.label-md}"
  button-primary-hover:
    backgroundColor: "{colors.action-hover}"
  button-primary-active:
    backgroundColor: "{colors.action-pressed}"
  button-secondary:
    backgroundColor: "{colors.control}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    height: 44px
    padding: 18px
    typography: "{typography.label-md}"
  input:
    backgroundColor: "{colors.workspace}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    height: 52px
    padding: 15px
    typography: "{typography.body-md}"
  product-panel:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: 24px
  studio-stage:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.text}"
    rounded: "{rounded.stage}"
    padding: 12px
---

# StemSplitter design system

## Overview

StemSplitter feels like a professional music tool before it feels like a
technology product. The public experience combines LANDR's restrained,
media-led arrival, Moises's continuous product environment, and AudioPod's
playable product evidence. It uses human studio imagery to establish context,
then lets the real splitter become the visual proof.

The product must feel calm, exact, and musically literate. It must not resemble
a generic startup template, an AI dashboard, a crypto product, or a collection
of interchangeable cards. Every visual effect needs a functional role.

## Colors

Forest neutrals carry the product. Warm paper appears only when the narrative
needs a deliberate pause. Mineral green is scarce enough to retain meaning.

- Use `action` only for the primary action and immediate interactive feedback.
- Use `success` for completed states. Never use `action` as a success token.
- Use `metadata` or `quiet` for eyebrows, technical labels, and provenance.
- Use `paper` only for the inset editorial stage.
- Derive translucent borders and glows from an existing token. Keep decorative
  alpha at or below 22 percent.
- Never use pure black, pure white, blue-purple gradients, or unrelated accent
  colors.
- Keep body text at WCAG AA contrast. Metadata can be quieter, but it must
  remain readable at the specified size.

## Typography

Sora provides the editorial display voice. Instrument Sans carries interface
and body copy. IBM Plex Mono identifies metadata, provenance, status labels,
and measurements. All three families are self-hosted through Fontsource.

- Desktop display text uses the token values above and fluidly scales down.
- At 800px and below, hero display text uses `44px` to `58px`; editorial display
  text uses `38px` to `52px`; body text remains at least `16px`.
- Display headings use optical line breaks created by width constraints. Never
  insert HTML line breaks to force a desktop composition onto mobile.
- Use no more than three text sizes inside one functional panel.
- Keep paragraphs between 45 and 68 characters per line.
- Use mono text sparingly. Never use it as decorative filler.

## Layout

Desktop uses a centered `1440px` maximum canvas with `40px` outer gutters. The
hero can span the viewport. Product content remains inside the canvas. Mobile
uses `12px` outer gutters and recomposes content instead of hiding it.

- Use a 12-column desktop grid and a 4-column mobile grid.
- Align the studio introduction with the studio's functional content edge.
- Let the hero flow directly into the studio with a slight spatial overlap. Do
  not insert a centered slogan or narrative band between them.
- Use spacing from the token scale. Optical adjustments can use `4px`, but they
  must solve a visible alignment problem.
- Section spacing must express hierarchy. Do not assign identical vertical
  padding to unrelated sections.
- Keep one primary action in each viewport state.
- Touch targets must be at least `44px` square.

## Elevation & Depth

Depth uses three levels. Adding more shadows does not create more hierarchy.

1. The page canvas has no shadow.
2. A major studio or media stage uses one ambient shadow:
   `0 32px 96px rgba(0, 0, 0, 0.38)`.
3. Controls and internal panels use tonal contrast, a one-pixel border, and an
   optional inset highlight. They do not receive independent ambient shadows.

The ivory editorial stage uses a light-surface shadow:
`0 24px 64px rgba(23, 48, 33, 0.14)`. Glass is permitted only above moving or
photographic media where blur is visible. Never apply backdrop blur to an
opaque dropzone or a solid product panel.

## Shapes

Shape communicates containment level. Radius cannot be chosen independently
for each component.

- Use `28px` for the main studio stage.
- Use `16px` for internal product panels and the dropzone.
- Use `8px` for segmented controls, `10px` for standard buttons, and `12px`
  for fields.
- Use the full radius only for compact utility pills and status chips.
- Use `32px 12px 32px 12px` for the editorial stage to create authored
  asymmetry.
- Use `12px 32px 12px 32px` for the closing media stage. It must not mirror the
  editorial stage.

## Components

Components inherit the token values in the front matter and the state rules
below. A component cannot introduce a new green, radius, or shadow without an
explicit update to this file.

### Buttons

Primary buttons transition background, transform, and shadow over `160ms`.
Hover lifts by `1px`; active returns to the baseline and uses `action-pressed`.
Focus uses the global `focus` outline. Disabled buttons retain their shape and
use 50 percent opacity. Loading buttons keep their width and replace only the
leading or trailing icon.

### Navigation

The hero navigation remains transparent over media. It has no glass capsule or
floating card. Desktop uses one quiet utility CTA. Mobile keeps the CTA at
`44px` high and removes the center links.

### Hero

The hero fills the first viewport. Copy is centered because the media is the
spatial anchor. The title has one natural desktop wrap and no forced mobile
breaks. The gradient protects text while preserving skin tones, console lights,
and image depth. The primary action scrolls to the functional input, not an
introductory heading.

### Studio

The studio introduction uses an asymmetric text composition before the
functional stage. The outer stage owns the ambient shadow. Internal panels use
border and tone only. Source validation appears inside the source panel;
server availability appears at the studio level; job failures appear in job
progress. After you select a local file, the source panel exposes a real audio
transport, seek control, and live source signal. It must not decode the entire
file only to draw a decorative waveform.

The public experience must also expose one real, provenance-labeled sample
session that remains playable when the production API is unavailable. A static
product mockup or decorative waveform cannot satisfy this requirement.

### Editorial stage

The editorial stage uses a warm paper surface, asymmetric corners, and a quiet
radial tint. An inset session anatomy diagram explains one shared timeline and
visible release states. The diagram is explanatory, not an interactive audio
preview. Its detail rows use rules rather than cards, and it cannot introduce
another primary action.

### Closing media

The closing media uses a distinct crop from the hero, asymmetric corners, and
a single action. Copy sits against the darkest image region. The image cannot
be mirrored, blurred, or covered by a generic glass panel.

### Motion

Use one hero entrance, job progress transitions, progressive stem publication,
and playhead movement. Hover motion is limited to `1px`. Respect reduced motion
by removing transforms, video autoplay, and nonessential transitions.

## Do's and Don'ts

- Do let the working product provide evidence.
- Do use asymmetry where it clarifies the page's editorial rhythm.
- Do verify every section at `1440px`, `1024px`, `390px`, and `320px` widths.
- Do give errors an owner: source, system, job, or artifact.
- Do preserve visible focus, keyboard operation, and reduced-motion behavior.
- Don't repeat centered headline compositions across consecutive sections.
- Don't use equal radii, shadows, or padding across unrelated containment
  levels.
- Don't use bright green for decoration, metadata, and success simultaneously.
- Don't add numbered marketing steps, proof-card grids, fake waveforms, or
  unsupported metrics.
- Don't alternate full-width light and dark sections as a template rhythm.
- Don't place decorative effects where no physical or interaction model
  justifies them.

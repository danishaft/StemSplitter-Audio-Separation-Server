# StemSplitter product blueprint

This document is the product authority for StemSplitter. It defines who the
product serves, what experience it must provide, which capabilities exist, and
which ideas are not yet safe to promise. The roadmap controls implementation;
this document controls product meaning and customer-facing claims.

## Product promise

StemSplitter turns a finished song into an honest, editable musical workspace.
A musician should be able to bring in one track, understand what the system can
separate, listen critically, shape the result, and continue working without
moving through disconnected tools.

The product is not merely a download utility. Its long-term value is the path
from a mixed recording to practice, production, remixing, analysis, and export.

## Product position

StemSplitter is for musicians who need useful musical parts rather than an
impressive stem count. It competes on four connected strengths:

- one import creates a persistent project rather than a disposable conversion;
- the workspace supports listening, mixing, comparison, and export together;
- quality and model limitations remain visible instead of being hidden;
- the same product can run as a hosted service or a self-hosted platform.

The product should be described as an evaluation system until its public stem
families pass the release gates in the research roadmap. Marketing must never
turn a configured model into a quality claim.

## Product principles

These principles govern feature, content, and interaction decisions.

1. **Music comes before AI.** Show the track, waveform, stems, and controls
   before model names or technical language.
2. **One upload should open a workflow.** Do not make users repeatedly process
   the same song to explore another stem or tool.
3. **Listen before trust.** Every result needs immediate auditioning, original
   comparison, and a clear quality state.
4. **Never fabricate certainty.** Separate model support, processing success,
   instrument presence, and release qualification.
5. **Keep creative momentum.** A completed split should lead naturally to
   practice, remixing, export, or a saved project.
6. **Give people control.** Make cancellation, retries, deletion, retention,
   privacy, and export behavior understandable.
7. **Progressive depth beats clutter.** Make the first split simple while
   keeping professional controls close at hand.
8. **Cloud and self-hosted are one product.** Share contracts and core
   workflows while allowing deployment-specific account and storage controls.

## Primary users

The first release should serve a focused set of musicians without assuming
that every user has the same goal.

| User | Primary job | Successful outcome |
| --- | --- | --- |
| Producer or remixer | Recover parts for arrangement and sampling | Clean, aligned WAV stems in a DAW |
| Artist or songwriter | Study a reference and build around it | Useful parts, tempo, key, and guides |
| Instrumentalist | Learn or rehearse a difficult part | Loop, slow down, mute, and isolate |
| Vocalist | Rehearse against an instrumental or inspect harmony | Vocal and backing context with pitch-safe playback |
| DJ | Prepare edits, mashups, or live material | Fast stem auditioning and reliable exports |
| Engineer or educator | Analyze arrangements and explain parts | Repeatable project, labels, and shareable evidence |
| Developer or operator | Integrate or host separation | Stable API, model provenance, and operational controls |

The initial product should optimize for producers, artists, instrumentalists,
and DJs. Developer and self-hosted workflows are important, but they must not
make the musician-facing interface feel like an infrastructure console.

## Core journey

The complete journey is a loop rather than a one-time conversion funnel.

1. **Discover.** Understand the musical result, supported inputs, honest stem
   status, and expected workflow before signing in.
2. **Import.** Upload a local file or choose an eligible catalogue source.
3. **Configure.** Select a separation mode, expected outputs, and export needs
   without requiring knowledge of model internals.
4. **Process.** See upload, queue, inference, packaging, and recovery states.
5. **Inspect.** Compare the original and stems using synchronized playback.
6. **Shape.** Solo, mute, balance, loop, seek, and choose useful outputs.
7. **Continue.** Practice, remix, send to a DAW, download, or share.
8. **Return.** Reopen the project with its source, settings, quality state, and
   artifacts intact for the promised retention period.

## Product surfaces

Each surface has one primary responsibility. Combining all of them into one
long landing page would weaken both discovery and daily use.

### Public site

The public site explains the product through sound and musician outcomes. Its
primary pages are Home, Stem separation, Workflows, Quality, Research,
Developers, Self-host, and Pricing when billing is introduced.

The home page should include an interactive before-and-after example, a simple
feature overview, real workflow stories, transparent quality language, and one
clear action to start a project.

### Project library

The library is the returning user's home. It contains recent projects, active
jobs, saved presets, source and model provenance, expiration state, search,
filters, and explicit deletion controls.

### Separation workspace

The workspace combines source configuration, live job state, synchronized
waveforms, stem channels, transport controls, quality information, and export.
It is the center of the product and should receive more design attention than
the marketing site.

### Practice workspace

The practice workspace reuses the same project and audio engine. It adds loop
regions, speed, pitch, count-in, metronome, chords, lyrics, and setlists without
creating another copy of the song.

### Create workspace

The create workspace supports simple arrangements, stem regions, transitions,
and remix preparation. It should hand off to a DAW rather than trying to become
a complete DAW in the first product generation.

### Quality and research

The quality surface shows supported stems, benchmark coverage, known limits,
model releases, listening examples, and methodology. It should help users
choose the right tool and help researchers reproduce claims.

### Developer and self-hosted surfaces

These surfaces provide API contracts, keys, webhooks, usage, model packs,
deployment guidance, health, and version information. Administrative controls
must remain separate from musician project controls.

## Capability pillars

The full product is organized into eight pillars. This prevents an arbitrary
feature list from becoming the roadmap.

### Import

Users can bring audio into a project with clear rights, format, size, duration,
retention, and cost expectations.

- local upload;
- eligible Audius catalogue import;
- resumable direct upload;
- future licensed catalogue providers through one provider contract;
- future batch import for professional workflows.

### Separate

Users choose an outcome, not an unexplained checkpoint. The system then routes
to qualified models and records execution provenance.

- evaluation stem profile;
- faster preview profile;
- selectable quality or speed presets;
- presence-aware specialist separation;
- model comparison when it provides a measured benefit;
- safe retries, cancellation, and recovery.

### Listen and mix

Results become useful when users can hear relationships between the original
and every stem without synchronization errors.

- synchronized waveforms and transport;
- original-versus-result comparison;
- solo, mute, volume, pan, loop, and seek;
- stem groups and hierarchy;
- clipping, missing-stem, and quality notices;
- optional loudness-matched comparison.

### Practice

Practice tools turn a separation into a recurring musician workflow.

- speed change without unwanted pitch change;
- pitch and key adjustment;
- loop regions and count-in;
- metronome and tempo map;
- chords and lyrics;
- setlists and rehearsal notes.

### Create

Creation tools should remove handoff friction without recreating a full DAW.

- stem region selection and arrangement;
- export selected stems or a processed mix;
- MIDI and chord guides;
- remix and mashup preparation;
- DAW handoff and future plugin access.

### Organize and collaborate

Persistent projects are what make the product worth revisiting.

- project history, rename, search, tags, and filters;
- presets and reproducible settings;
- favorites, notes, and versions;
- expiring review links;
- later collaboration and comments.

### Export and integrate

Export must preserve timing, quality, provenance, and user choice.

- individual WAV files and archives;
- selected-stem bundles;
- tempo-locked WAV and MIDI guide artifacts where supported;
- format, sample-rate, and bit-depth controls;
- future DAW, plugin, API, and webhook integrations.

### Trust and control

Trust is a product capability, not a legal footer.

- honest feature and quality labels;
- source, model, settings, and release provenance;
- retention and deletion controls;
- private artifacts and tenant isolation;
- accessibility, incident communication, and status visibility;
- benchmark methodology and known limitations.

## Feature status language

Every product surface must use the same status vocabulary. No other status
wording should appear without a product decision.

| Status | Meaning | Public treatment |
| --- | --- | --- |
| Available | Released and supported for the stated environment | Normal feature presentation |
| Evaluation | Usable, but quality or release evidence is incomplete | Visible evaluation label and limitation |
| Experimental | Opt-in behavior with a higher chance of failure or change | Warning before use; never the default |
| Coming soon | Committed, designed, and scheduled work | May be previewed without an active control |
| Research | A problem under investigation with no release commitment | Keep on quality or research surfaces |
| Vision | A possible future direction | Keep out of customer-facing promises |

"Coming soon" is not a substitute for "we want this." A feature can use the
label only when its owner, dependency, acceptance criteria, and delivery phase
exist in the roadmap.

## Current product truth

This table maps the product to the repository as of 31 July 2026. It should be
updated whenever a capability changes release state.

| Capability | Status | Current truth |
| --- | --- | --- |
| Local file import | Available | Direct private upload is implemented |
| Audius search and import | Available | Eligible downloadable tracks can be selected |
| Job progress | Available | Queued through terminal states are represented |
| Cancellation | Available | API and current page expose cancellation |
| Retry, resume, and deletion | Available in API | Full library UI is not complete |
| Individual playback and download | Available | Results use independent audio controls |
| Stem archive | Available | Completed artifacts can include a bundle |
| Eleven requested stem outputs | Evaluation | Model support is not equivalent to release quality |
| Vocals, instrumental, drums, bass | Evaluation | Internal release qualification remains pending |
| Kick and snare | Evaluation | Audible bleed remains possible by source |
| Piano and acoustic guitar | Evaluation | Internal domain review remains pending |
| Electric guitar, synth, and strings | Experimental | Internal product evaluation is incomplete |
| Wind | Research | No qualified delivery model is assigned |
| Tempo-locked WAVs and MIDI guides | Experimental | Produced only by supporting profiles and runs |
| Authenticated project library | Coming soon | Backend boundaries exist; the complete UI does not |
| Synchronized mixer workspace | Coming soon | Current playback controls are independent |
| Practice suite | Vision | Product direction, not a scheduled release claim |
| Remix and arrangement workspace | Vision | Product direction, not a scheduled release claim |
| DAW plugin and native apps | Vision | No public delivery commitment exists |

## First complete release

The first complete musician-facing release is not defined by having every
vision feature. It is complete when one project can move safely from import to
useful export without terminal access or misleading quality claims.

The release must include:

- account entry, recovery, and a persistent project library;
- upload preflight and an honest submission summary;
- durable progress, reconnect, retry, cancellation, and deletion behavior;
- synchronized original and stem playback;
- solo, mute, volume, seek, loop, and A/B comparison;
- individual and selected-stem downloads with retention messaging;
- per-stem status, limitations, and feedback;
- responsive and keyboard-complete critical flows;
- automated first-project coverage across the deployed stack.

Practice, remixing, collaboration, plugins, and native apps can follow without
making the first release feel unfinished.

## Competitive synthesis

Competitors are references for solved interaction problems, not templates for
our identity. Their public products were reviewed in July 2026.

| Product | Strong lesson | Pattern to avoid |
| --- | --- | --- |
| [Moises](https://moises.ai/features/) | A polished musician suite, clear workflows, and reasons to return | Allowing breadth to hide which capability is central |
| [BandLab Splitter](https://help.bandlab.com/hc/en-us/articles/16560236938777-Using-BandLab-Splitter) | Waveform, stem levels, solo, mute, speed, loop, pitch, and Studio handoff in one flow | Locking the product identity to practice alone |
| [Fadr](https://fadr.com/help/stems) | Separation continues into MIDI, chords, remixing, DJ work, and plugins | Letting advanced options overwhelm the first split |
| [AudioPod](https://audiopod.ai/free-stem-splitter) | Clear acquisition pages and a broad feature taxonomy | Treating a conversion form as the finished workspace |
| [LALAL.AI](https://www.lalal.ai/stem-splitter/) | Broad stem selection, model choice, previews, formats, apps, and API | Fragmenting one song across repeated extraction actions |

The product direction is therefore **Moises-level coherence, BandLab-level
workspace usability, Fadr-level continuation, and LALAL.AI-level capability
clarity**, with more honest release evidence than any stem-count headline.

## Information architecture

Navigation should separate discovery, daily work, and technical administration.

The public navigation is Product, Workflows, Quality, Research, Developers,
Self-host, and Sign in. Pricing appears only when plans are real.

The application navigation is Library, New separation, Projects, Presets, and
Exports. Account, storage, accessibility, and deployment settings live under
Settings. Research and infrastructure diagnostics do not belong in the main
musician navigation.

Within a project, the persistent sections are Workspace, Practice, Create,
Files, and Details. Unreleased sections should appear only when they are truly
Coming soon; Vision items remain absent.

## Success measures

Metrics should describe useful musical outcomes and healthy operation rather
than reward uploads alone.

- first-project completion rate;
- time from import to first audible stem;
- time from completion to first useful export;
- percentage of completed projects reopened within 30 days;
- stem audition, solo, loop, and export usage;
- per-stem acceptance and issue-report rates;
- cancellation, retry, failure, and recovery rates;
- measured quality, latency, and cost by model release;
- accessibility completion and critical-flow error rates.

The north-star behavior is a musician returning to an existing project to
listen, practice, create, or export again.

## Product decision gate

A feature enters implementation only when the team can answer all of these
questions clearly.

- Which user and musical job does it serve?
- At which point in the core journey does it belong?
- Is it Available, Evaluation, Experimental, Coming soon, Research, or Vision?
- What evidence moves it to Available?
- What happens when its model, network, storage, or provider fails?
- How does it behave with keyboard, touch, narrow screens, and reduced motion?
- Which existing component or contract owns it?
- Which metric shows that it improved the product?

This gate keeps the product ambitious without allowing the interface or roadmap
to become a collection of disconnected AI features.

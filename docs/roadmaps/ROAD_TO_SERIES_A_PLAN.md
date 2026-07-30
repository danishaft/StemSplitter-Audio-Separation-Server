# Road to Series A plan

This document is the execution source of truth for turning the current 8-stem
backend into a reliable cloud service and self-hosted product, engineering the
cloud edition for a modeled 50,000 monthly active users, and collecting the
evidence required for a credible Series A process. It covers the remaining
product, audio-quality, platform, distribution, operations, security, growth,
and company-readiness work. Last updated: July 25, 2026.

> **Note:** The backend is a functional preview, but the complete product is
> still under active development. Passing code tests does not prove stem
> quality, production reliability, or market readiness.

## How to use this plan

Update this file during every implementation pass. Do not create a competing
roadmap in chat or another file. The commercial-grade implementation plan
remains a detailed audio-research reference, but this file controls launch and
Series A readiness when the plans overlap.

- Mark a task `[x]` only after its evidence exists.
- Leave a task `[ ]` while it is pending.
- Prefix a pending task with `BLOCKED:` when an external dependency prevents
  progress, and record the unblock condition in the decision log.
- Add newly discovered work to the discovery log before implementing it.
- Freeze shared contracts first, then use the dependency map to run independent
  workstreams in parallel.
- Record links or file paths in the evidence register before closing a phase.
- Never promote a stem, model, feature, or capacity claim without its release
  evidence.
- Use the lean execution gates below to decide what blocks the next user
  cohort. The detailed phases are a backlog and evidence checklist, not a
  requirement to finish 200 tasks before anybody can use the product.

## Scale-ready execution gates

These gates build the difficult-to-change 50,000-user foundations before
unsupervised external access. They do not claim that modeled capacity equals
operating history. Supervised testing may continue while the scale-ready core
is implemented.

### Gate A: supervised creator proof

Use this gate for an artist or producer testing on the founder's computer while
the production foundation is under construction.

- Publish only stems that currently pass the available evidence.
- Complete one real upload-to-playback-to-download golden path.
- Provide synchronized playback, solo, mute, volume, and downloads.
- Show errors clearly and retain enough diagnostics to investigate failures.

### Gate B: 50,000-user scale-ready core

Complete this gate before unsupervised cloud access. It is the immediate
engineering target and contains every expensive-to-replace boundary.

- Make PostgreSQL the sole durable authority for jobs, immutable attempts,
  model releases, usage, and audit events.
- Dispatch through a transactional outbox and accept authenticated, idempotent
  completion callbacks. Keep Redis and RQ as replaceable transport.
- Keep the API stateless and all media in private object storage before queue
  admission.
- Implement idempotency, retry ownership, cancellation, reconciliation,
  backpressure, priority classes, complete deletion, and content
  fingerprinting.
- Make Modal authentication fail closed and eliminate credential forwarding,
  SSRF, unbounded downloads, and unsafe archive extraction.
- Implement tenant isolation, quotas, rate limits, spend controls, stable error
  contracts, and immutable audit records.
- Establish versioned execution, storage, identity, billing, configuration,
  API, event, manifest, and model-release contracts.
- Add immutable images, infrastructure-as-code, migrations, CI/CD, signed
  promotion, rollback, backups, disaster recovery, logs, metrics, traces,
  alerts, SLOs, and runbooks.
- Prove the modeled control-plane workload at twice peak using GPU stubs, then
  run bounded real-GPU concurrency, cost, and failure tests.
- Document architecture decisions, threat boundaries, capacity assumptions,
  benchmark evidence, and known limits.

### Gate C: complete cloud product

Complete this gate from the scale-ready core before public paid access.

- Complete honest per-stem quality gates and hide every rejected stem.
- Complete signup, tenant isolation, upload, progress, playback, download,
  history, retry, feedback, support, and deletion.
- Add the usage ledger, entitlements, Stripe, refunds, reconciliation, cost
  attribution, margin controls, and abuse protection.
- Complete the 30-song benchmark, commercial comparison, trained-listener
  study, model promotion, and model rollback process.
- Publish terms, privacy, rights confirmation, retention, support, and
  takedown procedures.
- Pass browser, two-tenant, lifecycle, security, failure, restore, and
  production deployment gates.

### Gate D: stable self-hosted product

Build this gate from the same scale-ready core and release candidate.

- Ship Docker Compose, local CUDA, local and S3-compatible storage, local or
  OIDC identity, model management, setup diagnostics, backups, and upgrades.
- Prove clean installation, offline behavior, migration, rollback, restore,
  deletion, and the same audio-quality contract as cloud.
- Keep telemetry opt-in and remove all cloud billing and credential
  dependencies.
- Add Helm only when an operator requirement or measured deployment need
  justifies it.

### Gate E: prove and operate at scale

This gate turns engineered capacity into truthful operating evidence.

- Roll out cohort by cohort while measuring activation, retention, job success,
  queue delay, cost, margin, incidents, and support load.
- Re-run capacity and failure tests with observed workload distributions.
- Add regions, queue technology, Kubernetes, or GPU-scheduler changes only
  when measured boundaries require them.
- Reach the 50,000-user operating target without changing the core contracts.
- Build fundraising, corporate, and data-room evidence in parallel with
  traction.

### Parallel implementation workstreams

After the Gate B architecture decisions are frozen, execute these workstreams
in parallel against the same contracts.

- Control plane: authority, outbox, attempts, tenancy, usage, and lifecycle.
- Execution platform: Modal security, autoscaling, callbacks, cost, and local
  CUDA provider.
- Data plane: direct uploads, object storage, artifacts, deletion, and content
  identity.
- ML quality: model registry, benchmarks, listener evidence, and promotion.
- Product: authentication, upload, progress, auditioning, history, and support.
- Platform: containers, infrastructure-as-code, CI/CD, observability, recovery,
  and security.
- Distribution: Compose, setup, model delivery, upgrades, and self-hosting.
- Verification: browser, load, failure, tenant, benchmark, and cost evidence.

### Explicit non-requirements

Do not add any item below merely to appear sophisticated.

- Microservices without an independently scaling or ownership boundary.
- Kafka, Temporal, or another queue system before the current transport fails a
  measured requirement.
- Multi-region active-active infrastructure before latency or resilience
  evidence requires it.
- Kubernetes or Helm before the container and Compose contracts pass.
- Hundreds of checkpoints, custom training, or 12-stem marketing without
  per-stem evidence.
- A plugin marketplace, native desktop applications, or broad CPU and ARM
  packaging without customer demand.

## Diagnosis

The project has a credible backend foundation, but it is not yet a user-ready
service. The July 25 architecture audit found unproven audio quality,
fail-open Modal authentication, unsafe credential forwarding, split job
authority, API-local upload assumptions, incomplete deletion, duplicated model
registries, incomplete tenant and billing boundaries, an unfinished user
interface, and no production operating history.

The first milestone is not Series A. The first milestone is a trustworthy
product that repeatedly completes an 8-stem job, explains failures, protects
user files, controls GPU cost, and gives users a polished way to hear and
download results. The second milestone is evidence that people return and pay.

LALAL.AI is not a 50,000-user benchmark. Its
[official company history](https://www.lalal.ai/about/) reported about 6.79
million registered users at the end of 2025. Our 50,000-user target is a
serious engineering and operating milestone, not competitive scale parity.

## Guiding policies

These policies govern implementation and resolve tradeoffs throughout the
roadmap.

- Protect truth over output count. Claim eight stems only after all eight pass
  the release gates.
- Ship cloud and self-hosted editions from one shared application and separation
  core. Use provider adapters instead of product forks.
- Keep one product contract. The production profile remains the only default
  user-facing separation path.
- Keep the standard kit small. Add infrastructure only when a documented
  requirement cannot be met safely with the current kit.
- Make PostgreSQL the sole durable authority for jobs, attempts, model releases,
  usage, and audit events. Queues transport work, and GPU workers execute it.
- Separate control-plane work from GPU execution. The cloud edition uses Modal;
  the self-hosted edition uses local CUDA or an explicitly configured remote
  execution provider.
- Make every costly action metered, idempotent, cancellable where possible, and
  attributable to one user and job.
- Treat uploaded audio as private data. Minimize retention, use signed access,
  and make deletion verifiable.
- Treat model licenses and source-audio rights as release gates, not paperwork
  to resolve later.
- Roll out in measured cohorts. Do not expose 50,000 users to an unmeasured
  queue, cost model, or failure mode.
- Prefer reversible releases, feature flags, and explicit rollback criteria.
- Use user behavior, blind listening, and benchmark evidence together. No
  single metric decides product quality.
- Treat every model and application release as an immutable, reproducible,
  reversible artifact.

## End-state definitions

The roadmap uses three separate finish lines. Reaching one finish line does not
automatically satisfy the next.

### Product-ready definition

The product is ready for paying users only when every item below is true.

- Eight stems pass the approved benchmark and listening gates.
- Upload and Audius input complete through the same production workflow.
- Users can sign in, submit, monitor, cancel, replay, download, and delete jobs.
- Jobs and artifacts survive API restarts and multiple API instances.
- User data is tenant-isolated and delivered through expiring signed URLs.
- Billing, minute accounting, quotas, refunds, and GPU budget controls work.
- Production monitoring, alerting, backups, restore tests, and runbooks exist.
- Terms, privacy, copyright attestation, model licenses, and takedown handling
  are reviewed and published.
- Load and failure tests pass at twice the first rollout target.
- Support can inspect and resolve a failed job without direct server access.

### Modeled 50,000-user design envelope

Capacity planning separates monthly users from concurrent work. The initial
envelope scales the previous conservative assumptions and must be revised with
observed distributions after each rollout cohort. GPU-heavy tests use stubs for
control-plane scale and a bounded real-GPU sample for execution evidence.

| Measure | Design target |
| --- | --- |
| Monthly active users | 50,000 |
| Modeled daily active users | 5,000 |
| Modeled jobs per active user per month | 2 |
| Modeled monthly jobs | 100,000 |
| Modeled average input duration | 4 minutes |
| Modeled monthly audio | 400,000 input minutes |
| Peak active web sessions | 2,500 |
| Peak simultaneous uploads | 500 |
| Peak job-submission burst | 250 per minute |
| Control-plane proof | Twice modeled peak with GPU stubs and no data loss |
| GPU concurrency | Derived from measured latency, queue SLO, and cost ceiling |
| Real-GPU proof | Cost-capped concurrency, retry, and autoscaling campaign |
| API availability target | 99.9% monthly after paid public launch |
| Platform-caused job success target | At least 99% |
| Security target | Zero cross-tenant artifact exposure |
| Economic target | Positive contribution margin at modeled monthly volume |

### Series A-ready definition

Series A readiness requires repeatable demand and defensible operating
evidence, not only a deployed application.

- Reach the board-approved traction threshold, with 50,000 monthly active users
  as the current operating target and verified analytics.
- Demonstrate a stable activation funnel from signup to first useful stem.
- Demonstrate improving four-week creator retention by acquisition cohort.
- Demonstrate paid conversion and a credible path to sustainable gross margin.
- Show that processing volume grows without proportional support incidents.
- Show blind quality evidence against named alternatives on the target use
  cases.
- Maintain a complete model, checkpoint, dataset, and license register.
- Maintain security, privacy, architecture, reliability, and incident records.
- Maintain a current KPI deck, financial model, cap table, product roadmap, and
  investor data room.

### Dual-edition product definition

The cloud and self-hosted editions share the same API, job state machine, stem
contract, model registry, frontend, database migrations, artifact manifest,
quality gates, and observability interfaces. Deployment-specific behavior must
enter through these adapters:

- `ExecutionProvider`: Modal for cloud, and local CUDA for self-hosting.
- `ObjectStore`: B2 for cloud, and S3-compatible or local storage for
  self-hosting.
- `IdentityProvider`: managed identity for cloud, and local or external OIDC
  identity for self-hosting.
- `BillingProvider`: metered cloud billing, and disabled or externally managed
  billing for self-hosting.
- `ConfigurationProvider`: managed secrets for cloud, and setup-wizard or
  environment configuration for self-hosting.

## Standard kit

Use this default stack until evidence requires a change. Record any deviation
as an architecture decision before implementation.

| Concern | Standard choice |
| --- | --- |
| Web client | React, TypeScript, and Vite |
| API | FastAPI, Pydantic, generated OpenAPI client, and Uvicorn |
| GPU inference | Provider interface with Modal and local CUDA implementations |
| Durable authority | PostgreSQL jobs, attempts, releases, usage, and audit events |
| Dispatch | Transactional outbox; Redis and RQ only as the initial transport |
| Artifact storage | Provider interface for B2, S3-compatible storage, and local files |
| Authentication | Provider interface for managed JWT, local identity, and OIDC |
| Payments | Stripe Checkout, Billing, and webhooks |
| Observability | OpenTelemetry-compatible signals and Sentry error reporting |
| Product analytics | Privacy-conscious event analytics |
| Deployment | Managed cloud, Docker Compose, and later Kubernetes or Helm |
| Secrets | Deployment-platform secret manager |
| Model distribution | Versioned manifests, checksums, licenses, and resumable downloads |
| Local legacy path | Demucs for diagnostics only |

## Master progress tracker

Use this table for executive status. Detailed checkboxes and exit gates remain
the authority for completion. Dates are assigned only after available team
capacity and vendor decisions are known.

| Phase | Outcome | Primary role | Status |
| --- | --- | --- | --- |
| Baseline | Hierarchical 12-stem contract foundation | Backend and audio | Foundation complete |
| Phase 0 | Locked scope, vendors, environments, and budget | Founder and technical lead | Not started |
| Phase 1 | Proven API-to-Modal golden path | Backend and QA | Not started |
| Phase 2 | Qualified eight-stem audio quality | Audio research and QA | Not started |
| Phase 3 | Complete web product experience | Product and frontend | In progress |
| Phase 4 | Durable multi-user control plane | Backend and platform | Audit remediation required |
| Phase 5 | Billing, quotas, and unit economics | Backend, product, and finance | Not started |
| Phase 6 | Security, privacy, and rights readiness | Security, legal, and founder | Not started |
| Phase 7 | Reliable production operations | Platform and QA | In progress; cloud deployment deferred until specialist training |
| Phase 8 | Support, analytics, and beta readiness | Product and support | Not started |
| Phase 8S | Releasable self-hosted edition | Platform and product | Not started |
| Phase 9 | Controlled rollout to 50,000 MAU | Founder, product, and operations | Not started |
| Phase 10 | Auditable Series A evidence | Founder and finance | Not started |

## July 25 audit truth reset

The multi-role architecture audit overrides earlier readiness assumptions.
Existing code remains useful, but no item below is production-ready until its
remediation task and proof gate pass.

- Modal worker authentication currently fails open when its API key is absent.
- Worker-provided absolute URLs can receive bearer credentials and create an
  SSRF or credential-disclosure path.
- PostgreSQL, RQ, API polling, leases, reconciliation, and Modal JSON state
  overlap as job authorities and can produce duplicate execution.
- API-local multipart and imported media can be unavailable to a separately
  deployed queue worker.
- Recovery attempt identifiers and cancellation identifiers can diverge.
- Job deletion does not prove deletion of every Modal Volume and object-store
  artifact.
- Production publication is not blocked by the model qualification result.
- The YAML model inventory and worker runtime registry are not one enforceable
  source of truth.
- Current Modal branch limits prevent meaningful horizontal GPU autoscaling.
- Presigned upload limits are described by the API but not enforced by storage
  policy.
- The release benchmark completed only nine of 30 songs. It rejected guitar,
  found piano weak, and did not objectively cover every advertised stem.
- The repository does not yet provide a reproducible, signed release from the
  current dirty and partly untracked source state.

## Completed baseline

These capabilities exist in the repository. They are foundations, not proof
that the product is ready for users.

- [x] `BASE-01` Define the hierarchical 12-stem product contract. Six stems
  have selected delivery models, and six specialist stems remain without a
  qualified production model after SAM Audio failed the piano gate.
- [x] `BASE-02` Integrate the Modal GPU worker path.
- [x] `BASE-03` Prevent silent local Demucs fallback for the production
  profile.
- [x] `BASE-04` Publish structured manifests, artifact groups, and ZIP bundles.
- [x] `BASE-05` Expose profile and stem metadata through `GET /capabilities`.
- [x] `BASE-06` Accept local MP3, WAV, FLAC, OGG, and M4A uploads.
- [x] `BASE-07` Add Audius search, metadata inspection, and licensed import.
- [x] `BASE-08` Reject protected Audius tracks before downloading audio.
- [x] `BASE-09` Persist Audius source and license provenance in job records.
- [x] `BASE-10` Pass the current project-owned automated suite: 88 passed and
  8 skipped as of July 24, 2026.
- [x] `BASE-11` Keep experimental, derived, and production artifacts separate.
- [x] `BASE-12` Create model registry, benchmark, comparator, and candidate
  selection foundations.

## Phase 0: Lock scope and operating decisions

This phase prevents implementation drift. It produces one explicit product
scope and resolves the infrastructure decisions required by later phases.

- [ ] `P0-01` Rename or alias `quality_gpu_experimental` to a stable production
  name such as `quality_8_gpu` without breaking existing clients.
- [ ] `P0-02` Make the production profile the default for user-facing jobs.
- [x] `P0-03` Hide legacy, benchmark, and MVSEP profiles from ordinary users.
- [ ] `P0-04` Define the maximum upload size, duration, formats, and retention
  period for free and paid plans.
- [ ] `P0-05` Approve the standard-kit vendors and monthly launch budget.
- [ ] `P0-06` Define environments for local, test, staging, and production.
- [ ] `P0-07` Define the product name, primary domain, support address, and
  legal entity displayed to users.
- [ ] `P0-08` Create architecture decision records for authentication, object
  storage, database hosting, queue hosting, and deployment hosting.
- [ ] `P0-09` Create a secrets inventory and remove any undocumented local-only
  configuration assumptions.
- [ ] `P0-10` Reconcile stale status claims in older roadmap files and point
  them to this plan.
- [ ] `P0-11` Freeze separate cloud and self-hosted product contracts while
  preserving one API and manifest contract.
- [ ] `P0-12` Approve interfaces for execution, object storage, identity,
  billing, and configuration providers.
- [ ] `P0-13` Approve the canonical authority design: PostgreSQL owns durable
  state, an outbox dispatches work, queues remain transport, and workers return
  signed completion events.
- [ ] `P0-14` Decide whether RQ remains the beta transport or is replaced after
  measured reliability evidence; do not rewrite it for fashion.
- [ ] `P0-15` Define the supported self-hosted matrix for operating systems,
  CPU architecture, NVIDIA driver, CUDA, VRAM, storage, and offline behavior.
- [ ] `P0-16` Define cloud, Community self-hosted, and future Team self-hosted
  feature and support boundaries.
- [ ] `P0-17` Freeze the 50,000-user workload, latency, availability, recovery,
  retention, security, and cost assumptions in a versioned capacity model.
- [x] `P0-18` Audit platform reference implementations and record source
  commits, licenses, reusable boundaries, rejection reasons, and adoption
  gates in `../architecture/PLATFORM_REFERENCE_IMPLEMENTATION_MAP.md`.
- [x] `P0-19A` Build and pass the deterministic Hatchet product-contract and
  SDK compatibility proof without changing production dispatch.
- [ ] `P0-19B` Run the real Hatchet server campaign for priority, concurrency,
  cancellation, retry, worker-crash recovery, and duplicate-effect behavior.
  Keep RQ until this passes; Docker was unavailable for the July 26 attempt.
- [x] `P0-20` Audit mature FastAPI implementations and select Onyx, Prefect,
  InvokeAI, and the official FastAPI full-stack template as bounded references.

**Exit gate:** Product scope, vendors, environments, limits, and budget are
written down and approved. No unresolved choice blocks Phase 3 or Phase 4.

## Phase 1: Prove the real eight-stem golden path

This phase validates the actual FastAPI-to-Modal-to-artifact workflow. Mocked
tests do not satisfy this gate.

- [ ] `P1-01` Select a legally usable, representative five-minute validation
  song and preserve its source provenance.
- [x] `P1-02` Submit the song through `POST /jobs`, not directly to the worker.
- [x] `P1-03` Record queue, upload, model, artifact-import, packaging, and total
  timings.
- [x] `P1-04` Confirm all eight named outputs exist and are nonempty.
- [ ] `P1-05` Confirm every output has the expected duration, sample rate,
  channel count, and bit depth.
- [ ] `P1-06` Confirm manifest paths, artifact URLs, and ZIP contents match the
  eight-stem contract exactly.
- [ ] `P1-07` Confirm source provenance reaches status and final manifest.
- [ ] `P1-08` Confirm malformed input, worker timeout, worker rejection, and
  artifact-import failure produce stable user-facing errors.
- [ ] `P1-09` Confirm an API restart during a job does not create duplicate GPU
  spend; record the current failure if persistence is not implemented yet.
- [ ] `P1-10` Save the complete golden-path evidence under `benchmarks/`.
- [ ] `P1-11` Make Modal authentication fail closed and inject the production
  worker secret into every deployed ASGI and function entry point. Test missing,
  malformed, expired, replayed, and rotated credentials.
- [ ] `P1-12` Permit credentials only for allowlisted worker origins and reject
  arbitrary absolute callback, artifact, and download URLs. Test private IPs,
  redirects, DNS rebinding, and malicious worker responses.
- [ ] `P1-13` Bound response size, archive expansion, file count, redirects,
  timeouts, checksums, paths, symlinks, expansion ratio, and total bytes for
  every remote artifact.
- [ ] `P1-14` Enforce the selected model release and stem qualification result
  before publishing any production artifact.
- [ ] `P1-15` Configure real branch concurrency and prove autoscaling without
  cross-job state leakage or uncontrolled cost.
- [ ] `P1-16` Prove that deleting a job removes B2 objects, temporary uploads,
  Modal Volume files, manifests, archives, and derived artifacts.

**Exit gate:** One full production-contract job completes through the public
API, and every artifact and failure assertion has saved evidence.

## Phase 2: Qualify audio quality for release

This phase decides which of the 12 target stems deserve a production claim. It
must qualify each stem independently before users spend money.

- [ ] `P2-01` Freeze a diverse launch corpus of at least 30 songs covering
  Afrobeats, pop, hip-hop, rock, electronic, acoustic, live, dense, sparse,
  mono, stereo, lossy, and lossless material.
- [ ] `P2-02` Add ground-truth datasets that cover every stem family where
  legally and technically possible.
- [ ] `P2-03` Record dataset versions, licenses, hashes, excerpts, and permitted
  uses.
- [ ] `P2-04` Purchase a fixed comparator budget for LALAL.AI, Moises, or other
  approved commercial outputs.
- [ ] `P2-05` Generate all candidates once and cache immutable outputs so
  scoring changes do not spend GPU credits again.
- [ ] `P2-06` Measure SI-SDR or SDR, leakage, silence errors, clipping, phase,
  loudness, reconstruction error, and runtime per stem.
- [ ] `P2-07` Create a blind listening tool with randomized A/B ordering.
- [ ] `P2-08` Recruit at least five reviewers with musicianship, production, or
  mixing experience.
- [ ] `P2-09` Rate isolation, naturalness, artifacts, missing content, and
  practical usability for every stem.
- [ ] `P2-10` Require at least 90% of launch-corpus jobs to have no critical
  stem failure.
- [ ] `P2-11` Require our result to be preferred or tied in at least 60% of
  blind comparisons for each claimed stem family.
- [ ] `P2-12` Set per-stem objective thresholds from ground truth and approved
  commercial baselines; do not reuse generic publishability scores.
- [ ] `P2-13` Replace, reroute, or remove any stem that fails its gate.
- [ ] `P2-14` Pin model versions, checksums, licenses, routing, and postprocess
  configuration for the release candidate.
- [ ] `P2-15` Add the approved corpus and thresholds to a repeatable regression
  command.
- [ ] `P2-16` Publish an internal release report that names passed, failed, and
  excluded stems without marketing language.
- [ ] `P2-17` Replace the duplicated YAML and hardcoded runtime registries with
  one validated, versioned model-release source of truth.
- [ ] `P2-18` Record architecture, checkpoint hash, source, license,
  redistribution permission, supported stems, preprocessing, routing, and
  rollback target for every model release.
- [ ] `P2-19` Record quality, latency, VRAM, and cost at each supported
  quality-speed profile.
- [ ] `P2-20` Calibrate objective thresholds against listener mean-opinion
  scores and document every objective-versus-subjective disagreement.
- [ ] `P2-21` Add silent-source, absent-instrument, bleed, phase, stereo-image,
  reconstruction, and adversarial-genre tests.
- [ ] `P2-22` Build immutable candidate caches keyed by source fingerprint,
  excerpt, model release, route, and postprocessing version.
- [ ] `P2-23` Implement model promotion, canary, rollback, quarantine, and
  emergency-disable workflows.
- [ ] `P2-24` Publish model cards for every user-visible release and label weak
  or unqualified stems as experimental or unavailable.
- [ ] `P2-25` Measure instrument-presence detection and confidence gating before
  using either to skip a model or publish a stem.
- [ ] `P2-26` Promote routing, ensemble, residual redistribution, phase
  alignment, or refinement logic only when the frozen corpus proves a
  per-stem improvement without unacceptable latency or cost.
- [ ] `P2-27` Start custom training or fine-tuning only after the candidate
  registry proves that no legally usable open checkpoint passes a required
  stem gate, then define dataset lineage and reproducible training evidence.

**Exit gate:** Each publicly claimed stem has objective evidence, blind
listening evidence, known model provenance, a known license, and a pass
decision. Unqualified stems remain visibly pending.

## Phase 3: Build the complete user experience

This phase replaces the current static page with the product users will
actually experience on desktop and mobile.

- [x] `P3-01` Create the React, TypeScript, and Vite application shell with
  strict type checking.
- [x] `P3-02` Consume `GET /capabilities` instead of hardcoding profiles,
  stems, limits, or source types.
- [ ] `P3-03` Build signup, login, logout, session expiry, and account recovery.
- [ ] `P3-04` Build drag-and-drop upload with format, duration, and size
  preflight.
- [x] `P3-05` Build Audius search with artwork, artist, duration, license, and
  clear import eligibility.
- [ ] `P3-06` Build a submission summary that shows expected stems, estimated
  minutes, plan usage, retention, and rights confirmation.
- [x] `P3-07` Build queued, uploading, processing, packaging, completed,
  cancelled, and failed job states.
- [ ] `P3-08` Add resumable or retryable upload behavior for unstable networks.
- [ ] `P3-09` Build synchronized waveform playback for the mix and all stems.
- [ ] `P3-10` Add solo, mute, volume, seek, loop, and A/B controls.
- [ ] `P3-11` Add individual stem and ZIP downloads with expiry messaging.
- [ ] `P3-12` Build project history, retry, rename, delete, and expiration
  views.
- [ ] `P3-13` Build actionable error states using stable API error codes.
- [ ] `P3-14` Add per-job quality feedback and issue-reporting controls.
- [ ] `P3-15` Make keyboard navigation, focus states, labels, contrast, and
  screen-reader output meet WCAG 2.2 AA for critical flows.
- [ ] `P3-16` Test the complete flow on current Chrome, Firefox, Safari, Edge,
  Android, and iOS viewport sizes.
- [ ] `P3-17` Add a privacy-safe consent and analytics preference interface.
- [ ] `P3-18` Resume active jobs and their latest events after refresh, logout,
  reconnect, or device change.
- [ ] `P3-19` Show queue position, estimated wait, current processing stage,
  elapsed time, and actionable recovery state without inventing precision.
- [ ] `P3-20` Add a persistent project library with search, filters, source
  provenance, model release, settings, and expiration state.
- [ ] `P3-21` Add reusable separation presets and preserve deterministic job
  provenance for support and reproducibility.
- [ ] `P3-22` Define a versioned source-provider interface so Audius and future
  licensed catalogue integrations do not leak provider logic across the app.
- [ ] `P3-23` Define export contracts for selected stems, full archives, DAW
  handoff, and future share links without storing permanent duplicate ZIPs.
- [ ] `P3-24` Automate the fresh-account browser golden path from signup and
  upload through progress, synchronized playback, download, and deletion.

### Deferred frontend and product research

Review these products when Phase 3 frontend redesign starts. Use them to
identify proven workflow, information architecture, playback, and visual
communication patterns. Do not copy their branding, assume undocumented
technical behavior, or expand the current backend scope based on appearance.

- [Moises product](https://moises.ai/): Review upload-to-result flow, stem
  auditioning, project organization, progress communication, and upgrade
  boundaries.
- [Moises Research innovations for 2025](https://music.ai/blog/research/Moises-Research-Innovations-2025/):
  Review how research capability, quality evidence, and product value are
  communicated to non-research users.
- [Stable Audio](https://stableaudio.com/): Review onboarding, task focus,
  generation controls, result presentation, and audio-first interaction
  patterns.
- [Vocuno](https://vocuno.com/): Review its product positioning, primary user
  journey, audio controls, and visual hierarchy.

Keep this research deferred until the frontend work begins. Validate every
pattern against the project's own user journey, accessibility requirements,
API contract, and measured processing behavior before adoption.

**Exit gate:** A new user can complete the first-stem journey without terminal
access, staff intervention, hidden profiles, or unexplained errors.

## Phase 4: Build the multi-user control plane

This phase removes single-machine assumptions and makes jobs durable,
tenant-safe, retryable, and horizontally deployable.

- [ ] `P4-01` Define PostgreSQL schemas for users, organizations, memberships,
  projects, inputs, jobs, attempts, artifacts, model releases, usage ledger,
  plans, API keys, webhooks, and audit events.
- [x] `P4-02A` Add and apply the initial control-plane migration to managed
  PostgreSQL.
- [ ] `P4-02B` Add and prove the migration rollback procedure.
- [x] `P4-03A` Implement JWT authentication and ownership checks on every job
  and artifact route.
- [x] `P4-03B` Configure Supabase ES256 JWT verification and pass a real-token
  route probe.
- [ ] `P4-03C` Pass cross-tenant route tests with two managed identities.
- [x] `P4-04A` Implement scoped object references, direct uploads, GPU-side
  materialization, worker-side packaging, and object publication.
- [ ] `P4-04B` Configure the private S3-compatible provider, migrate manifests,
  apply retention, and prove the path with a measured Modal run.
- [x] `P4-05A` Generate short-lived signed URLs for object artifacts without
  persisting the signed values.
- [ ] `P4-05B` Remove production dependence on local artifact routes after the
  object path passes deployment verification.
- [x] `P4-06A` Implement Redis and RQ dispatch with explicit execution
  timeouts.
- [x] `P4-06B` Configure managed native TLS Redis and prove RQ execution for a
  real application job.
- [x] `P4-06C` Prove queue recovery after worker termination.
- [x] `P4-07A` Implement a persistent job state machine with valid
  transitions and a distinct `cancelling` state.
- [x] `P4-07B` Prove queued job leasing and cancellation against managed
  PostgreSQL.
- [x] `P4-07C` Run crash-recovery drills against PostgreSQL.
- [x] `P4-08A` Add owner-scoped idempotency keys to job creation.
- [ ] `P4-08B` Add idempotency to future payment-sensitive operations.
- [x] `P4-09` Add bounded retries with distinct retryable and terminal errors.
- [x] `P4-10A` Implement truthful queued and Modal cancellation semantics.
- [ ] `P4-10B` Prove cancellation races and orphan prevention in staging.
- [x] `P4-11` Reconcile orphaned Modal jobs and artifacts after API or worker
  restarts.
- [x] `P4-12A` Add renewable database-backed execution leases.
- [x] `P4-12B` Prove lease takeover and duplicate-spend prevention in staging.
- [x] `P4-13` Add durable event delivery through polling. Add server-sent
  events only if measured UX requires it.
- [x] `P4-14A` Implement terminal job deletion and an expiry sweep that removes
  referenced object-storage media.
- [ ] `P4-14B` Schedule the sweep, configure abandoned-upload lifecycle rules,
  and prove hard deletion against B2.
- [ ] `P4-15` Implement account export and account deletion workflows.
- [ ] `P4-16` Add an admin API for safe job inspection, retry, cancellation,
  credit adjustment, and deletion.
- [ ] `P4-17` Run a backup-and-restore drill for PostgreSQL and object metadata.
- [ ] `P4-18` Make PostgreSQL the only durable job-state authority and remove
  Modal JSON files, queue metadata, and in-process dictionaries as competing
  authorities.
- [ ] `P4-19` Store immutable execution attempts separately from the logical
  job and use the same attempt identity for dispatch, cancellation, callbacks,
  retries, cost, and audit events.
- [ ] `P4-20` Replace API-side blocking Modal polling with a transactional
  outbox and authenticated, idempotent worker-completion callback.
- [ ] `P4-21` Publish every upload and provider import to durable object storage
  before queue admission so API and queue-worker containers share no media
  filesystem assumption.
- [ ] `P4-22` Define one retry owner per failure boundary and prove that API,
  RQ, reconciliation, and Modal cannot retry the same attempt independently.
- [ ] `P4-23` Add canonical audio fingerprinting and source identity so exact
  duplicates can reuse approved immutable results without duplicate GPU spend.
- [ ] `P4-24` Partition interactive preview, full-quality, recovery,
  coordinator, and maintenance work with explicit priority, backpressure, and
  reserved recovery capacity.
- [ ] `P4-25` Enforce upload size at the object-store policy boundary, verify
  the committed object before dispatch, and reject abandoned or oversized
  uploads.
- [ ] `P4-26` Stream or generate archives on demand and prove that archive
  creation cannot duplicate permanent storage or exhaust API memory.
- [ ] `P4-27` Version API, manifest, event, and provider contracts and define
  backward-compatibility and migration rules.
- [ ] `P4-28` Run a 100-job crash, retry, callback-replay, and cancellation
  campaign with zero duplicate charges, terminal-state reversals, or orphaned
  artifacts.
- [ ] `P4-29` Implement organization tenancy, roles, invitations, ownership
  transfer, and tenant-scoped quotas without weakening personal accounts.
- [ ] `P4-30` Add scoped API keys and signed outbound webhooks only after the
  browser workflow and tenant boundary pass their release gates.
- [x] `P4-31` Remove the synchronous `/separate` production path or route it
  through the same durable job contract; never run chargeable GPU work inside
  a Gunicorn request.
- [ ] `P4-32` Add connection pooling, bounded transactions, required indexes,
  query-plan evidence, keyset pagination, and query budgets for every hot
  control-plane path.
- [ ] `P4-33` Define backward-compatible, expand-and-contract database
  migrations and prove mixed-version deployment without downtime or state
  corruption.
- [x] `P4-34` Publish an OpenAPI contract and generated or contract-tested web
  client types so backend and frontend releases cannot silently drift.
- [x] `P4-35` Replace the Flask transport with domain-oriented FastAPI routers,
  Pydantic schemas, dependency-based authentication, global error handling, and
  Uvicorn deployment while preserving the `splitter/` domain modules.
- [x] `P4-36` Remove Flask, Flask-CORS, Flask-Talisman, Gunicorn WSGI
  configuration, manual frontend response types, and the synchronous legacy
  routes after FastAPI contract and browser parity pass.

**Exit gate:** Multiple API instances can process users concurrently without
duplicate jobs, lost state, local-disk dependence, or cross-tenant access.

## Phase 5: Meter usage and control economics

This phase prevents uncontrolled GPU spending and proves that pricing can
support the service.

- [ ] `P5-01` Measure input duration before accepting a chargeable job.
- [ ] `P5-02` Create an append-only usage ledger for reserved, consumed,
  released, refunded, and promotional minutes.
- [ ] `P5-03` Define free, trial, paid, and internal plan entitlements.
- [ ] `P5-04` Add per-user upload, job, concurrency, and daily rate limits.
- [ ] `P5-05` Reserve usage before queueing and reconcile it exactly once after
  completion or failure.
- [ ] `P5-06` Integrate Stripe Checkout and customer billing management.
- [ ] `P5-07` Verify Stripe webhook signatures and make webhook processing
  idempotent.
- [ ] `P5-08` Define refund and credit-restoration rules for each failure class.
- [ ] `P5-09` Record Modal GPU time, API cost, storage, egress, and support cost
  per job.
- [ ] `P5-10` Calculate contribution margin per processed minute and per plan.
- [ ] `P5-11` Add daily, weekly, and monthly provider budget alerts.
- [ ] `P5-12` Add a global GPU-spend circuit breaker and per-account abuse
  breaker.
- [ ] `P5-13` Validate plan prices against observed usage and a minimum 60%
  gross-margin launch target.
- [ ] `P5-14` Model the cost of 100,000 monthly jobs and a two-times stress
  case.
- [ ] `P5-15` Measure cold and warm latency, billed GPU time, queue delay,
  storage, and egress for every production route and supported duration.
- [ ] `P5-16` Attribute deduplication and cache savings without billing a user
  for GPU work that did not occur.
- [ ] `P5-17` Define separate cloud plan economics and self-hosted support or
  licensing economics without adding cloud billing to Community installations.

**Exit gate:** Every GPU minute has an owner, entitlement, cost record, and
reconciliation outcome, and modeled 50,000-user usage stays within budget.

## Phase 6: Complete security, privacy, and rights work

This phase protects user data, the company, and the artists whose work enters
the system.

- [ ] `P6-01` Perform a route-by-route authorization and tenant-isolation audit.
- [ ] `P6-02` Validate file signatures with `ffprobe`; do not trust filenames or
  MIME headers alone.
- [ ] `P6-03` Reject malformed media, decompression bombs, extreme channel
  counts, unsafe duration, and unsupported codecs before GPU submission.
- [ ] `P6-04` Keep URL imports provider-controlled or apply complete SSRF
  protections to any future direct URL source.
- [ ] `P6-05` Add API rate limiting, request IDs, secure headers, CORS policy,
  and maximum body enforcement at the reverse proxy.
- [ ] `P6-06` Encrypt transport, database connections, object storage, and
  backups.
- [ ] `P6-07` Rotate all production secrets and document rotation ownership.
- [ ] `P6-08` Add dependency, container, secret, and static security scans to
  continuous integration, with severity gates, expiry dates, and ownership for
  every exception.
- [ ] `P6-09` Add immutable audit events for login, job access, deletion,
  billing, and admin actions.
- [ ] `P6-10` Publish terms of service, privacy policy, cookie policy, retention
  policy, and acceptable-use policy.
- [ ] `P6-11` Require users to confirm rights or authorization for uploaded
  audio before processing.
- [ ] `P6-12` Publish a copyright complaint and takedown process.
- [ ] `P6-13` Review every production model, checkpoint, dataset, and runtime
  dependency for commercial-use compatibility.
- [ ] `P6-14` Preserve Audius license and attribution requirements in the UI,
  job, manifest, and download experience.
- [ ] `P6-15` Define data-processing vendors and publish the necessary vendor
  disclosures.
- [ ] `P6-16` Conduct an independent penetration test before paid public access.
- [ ] `P6-17` Fix all critical and high findings or document an approved
  compensating control.
- [ ] `P6-21` Produce a software bill of materials, sign release images, verify
  model checksums, and publish vulnerability response ownership.
- [ ] `P6-22` Define self-hosted trust boundaries, rootless container defaults,
  secret storage, network exposure, administrator powers, and secure reset.
- [ ] `P6-23` Make product telemetry opt-in for self-hosted installations and
  document every event and external connection.
- [ ] `P6-24` Verify model redistribution rights separately from permission to
  run a model in the managed cloud.

**Exit gate:** Paid public access has legal review, tenant isolation, validated
media handling, deletion, auditability, and no unresolved critical security
finding.

## Phase 7: Make operations reliable and observable

This phase creates the controls required to operate the service without
watching terminals or discovering failures from users.

### Locked cloud deployment topology

This topology is approved but not yet implemented. Cloud deployment work
resumes after the electric-guitar, strings, and wind/brass corpora are frozen
and their first production candidates complete the initial qualification gate.
This sequencing does not permit public access before the remaining product,
security, billing, reliability, and release gates pass.

- Cloudflare Pages serves the React and Vite application.
- Cloudflare manages DNS, TLS, CDN behavior, web application firewall rules,
  denial-of-service controls, and edge rate limits.
- Azure Container Apps runs separate FastAPI API, RQ worker, and scheduled
  maintenance containers.
- Azure Container Registry stores immutable application images.
- Azure Key Vault stores deployment secrets. GitHub Actions uses workload
  identity federation instead of long-lived Azure credentials.
- Supabase remains the PostgreSQL authority and JWT identity provider.
- Upstash remains the TLS Redis and RQ transport.
- Backblaze B2 remains the private input and artifact object store.
- Modal remains the GPU execution provider.
- Sentry captures redacted application errors. Existing Prometheus metrics and
  Azure operational telemetry provide service and infrastructure signals.
- OpenTofu or Terraform declares Cloudflare, Azure, DNS, deployment, and alert
  configuration. Provider data is imported rather than recreated when a
  managed service already exists.

Azure does not replace Supabase, Upstash, B2, or Modal in this phase. A provider
migration requires measured evidence that the existing service misses an
approved reliability, cost, latency, or capacity target.

- [x] `P7-01` Run FastAPI through the production ASGI entry point with health,
  readiness, metrics, and version endpoints.
- [ ] `P7-02` Produce immutable Docker images for API, queue worker, and web
  client.
- [ ] `P7-03` Build continuous integration for linting, tests, migrations,
  security scans, and image builds.
- [ ] `P7-04` Build staging and production deployment pipelines with manual
  production approval.
- [ ] `P7-05` Add structured logs with request, user, job, worker, and model
  release identifiers.
- [ ] `P7-06` Add Sentry error reporting with audio content and secrets
  redacted.
- [ ] `P7-07` Add metrics for API latency, queue depth, wait time, job duration,
  worker failures, artifact failures, cost, and success by model release.
- [ ] `P7-08` Define service-level indicators and a 99.5% initial service-level
  objective.
- [ ] `P7-09` Alert on sustained queue growth, error spikes, stuck jobs,
  duplicate spend, and storage failures. Phase 5 owns financial budget alerts.
- [ ] `P7-10` Create runbooks for API outage, Modal outage, database outage,
  queue outage, storage outage, billing failure, and data exposure.
- [ ] `P7-11` Add feature flags and a production-profile kill switch.
- [ ] `P7-12` Test rollback for application code, database migrations, model
  release, and frontend release.
- [ ] `P7-13` Load-test ordinary API traffic at twice the 50,000-user modeled
  peak.
- [ ] `P7-14` Load-test queue admission with stubbed GPU execution, then run a
  controlled real-GPU concurrency test within a fixed budget.
- [ ] `P7-15` Perform restart, timeout, slow-upload, provider-rate-limit,
  corrupted-artifact, and partial-outage fault tests.
- [ ] `P7-17` Instrument distributed traces across browser, API, outbox, queue,
  execution provider, object store, callback, and billing reconciliation.
- [ ] `P7-18` Define stable machine-readable error codes with retryability,
  ownership, user guidance, operator guidance, and support correlation.
- [ ] `P7-19` Build immutable release manifests that bind source commit, image
  digest, migration version, frontend version, model releases, and
  configuration schema.
- [ ] `P7-20` Add dependency lock verification, reproducible builds, pull
  request images, software bills of materials, and signed promotion. `P6-08`
  owns security scan policy.
- [ ] `P7-21` Schedule and prove cache eviction, temporary archive cleanup, and
  maintenance jobs not already covered by the Phase 4 media lifecycle.
- [ ] `P7-22` Test disaster recovery from a clean environment using only
  documented backups, release artifacts, secrets, and runbooks.
- [ ] `P7-23` Collect 30 consecutive days of staging and controlled-beta
  reliability, latency, cost, and incident history before the public claim.
- [ ] `P7-24` Declare Cloudflare, Azure Container Apps, Azure Container
  Registry, Azure Key Vault, DNS, service configuration, and alerts through
  reviewed OpenTofu or Terraform. Import existing Supabase, Upstash, B2, and
  Modal identifiers as configuration without recreating those services.
- [ ] `P7-25` Put `app.<domain>` and `api.<domain>` behind Cloudflare-managed
  DNS and TLS. Configure WAF rules, upload-aware rate limits, denial-of-service
  controls, safe caching, and explicit origin protection.
- [ ] `P7-26` Prove horizontal API, dispatch, maintenance, and execution
  replicas without sticky local state, duplicate work, or connection-pool
  exhaustion.
- [ ] `P7-27` Build and deploy separate FastAPI API, RQ worker, and maintenance
  images to Azure Container Apps with immutable revisions, health checks,
  resource limits, controlled scaling, and rollback.
- [ ] `P7-28` Deploy the React and Vite client to Cloudflare Pages and configure
  its production API origin without embedding service credentials.
- [ ] `P7-29` Add the Supabase signup, login, token refresh, logout, and account
  recovery flow to the web client. Remove the manual `localStorage` token
  requirement from the user journey.
- [ ] `P7-30` Store production secrets in Azure Key Vault and synchronize only
  the minimum required values into each Container App. Keep Cloudflare and
  GitHub credentials outside application containers.
- [ ] `P7-31` Configure the exact production CORS origin and a non-empty Modal
  worker API key, then pass both configuration-only and live production
  preflight checks.
- [ ] `P7-32` Connect GitHub Actions to Cloudflare and Azure through short-lived
  identity, then implement preview, staging, migration, image promotion,
  production approval, and rollback workflows.
- [ ] `P7-33` Connect Sentry, Prometheus, Azure telemetry, and provider health
  signals to actionable alerts before external unsupervised access.

**Exit gate:** The service passes capacity and failure tests, alerts reach an
owner, every critical incident has a runbook, and rollback is demonstrated.

## Phase 8: Prepare support, analytics, and beta operations

This phase equips the team to learn from users and resolve problems during a
controlled beta.

- [ ] `P8-01` Define the activation event as a completed job followed by stem
  playback or download.
- [ ] `P8-02` Instrument signup, source choice, upload start, submission,
  completion, first playback, download, repeat job, upgrade, cancellation, and
  quality feedback.
- [ ] `P8-03` Build dashboards for acquisition, activation, job completion,
  retention, paid conversion, support rate, and gross margin.
- [ ] `P8-04` Create a support inbox, response templates, severity policy, and
  escalation path.
- [ ] `P8-05` Create an admin console that resolves common failures without
  database or shell access.
- [ ] `P8-06` Define refund, abuse, copyright, privacy, and data-loss support
  procedures.
- [ ] `P8-07` Recruit a balanced beta cohort of artists, producers, DJs,
  engineers, educators, and casual creators.
- [ ] `P8-08` Create an onboarding checklist and a five-minute first-value
  target.
- [ ] `P8-09` Create a weekly quality-review process that connects user reports
  to model release and regression evidence.
- [ ] `P8-10` Create a public status page and incident communication template.
- [ ] `P8-11` Define beta terms, support hours, and expected response times.
- [ ] `P8-12` Freeze the launch candidate and complete the launch-readiness
  review.

**Exit gate:** The team can observe the funnel, support every beta user, trace
quality complaints, issue credits, and communicate incidents.

## Phase 8S: Release the self-hosted edition

This phase packages the same tested platform for users who operate their own
infrastructure. It must not create a separate separation engine, API, frontend,
manifest, or migration history.

- [ ] `SH-01` Extract and enforce provider interfaces for execution, object
  storage, identity, billing, configuration, and telemetry.
- [ ] `SH-02` Build a production Docker Compose distribution with API, web,
  PostgreSQL, Redis transport, maintenance, and local GPU worker services.
- [ ] `SH-03` Implement the local CUDA execution provider with explicit GPU,
  VRAM, driver, CUDA, model, and disk-space capability checks.
- [ ] `SH-04` Implement local-filesystem and generic S3-compatible storage
  providers with the same private-artifact and deletion contract as B2.
- [ ] `SH-05` Build a setup and administration flow for storage, identity,
  execution, retention, models, and connectivity without exposing secrets to
  ordinary users.
- [ ] `SH-06` Build a resumable model manager that verifies source, license,
  acceptance, version, size, checksum, disk capacity, and installed state.
- [ ] `SH-07` Support secure single-user mode, local team accounts, and external
  OIDC without cloud-only Supabase assumptions.
- [ ] `SH-08` Provide versioned configuration schemas, automatic database
  migrations, pre-upgrade backups, compatibility checks, and tested rollback.
- [ ] `SH-09` Provide backup, restore, export, retention, and complete deletion
  commands for database, configuration, models, and artifacts.
- [ ] `SH-10` Prove offline operation after approved models and images are
  installed, and document every feature that requires an external service.
- [ ] `SH-11` Publish supported hardware profiles and truthful performance
  expectations; reject unsupported configurations with actionable diagnostics.
- [ ] `SH-12` Add local health, logs, metrics, job inspection, cleanup, and a
  redacted diagnostic bundle for support.
- [ ] `SH-13` Publish signed versioned images, release notes, migration notes,
  checksums, and supported upgrade paths.
- [ ] `SH-14` Test clean install, restart, upgrade, rollback, backup, restore,
  model download, job execution, and uninstall on every supported platform.
- [ ] `SH-15` Write operator, administrator, security, troubleshooting, GPU,
  storage, identity, backup, upgrade, and recovery documentation.
- [ ] `SH-16` Add a Kubernetes or Helm distribution only after the Compose
  contract passes and without introducing a second application architecture.
- [ ] `SH-17` Define versioned integration contracts for music sources, storage,
  execution, and DAW clients; postpone a plugin marketplace until demand.
- [ ] `SH-18` Confirm that self-hosted telemetry is disabled by default or
  explicitly opted in, and that no cloud credential or billing dependency
  exists.
- [ ] `SH-19` Publish the model redistribution matrix and require users to
  obtain restricted checkpoints directly when redistribution is prohibited.
- [ ] `SH-20` Run the same golden-path, quality, security, lifecycle, and
  recovery suites against a clean self-hosted installation.

**Exit gate:** A new operator can install, configure, split, upgrade, back up,
restore, and remove the product from documented instructions without hidden
cloud dependencies or source-code changes.

## Phase 9: Roll out incrementally to 50,000 users

This phase expands access only when the previous cohort meets its quality,
reliability, cost, and support gates. Capacity means monthly active users, not
registered accounts or email signups.

- [ ] `R0` Complete staff dogfooding with 5-10 users and at least 50 diverse
  jobs.
- [ ] `R0-GATE` Require zero critical privacy defects, at least 95% job success,
  and no unexplained usage-ledger mismatch.
- [ ] `R1` Run a private alpha with 25 invited creators and at least 100 jobs.
- [ ] `R1-GATE` Require at least 60% activation, at least 95% job success, and
  fewer than 15 support contacts per 100 jobs.
- [ ] `R2` Expand to 100 users after fixing all repeated alpha failure classes.
- [ ] `R2-GATE` Require at least 97% platform job success, no critical security
  finding, measured cost per minute, and at least 25% four-week retention among
  activated creators.
- [ ] `R3` Expand to 500 users with payment enabled for a limited cohort.
- [ ] `R3-GATE` Require successful billing reconciliation, at least 5% paid
  conversion among eligible activated users, at least 60% gross margin, and no
  unresolved severity-one incident.
- [ ] `R4` Expand to 1,000 users with controlled referral access.
- [ ] `R4-GATE` Require four weeks within the error budget, stable queue wait,
  decreasing support contacts per 100 jobs, and a completed capacity rerun.
- [ ] `R5` Expand to 2,000 monthly active users.
- [ ] `R5-GATE` Require eight weeks of reliable operation, cohort retention,
  sustainable unit economics, tested incident response, and a current
  investor KPI package.
- [ ] `R6` Expand to 10,000 monthly active users after observed demand and
  capacity remain within the Gate B contracts.
- [ ] `R6-GATE` Require a capacity rerun with observed workload distributions,
  stable p95 queue delay, positive contribution margin, and no unresolved
  systemic incident.
- [ ] `R7` Expand to 25,000 monthly active users with provider capacity and
  support coverage reserved.
- [ ] `R7-GATE` Require four weeks within the 99.9% error budget, tested
  disaster recovery, stable quality, and no uncontrolled infrastructure cost.
- [ ] `R8` Expand to 50,000 monthly active users.
- [ ] `R8-GATE` Require eight weeks of reliable operation at target scale,
  sustainable retention and margin, current security review, tested recovery,
  and an evidence-backed next capacity plan.

**Rollback rule:** Pause invitations when a gate fails. Disable new paid jobs
for any security, tenant-isolation, billing-integrity, or uncontrolled-spend
incident. Roll back the model release when quality regression exceeds its
approved threshold.

## Phase 10: Build the Series A evidence package

This phase turns operating history into an auditable company narrative. Begin
collecting evidence during beta; do not reconstruct it immediately before
fundraising.

- [ ] `P10-01` Publish a monthly KPI review with acquisition, activation,
  retention, revenue, gross margin, processing volume, and reliability.
- [ ] `P10-02` Maintain weekly and monthly cohort retention by acquisition
  source and user segment.
- [ ] `P10-03` Quantify the strongest use cases and identify the segment with
  the highest retention and willingness to pay.
- [ ] `P10-04` Produce blind benchmark evidence and user case studies for the
  eight-stem quality claim.
- [ ] `P10-05` Quantify model or orchestration advantages that competitors
  cannot reproduce by merely using the same public checkpoint.
- [ ] `P10-06` Maintain a 24-month financial model with pricing, GPU cost,
  storage, payroll, marketing, support, runway, and hiring assumptions.
- [ ] `P10-07` Maintain a clean cap table, incorporation records, contracts,
  taxes, and intellectual-property assignments.
- [ ] `P10-08` Maintain the model, code, dataset, dependency, and trademark
  intellectual-property register.
- [ ] `P10-09` Maintain architecture, security, privacy, incident, uptime, and
  disaster-recovery evidence.
- [ ] `P10-10` Maintain a product roadmap tied to customer evidence and the use
  of Series A funds.
- [ ] `P10-11` Build the investor data room with controlled permissions and an
  index of current documents.
- [ ] `P10-12` Prepare a concise fundraising narrative covering problem,
  wedge, product, quality evidence, market, traction, retention, economics,
  differentiation, team, and financing plan.
- [ ] `P10-13` Define the Series A trigger before outreach, including minimum
  retention, revenue, growth, margin, and runway conditions.
- [ ] `P10-14` Run legal, financial, security, and technical diligence dry
  runs before opening the round.

**Exit gate:** Every material investor claim can be traced to current product,
financial, legal, or analytics evidence in the data room.

## Dependency map

Use these dependencies to sequence work and identify safe parallel tracks.

- Phase 0 blocks all vendor-specific production implementation.
- Phase 1 blocks quality claims and provides the real timings for cost work.
- Phase 2 blocks public claims and paid rollout.
- Phase 3 can begin after Phase 0 and run in parallel with Phase 2.
- Phase 4 blocks multi-user beta, billing, and reliable history.
- Phase 5 depends on Phase 4 job ownership and persistent usage records.
- Phase 6 depends on the Phase 3 user flow and Phase 4 storage architecture.
- Phase 7 depends on the Phase 4 deployable control plane.
- Phase 8 depends on stable product, identity, and observability contracts.
- Phase 8S depends on the shared provider contracts, model-release authority,
  quality gates, lifecycle behavior, and reproducible images from Phases 0
  through 7. Compose precedes Helm.
- Phase 9 starts only after Phases 2 through 8 pass their exit gates.
- Phase 10 data collection begins during Phase 8 and continues through Phase 9.

## Release blockers

Do not open cloud access to paying users while any cloud blocker below remains
unresolved.

- All eight stems must pass Phase 2.
- Modal authentication must fail closed, and no credential can reach an
  untrusted origin.
- Authentication and tenant isolation must pass review.
- PostgreSQL must be the sole durable job authority.
- The production API must run through the FastAPI contract with no hidden Flask
  or synchronous GPU path.
- Jobs and artifacts must remain durable across process restarts.
- Private object storage and signed artifact delivery must be active.
- Upload limits, complete deletion, and provider lifecycle rules must be proven.
- Usage accounting and GPU spend controls must reconcile exactly.
- Terms, privacy, rights confirmation, and takedown handling must be published.
- Production monitoring, alerts, runbooks, backups, and restore tests must pass.
- Load and fault tests must meet the approved capacity assumptions.
- Support and admin workflows must resolve common failures safely.
- No unresolved critical or high security finding can exist.
- The release must come from immutable, scanned, signed, reproducible artifacts.

Do not publish the self-hosted edition as stable while any self-hosted blocker
below remains unresolved.

- The cloud and self-hosted editions must pass the same stem-quality gates.
- A clean Compose installation must complete the full golden path.
- Local CUDA, local storage, generic S3, local identity, and OIDC contracts must
  pass their supported configuration tests.
- Model licenses, redistribution rules, checksums, and acceptance flows must be
  complete.
- Install, upgrade, rollback, backup, restore, deletion, and offline behavior
  must pass from the published artifacts.
- Telemetry must be opt-in, and cloud billing or credentials must not be
  required.
- The supported hardware and software matrix must be truthful and documented.

## Evidence register

Add evidence as phases complete. A task without evidence remains incomplete.

| Evidence | Status | Location |
| --- | --- | --- |
| Automated project suite | Available | `tests/` |
| Hierarchical 12-stem product contract | Available | `models/product_12_stem_contract.yaml` |
| Legacy eight-stem evaluation contract | Available | `splitter/stem_contract.py` |
| GPU worker contract | Available | `../architecture/GPU_WORKER_CONTRACT.md` |
| Production architecture | Available | `../architecture/PRODUCTION_ARCHITECTURE.md` |
| Production web application | Implemented, not release-complete | `frontend/` |
| Frontend design source | Available | `https://www.figma.com/design/QsLAJ4yc2UB3HvUQdXsVyw` |
| Production process images | Defined, build not verified locally | `Dockerfile` |
| Lifecycle implementation | Live recovery and retry drills passed | `benchmarks/reliability/managed-recovery-drills-2026-07-19.json` |
| Object media-path contract | Deployed experimentally | `splitter/object_storage.py` |
| Model registry | Available | `models/registry.yaml` |
| Full API-to-Modal golden-path report | Partial | `benchmarks/gpu_bakeoff/parallel-b2-api-golden-path-v1/` |
| FastAPI-to-RQ-to-Modal Booty2 report | Completed; quality qualification remains rejected | `benchmarks/golden_path/booty2-fastapi-rq-modal-b2-2026-07-26.json` |
| Frozen 30-song launch corpus | Available | `benchmarks/corpus/release-30-v1.json` |
| Per-stem benchmark scorecard | Early rejection after nine valid songs | `benchmarks/results/release-30-l4-l4-v1-scorecard.json` |
| Blind listening report | Missing | `benchmarks/listening/` |
| Commercial comparator report | Partial | `benchmarks/external_stems/` |
| Model and dataset license report | Partial | Repository planning documents |
| Load-test report | Local baseline available | `benchmarks/load/` |
| Security review and penetration test | Missing | Private data room |
| Backup-and-restore report | Missing | Operations evidence |
| Unit-economics model | Pilot estimate available | `benchmarks/gpu_bakeoff/` |
| Beta KPI and retention dashboard | Missing | Product analytics |
| Incident history and reliability report | Missing | Operations evidence |
| July 25 multi-role architecture audit | Findings captured, remediation open | This plan |
| Platform reference implementation map | Available | `../architecture/PLATFORM_REFERENCE_IMPLEMENTATION_MAP.md` |
| Mature FastAPI source audit | Available | `../architecture/PLATFORM_REFERENCE_IMPLEMENTATION_MAP.md` |
| FastAPI and generated-client contract | Implemented; browser E2E still open | `splitter/api/`, `frontend/src/api/` |
| Hatchet deterministic adoption proof | Passed; real server campaign blocked by missing Docker | `benchmarks/hatchet/` |
| Canonical model-release registry | Missing | Database and release artifacts |
| Cloud 100-job failure campaign | Missing | `benchmarks/reliability/` |
| Self-hosted Compose acceptance report | Missing | `benchmarks/self_hosted/` |
| Signed software and model manifest | Missing | Release artifacts |
| Subjective listening and MOS calibration | Missing | `benchmarks/listening/` |

## Decision log

Record decisions that change scope, vendors, release gates, pricing, retention,
or architecture. Include the reason and reversal condition.

| Date | Decision | Reason | Reversal condition |
| --- | --- | --- | --- |
| July 17, 2026 | Plan for 2,000 monthly active users as the first scale milestone. | This is large enough to expose operating and retention weaknesses without pretending to match incumbent scale. | Superseded on July 25 by the 50,000-user scale-ready engineering target. |
| July 17, 2026 | Keep the production claim at eight stems. | Additional candidates do not yet have complete quality evidence. | Expand only after the same Phase 2 gate passes for each new stem. |
| July 17, 2026 | Keep Modal as the GPU execution layer. | It is already integrated and avoids premature infrastructure migration. | Reconsider when measured cost, latency, capacity, or reliability misses an approved target. |
| July 17, 2026 | Use Audius only for explicitly importable licenses. | Playback availability does not grant derivative-work permission. | Expand through a reviewed licensing agreement or another rights-cleared provider. |
| July 18, 2026 | Keep media bytes out of the production API and finalize artifacts in the Modal worker. | The measured prototype spent more time moving and repackaging outputs than running model inference. | Reconsider only if measured direct storage is slower, less reliable, or materially more expensive. |
| July 18, 2026 | Use Backblaze B2 as the initial private object store. | The first 10 GB is always free without a billing method, account caps can prevent charges, and its S3-compatible API fits the storage adapter. | Reconsider when measured latency, reliability, or the 10 GB cap blocks the beta workload. |
| July 18, 2026 | Create the ZIP in the CPU orchestrator after GPU branches finish. | WAV compression wasted GPU time, but the product contract still requires one downloadable bundle. | Move to on-demand bundling if measured ZIP latency or duplicate storage exceeds the approved budget. |
| July 18, 2026 | Require actual Modal billing reconciliation before pricing. | Public base-rate estimates understated isolated app-interval spend because they excluded the execution multiplier and cold start. | Replace interval attribution with per-job provider billing if Modal exposes it. |
| July 18, 2026 | Keep heterogeneous parallel execution isolated from production. | The best pilot preserved quality and reduced worker latency to 73.898 seconds, but it missed the 60-second gate. | Promote only after the same frozen excerpt completes in 60 seconds or less without a quality regression or unacceptable billed cost. |
| July 18, 2026 | Keep the volume-free B2 worker isolated after its first successful run. | It completed all eight stems but required 112.322 worker seconds on the cold path. | Promote only after the quality, warm-latency, billing, ZIP, and cleanup gates pass. |
| July 19, 2026 | Keep Flask and harden lifecycle guarantees at their owning boundaries. | Changing web frameworks would not improve model quality, GPU latency, or durability. | Superseded on July 25 after the product expanded to typed cloud and self-hosted contracts. |
| July 19, 2026 | Use Supabase for PostgreSQL and JWT identity, and Upstash native TLS Redis for RQ. | The providers fit the existing control-plane contracts and completed live migration, queue, lease, and token probes. | Reconsider if recovery drills, cost, latency, or operational limits fail the beta gate. |
| July 19, 2026 | Use the Modal jobs Volume for parallel branch exchange and B2 only at the external media boundary. | The B2-intermediate design amplified downloads and failed during the release run; the corrected warm path completed in 23.524 seconds. | Reconsider if concurrent Volume consistency or measured latency fails under load. |
| July 24, 2026 | Use one hierarchical 12-stem product contract. | Six stems have selected delivery models; piano, acoustic guitar, electric guitar, synth, strings, and wind remain pending after SAM Audio failed the piano ground-truth gate. | Select new specialist candidates and promote each stem only after ground-truth metrics, blind listening, stereo review, latency, and cost gates pass. |
| July 24, 2026 | Serve the React and Vite client through Flask in one API image. | This preserves one same-origin product deployment while RQ and maintenance run as separate processes. | Split web hosting only if measured deployment, caching, or scaling limits require it. |
| July 25, 2026 | Ship cloud and self-hosted editions from one shared core through provider adapters. | Users need both managed signup and private operation without two products drifting apart. | Split only if a documented platform constraint cannot be represented by an adapter. |
| July 25, 2026 | Make PostgreSQL the sole durable authority and treat queues and GPU workers as execution infrastructure. | The audit found overlapping authorities that can retry, cancel, and complete the same logical job differently. | Replace PostgreSQL only through a new recorded architecture decision and migration proof. |
| July 25, 2026 | Keep RQ only as the initial transport, not permanent job authority. | A framework rewrite does not fix ownership; transactional dispatch and idempotent completion do. | Replace RQ when measured scale, workflow complexity, or reliability justifies another transport or workflow engine. |
| July 25, 2026 | Require objective and trained-listener evidence for model promotion. | Public model metrics can disagree with perceived musical usefulness. | No reversal; thresholds can change only through saved evidence. |
| July 25, 2026 | Require Docker Compose before Kubernetes or Helm for self-hosting. | Compose proves the portable service contract with less operational surface. | Start Helm earlier only for a committed customer whose requirements justify it. |
| July 25, 2026 | Build the difficult-to-change core for a modeled 50,000 monthly active users before unsupervised access. | The repository must demonstrate serious scale engineering while avoiding ornamental infrastructure. | Revise workload numbers with observed traffic, but preserve the authority, idempotency, security, and contract boundaries. |
| July 25, 2026 | Replace Flask with FastAPI while preserving Python domain services. | The current API manually duplicates validation and frontend types and lacks an ASGI, OpenAPI-first transport boundary. | Reverse only if the contract migration fails measured correctness, operability, or performance gates. |
| July 26, 2026 | Use Cloudflare Pages and edge controls for the web client, Azure Container Apps for FastAPI, RQ, and maintenance, and retain Supabase, Upstash, B2, and Modal for their existing responsibilities. This supersedes the July 24 single-image web decision. | Static web delivery and edge protection scale independently from persistent Python services, while retaining the already integrated database, queue, object-store, identity, and GPU providers avoids an unnecessary migration. | Reconsider only when measured cost, reliability, latency, capacity, or operational complexity misses an approved target. |
| July 26, 2026 | Defer implementation of the locked cloud topology until electric-guitar, strings, and wind/brass production candidates complete their first qualification gate. | The current execution focus is closing the three remaining specialist model and dataset gaps without losing the exact return path for the user-facing product. | Resume platform work immediately if model work becomes blocked or if a supervised user test requires a secure cloud environment. |

## Discovery log

Add newly discovered work here before assigning it to a phase.

| Date | Phase | Discovery | Action |
| --- | --- | --- | --- |
| July 17, 2026 | All | The current backend lacks durable multi-user state, configured private object storage, billing, and a production UI. | Added Phases 3 through 7. |
| July 18, 2026 | Phase 4 | The object data-plane contract is implemented, but Redis, RQ, PostgreSQL, leases, and reconciliation remain absent. | Verify the object path first, then migrate the control plane without changing the media contract. |
| July 18, 2026 | Phase 2 | The 60-second BabySlakh pilot scored bass at 15.23 SI-SDR, drums at 14.33, guitar at 8.40, and piano at 1.90. | Treat piano as weak, retain the other results as pilot evidence only, and expand ground-truth coverage before release claims. |
| July 18, 2026 | Phase 5 | T4 completed the pilot in 90.75 seconds and L4 in 78.36 seconds; neither met the 60-second gate. | Test concurrent model execution before paying for more sequential GPU candidates. |
| July 18, 2026 | Phase 5 | Parallel L4 branches reduced publishing to 2.181 seconds, but concurrent model runs expanded to about 60 seconds each and total worker time remained 73.898 seconds. | Stop paid architecture runs until profiling explains the concurrent inference slowdown; do not promote the candidate. |
| July 18, 2026 | Phase 5 | A release-ineligible 10-second diagnostic measured only 3.8-4.9% average GPU utilization, about 6% active GPU samples, and 15-17 seconds of shared-volume reload time per branch. | Build a volume-free branch contract and optimize the CPU-driven MDXC loop before another full pilot. |
| July 18, 2026 | Phase 5 | The diagnostic exceeded its assumption-based cost ceiling because the runner could not cancel remote work. | Deployed a common worker deadline that cancels outstanding Modal branch calls when an explicit budget is reached. |
| July 17, 2026 | Phase 9 | LALAL.AI reported about 6.79 million registered users at the end of 2025. | Treat 50,000 users as a serious target, not competitor parity. |
| July 18, 2026 | Phase 4 | PostgreSQL, RQ, JWT, idempotency, lease, cancellation, reconciliation, health, and metrics adapters now exist, but managed providers are not configured. | Keep tasks open until migrations and failure drills pass against real services. |
| July 19, 2026 | Phase 4 | Atomic admission, renewable leases, truthful cancellation, event polling, terminal deletion, and expiry sweeping now exist in code. | Activate managed services, schedule retention, and run race and recovery drills before promotion. |
| July 19, 2026 | Phase 4 | Supabase PostgreSQL and JWT plus Upstash Redis and RQ passed live migration, queue, lease, cancellation, and token probes. | Run cross-tenant, race, crash-recovery, restore, and retention drills before promotion. |
| July 19, 2026 | Phase 4 | Managed worker-crash, bounded-retry, expired-lease, and orphan-reconciliation drills passed without duplicate Modal dispatch. | Keep restore and cross-tenant cancellation-race drills open. |
| July 19, 2026 | Phase 2 | Nine valid release-corpus songs produced strong bass and drums but rejected guitar and weak piano evidence. | Stop the remaining paid run and replace the guitar and piano model paths before restarting qualification. |
| July 19, 2026 | Phase 5 | The corrected shared-Volume warm path completed a 60-second excerpt in 23.524 worker seconds at an estimated base GPU cost of $0.004789. | Reconcile the closed Modal billing interval before pricing. |
| July 18, 2026 | Phase 5 | The volume-free B2 run published the complete eight-stem contract in 112.322 worker seconds at an estimated base GPU cost of $0.02893. | Preserve the evidence, reject the latency gate, and avoid another paid run until deterministic runtime work is ready. |
| July 24, 2026 | Phase 2 | `facebook/sam-audio-large` access was approved, and the pinned 8.25-billion-parameter checkpoint loaded successfully on a Modal A100 80 GB at 48 kHz. | Keep all six SAM outputs out of the public artifact contract until ground-truth metrics, blind listening, stereo review, latency, and cost qualification finish. |
| July 24, 2026 | Phase 2 | SAM Audio's official eight-candidate text protocol scored piano at -5.33 dB SI-SDR on the frozen 10-second BabySlakh excerpt; the existing separator scored 2.99 dB on the same audio. | Reject SAM as the shared six-stem production path, stop further SAM GPU qualification, and select stem-specific candidates for the six pending stems. |
| July 24, 2026 | Phase 7 | API, queue-worker, maintenance-worker, and migration image targets are defined, but Docker or Podman is not installed on the development machine. | Build, scan, and run all targets in CI before marking `P7-02` complete. |
| July 25, 2026 | Phase 4 | Phase 4 implementation overlaps PostgreSQL, RQ, API polling, leases, reconciliation, and Modal JSON state. | Reopen production readiness and implement one authority, outbox dispatch, immutable attempts, and signed completion. |
| July 25, 2026 | Phase 6 | Modal authentication can fail open, and worker-supplied absolute URLs can receive bearer credentials. | Block public deployment until authentication fails closed and all credential-bearing origins are allowlisted. |
| July 25, 2026 | Phases 4, 7, and 8S | AudioMuse-AI demonstrates useful canonical identity, queue-priority, setup, packaging, and supply-chain patterns. | Add those patterns without copying its Redis authority or shared plugin-volume assumptions. |
| July 25, 2026 | Phase 3 | ACE-Step UI demonstrates refresh-safe jobs, queue progress, project history, and professional audio auditioning. | Treat these as core product workflow, not optional visual polish. |
| July 25, 2026 | Phase 2 | OpenMusic documents disagreement between objective metrics and subjective musicality. | Add MOS calibration and multi-objective model release cards without copying its research-demo deployment. |
| July 25, 2026 | Phase 0 | Dify, Hatchet, OpenMeter, MLflow, InvokeAI, and CVAT cover most risky platform boundaries. Dify is license-restricted for multi-tenant reuse; Hatchet is an MIT-licensed durable-workflow candidate. | Run the Hatchet proof first, adopt MLflow selectively, adapt Apache or MIT patterns, and keep restricted repositories read-only. |
| July 25, 2026 | Phase 4 | Onyx, Prefect, InvokeAI, and the official template demonstrate mature FastAPI patterns across cloud, orchestration, local GPU, OpenAPI clients, testing, and deployment. | Migrate only the HTTP transport, preserve domain services, and remove Flask after parity passes. |
| July 26, 2026 | Phase 4 | FastAPI, Pydantic, generated OpenAPI TypeScript bindings, and Uvicorn replace the Flask/Gunicorn transport. The synchronous separation route is removed. | Reverse only if measured ASGI correctness or operability regresses after production-like load and browser E2E tests. |
| July 26, 2026 | Phase 0 | Keep RQ while Hatchet remains on conditional hold. The deterministic product ledger passed 9/9 checks, but no real server campaign ran because Docker is unavailable. | Adopt Hatchet only after real priority, concurrency, cancellation, retry, crash-recovery, and duplicate-effect gates pass repeatedly. |

## Measured pilot evidence

The first cost-quality pilot is saved under `benchmarks/gpu_bakeoff/`. It is a
screening result, not a release benchmark, because only one of three frozen
songs has ground truth and only four of eight product stems are objectively
scorable in that track.

- The frozen pilot corpus contains three hashed 60-second excerpts and is
  explicitly marked `release_claim_eligible: false`.
- T4 used 90.753 worker seconds and an estimated base GPU cost of $0.014883.
- L4 used 78.363 worker seconds and an estimated base GPU cost of $0.017397.
- T4 and L4 produced identical ground-truth scores within the saved precision.
- The first L4 plus T4 parallel pilot completed in 88.998 worker seconds at an
  estimated base GPU cost of $0.024627.
- The optimized L4 plus L4 pilot completed in 73.898 worker seconds at an
  estimated base GPU cost of $0.027518.
- Parallel object publishing reduced publication from 13.382 seconds to 2.181
  seconds.
- Every candidate published the same eight-stem contract and produced identical
  ground-truth scores within the saved precision.
- The 10-second profiling diagnostic is explicitly marked
  `release_claim_eligible: false` and cannot support product quality claims.
- The diagnostic measured 3.819-4.884% average GPU utilization and only
  5.78-6.04% active GPU samples. Separation CPU time was 93% of wall time,
  which indicates an effectively single-core Python execution path.
- Concurrent shared-volume reloads consumed 14.907 and 16.639 seconds before
  model work, while volume commits consumed another 0.846 and 4.104 seconds.
- Source review of `audio-separator==0.44.3` confirmed that MDXC processes
  chunks in Python, transfers each prediction to CPU, performs overlap-add on
  CPU, and writes every generated stem before the product contract rejects
  unused outputs.
- Eager bundle time and bundle storage were both zero after ZIP deferral.
- Preliminary isolated app-interval billing is attached to each report and
  must be reconciled again after the billing interval closes.
- The first volume-free B2 run completed all eight stems with no missing
  features. It used 112.322 worker seconds, 97.033 parallel-wait seconds,
  8.410 object-publication seconds, and an estimated base GPU cost of $0.02893.
- The B2 run proves the object-reference path, but it fails the 60-second gate.
- The historical local Gunicorn baseline completed 200 of 200 requests at
  169.876 requests per second with 154.366 ms p95 latency. It is superseded as
  a runtime baseline; an equivalent Uvicorn load report is still required.
- The FastAPI migration passed all 116 tests in bounded shards: 109 passed and
  seven optional network tests skipped. A monolithic run exceeds the current
  machine's native-library memory budget, so CI must run bounded shards.
- The React production bundle compiles against generated OpenAPI bindings.

## Current resume checkpoint

Resume with the first incomplete task on the critical path. As of July 26,
2026, useful B2, Modal, PostgreSQL, RQ, JWT, lifecycle, frontend, and benchmark
foundations exist, but the audit invalidated the production-readiness
assumption. Modal authentication and outbound credential handling are release
blockers. Job authority remains split, the model registry is not enforceable,
complete deletion is unproven, and the eight-stem release candidate is rejected
because the corpus stopped after nine valid songs with bad guitar and weak
piano evidence.

The founder-selected execution order is currently:

1. Assemble rights-cleared corpora and train or qualify electric guitar,
   strings, and wind/brass production candidates.
2. Return to Phase 7 at `P7-24` and implement the locked Cloudflare and Azure
   topology through `P7-33`.
3. Continue the remaining user, billing, security, reliability, and rollout
   gates before external unsupervised access.

The platform return checkpoint is satisfied only when all three specialist
candidate runs have immutable dataset manifests, reproducible checkpoints, and
initial objective and listening results. A blocked or failed candidate also
satisfies the checkpoint when its evidence and next decision are recorded; the
platform work must not disappear behind indefinite model research.

Keep specialist training within an approved fixed budget. Do not expose paying
users or call the self-hosted edition stable until the relevant gates in this
plan pass. Preserve working foundations, but refactor their ownership
boundaries before adding another orchestration layer.

## Next steps

Execute the remaining work as one coordinated scale-ready program:

1. Freeze `P0-11` through `P0-17`, run the real `P0-19B` Hatchet campaign when
   Docker is available, and keep RQ until that evidence exists.
2. Run the control-plane, execution, data-plane, ML, product, platform,
   distribution, and verification workstreams in parallel.
3. Integrate continuously through versioned contracts and one release
   candidate instead of merging separate cloud and self-hosted products later.
4. Block external unsupervised access until the Gate B security, authority,
   lifecycle, recovery, and capacity evidence passes.
5. Continue supervised Gate A creator testing without treating it as
   production evidence.
6. Pass Gate C and Gate D independently, then roll out through Phase 9 while
   collecting the operating and Series A evidence in Phase 10.

# Platform reference implementation map

This document maps each high-risk platform boundary to a current, proven
open-source implementation. It reduces design risk and implementation time
without turning the product into an unmaintainable collection of copied code.

Audit date: July 25, 2026.

## Decision

Use a reference portfolio instead of searching for one repository that matches
the whole product:

- Keep Hatchet on conditional hold as the durable workflow candidate until its
  real server campaign passes; continue using RQ in production meanwhile.
- Use Onyx as the primary cloud FastAPI structure reference.
- Use Prefect as the FastAPI orchestration and state-transition reference.
- Use the official FastAPI full-stack template for the API, authentication,
  OpenAPI client, test, and deployment baseline.
- Use MLflow for model evaluation tracking and release-registry workflows.
- Adapt OpenMeter's ledger, entitlement, and reconciliation invariants to the
  existing PostgreSQL control plane.
- Adapt InvokeAI's model installation, metadata, integrity, and cache patterns
  to audio checkpoints.
- Use Dify as a read-only deployment and operations reference.
- Use CVAT as a read-only large-media lifecycle and asynchronous-job reference.
- Keep the existing audio-specific references in
  `../research/OPEN_SOURCE_REPO_DUE_DILIGENCE_2026.md`.

No repository proves our audio quality, Modal integration, tenant contract, or
50,000-user capacity. Those remain project-owned acceptance gates.

## Reuse rules

Every imported dependency or adapted pattern must satisfy these rules:

- Pin the audited source commit and record its license.
- Prefer a maintained dependency over copied internal code.
- Copy code only when the license permits it and attribution is preserved.
- Never copy a data model or queue contract without mapping it to our product
  invariants.
- Add a project-owned contract test before replacing an existing boundary.
- Keep PostgreSQL as product authority even when an external workflow engine
  owns execution history.
- Reject any dependency that prevents both cloud and self-hosted distribution.
- Record the adoption decision and reversal condition in an ADR.

## Reference matrix

| Boundary | Primary reference | Commit | License | Decision |
| --- | --- | --- | --- | --- |
| Cloud FastAPI application | [Onyx](https://github.com/onyx-dot-app/onyx) | `c6a758d` | MIT outside `ee/`; enterprise license inside `ee/` | Primary structure reference |
| FastAPI orchestration server | [Prefect](https://github.com/PrefectHQ/prefect) | `d2d873b` | Apache 2.0 | Study state and service patterns |
| FastAPI product baseline | [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) | `5b358ea` | MIT | Adapt directly |
| Full deployment shell | [Dify](https://github.com/langgenius/dify) | `5aa2092` | Modified Apache 2.0 with multi-tenant restrictions | Study only |
| Durable workflows | [Hatchet](https://github.com/hatchet-dev/hatchet) | `41b0563` | MIT | Evaluate for adoption |
| Usage and billing | [OpenMeter](https://github.com/openmeterio/openmeter) | `6457e4b` | Apache 2.0 | Adapt invariants |
| Model registry | [MLflow](https://github.com/mlflow/mlflow) | `8a6e8c4` | Apache 2.0 | Adopt selectively |
| Local model manager | [InvokeAI](https://github.com/invoke-ai/InvokeAI) | `68b9017` | Apache 2.0, with separate model licenses | Adapt patterns |
| Media job lifecycle | [CVAT](https://github.com/cvat-ai/cvat) | `4aa0be3` | MIT | Study and contract-test |

## Onyx: mature cloud FastAPI structure

Onyx is the closest mature FastAPI cloud application reference. Its Community
Edition combines FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, specialized
Celery workers, tenant-aware queues, OAuth, React and Next.js, Docker,
monitoring, and extensive production conventions.

Study these boundaries:

- `backend/onyx/main.py` for application creation, middleware, router
  registration, startup, and exception handling.
- `backend/onyx/server/` for domain-oriented routers and dependency injection.
- `backend/onyx/db/` for keeping database access behind one module boundary.
- `backend/onyx/background/celery/` for specialized worker applications,
  priorities, task expiry, monitoring, and liveness.
- `deployment/` for cloud and self-hosted service composition.

Adapt these practices:

- Keep routers grouped by product domain instead of one API module.
- Keep request models, domain services, persistence, and worker tasks separate.
- Use stable machine-readable application errors and global exception handling.
- Require tenant context and authorization at the dependency boundary.
- Give every queued task an expiry, ownership context, and monitoring signal.
- Keep heavy, light, scheduled, and monitoring work isolated.

Do not copy anything under an `ee/` directory without a separate license
decision. Do not import Onyx's search, connector, Vespa, LLM, or
enterprise-auth complexity.

## Prefect: mature FastAPI orchestration patterns

Prefect is an Apache-licensed, self-hosted and cloud workflow platform with a
large FastAPI server, PostgreSQL state, SQLAlchemy, Alembic migrations,
workers, concurrency limits, events, cleanup, scheduling, and reconciliation.

Study these files:

- `src/prefect/server/api/server.py` for modular FastAPI assembly.
- `src/prefect/server/api/dependencies.py` for request dependencies.
- `src/prefect/server/orchestration/` for explicit transition policies and
  rules.
- `src/prefect/server/database/interface.py` and
  `src/prefect/server/database/dependencies.py` for database abstraction.
- `src/prefect/server/models/` for service-layer persistence.
- `src/prefect/server/services/` for scheduler, cleanup, cancellation, and
  reconciliation services.
- `src/prefect/server/events/` for durable event handling.

Do not adopt Prefect as another workflow engine while Hatchet remains under
evaluation. Use Prefect to validate state-machine, service, event, migration,
and API patterns.

## Official FastAPI full-stack template

The official MIT-licensed template supplies a clean starting point for the
transport and product shell:

- `backend/app/main.py` for app construction.
- `backend/app/api/main.py` and `backend/app/api/routes/` for router structure.
- `backend/app/api/deps.py` for authentication and database dependencies.
- `backend/app/core/` for settings, security, and database configuration.
- `backend/tests/` for API and persistence tests.
- `frontend/src/client/` for the generated OpenAPI TypeScript client.
- `frontend/tests/` for Playwright authentication and product flows.
- `compose.yml` and `.github/` for development, deployment, and CI.

Adapt the structure and tooling, not its generic item domain or simplistic
authorization model. Use SQLAlchemy and Alembic directly where the current
control-plane schema needs features beyond SQLModel.

## Dify: deployment and operations shell

Dify is the closest stack-level reference. It combines Flask, PostgreSQL,
Redis and Celery workers, pluggable object storage, a web application, Docker
Compose, cloud and self-hosted editions, migrations, OpenTelemetry, health
checks, and SSRF isolation.

Study these files:

- `docker/docker-compose.yaml` for API, worker, scheduler, web, database, Redis,
  health-check, and network composition.
- `api/extensions/storage/base_storage.py` and
  `api/extensions/ext_storage.py` for storage-provider boundaries.
- `api/extensions/otel/` for application and worker tracing.
- `api/libs/db_migration_lock.py` for migration serialization.
- `api/celery_healthcheck.py` for worker readiness.
- `docker/ssrf_proxy/` for outbound-network isolation.
- `api/migrations/` and release notes for upgrade discipline.

Do not copy Dify source into this product. Its current license requires
authorization for operating its source as a multi-tenant service and restricts
frontend reuse. Reimplement only the architectural patterns behind our own
interfaces and tests.

## Hatchet: durable workflow candidate

Hatchet is the highest-leverage adoption candidate. It provides a
PostgreSQL-backed durable queue, Python workers, retries, timeouts, scheduling,
concurrency controls, fairness, rate limits, progress history, observability,
cloud hosting, and self-hosting.

Inspect these files:

- `pkg/repository/scheduler_queue.go` for queue scheduling.
- `pkg/repository/scheduler_lease.go` for scheduler ownership.
- `pkg/repository/rate_limit.go` for rate-limit persistence.
- `pkg/scheduling/v1/concurrency/` for concurrency and fairness strategies.
- `internal/msgqueue/postgres/msgqueue.go` for PostgreSQL messaging.
- `api-contracts/` for versioned worker and workflow contracts.

Run a bounded adoption proof before implementing more custom RQ lifecycle code.
The proof must demonstrate:

- One product job maps to immutable Hatchet workflow and attempt identifiers.
- A PostgreSQL outbox can trigger Hatchet idempotently.
- Preview, quality, recovery, and maintenance priorities remain isolated.
- Per-tenant concurrency and rate limits work.
- Worker termination, timeout, retry, and cancellation preserve product state.
- Modal dispatch and authenticated completion work without blocking an API
  request.
- Callback replay cannot duplicate artifacts, usage, billing, or terminal
  transitions.
- One hundred fault-injected jobs create zero duplicate economic effects.
- Docker Compose supports the same workflow contract for self-hosting.

The deterministic ledger and SDK proof passed on July 26, 2026, but Docker was
unavailable, so the real server campaign did not run. Keep RQ until Hatchet
proves priority ordering, concurrency enforcement, in-flight cancellation,
worker-crash reassignment, bounded server retries, and zero duplicate product
effects. Hatchet never becomes the authority for accounts, billing, artifacts,
or the public job record.

## OpenMeter: usage and billing invariants

OpenMeter provides production patterns for usage events, meters,
subscriptions, entitlements, prepaid credits, Stripe integration, customer
portals, and threshold notifications.

Study these files:

- `openmeter/ledger/` for immutable financial entries.
- `openmeter/credit/` for grants, balances, burn order, and resets.
- `openmeter/subscription/entitlement/` for feature access.
- `openmeter/app/stripe/` for Stripe mapping and webhook handling.
- `api/openapi.yaml` for API-first usage contracts.

Do not deploy OpenMeter's Kafka and ClickHouse architecture for the initial
100,000-job monthly envelope. It solves a much higher event-ingestion problem
and would add unnecessary operations. Adapt these invariants in PostgreSQL:

- Every event has a stable idempotency identity.
- Reservations, consumption, release, refund, and adjustment are separate
  append-only entries.
- Balances are derived and repairable, not silently overwritten.
- Provider webhooks are verified, replay-safe, and reconciled.
- Every job cost and customer charge traces to immutable source events.

Reconsider the OpenMeter service when measured event volume or billing
complexity exceeds the PostgreSQL implementation.

## MLflow: model and evaluation authority

MLflow provides established experiment tracking, artifact storage, model
versions, tags, aliases, evaluation records, and environment promotion.

Use it for:

- Benchmark runs, parameters, metrics, listener-study summaries, and artifacts.
- Checkpoint source, hash, license, model card, route, and postprocess metadata.
- Candidate, champion, quarantined, and rollback aliases.
- B2 or another S3-compatible artifact backend.
- Promotion evidence across development, staging, and production.

The product database must snapshot the immutable MLflow model-version identity
into each job. Runtime publication must never resolve a mutable alias after a
job starts. Model redistribution rights remain a project-owned release gate.

## InvokeAI: self-hosted model management

InvokeAI is a mature local creative-AI application with FastAPI, a React
interface, routers, custom OpenAPI behavior, event streaming, download queues,
multi-user tests, model management, model metadata, model cache, and a
commercially friendly core license.

Study these files:

- `invokeai/backend/model_manager/README.md` for manager responsibilities.
- `invokeai/backend/model_manager/load/model_loader_registry.py` for loader
  registration.
- `invokeai/backend/model_manager/model_on_disk.py` for installed state.
- `invokeai/backend/model_manager/metadata/` for source metadata.
- `invokeai/backend/model_manager/load/model_cache/` for bounded cache
  behavior and statistics.
- `invokeai/app/api_app.py` for the FastAPI self-hosted application.
- `invokeai/app/services/events/` for API event delivery.
- `tests/app/routers/` for API, download, live-update, and multi-user tests.

Adapt these patterns:

- Download to a temporary location, validate, then atomically install.
- Record source, license, expected size, checksum, architecture, and installed
  state.
- Resume interrupted downloads and report progress.
- Refuse execution when disk, VRAM, CUDA, or checkpoint requirements fail.
- Keep a loader registry separate from the user-visible model release.
- Make cache eviction observable and deterministic.

Do not copy image-model taxonomies, SQLite assumptions, or image-specific
workflow code.

## CVAT: media lifecycle and asynchronous jobs

CVAT is a mature media-heavy web application with PostgreSQL, Redis and RQ,
cloud storage, asynchronous workers, progress reporting, cancellation,
organizations, webhooks, Docker Compose, and extensive integration tests.

Use it to validate:

- Media import and export job boundaries.
- Cloud-storage credentials and object-reference handling.
- Job progress, cancellation, failure, and recovery semantics.
- Organization and ownership tests.
- Large-file and S3 integration fixtures.
- Worker and queue separation in Compose.

Do not copy CVAT's Django models, multiple Redis deployment, ClickHouse
analytics, OPA integration, or domain-specific annotation workflow.

## Existing audio references

Keep the decisions already recorded in
`../research/OPEN_SOURCE_REPO_DUE_DILIGENCE_2026.md`:

- `python-audio-separator` remains the runtime and model-adapter reference.
- StemDeck remains the local lifecycle, cancellation, recovery, streaming, and
  cleanup reference.
- Ultimate Vocal Remover remains the model-configuration and ensemble reference.
- AudioMuse-AI remains the audio-oriented worker, canonical identity,
  priority-queue, setup, packaging, and supply-chain reference.
- ACE-Step UI remains the job-resumption, queue-progress, project-library, and
  creative auditioning reference.

None of these replaces the independent quality benchmark.

## Implementation sequence

Use references to compress the scale-ready program:

1. Build the FastAPI transport from the official template structure.
2. Apply Onyx router, persistence, tenancy, error, and worker boundaries.
3. Validate state and service design against Prefect.
4. Run the Hatchet adoption proof before extending RQ.
5. Freeze project-owned job, attempt, event, artifact, and usage contracts.
6. Implement the Dify-style deployment shell using original project code.
7. Implement storage, tracing, migrations, SSRF controls, and health checks
   against those contracts.
8. Adopt MLflow for benchmark and model-release evidence.
9. Implement the PostgreSQL usage ledger using OpenMeter invariants.
10. Implement the self-hosted model manager using InvokeAI patterns.
11. Port CVAT, Dify, Hatchet, and StemDeck failure scenarios into project-owned
   integration tests.
12. Run the modeled 50,000-user control-plane load and failure campaign.

## Expected schedule effect

This approach can reduce the scale-ready implementation estimate from six to
eight weeks to approximately four to six weeks because it avoids inventing
queue semantics, deployment composition, usage-ledger invariants, model
management, and operational tests from scratch.

It cannot compress the following evidence safely:

- The 30-song stem-quality benchmark.
- Commercial comparator exports.
- Trained producer listening.
- Real Modal cost and concurrency measurements.
- Independent security review.
- Actual operating history at 50,000 users.

## Rejection list

Do not use these projects as direct dependencies for the current product:

- Dify source or frontend, because of its multi-tenant and branding license
  conditions.
- Windmill Community Edition, because its current terms restrict managed
  service and embedded commercial use.
- OpenMeter's Kafka and ClickHouse deployment before measured event volume
  requires it.
- CVAT's complete infrastructure stack, because most of it serves annotation
  and analytics requirements we do not have.
- InvokeAI's application schema, because it models image generation rather than
  audio separation.
- Any repository whose README claims scale without reproducible failure,
  latency, and capacity evidence.

## Exit gate

The reference phase is complete when every adopted boundary has:

- An audited commit and license record.
- An ADR with alternatives and reversal conditions.
- A project-owned interface and acceptance suite.
- A migration plan from the current implementation.
- A working cloud and self-hosted proof.
- No copied restricted code or hidden dependency on another product's cloud.

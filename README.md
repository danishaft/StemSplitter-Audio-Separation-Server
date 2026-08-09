# StemSplitter

StemSplitter is an asynchronous music source-separation platform. A FastAPI
control plane owns jobs, authentication, queueing, and artifacts; remote GPU
workers run model inference; and a Next.js client handles uploads, progress,
audio playback, and downloads.

The current eleven-stem route is an **evaluation profile**, not a
production-quality claim. The platform architecture is usable, but individual
stem families still require benchmark and listening qualification.

## Current contract

The public evaluation profile is `quality_gpu_experimental`. It requests these
outputs:

- `vocals`
- `instrumental`
- `drums`
- `bass`
- `kick`
- `snare`
- `piano`
- `acoustic_guitar`
- `electric_guitar`
- `synth`
- `strings`

`wind` remains disabled. A file's existence doesn't prove separation quality.
The API exposes missing features, rejected candidates, model provenance, and
worker timings in every completed manifest.

## Architecture

The production-shaped path keeps control-plane work off the GPU and audio bytes
out of PostgreSQL and Redis.

```text
Next.js 16 + OpenNext on Cloudflare Workers/WAF
  -> private presigned upload
  -> Azure Container Apps FastAPI API
  -> PostgreSQL job authority
  -> transactional dispatch outbox
  -> Redis/RQ durable dispatch
  -> Modal GPU worker
  -> private B2/S3 artifacts
  -> signed playback and download URLs
```

The maintenance worker reconciles orphaned jobs and deletes expired artifacts.
Development can use JSON state and a single-process thread dispatcher, but
production configuration rejects those fallbacks.

Read the
[`production architecture`](docs/architecture/PRODUCTION_ARCHITECTURE.md) and
[`repository structure`](docs/architecture/REPOSITORY_STRUCTURE.md) for the
complete component boundaries.

## Repository

The main directories have explicit ownership:

| Path | Responsibility |
| --- | --- |
| `splitter/api/` | FastAPI transport, schemas, middleware, and routes |
| `splitter/application/` | Application use cases and dispatch coordination |
| `splitter/infrastructure/` | PostgreSQL, Redis/RQ, and object storage |
| `splitter/observability/` | Structured logs and request correlation |
| `workers/` | Modal and specialist GPU worker applications |
| `apps/web/` | Next.js App Router web client and edge API gateway |
| `packages/api-client/` | Generated OpenAPI schema and typed browser client |
| `models/` | Model registry and qualification configuration |
| `benchmarks/` | Quality, latency, cost, and reliability evidence |
| `training/` | Training recipes and manifests |
| `datasets/` | Dataset inventories, licenses, and staging metadata |
| `docs/` | Architecture, operations, research, roadmaps, and history |

Research assets don't define product release status. Runtime code reads
machine-readable contracts from `models/`.

## Local development

Install Python 3.12, Node.js 24, pnpm 10, FFmpeg, and libsndfile. Then install
the API and web dependencies:

```bash
python -m venv .venvs/api
.venvs/api/bin/python -m pip install -e '.[dev]'
pnpm install --frozen-lockfile
```

Create `apps/web/.env.local` from `apps/web/.env.production.example`, then set
a real Clerk development publishable key. Copy `apps/web/.dev.vars.example` to
`apps/web/.dev.vars` for local edge-proxy bindings.

Start the single-machine API and web development servers in separate shells:

```bash
VENV_DIR="$PWD/.venvs/api" ./start.sh
pnpm --filter @stemsplitter/web dev
```

This path uses one API process because an in-memory dispatcher cannot safely
coordinate multiple processes.

## Production-shaped local stack

Docker Compose starts PostgreSQL, Redis, migrations, the API, an RQ worker, and
the maintenance worker:

```bash
make compose-up
```

See the
[`local stack runbook`](docs/operations/LOCAL_STACK.md) for configuration and
verification.

## Configuration

Copy `.env.production.example` into a secret-managed environment and replace
every placeholder. Production startup requires:

- PostgreSQL for authoritative job state and execution leases.
- Redis/RQ for durable dispatch and retries.
- Private S3-compatible storage, such as Backblaze B2.
- JWT verification through a managed identity provider.
- Cloudflare origin verification, trusted hosts, and shared rate limits.
- An explicit CORS allowlist.
- A configured GPU worker URL and API key.
- Azure Monitor, generic OpenTelemetry, or Sentry telemetry.

Multipart API uploads are disabled by default in production. Clients first
request `POST /uploads`, upload directly to private storage, and then create a
job using the returned object reference.

## API

The primary routes are:

| Route | Purpose |
| --- | --- |
| `POST /uploads` | Create a principal-scoped private upload grant |
| `POST /jobs` | Create an upload, object, or Audius-backed job |
| `GET /jobs/{job_id}` | Read status, timings, and signed artifacts |
| `GET /jobs/{job_id}/events` | Poll ordered durable job events |
| `POST /jobs/{job_id}/cancel` | Request local and remote cancellation |
| `POST /jobs/{job_id}/resume` | Resume a recoverable remote job |
| `DELETE /jobs/{job_id}` | Delete a terminal job and its artifacts |
| `GET /capabilities` | Read profiles, contracts, inputs, and warnings |
| `GET /health/live` | Check process liveness |
| `GET /health/ready` | Check PostgreSQL, Redis, and object storage |
| `GET /metrics` | Export Prometheus metrics |

The OpenAPI document generates the TypeScript client in
`packages/api-client/src/`.

## Verification

Run backend and frontend checks through the canonical command surface:

```bash
make test
make frontend
```

Regenerate the API contract after schema or route changes:

```bash
make openapi
```

CI runs the backend suite, frontend build, API container build, Bicep and
Terraform validation, Worker dry-run, CodeQL, dependency review, and Trivy.

The Expo mobile client remains planned work. It is not part of the current
release artifact.

## Known limits

The architecture and model quality have separate release gates.

- The eleven-stem profile remains evaluation-only.
- `synth` currently has known bleed on the Channel evaluation run.
- Silent specialist outputs can represent instrument absence or model failure;
  presence detection and quality qualification remain future ML work.
- The complete 30-song ground-truth quality benchmark is unfinished.
- Local JSON and thread adapters are development-only.
- Production infrastructure is defined but still requires account credentials,
  provider deployment, recovery drills, load evidence, and operating history.

Research decisions and executed work are preserved in
[`docs/history/STEM_SPLITTER_ENGINEERING_LOG.md`](docs/history/STEM_SPLITTER_ENGINEERING_LOG.md).

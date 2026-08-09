# Repository structure

StemSplitter uses a service-oriented Python repository with a Next.js web
client and separately deployed GPU workers. The control plane owns jobs and
artifacts; model processes only implement the worker contract.

## Runtime code

The `splitter/` package contains code shipped in the API and queue-worker
images.

| Path | Responsibility |
| --- | --- |
| `splitter/api/` | FastAPI transport, schemas, middleware, and route handlers |
| `splitter/application/` | Use-case coordination across persistence, queues, and jobs |
| `splitter/infrastructure/` | PostgreSQL, Redis/RQ, and object-storage adapters |
| `splitter/observability/` | Structured logging and request correlation |
| `splitter/sources/` | External catalog adapters, including Audius |
| `splitter/jobs.py` | Queue execution and separation-pipeline orchestration |
| `splitter/stem_contract.py` | Product artifact selection and hierarchy rules |
| `splitter/config.py` | Environment-derived runtime configuration |
| `splitter/bootstrap.py` | Process-local dependency construction and shutdown |

The root `splitter/job_store.py`, `splitter/dispatch.py`, and
`splitter/object_storage.py` modules are compatibility façades. New production
code imports adapters from `splitter/infrastructure/`.

## Applications and workers

The API and web client have different build and deployment lifecycles.

| Path | Responsibility |
| --- | --- |
| `audio_api.py` | ASGI compatibility entrypoint |
| `apps/web/` | Next.js App Router application and Cloudflare edge gateway |
| `packages/api-client/` | Generated OpenAPI schema and typed client package |
| `workers/` | Modal and remote GPU worker applications |
| `scripts/run_api.py` | API process entrypoint |
| `scripts/run_rq_worker.py` | Durable queue-worker entrypoint |
| `scripts/run_maintenance_worker.py` | Reconciliation and retention worker |

The API never imports model checkpoints. GPU workers receive an input reference
and return immutable artifact references through the documented worker
contract.

## Research and evidence

Research assets don't define production release status.

| Path | Responsibility |
| --- | --- |
| `models/` | Model registry, architecture configuration, and qualification state |
| `training/` | Training recipes, manifests, and generated training inputs |
| `datasets/` | Dataset inventories, licenses, manifests, and local staging |
| `benchmarks/` | Immutable fixtures, results, and external comparisons |
| `research/` | Research workbench code and run metadata |
| `notebooks/` | Interactive research interfaces |
| `experiments/` | Isolated proofs that aren't part of the runtime |

Generated audio, model caches, virtual environments, and experiment runs are
excluded through `.gitignore`.

## Deployment and operations

Deployment files remain at the repository root because they describe the whole
system.

| Path | Responsibility |
| --- | --- |
| `pyproject.toml` | Python package, dependencies, and tool configuration |
| `compose.yaml` | Local production-shaped service topology |
| `Dockerfile` | API, queue, maintenance, and migration images |
| `Makefile` | Canonical developer commands |
| `package.json` | pnpm workspace and Turborepo command surface |
| `pnpm-workspace.yaml` | Workspace membership and dependency catalog |
| `migrations/` | Ordered PostgreSQL schema changes |
| `.github/workflows/ci.yml` | Backend, frontend, and image verification |
| `requirements/` | Task-specific Modal, data, and research dependencies |

## Dependency direction

Transport code calls application services. Application services coordinate
runtime orchestration and infrastructure interfaces. Infrastructure adapters
don't import FastAPI, React, or model execution code. GPU workers communicate
through object references and the worker API rather than process-local paths.

This direction keeps model replacement independent from job lifecycle,
authentication, storage, and frontend behavior.

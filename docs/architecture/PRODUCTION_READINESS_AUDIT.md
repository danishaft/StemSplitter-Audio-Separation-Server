# Production readiness audit

This audit records the current product boundary for the eight-stem evaluation
build. It separates working architecture from release evidence so hosting work
does not hide unresolved quality or operational risks.

> **Note:** The eight-stem build is usable for controlled artist testing. It is
> not yet a production-qualified commercial release.

## Current stack

The product uses a clear control-plane, data-plane, and execution-plane split.

- React and Vite provide the browser workspace.
- FastAPI and Uvicorn provide the API control plane.
- A Cloudflare Worker serves the React frontend and proxies API requests.
- PostgreSQL stores authoritative job state when `JOB_STORE_BACKEND=postgres`.
- Redis and RQ provide durable dispatch when `JOB_DISPATCH_BACKEND=rq`.
- Modal provides GPU execution and model inference.
- Private S3-compatible storage holds uploads, stems, manifests, and bundles.
- Prometheus-compatible metrics and live/readiness endpoints expose operations.
- Azure Monitor/OpenTelemetry and optional Sentry expose traces and errors.
- The local JSON and thread paths remain development and compatibility paths.

## What is working

The code has the boundaries required for a serious first deployment.

- Direct uploads keep large audio out of the API process.
- Job creation supports idempotency keys, ownership, leases, retries, and
  cancellation states.
- The GPU worker publishes the normalized `quality_8_stems` contract.
- Artifacts are exposed through private signed URLs or local range-capable
  responses.
- The UI can submit uploads or license-approved Audius sources and can inspect
  job progress and artifacts.

## Measured limits

The current evidence is useful for planning but does not support a parity claim.

- The 60-second GPU pilot completes in roughly 78 to 108 seconds end to end,
  depending on the worker topology and warm state.
- Pilot GPU estimates are about $0.017 to $0.025 per audio minute before API,
  storage, queue, and retry overhead.
- The current 30-song release scorecard rejects the eight-stem candidate.
- Specialist model gaps remain separate from the eight-stem product path.

## Required before public production

Complete these gates in order. Do not solve them by adding more specialist
models to the default path.

1. Run the full provider-backed preflight with PostgreSQL, Redis, private
   storage, JWT verification, and the Modal worker enabled.
2. Run cross-tenant ownership, cancellation-race, retry, orphan-recovery, and
   restore drills against the managed services.
3. Schedule expiry cleanup and configure abandoned-upload lifecycle rules.
4. Re-run the frozen quality corpus and blind producer listening review after
   the current release rejection is addressed.
5. Record actual Modal billing and set a price floor above worst-case retries.
6. Promote the eight-stem profile only after the quality and operations gates
   pass; keep specialist lanes explicitly experimental.

## Hosting shape

Deploy the API, RQ worker, and maintenance worker as separate services from the
same image. Run PostgreSQL, Redis, and private S3-compatible storage as managed
services. Deploy the Modal GPU worker separately and connect it through the
authenticated worker URL. Keep the API stateless and let the database remain
the job authority.

The repository contains the image targets, Azure Bicep, Cloudflare Worker and
rules, deployment workflow, dispatch outbox, and startup scripts for this
shape. The remaining platform work is provider activation and live
verification, not a new application architecture.

## Next steps

Finish the UI and artifact delivery cleanup, then run the provider-backed
preflight and one controlled artist test. Return to specialist model research
only after the eight-stem product path has a clean operational baseline.

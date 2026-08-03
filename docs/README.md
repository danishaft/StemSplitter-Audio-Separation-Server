# StemSplitter documentation

This directory separates the production platform design from model research and
historical plans. Start with the production architecture, then use the
operations documents when you deploy or operate the service.

## Architecture

The architecture documents define runtime boundaries and production contracts.

- [`PRODUCTION_ARCHITECTURE.md`](architecture/PRODUCTION_ARCHITECTURE.md)
  defines the control plane, queue, storage, and GPU worker topology.
- [`PRODUCTION_PLATFORM.md`](architecture/PRODUCTION_PLATFORM.md) defines the
  Cloudflare, Azure, recovery, security, and observability implementation.
- [`GPU_WORKER_CONTRACT.md`](architecture/GPU_WORKER_CONTRACT.md) defines the
  remote inference boundary.
- [`PLATFORM_REFERENCE_IMPLEMENTATION_MAP.md`](architecture/PLATFORM_REFERENCE_IMPLEMENTATION_MAP.md)
  records the external engineering references used by the project.
- [`PRODUCTION_READINESS_AUDIT.md`](architecture/PRODUCTION_READINESS_AUDIT.md)
  records known production gaps.
- [`REPOSITORY_STRUCTURE.md`](architecture/REPOSITORY_STRUCTURE.md) defines code
  ownership and dependency direction.

## Roadmaps

The roadmap directory contains delivery plans. The research-to-production
roadmap is the current planning authority; older plans remain available as
historical context.

- [`RESEARCH_TO_PRODUCTION_MASTER_ROADMAP.md`](roadmaps/RESEARCH_TO_PRODUCTION_MASTER_ROADMAP.md)
  is the current end-to-end roadmap.
- [`ROAD_TO_SERIES_A_PLAN.md`](roadmaps/ROAD_TO_SERIES_A_PLAN.md) covers product
  and platform scale.

## Research

The research directory contains model, dataset, licensing, and benchmark
decisions. These documents don't define production release status.

- [`SPECIALIST_MODEL_SELECTION.md`](research/SPECIALIST_MODEL_SELECTION.md)
  records candidate model decisions.
- [`SPECIALIST_DATASET_ACQUISITION_MAP.md`](research/SPECIALIST_DATASET_ACQUISITION_MAP.md)
  records dataset sources and rights.
- [`OPEN_MODEL_AUDIT_2026.md`](research/OPEN_MODEL_AUDIT_2026.md) records the
  open-model audit.

## History

The history directory preserves implementation evidence and superseded
decisions without presenting them as current runtime contracts.

- [`STEM_SPLITTER_ENGINEERING_LOG.md`](history/STEM_SPLITTER_ENGINEERING_LOG.md)
  records executed work, incidents, and evidence.

## Operations

The operations directory contains procedures for running and validating the
platform.

- [`LOCAL_STACK.md`](operations/LOCAL_STACK.md) runs the complete local
  production-shaped service topology.
- [`PRODUCTION_DEPLOYMENT.md`](operations/PRODUCTION_DEPLOYMENT.md) configures
  and deploys the cloud platform.
- [`DISASTER_RECOVERY.md`](operations/DISASTER_RECOVERY.md) verifies backup,
  restore, queue recovery, and object recovery.

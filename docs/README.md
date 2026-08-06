# StemSplitter documentation

This directory separates the production platform design from model research and
historical plans. Start with the production architecture, then use the
operations documents when you deploy or operate the service.

## Product

The product documents define the user promise, scope, workflows, feature
statuses, and release language.

- [`product-blueprint.md`](product/product-blueprint.md) is the authority for
  product positioning, capability pillars, current truth, and future scope.

## Design

The design documents translate the product strategy into reusable visual,
interaction, content, and accessibility rules.

- [`design-system.md`](design/design-system.md) defines the product's art
  direction, tokens, layouts, components, audio interactions, and design gates.
- [`competitive-ui-teardown.md`](design/competitive-ui-teardown.md) records the
  Moises, Fadr, and BandLab interaction patterns behind the active waveform-first
  direction.
- [`moises-ui-ux-case-study.md`](design/moises-ui-ux-case-study.md) records the
  measured Moises surface, typography, depth, media, navigation, product, and
  responsive patterns that gate the V3 redesign.
- [`public-platform-ui-case-studies.md`](design/public-platform-ui-case-studies.md)
  records the public Suno, Fadr, BandLab, and LANDR evidence and defines the
  cross-platform ownership model and acceptance gate for V3.

## Architecture

The architecture documents define runtime boundaries and production contracts.

- [`PRODUCTION_ARCHITECTURE.md`](architecture/PRODUCTION_ARCHITECTURE.md)
  defines the control plane, queue, storage, and GPU worker topology.
- [`PRODUCTION_PLATFORM.md`](architecture/PRODUCTION_PLATFORM.md) defines the
  Cloudflare, Azure, recovery, security, and observability implementation.
- [`ML_PLATFORM_ARCHITECTURE.md`](architecture/ML_PLATFORM_ARCHITECTURE.md)
  defines dataset and feature lineage, reproducible training and evaluation,
  model releases, CPU and GPU scheduling, shadow and canary deployment, and ML
  observability.
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

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

PYTHON ?= .venvs/api/bin/python
PYTEST ?= .venvs/api/bin/pytest
PNPM ?= pnpm

.PHONY: help install test test-fast lint lint-python frontend openapi compose-up compose-down preflight

help:
	@printf '%s\n' \
		"install       Install backend and frontend development dependencies" \
		"test          Run the complete local backend suite" \
		"test-fast     Run tests excluding slow and integration cases" \
		"lint          Run backend static checks and the frontend type checker" \
		"frontend      Build the production Next.js application" \
		"openapi       Regenerate the OpenAPI schema and TypeScript client" \
		"compose-up    Start PostgreSQL, Redis, API, queue, and maintenance" \
		"compose-down  Stop the local production-shaped stack" \
		"preflight     Validate production configuration"

install:
	$(PYTHON) -m pip install -e '.[dev]'
	$(PNPM) install --frozen-lockfile

test:
	$(PYTEST) -q

test-fast:
	$(PYTEST) -q -m 'not slow and not integration'

lint-python:
	$(PYTHON) -m ruff check \
		splitter/api splitter/application splitter/infrastructure \
		splitter/observability splitter/auth.py splitter/bootstrap.py \
		splitter/config.py splitter/gpu_worker_client.py splitter/jobs.py \
		splitter/path_safety.py splitter/runtime.py splitter/util.py \
		workers/audio_separator_gpu_worker.py \
		scripts/apply_migrations.py scripts/backup_postgres.py \
		scripts/production_preflight.py scripts/restore_postgres.py \
		scripts/run_api.py scripts/validate_gpu_registry_alignment.py \
		scripts/run_maintenance_worker.py scripts/run_rq_worker.py \
		tests/test_gpu_worker_api.py tests/test_platform_security.py

lint: lint-python
	$(PNPM) typecheck

frontend:
	$(PNPM) build

openapi:
	$(PYTHON) -m scripts.export_openapi
	$(PNPM) api:generate

compose-up:
	docker compose up --build

compose-down:
	docker compose down

preflight:
	$(PYTHON) -m scripts.production_preflight

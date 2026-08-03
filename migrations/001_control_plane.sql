BEGIN;

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    idempotency_key TEXT,
    profile TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT,
    worker_job_id TEXT,
    payload JSONB NOT NULL,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    attempt INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS jobs_owner_idempotency_key_idx
    ON jobs (owner_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS jobs_status_updated_at_idx
    ON jobs (status, updated_at);

CREATE INDEX IF NOT EXISTS jobs_worker_job_id_idx
    ON jobs (worker_job_id)
    WHERE worker_job_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS job_events_job_created_idx
    ON job_events (job_id, created_at);

COMMIT;

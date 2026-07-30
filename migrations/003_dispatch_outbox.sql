BEGIN;

CREATE TABLE IF NOT EXISTS job_dispatch_outbox (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    dispatch_id TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dispatched_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS job_dispatch_outbox_pending_idx
    ON job_dispatch_outbox (available_at, id)
    WHERE dispatched_at IS NULL;

COMMIT;

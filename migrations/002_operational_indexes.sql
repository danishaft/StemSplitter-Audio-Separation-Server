BEGIN;

CREATE INDEX IF NOT EXISTS jobs_owner_status_updated_idx
    ON jobs (owner_id, status, updated_at);

CREATE INDEX IF NOT EXISTS jobs_active_lease_expiry_idx
    ON jobs (lease_expires_at, updated_at)
    WHERE status IN ('queued', 'running', 'finalizing', 'cancelling');

CREATE INDEX IF NOT EXISTS job_events_job_id_id_idx
    ON job_events (job_id, id);

COMMIT;

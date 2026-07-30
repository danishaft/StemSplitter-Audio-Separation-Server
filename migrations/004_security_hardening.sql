BEGIN;

REVOKE ALL ON TABLE jobs FROM anon, authenticated;
REVOKE ALL ON TABLE job_events FROM anon, authenticated;
REVOKE ALL ON TABLE job_dispatch_outbox FROM anon, authenticated;
REVOKE ALL ON SEQUENCE job_events_id_seq FROM anon, authenticated;
REVOKE ALL ON SEQUENCE job_dispatch_outbox_id_seq FROM anon, authenticated;

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_dispatch_outbox ENABLE ROW LEVEL SECURITY;

COMMIT;

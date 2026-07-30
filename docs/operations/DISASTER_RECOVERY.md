# Disaster recovery

This runbook verifies that job authority and private media can be recovered
without depending on an API container's local filesystem. Perform the drill in
a disposable environment before public rollout and after every material
database or storage change.

## Recovery objectives

Use these initial operating targets until measured user behavior justifies a
different contract:

- Database recovery point objective: 24 hours.
- Database recovery time objective: 4 hours.
- Uploaded media retention: 7 days unless the user deletes it sooner.
- Completed job artifacts: 30 days during evaluation.

## Database backup

Azure runs `scripts.backup_postgres` daily at 03:00 UTC. The command creates a
PostgreSQL custom-format dump and uploads it to the private
`stemsplitter/backups/postgres/` prefix.

Run an on-demand backup with:

```bash
python -m scripts.backup_postgres
```

Record the returned object reference in the recovery drill evidence.

## Database restore drill

Restore only into an empty disposable database. The restore command requires an
exact hostname confirmation to reduce accidental production restores:

```bash
python -m scripts.restore_postgres \
  --key stemsplitter/backups/postgres/REPLACE.dump \
  --confirm-database-host disposable-database.example
```

After restoration, apply migrations and run `scripts.production_preflight`.
Verify job ownership, events, outbox state, and terminal artifact references.

## Queue recovery

Redis is transport, not authority. If Redis is lost:

1. Restore Redis connectivity.
2. Start the RQ and maintenance workers.
3. Let the maintenance worker drain pending outbox rows.
4. Let lease reconciliation recover stale active jobs.
5. Confirm no terminal job was executed again.

Do not restore queue state from PostgreSQL by manually editing job status.

## Object recovery

B2 remains private and versioned during the evaluation period. Test recovery by
restoring one hidden object version, generating a fresh signed URL, and
confirming playback. Never persist a signed URL in PostgreSQL or logs.

## Evidence

For every drill, record the image SHA, migration version, backup object key,
start and completion time, recovered job count, duplicate execution count, and
any manual intervention. A successful backup without a successful restore is
not recovery evidence.

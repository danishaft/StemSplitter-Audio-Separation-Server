# Local production-shaped stack

The local stack runs the same process boundaries used in deployment:
PostgreSQL, Redis/RQ, migrations, FastAPI, a queue worker, and a maintenance
worker. It uses development authentication and configuration defaults.

## Requirements

Install Docker with the Compose plugin. Add optional B2 and Modal credentials to
`.env.local` when you need remote separation.

## Start the stack

Run the following command from the repository root:

```bash
make compose-up
```

The API becomes available at `http://localhost:5000`. PostgreSQL and Redis bind
only to the local loopback interface.

## Verify the stack

Check liveness and dependency readiness:

```bash
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/health/live').read().decode())"
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/health/ready').read().decode())"
```

The readiness endpoint reports PostgreSQL, Redis/RQ, and object-storage status
separately.

## Stop the stack

Stop application containers without deleting database or queue volumes:

```bash
make compose-down
```

Use `docker compose down --volumes` only when you intentionally want to delete
local PostgreSQL and Redis state.

## Production differences

Production requires PostgreSQL, Redis/RQ, private S3-compatible storage, JWT
authentication, an explicit CORS allowlist, and a configured GPU worker.
Multipart API uploads are disabled by default; clients upload directly to
private object storage before creating a job.

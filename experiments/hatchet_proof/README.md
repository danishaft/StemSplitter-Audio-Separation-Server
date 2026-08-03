# Hatchet adoption proof

This experiment tests whether Hatchet can replace the current RQ dispatch layer
without changing the product's job, attempt, terminal-effect, or economic-effect
contracts. It does not modify or import production dispatch code.

> **Note:** This is a preview experiment. Passing the deterministic contract
> tests does not prove Hatchet server behavior.

## Decision boundary

The proof separates evidence into three classes:

- `executed_evidence` records behavior executed on this machine.
- `source_confirmed_not_executed` records capabilities found in the pinned
  Hatchet source but not exercised against a server.
- `blocked_evidence` records checks that still require an actual server and
  worker.

Do not treat source inspection or deterministic tests as a real Hatchet pass.
Only `benchmarks/hatchet/real-campaign.json` can record the integration pass.

## Product contract

PostgreSQL remains the product authority if Hatchet is adopted. Hatchet owns
workflow scheduling, but it does not own billable truth.

The proof uses these stable identifiers:

- `job_id` identifies the user-visible separation job.
- `attempt_id` is `<job_id>:attempt:<number>`.
- `dispatch_key` is `stem-separation:<attempt_id>`.
- Hatchet's run ID is an external orchestration reference stored on the attempt.
- `callback_id` deduplicates delivery.
- `usage:<attempt_id>` deduplicates the economic effect.

Priority and concurrency are explicit dispatch metadata. The Hatchet task uses
status-based idempotency on `input.dispatch_key`, two retries, and a concurrency
limit of two active tasks per `input.tenant_id`.

## Run deterministic evidence

This command uses only the Python standard library:

```bash
python3 experiments/hatchet_proof/run_contract_proof.py
```

The command writes `benchmarks/hatchet/contract-proof.json`. It proves the
product ledger invariants, not Hatchet scheduling.

You can also verify that the task definition imports with the pinned SDK. This
check still does not contact a Hatchet server:

```bash
HATCHET_CLIENT_TOKEN='<synthetic-local-jwt>' \
HATCHET_CLIENT_TLS_STRATEGY='none' \
experiments/hatchet_proof/.venv/bin/python \
  experiments/hatchet_proof/check_sdk_contract.py
```

The command writes `benchmarks/hatchet/sdk-compatibility.json`.

## Run the real Hatchet campaign

You need Docker, Python 3.10 or newer, and the fixed development worker token
shown in the Hatchet dashboard banner or under **Settings > API Tokens**.
Auth-disabled Hatchet images still require this worker token over gRPC.

Run the integration campaign with these steps:

1. Start the pinned Hatchet stack.

   ```bash
   docker compose \
     -f experiments/hatchet_proof/docker-compose.yml \
     up -d
   ```

2. Open `http://localhost:8888`, and copy the development worker token.

3. Create an isolated virtual environment and install the pinned SDK.

   ```bash
   python3 -m venv experiments/hatchet_proof/.venv
   experiments/hatchet_proof/.venv/bin/pip install \
     -r experiments/hatchet_proof/requirements.txt
   ```

4. Export the token and local transport settings.

   ```bash
   export HATCHET_CLIENT_TOKEN='<development-worker-token>'
   export HATCHET_CLIENT_HOST_PORT='localhost:7077'
   export HATCHET_CLIENT_SERVER_URL='http://localhost:8888'
   export HATCHET_CLIENT_TLS_STRATEGY='none'
   ```

5. Run the real campaign.

   ```bash
   experiments/hatchet_proof/.venv/bin/python \
     experiments/hatchet_proof/real_campaign.py
   ```

6. Stop the isolated stack after the report is written.

   ```bash
   docker compose \
     -f experiments/hatchet_proof/docker-compose.yml \
     down -v
   ```

The campaign must pass idempotent dispatch, priority ordering, tenant
concurrency, bounded retry, cancellation, worker-process crash recovery,
callback replay, and duplicate-effect checks.

## Pinned source

The proof was designed against Hatchet commit `41b056313b43`, tag `v0.98.7`,
and Python SDK `1.37.0`. The inspected reference implementations are:

- `sdks/python/examples/idempotency/`
- `sdks/python/examples/priority/`
- `sdks/python/examples/retries/`
- `sdks/python/examples/cancellation/`
- `sdks/python/examples/concurrency_limit/`
- `frontend/docs/pages/self-hosting/docker-compose.mdx`
- `frontend/docs/pages/self-hosting/hatchet-lite.mdx`

The server source contains the required primitives. This proof still rejects
adoption until the real campaign passes because those primitives must work
together under this project's terminal and economic contracts.

## Next steps

Adopt Hatchet only after the real campaign passes repeatedly and a separate
load test establishes scheduling latency and operational cost. If any
idempotency, cancellation, crash recovery, or duplicate-effect check fails,
keep PostgreSQL as authority and reject Hatchet for the production path.

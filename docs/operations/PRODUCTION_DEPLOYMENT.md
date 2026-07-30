# Production deployment

This runbook deploys the non-billing platform through GitHub Actions. It
provisions Azure Container Apps, publishes the Cloudflare Worker, applies
database migrations, and verifies the live dependency graph.

## Required accounts

Create or retain these provider resources before the first deployment:

- An Azure subscription with GitHub OpenID Connect federation.
- A Cloudflare account and zone for the public hostname.
- A managed PostgreSQL database.
- A TLS-enabled managed Redis instance.
- The existing private Backblaze B2 bucket.
- The existing authenticated Modal worker endpoint.
- A JWT identity provider.

Billing-provider configuration is intentionally absent.

## GitHub environment

Create a protected GitHub environment named `production`. Require review for
deployments from the default branch.

Configure these repository variables:

- `AZURE_APP_NAME`
- `AZURE_LOCATION`
- `AZURE_API_ORIGIN`
- `PUBLIC_WEB_ORIGIN`
- `AUTH_JWKS_URL`
- `AUTH_ISSUER`
- `AUTH_AUDIENCE`
- `OBJECT_STORAGE_BUCKET`
- `OBJECT_STORAGE_ENDPOINT_URL`
- `OBJECT_STORAGE_REGION`
- `GPU_WORKER_URL`

Configure these environment secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `DATABASE_URL`
- `REDIS_URL`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `GPU_WORKER_API_KEY`
- `EDGE_VERIFY_SECRET`
- `METRICS_BEARER_TOKEN`
- `SENTRY_DSN`, when Sentry is enabled

Generate `EDGE_VERIFY_SECRET` and `METRICS_BEARER_TOKEN` independently with at
least 32 random bytes. Never reuse a JWT, storage, or Modal credential.

## Provider configuration

Configure Backblaze B2 with the files under `infra/backblaze/`. Replace the
placeholder frontend origin before applying the CORS rule. Keep the bucket
private.

Initialize and apply the Cloudflare zone rules:

```bash
cd infra/cloudflare
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

Set the Worker custom domain in Cloudflare after the first Worker deployment.
Set `AZURE_API_ORIGIN` to the `apiOrigin` output from Azure.

## Deployment sequence

Run the `deploy platform` GitHub workflow. The workflow performs these steps:

1. Validates the Bicep template.
2. Provisions ACR, Container Apps, managed identity, and monitoring.
3. Builds one immutable image tagged with the Git commit SHA.
4. Deploys API, queue, maintenance, migration, and backup workloads.
5. Starts the migration job.
6. Verifies API readiness.
7. Builds and deploys the Cloudflare Worker and frontend assets.

The workflow uses GitHub OpenID Connect for Azure and does not store an Azure
client secret.

## Release verification

Verify the following behavior after deployment:

1. Request `/api/health/ready` through the Cloudflare hostname.
2. Confirm direct access to a non-health Azure API route returns `403`.
3. Confirm `/api/metrics` rejects a missing metrics token.
4. Upload a small owned audio file through the presigned B2 path.
5. Confirm the job, outbox, RQ dispatch, Modal execution, and signed artifacts.
6. Cancel one queued job and one running job.
7. Delete a terminal job and confirm its B2 objects are gone.
8. Confirm traces and errors appear in Azure Monitor.

## Rollback

Azure Container Apps retains revisions. Roll back the API, queue, and
maintenance applications to the same prior image SHA. Do not mix process
versions. Database migrations are forward-only; restore a database backup only
when a migration cannot be made backward compatible.

## Next steps

Run the [disaster recovery drill](DISASTER_RECOVERY.md) in a non-production
database before enabling unsupervised users.

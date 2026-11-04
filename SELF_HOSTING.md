# Self-hosting Model Deployer

## Prerequisites

- Docker Engine with the Compose plugin
- At least 4 GB RAM for the base stack; model environments need additional memory
- A host or reverse proxy that can expose the frontend and API

## Setup

1. Clone the repository and enter it.
2. Create the deployment environment file:

   ```sh
   cp .env.example .env
   ```

3. Replace every `replace-with-...` value in `.env`:
   - `DJANGO_SECRET_KEY` with a long random value
   - `POSTGRES_PASSWORD` with a strong database password
   - `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` with dedicated object-storage credentials
   - `RUNNER_AUTH_TOKEN` with a long random shared secret (generate one with
     `python -c "import secrets; print(secrets.token_urlsafe(32))"`). The API refuses to start
     without it unless `DJANGO_DEBUG=true`, and the runner refuses unless
     `RUNNER_ALLOW_UNAUTHENTICATED=true` (local development only).
4. Set `DJANGO_ALLOWED_HOSTS` to the hostnames used to reach the API and frontend.
5. Set `DJANGO_CORS_ALLOWED_ORIGINS` to the browser origins that are allowed to call the API, including your production frontend origin.
6. Billing (the simplified credit system described in `docs/marketplace-notes.md`) is disabled by default in `.env.example`. Leave `BILLING_ENABLED=false` for un-metered inference, or set it to `true` to enforce per-model credit charges. Credit deposits are **simulated, not payments**, and are refused unless `BILLING_DEMO_DEPOSITS=true` and the caller is staff (or `DJANGO_DEBUG=true`).
7. Start the stack:

   ```sh
   docker compose up --build -d
   ```

   Compose starts PostgreSQL, Redis, MinIO, the Django API, the Celery worker, the FastAPI runner, and the frontend. Named volumes preserve PostgreSQL, Redis, MinIO, and runner storage across container recreation.

   Only the API and frontend publish host ports. PostgreSQL, Redis, MinIO, and the runner are reachable only on the internal Compose network, which is all the stack needs; their connection settings come from `.env`. If you need direct host access for debugging (for example the MinIO web console), add an explicit localhost-only bind such as `127.0.0.1:9001:9001` in a compose override file — never a `0.0.0.0` binding.

## Create the first administrator

Run this once after the API container is healthy:

```sh
docker compose exec api python manage.py createsuperuser
```

The admin interface is available at `/admin/`. The API authentication endpoints are available under `/api/auth/`.

## Upload, deploy, and predict

1. Register or create an account through `/api/auth/register/`.
2. Log in through `/api/auth/login/` and keep the returned access token.
3. Approve the account for uploads (`UPLOAD_APPROVAL_REQUIRED=true` by default). Uploading a model
   means the platform installs and runs that code, so uploads are invite-only: either set
   `UPLOAD_APPROVAL_REQUIRED=false` or, preferably, approve the account in the admin
   (`/admin/` → Users → *can upload models*). Staff accounts are always approved.

   ```sh
   docker compose exec api python manage.py shell -c \
     "from django.contrib.auth import get_user_model; \
      get_user_model().objects.filter(username='USERNAME').update(can_upload_models=True)"
   ```

4. Upload a model ZIP containing `model.yaml`, the declared requirements file, and the model artifact:

   ```sh
   curl -X POST http://localhost:8000/api/models/upload/ \
     -H "Authorization: Bearer ACCESS_TOKEN" \
     -F file=@model.zip
   ```

5. Create a deployment with the returned `model_version_id`:

   ```sh
   curl -X POST http://localhost:8000/api/deployments/ \
     -H "Authorization: Bearer ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"model_version_id":"MODEL_VERSION_ID"}'
   ```

   The API returns `202 Accepted`. Poll the deployment endpoint until its status is `RUNNING`.

6. Create a model-specific API key through `/api/keys/` and call the prediction endpoint with both credentials:

   ```sh
   curl -X POST http://localhost:8000/api/predict/MODEL_ID/ \
     -H "Authorization: Bearer ACCESS_TOKEN" \
     -H "X-API-Key: MODEL_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"instances":[{"feature":1.2}]}'
   ```

Successful predictions are cached in Redis for `PREDICTION_CACHE_TTL_SECONDS` seconds. Cache keys include the model version, so deploying a new version does not reuse results from an older version.

## Configuration reference

The complete supported environment surface is listed in `.env.example`. Important production settings are:

- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS`
- `DJANGO_SECRET_KEY`
- `POSTGRES_*`
- `MINIO_*` (including the read-only `MINIO_WORKER_*` identity the runner uses)
- `REDIS_PASSWORD`, `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND`
- `RUNNER_SKLEARN_URL` and `RUNNER_PYTORCH_URL`
- `RUNNER_AUTH_TOKEN` and `RUNNER_AUTH_HEADER`
- `UPLOAD_APPROVAL_REQUIRED`
- `MAX_MODEL_ZIP_BYTES`, `INFERENCE_TIMEOUT_SECONDS`, and `PREDICTION_CACHE_TTL_SECONDS`
- `BILLING_ENABLED`, `BILLING_STARTING_CREDITS`, `BILLING_DEMO_DEPOSITS`, and `BILLING_MAX_DEPOSIT_AMOUNT`

### Internal runner authentication

The runner's `/init-model`, `/predict`, and `/teardown` endpoints require the shared secret in
`RUNNER_AUTH_TOKEN`, compared in constant time, and return `401` when it is missing or wrong. The
runner refuses to start when there is no secret at all, so the endpoints cannot silently serve
anonymous traffic. `/health` stays public because it is a liveness probe only and reveals no model
or storage state.

- The secret is read from the environment by the API, the Celery worker, and the runner container.
  It is never sent to subprocesses that run model code or install model dependencies.
- The value is never logged. Rotate it by generating a new secret, updating `RUNNER_AUTH_TOKEN` in
  `.env`, then recreating the `api`, `celery-worker`, and `worker` services together:

  ```sh
  docker compose up -d --force-recreate api celery-worker worker
  ```

  Requests between the old and new value failing during that window are expected; there is no
  dual-secret grace period.
- Do not set `RUNNER_ALLOW_UNAUTHENTICATED=true` on a host that anything can reach. It exists for
  local development only and disables runner authentication entirely.

### Redis authentication

Redis runs with `--requirepass ${REDIS_PASSWORD}`: every connection must authenticate. The compose
file makes `REDIS_PASSWORD` mandatory, so a `.env` that predates this change fails
`docker compose config -q` with `REDIS_PASSWORD is required` rather than starting an open Redis.

- Set `REDIS_PASSWORD` to a strong random value, and use the *same* password in `REDIS_URL`,
  `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` (`redis://:<password>@redis:6379/0`). A URL that
  omits it makes the cache and the Celery broker fail with an authentication error.
- The password is not passed on any command line: the healthcheck (`CMD redis-cli ping`) reads it
  from `REDISCLI_AUTH` in the container environment.
- The runner container never receives Redis credentials; it has no Redis URL at all.
- To rotate, change `REDIS_PASSWORD` and the three URLs together and recreate the affected services
  (`docker compose up -d --force-recreate redis api celery-worker`).

Do not expose PostgreSQL, Redis, or the MinIO API publicly unless there is a specific operational reason. Put HTTPS termination and public routing in Caddy, nginx, or another reverse proxy.

## Deploying to a server

The same `docker-compose.yml` runs locally and in production; only `.env` differs.

1. Point DNS at the host (an `A` record for the domain) and install Docker with the Compose plugin.
2. Clone the repository on the server and keep the production environment file outside the checkout, for example `~/modeldeployer.env.prod`, then copy it into place:

   ```sh
   cp ~/modeldeployer.env.prod .env
   ```

   `.env` and `.env.*` are gitignored; never commit either file.
3. Production values that must differ from `.env.example`:
   - `DJANGO_SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS=modeldeployer.shrihari.dev`
   - `DJANGO_CORS_ALLOWED_ORIGINS=https://modeldeployer.shrihari.dev`
   - `DJANGO_SECURE_SSL_REDIRECT=true`, `DJANGO_SECURE_COOKIES=true`, and
     `DJANGO_CSRF_TRUSTED_ORIGINS=https://modeldeployer.shrihari.dev`
   - `BILLING_ENABLED=true` only if you want to meter inference
   - strong `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
   - a strong `REDIS_PASSWORD` (compose refuses to start without it), repeated in `REDIS_URL` and
     the two `CELERY_*` URLs
   - a strong `RUNNER_AUTH_TOKEN` shared by the API, the Celery worker, and the runner
   - connection URLs pointing at the Compose service names (`db`, `redis`, `minio`, `worker`)
4. Validate and start:

   ```sh
   docker compose config -q
   docker compose up --build -d
   docker compose ps
   docker stats --no-stream
   ```

   `api` and `frontend` bind to `127.0.0.1` only; everything else is internal to the Compose network.
5. Put Caddy (or another proxy) in front. Keep `FRONTEND_PORT=8080` so the
   frontend does not compete with Caddy for host port 80. Copy
   `deploy/Caddyfile.example` into Caddy's configuration; it terminates TLS and
   routes `/api/`, `/admin/`, and `/static/` to the API and everything else to
   the console.
6. Smoke test the public URL:

   ```sh
   curl -I https://modeldeployer.shrihari.dev
   ```

   Then run one upload → deploy → predict through that URL, not just `localhost`.

### Updating a deployment

Back up data and object storage first using the automated backup tool. It reads
the current `POSTGRES_*` and `MINIO_*` settings (legacy `AWS_*` names remain
fallbacks):

```sh
./scripts/backup.sh ./backups/$(date +%Y%m%d_%H%M%S)
```

To update application code:

```sh
git pull
docker compose up --build -d
docker compose ps
```

See [docs/deploy_rollback.md](docs/deploy_rollback.md) for full rollback runbooks and database restoration using `scripts/restore.sh`.

Migrations run from the API entrypoint on start. If a pull added a migration and you need to run it separately:

```sh
docker compose exec api python manage.py migrate
```

Keep `.env` unchanged across updates unless `.env.example` gained a new variable. To roll back, check out the previous commit and run the same `docker compose up --build -d`.

## Known limitations

- The Compose deployment is intended for a single host; it does not provide multi-node orchestration.
- Celery task durability depends on the Redis volume and worker restart policy; external task monitoring is not included.
- The runner currently supports the implemented sklearn and PyTorch adapters only.
- Model builds and inference consume host CPU, memory, and disk; there is no built-in quota scheduler.
- Compose does not provide TLS. Configure HTTPS in the reverse proxy.
- The simplified credit system (billing) described in `docs/marketplace-notes.md` is the only monetization feature; it is disabled by default in `.env.example`.

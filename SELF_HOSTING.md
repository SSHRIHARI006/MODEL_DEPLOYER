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
4. Set `DJANGO_ALLOWED_HOSTS` to the hostnames used to reach the API and frontend.
5. Set `DJANGO_CORS_ALLOWED_ORIGINS` to the browser origins that are allowed to call the API, including your production frontend origin.
6. Billing (the simplified credit system described in `docs/marketplace-notes.md`) is disabled by default in `.env.example`. Leave `BILLING_ENABLED=false` for un-metered inference, or set it to `true` to enforce per-model credit charges.
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
3. Upload a model ZIP containing `model.yaml`, the declared requirements file, and the model artifact:

   ```sh
   curl -X POST http://localhost:8000/api/models/upload/ \
     -H "Authorization: Bearer ACCESS_TOKEN" \
     -F file=@model.zip
   ```

4. Create a deployment with the returned `model_version_id`:

   ```sh
   curl -X POST http://localhost:8000/api/deployments/ \
     -H "Authorization: Bearer ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"model_version_id":"MODEL_VERSION_ID"}'
   ```

   The API returns `202 Accepted`. Poll the deployment endpoint until its status is `RUNNING`.

5. Create a model-specific API key through `/api/keys/` and call the prediction endpoint with both credentials:

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
- `MINIO_*`
- `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND`
- `RUNNER_SKLEARN_URL` and `RUNNER_PYTORCH_URL`
- `MAX_MODEL_ZIP_BYTES`, `INFERENCE_TIMEOUT_SECONDS`, and `PREDICTION_CACHE_TTL_SECONDS`
- `BILLING_ENABLED` and `BILLING_STARTING_CREDITS`

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
   - `BILLING_ENABLED=true` only if you want to meter inference
   - strong `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
   - connection URLs pointing at the Compose service names (`db`, `redis`, `minio`, `worker`)
4. Validate and start:

   ```sh
   docker compose config -q
   docker compose up --build -d
   docker compose ps
   docker stats --no-stream
   ```

   `api` and `frontend` bind to `127.0.0.1` only; everything else is internal to the Compose network.
5. Put Caddy (or another proxy) in front. `deploy/Caddyfile.example` is a working block for this domain: it terminates TLS and routes `/api/`, `/admin/`, and `/static/` to the API and everything else to the console.
6. Smoke test the public URL:

   ```sh
   curl -I https://modeldeployer.shrihari.dev
   ```

   Then run one upload → deploy → predict through that URL, not just `localhost`.

### Updating a deployment

Back up the data volumes first; restoring without a backup is how data gets lost.

```sh
for volume in modeldeploy_postgres_data modeldeploy_minio_data; do
  docker run --rm -v "$volume":/data -v "$(pwd)":/backup alpine \
    tar czf "/backup/${volume}-$(date +%Y%m%d).tgz" /data
done

git pull
docker compose up --build -d
docker compose ps
```

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

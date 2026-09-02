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
5. Set `CORS_ALLOWED_ORIGINS` to the browser origins that are allowed to call the API.
6. Start the stack:

   ```sh
   docker compose up --build -d
   ```

   Compose starts PostgreSQL, Redis, MinIO, the Django API, the Celery worker, the FastAPI runner, and the frontend. Named volumes preserve PostgreSQL, Redis, MinIO, and runner storage across container recreation.

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
- `CORS_ALLOWED_ORIGINS`
- `DJANGO_SECRET_KEY`
- `POSTGRES_*`
- `MINIO_*`
- `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND`
- `RUNNER_SKLEARN_URL` and `RUNNER_PYTORCH_URL`
- `MAX_MODEL_ZIP_BYTES`, `INFERENCE_TIMEOUT_SECONDS`, and `PREDICTION_CACHE_TTL_SECONDS`

Do not expose PostgreSQL, Redis, or the MinIO API publicly unless there is a specific operational reason. Put HTTPS termination and public routing in Caddy, nginx, or another reverse proxy.

## Known limitations

- The Compose deployment is intended for a single host; it does not provide multi-node orchestration.
- Celery task durability depends on the Redis volume and worker restart policy; external task monitoring is not included.
- The runner currently supports the implemented sklearn and PyTorch adapters only.
- Model builds and inference consume host CPU, memory, and disk; there is no built-in quota scheduler.
- Compose does not provide TLS. Configure HTTPS in the reverse proxy.
- The marketplace, billing, wallet, multi-tenancy, and public model explorer features in `spec.md` are not part of this self-hosting package.

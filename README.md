# Model Deployer

## PROJECT VISION & OVERVIEW

Model Deployer is a developer-first platform for deploying machine learning models as isolated API endpoints: a GitHub for ML models. It provides upload, versioning, deployment, and inference routing through secure, containerized runtimes while keeping the control plane simple and auditable.

## ARCHITECTURE & INFRASTRUCTURE

**Tech stack**

- Django + Django REST Framework for the control plane and APIs.
- PostgreSQL as the primary database (SQLite fallback for local development), with Redis for caching and the Celery broker.
- Celery for durable, asynchronous deployment builds.
- MinIO (S3 API) for model artifact storage.
- SimpleJWT for authentication.
- React 19 + TypeScript + Vite + Tailwind for the console.
- Pytest for API and integration testing.

**Dynamic runner environments**

The platform builds and runs model environments dynamically using an isolated FastAPI runner worker. The control plane negotiates with the runner service to:

- Build isolated `uv` virtual environments from user-provided artifacts (`model.yaml`, `requirements.txt`).
- Start FastAPI inference servers natively bound to internal ports.
- Stream build logs and error tracebacks dynamically to the database.
- Track runtime metadata (runner URL, port, process state) in the `Deployment` model.

Inference traffic is proxied from the API gateway to the active deployment's internal URL. The deployment lifecycle is tracked in [deployments/models.py](deployments/models.py) with a guarded state machine.

**Frontend console**

The console is a React single-page app served as a static build (`frontend/`), talking to the API under `/api`:
- Public model explorer (`/`), user profiles (`/<username>`), and per-model pages (`/<username>/<model_name>`).
- Authenticated dashboard (`/dashboard`) for uploads, deployments, deploy logs, API keys, and interactive inference testing.
- In-app API reference at `/docs`.
- Token-based auth stored client-side, with automatic redirect on `401`.

## CORE API DESIGN

**Authentication**

- `POST /api/auth/register/` — Register user
- `POST /api/auth/login/` — Obtain JWT access/refresh tokens
- `POST /api/auth/refresh/` — Refresh access token

**Model registry**

- `POST /api/models/upload/` — Upload a model package (JWT required)
- `DELETE /api/models/<model_id>/` — Delete a model and wipe storage artifacts

**API keys**

- `GET /api/keys/` — List API keys for current user
- `POST /api/keys/` — Create API key for owned model
- `POST /api/keys/<key_id>/deactivate/` — Deactivate API key

**Deployments**

- `POST /api/deployments/` — Create a deployment (async build/run; returns 202)
- `GET /api/deployments/<deployment_id>/` — Deployment status/details

**Prediction gateway**

- `POST /api/predict/<model_id>/` — Run inference (requires BOTH JWT + `X-API-Key`)
- `POST /api/v1/inference/@<username>/<model_name>/` — Run inference by public address (JWT or a universal `md_live_...` API key); charges and credits are applied when billing is enabled
- `POST /api/keys/universal/` — Create a universal API key that works across models

**Monitoring**

- `GET /api/metrics/overview/` — Global usage and performance overview
- `GET /api/metrics/models/<model_id>/` — Per-model usage, performance, and build logs
- `GET /api/metrics/dashboard/summary/` — Dashboard summary counters
- `GET /api/metrics/dashboard/recent-predictions/` — Recent prediction activity
- `GET /api/metrics/dashboard/models/` — User model list with quick stats
- `GET /api/metrics/health/` — Service health (includes DB check)

**Prediction flow**

1. Client sends `POST /api/predict/<model_id>/` with JWT + `X-API-Key` (or calls the universal `@username/model` endpoint).
2. API gateway serves a Redis-cached response when the same model version and payload were seen within `PREDICTION_CACHE_TTL_SECONDS`.
3. On a miss it selects the latest RUNNING deployment for the model and proxies the payload to the runner's `/predict` endpoint.
4. The response is cached, returned to the client, and a `PredictionLog` is persisted.
5. Gateway maps upstream errors to HTTP 502/503/504.

## LOCAL SETUP & TESTING

### 1. Clone the repository

```
git clone <repository-url>
cd MODEL_DEPLOYER
```

### 2. Run with Docker Compose

The easiest way to spin up the entire stack (PostgreSQL, Redis, MinIO, API Gateway, Worker, and Frontend) is using Docker Compose:

```
docker compose up --build
```

The services will be available at:
- **Frontend Console**: `http://localhost:80`
- **API Gateway**: `http://localhost:8000`

PostgreSQL, Redis, MinIO, and the inference worker are internal to the Compose network; see `SELF_HOSTING.md` for debugging access.

### 3. Create an administrator and populate dummy data (Optional)

Migrations run automatically from the API container's entrypoint.

```
docker compose exec api python manage.py createsuperuser
docker compose exec api python populate_db.py
```

### 4. Run tests

Run the test suite from a checkout with `uv` (uses SQLite and in-memory caches):

```
uv run pytest
```

## CURRENT STATUS

- One `docker-compose.yml` runs the whole stack for local development, self-hosting, and the VPS deploy: PostgreSQL, Redis, MinIO (bucket auto-created), the Django API, a Celery worker, the FastAPI inference runner, and the frontend.
- Deployments run as Celery tasks and survive an API restart; predictions are cached in Redis per model version.
- The deployment state machine, proxy routing, and API-key scopes are implemented and hardened; see `SELF_HOSTING.md` for configuration and known limitations.
- The suite passes locally (`uv run pytest`), and a 20-model sklearn/PyTorch zoo has been validated end-to-end (upload → deploy → predict) with results in `test_models/results/`.

## THE ROADMAP

**Short-term**

- Deploy the compose stack to the production VPS behind a TLS-terminating reverse proxy.

**Mid-term**

- Expand `runners` adapters to natively support TensorFlow model payloads.

**Long-term**

- Production deployment on bare-metal VPS with Traefik/Nginx.
- Prometheus observability and structured service metrics.
- Integration with an autonomous AIOps/DevOps management agent.

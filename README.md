# Model Deployer

## PROJECT VISION & OVERVIEW

Model Deployer is a developer-first platform for deploying machine learning models as isolated API endpoints: a GitHub for ML models. It provides upload, versioning, deployment, and inference routing through secure, containerized runtimes while keeping the control plane simple and auditable.

## ARCHITECTURE & INFRASTRUCTURE

**Tech stack**

- Django + Django REST Framework for the control plane and APIs.
- PostgreSQL as the primary database (SQLite fallback for local development).
- SimpleJWT for authentication.
- Pytest for API and integration testing.

**Dynamic runner environments**

The platform builds and runs model environments dynamically using an isolated FastAPI runner worker. The control plane negotiates with the runner service to:

- Build isolated `uv` virtual environments from user-provided artifacts (`model.yaml`, `requirements.txt`).
- Start FastAPI inference servers natively bound to internal ports.
- Stream build logs and error tracebacks dynamically to the database.
- Track runtime metadata (runner URL, port, process state) in the `Deployment` model.

Inference traffic is proxied from the API gateway to the active deployment's internal URL. The deployment lifecycle is tracked in [deployments/models.py](deployments/models.py) with a guarded state machine.

**B2D Frontend Console**

The platform features a built-in, developer-first web application rendered natively via Django templates:
- Features a dark glassmorphism design system built with vanilla CSS.
- Client-side token routing and history state management.
- Dynamic dashboard with real-time model status indicators and metrics.
- Tabbed model management console with interactive inference testing and live deployment terminal logs.

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

**Monitoring**

- `GET /api/metrics/overview/` — Global usage and performance overview
- `GET /api/metrics/models/<model_id>/` — Per-model usage, performance, and build logs
- `GET /api/metrics/dashboard/summary/` — Dashboard summary counters
- `GET /api/metrics/dashboard/recent-predictions/` — Recent prediction activity
- `GET /api/metrics/dashboard/models/` — User model list with quick stats
- `GET /api/metrics/health/` — Service health (includes DB check)

**Prediction flow**

1. Client sends `POST /api/predict/<model_id>/` with JWT + `X-API-Key`.
2. API gateway selects the latest RUNNING deployment for the model.
3. Payload is proxied to the deployment runner `/predict` endpoint.
4. Response is returned to client and a `PredictionLog` is persisted.
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
- **MinIO Console**: `http://localhost:9001` (admin/adminpassword)

### 3. Run migrations and populate dummy data (Optional)

```
docker compose exec api python manage.py migrate
docker compose exec api python manage.py createsuperuser
docker compose exec api python populate_db.py
```

### 4. Run tests

You can run tests inside the API container:
```
docker compose exec api pytest -v --ds=config.settings_test
```

## CURRENT STATUS & TECHNICAL DEBT

- The entire stack is now fully containerized via `docker-compose.yml`, which manages PostgreSQL, Redis, MinIO (with auto-created `model-artifacts` bucket), the API gateway, the worker runner, and the frontend.
- The deployment state machine and proxy routing are implemented and hardened.

## THE ROADMAP

**Short-term**

- Containerize the Django/PostgreSQL control plane with `docker-compose.yml`.

**Mid-term**

- Expand `runners` adapters to natively support TensorFlow and PyTorch model payloads.

**Long-term**

- Production deployment on bare-metal VPS with Traefik/Nginx.
- Prometheus observability and structured service metrics.
- Integration with an autonomous AIOps/DevOps management agent.

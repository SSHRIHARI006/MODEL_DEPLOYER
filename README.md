# Model Deployer

## PROJECT VISION & OVERVIEW

Model Deployer is a developer-first platform for deploying machine learning models as isolated API endpoints: a GitHub for ML models. It provides upload, versioning, deployment, and inference routing through secure, containerized runtimes while keeping the control plane simple and auditable.

## ARCHITECTURE & INFRASTRUCTURE

**Tech stack**

- Django + Django REST Framework for the control plane and APIs.
- PostgreSQL as the primary database (SQLite fallback for local development).
- SimpleJWT for authentication.
- Pytest for API and integration testing.

**Dynamic containerization**

The platform builds and runs model containers dynamically using the Docker SDK. The control plane uses [core/container_manager.py](core/container_manager.py) to:

- Build images from user-provided artifacts via `build_image()`.
- Ensure a shared `model_network` bridge network exists via `ensure_network()`.
- Run containers in isolation with CPU/memory limits via `run_container()`.
- Track container metadata (image name, container name/ID, internal URL) in the `Deployment` model.

Inference traffic is proxied from the API gateway to the container internal URL (for example, `http://model_<deployment_id>:5000/predict`). The deployment lifecycle is tracked in [deployments/models.py](deployments/models.py) with a guarded state machine.

## CORE API DESIGN

**Authentication**

- `POST /api/auth/register/` — Register user
- `POST /api/auth/login/` — Obtain JWT access/refresh tokens
- `POST /api/auth/refresh/` — Refresh access token

**Model registry**

- `POST /api/models/upload/` — Upload a model package (JWT required)

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
- `GET /api/metrics/model/<model_id>/` — Per-model usage and performance
- `GET /api/metrics/dashboard/summary/` — Dashboard summary counters
- `GET /api/metrics/dashboard/recent/` — Recent prediction activity
- `GET /api/metrics/dashboard/models/` — User model list with quick stats
- `GET /api/metrics/health/` — Service health (includes DB check)

**Prediction flow**

1. Client sends `POST /api/predict/<model_id>/` with JWT + `X-API-Key`.
2. API gateway selects the latest RUNNING deployment for the model.
3. Payload is proxied to the deployment container `/predict` endpoint.
4. Response is returned to client and a `PredictionLog` is persisted.
5. Gateway maps upstream errors to HTTP 502/503/504.

## LOCAL SETUP & TESTING

### 1. Clone the repository

```
git clone <repository-url>
cd MODEL_DEPLOYER
```

### 2. Create virtual environment

```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```
pip install -r requirements.txt
```

or if using uv:

```
uv sync
```

### 4. Configure database

Copy `.env.example` to `.env` and set values.

### 5. Run migrations

```
python manage.py makemigrations
python manage.py migrate
```

### 6. Create superuser

```
python manage.py createsuperuser
```

### 7. Run server

```
python manage.py runserver
```

### 8. Run tests

```
pytest -v --ds=config.settings_test
pytest --cov=. --cov-report=term-missing --ds=config.settings_test
```

**Docker requirement**

For deployments and container builds, Docker must be installed and running on the host machine. The control plane uses the Docker SDK to build images and run containers.

## CURRENT STATUS & TECHNICAL DEBT

- The deployment state machine and container proxy routing are implemented.
- The system currently does not verify container readiness (health checks) before routing traffic. A readiness probe should be added before marking a deployment as RUNNING.

## THE ROADMAP

**Short-term**

- Containerize the Django/PostgreSQL control plane with `docker-compose.yml`.

**Mid-term**

- Implement `runners` adapters (scikit-learn, TensorFlow, PyTorch) to support framework-agnostic deployments.

**Long-term**

- Production deployment on bare-metal VPS with Traefik/Nginx.
- Prometheus observability and structured service metrics.
- Integration with an autonomous AIOps/DevOps management agent.

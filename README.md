# Model Deployer

Model Deployer is a backend platform for uploading, versioning, and serving machine learning models as API endpoints.

## Overview

This project provides a structured system to manage the lifecycle of machine learning models, including upload, deployment, and inference. It is designed with a modular architecture to support future extensions such as containerized deployment, distributed inference, and monitoring.

## Features

* Upload machine learning model packages
* Version control for models
* Deploy models as API endpoints
* Track prediction logs and usage
* API key-based access control
* JWT-based authentication
* DRF-based API architecture (APIView + serializers + permissions)
* Integration testing with pytest
* Admin panel for internal management
* Monitoring APIs for platform and model usage
* Health endpoint for service/database status checks
* Scoped rate limiting for prediction traffic
* Structured request logging with request IDs
* Basic web dashboard for auth, model management, and inference checks

## Tech Stack

* Backend: Django, Django REST Framework
* Database: PostgreSQL
* Language: Python 3.12
* Configuration: YAML
* Testing: pytest, pytest-django

## Project Structure

```
MODEL_DEPLOYER/
│
├── users/                  # Custom user model and authentication
├── api_keys/               # API key management
├── model_registry/         # Model and version management
├── deployments/            # Deployment lifecycle
├── prediction_gateway/     # Inference endpoints
├── monitoring/             # Logs and metrics
├── webapp/                 # Basic frontend and templates
├── runners/                # Runner abstraction (in progress)
├── tests/                  # Integration tests
├── conftest.py             # Shared pytest fixtures
│
├── config/                 # Django settings and routing
├── templates/              # HTML templates
├── manage.py
```

## Setup

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

Use environment variables (recommended). Copy `.env.example` to `.env` and set values.

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

---

## API Endpoints (Current)

Authentication:
* `POST /api/auth/register/` — Register user
* `POST /api/auth/login/` — Obtain JWT access/refresh tokens
* `POST /api/auth/refresh/` — Refresh access token

Model Registry:
* `POST /api/models/upload/` — Upload model package (authenticated)

API Keys:
* `GET /api/keys/` — List API keys for current user
* `POST /api/keys/` — Create API key for owned model
* `POST /api/keys/<key_id>/deactivate/` — Deactivate API key

Prediction Gateway:
* `POST /api/predict/<model_id>/` — Run inference (JWT + X-API-Key)

Monitoring:
* `GET /api/metrics/overview/` — Global usage and performance overview
* `GET /api/metrics/model/<model_id>/` — Per-model usage and performance
* `GET /api/metrics/dashboard/summary/` — Dashboard summary counters
* `GET /api/metrics/dashboard/recent/` — Recent prediction activity
* `GET /api/metrics/dashboard/models/` — User model list with quick stats
* `GET /api/metrics/health/` — Service health (includes DB check)

---

## Testing

The project uses app-level tests and integration tests:

* `authentication/tests/`
* `api_keys/tests/`
* `model_registry/tests/`
* `prediction_gateway/tests/`
* `monitoring/tests/`
* `tests/integration/`

All tests currently pass with end-to-end flow coverage for:

* User registration and login
* Model upload
* API key creation
* Prediction request lifecycle

Quick scripts for manual verification:

* `scripts/e2e_smoke.sh` — happy-path API flow
* `scripts/e2e_negative.sh` — negative cases + predict rate-limit checks

---

## Current Status

## Phase 1 Completed

Phase 1 is complete for the initial model deployment platform scope.

Completed scope:

The project currently includes:

* Database schema and relationships
* DRF migration for core API endpoints
* JWT authentication + API key authorization
* Model upload validation and safe extraction checks
* Prediction logging with success/error tracking
* Monitoring and dashboard APIs
* Basic web frontend pages (auth, dashboard, model detail)
* Health checks, request logging, and prediction throttling
* Automated API and integration test suite

---

## Future Work

* Runner abstraction completion for multiple ML frameworks
* Docker-based isolated execution for model runtimes
* Support for sklearn, TensorFlow, PyTorch, transformers, and RAG flows

## Environment Notes

By default, PostgreSQL is used when `POSTGRES_PASSWORD` is set.
For local/dev fallback with minimal setup, enable SQLite:

* `DJANGO_USE_SQLITE=true`

---

## License

This project is for educational and development purposes.

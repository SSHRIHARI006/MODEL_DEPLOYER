# ModelDeploy

ModelDeploy is a Django/React platform for registering machine-learning model bundles, managing immutable model versions, deploying them asynchronously, and exposing authenticated inference APIs. It is intended for local development and controlled self-hosting; it is not currently a safe public multi-tenant execution service.

## What is implemented

- Model upload with archive and manifest validation.
- Immutable model versions and deployment lifecycle APIs.
- JWT authentication, model-scoped API keys, and universal API keys.
- Django REST Framework control plane with Celery/Redis-backed deployment tasks.
- MinIO or S3-compatible artifact storage.
- FastAPI runner bridges for supported scikit-learn and PyTorch artifacts.
- React/TypeScript console for discovery, model management, deployments, keys, and inference testing.
- Optional credit-ledger billing and monitoring endpoints.
- Backup/restore scripts and a deployment runbook under [docs/](docs/).

## Architecture

```text
React/Vite console ──> Django/DRF API ──> PostgreSQL
                              │
                              ├── Celery ──> Redis
                              ├── MinIO/S3 artifact storage
                              └── FastAPI runner ──> model subprocesses
```

The runner currently installs each model's declared dependencies into a virtual environment and loads the artifact through the supported bridge. Cold subprocess execution has bounded time and output limits; warm IPC runtimes are opt-in and disabled by default.

## Security limitation

Uploaded requirements, Python modules, joblib/pickle artifacts, and full PyTorch artifacts are executable code. The current Compose deployment runs them inside a shared worker container and network boundary. Virtual environments, filtered environment variables, read-only object-storage credentials, and subprocess timeouts do not provide OS-level tenant isolation.

Keep `UPLOAD_APPROVAL_REQUIRED=true` and restrict uploads to trusted or explicitly approved users. Do not use this repository as a public arbitrary-code model-hosting service until model builds and inference run in a separately reviewed per-model container, gVisor sandbox, or microVM with enforced filesystem, network, credential, and resource boundaries. See [docs/security.md](docs/security.md).

## Repository layout

- `authentication/`, `users/`, `api_keys/`: accounts and authentication.
- `model_registry/`: model bundles, manifests, versions, and artifact storage.
- `deployments/`: deployment state and Celery build tasks.
- `prediction_gateway/`: authenticated inference and billing paths.
- `monitoring/`: health and usage metrics.
- `runners/`: FastAPI runner, framework bridges, and runner clients.
- `core/`: archive validation, storage helpers, errors, and throttling.
- `frontend/`: React/Vite console.
- `tests/` and app-local `*/tests/`: unit, contract, and integration tests.
- `deploy/` and `docker-compose.yml`: self-hosting configuration.

## Prerequisites

For the supported development setup, use Python 3.12+, Node.js 22+, npm, and Docker Engine with the Compose plugin. PostgreSQL, Redis, and MinIO are provided by Compose. A host running model dependencies needs additional CPU, memory, and disk beyond the base services.

## Local setup

Create a sanitized environment file and replace every placeholder:

```sh
cp .env.example .env
docker compose config -q
docker compose up --build -d
```

The API is bound to `127.0.0.1:8000` by default and the console to `127.0.0.1:80`. PostgreSQL, Redis, MinIO, and the runner are internal Compose services. Create an administrator after the API is healthy:

```sh
docker compose exec api python manage.py createsuperuser
```

For a host-only backend/frontend workflow, install the locked dependencies, apply migrations, and run the services separately:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000

cd frontend
npm ci
npm run dev
```

The complete environment surface is documented in [.env.example](.env.example). Production deployments should use strong secrets, `DJANGO_DEBUG=false`, explicit allowed hosts and CORS origins, authenticated Redis, and a reverse proxy for TLS. See [SELF_HOSTING.md](SELF_HOSTING.md).

## API examples

Register and log in through `/api/auth/register/` and `/api/auth/login/`, then upload an approved model bundle containing `model.yaml`, its declared requirements file, and its artifact:

```sh
curl -X POST http://127.0.0.1:8000/api/models/upload/ \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -F file=@model.zip
```

Deploy the returned model version and poll its deployment until it reaches a terminal state:

```sh
curl -X POST http://127.0.0.1:8000/api/deployments/ \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_version_id":"MODEL_VERSION_ID"}'
```

The direct prediction route requires a JWT and model-scoped API key:

```sh
curl -X POST http://127.0.0.1:8000/api/predict/MODEL_ID/ \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "X-API-Key: MODEL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"instances":[{"feature":1.2}]}'
```

The universal inference route supports the documented JWT/universal-key contract in [docs/auth_contracts.md](docs/auth_contracts.md). Model input and output compatibility remains model-dependent.

## Verification

Useful non-destructive checks are:

```sh
DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py check
DJANGO_SETTINGS_MODULE=config.settings_test .venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pytest
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```

Historical test-result files and model-zoo outputs are intentionally not part of the public source tree. Run the relevant checks in the exact checkout being reviewed; do not infer release readiness from old reports.

## Status and roadmap

The application features and local test suites are actively developed. Real PostgreSQL/Redis/MinIO integration, production lifecycle behavior, full model-zoo execution, and browser journeys against a live backend require separate environment verification. The highest-priority roadmap item is replacing the shared model worker with a genuinely isolated per-model execution boundary before enabling public uploads.

There is currently no published license or contribution policy in this repository. Add those before representing the project as an open-source release.

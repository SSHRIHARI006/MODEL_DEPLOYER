# Security model

This is the authoritative description of how credentials, boundaries, and model execution are
separated in this stack. It documents **which** secret lives where and why; it never contains a
secret value.

Related: `.env.example` (the complete configuration surface), `SELF_HOSTING.md` (deployment and
rotation steps), `docs/marketplace-notes.md` (product scope).

## SEC-01 release gate: untrusted model execution

Model requirements, serialized artifacts, and inference bridges execute inside the shared runner container. Per-model virtual environments and filtered child environments are defense-in-depth only: they do not isolate filesystem, process namespace, network, CPU/memory, or container credentials. The shared-worker architecture is therefore not suitable for multi-tenant or public production use. Keep production deployment at **NO-GO** until this gate is met or an explicit, justified single-tenant mitigation is accepted for a specific deployment model.

The smallest viable implementation is a trusted supervisor that launches a disposable per-model-version container or VM with a dedicated non-root UID/user namespace; dropped capabilities and seccomp/AppArmor; read-only root filesystem and only version-scoped artifact/scratch mounts; no control-plane, database, Redis, Docker socket, host filesystem or MinIO-admin access; deny-by-default network/egress; and enforced cgroup CPU, memory, PID, disk and wall-time limits with supervisor cancellation. Artifacts should be mounted read-only or fetched using short-lived credentials scoped to one version prefix. Validate isolation with adversarial filesystem/network/credential/process/resource tests. This is a substantial execution architecture change and has not been implemented in this working tree.

A dedicated single-tenant host with uploads disabled or restricted to trusted reviewed models may reduce exposure only if its isolation and co-resident workloads are explicitly accepted. It is not a sandbox and is not a general multi-user mitigation.

## Trust boundary

The one boundary that matters most is **uploaded model code**. `model.yaml` declares a
`requirements` file that the runner installs with `uv pip install`, and the model artifact is then
loaded and executed in a subprocess. Anything a user uploads is therefore treated as untrusted
code that has to be contained by:

- keeping the runner's own credentials away from it (this document),
- limiting what the archive may contain (`core/archive.py`, SEC-04),
- the runner refusing unauthenticated callers (SEC-02),
- the timeouts and process limits added by spec 5 (REL-*).

Until a per-model sandbox exists (see *Residual risks*), model uploads remain
invite/staff-approved, not open to the public internet.

| Component | Reachable from | Trust level |
|---|---|---|
| `frontend` | host port, via reverse proxy | untrusted (browser) |
| `api` | host port, via reverse proxy | trusted control plane |
| `celery-worker` | Compose network only | trusted control plane |
| `worker` (inference runner) | Compose network only | **hosts untrusted code** |
| `db`, `redis`, `minio` | Compose network only | trusted data stores |
| `minio-init` | runs once, then exits | trusted bootstrap |

## Credentials by component

| Credential | api | celery-worker | worker | minio-init |
|---|---|---|---|---|
| `DJANGO_SECRET_KEY` | yes | yes | **no** | no |
| `POSTGRES_*` | yes | yes | **no** | no |
| `REDIS_URL` / `CELERY_*` | yes | yes | **no** | no |
| `MINIO_ROOT_*` | yes | yes | **no** | yes (bootstrap only) |
| `MINIO_WORKER_*` (read-only) | no | no | yes | yes (creates it) |
| `RUNNER_AUTH_TOKEN` | yes | yes | yes | no |

The runner's environment is an explicit allowlist in `docker-compose.yml` (`worker.environment`),
not `env_file: .env`. `tests/test_compose_security.py` fails if that allowlist grows a
control-plane credential.

## Internal runner authentication (SEC-02)

- `/init-model`, `/predict`, and `/teardown` require the shared secret in the header named by
  `RUNNER_AUTH_HEADER` (default `X-Runner-Token`), compared in constant time.
- Missing and incorrect credentials both return `401`; the response does not distinguish them.
- The runner refuses to start (import-time error) unless `RUNNER_AUTH_TOKEN` is set or
  `RUNNER_ALLOW_UNAUTHENTICATED=true` is set explicitly. The Django control plane likewise refuses
  to load settings without a token when `DJANGO_DEBUG` is false.
- `/health` stays unauthenticated: it is a liveness probe for the container and reveals no model,
  storage, or deployment state.
- The token is passed to the runner as an environment variable and is **removed** from the
  environment of every subprocess the runner starts.
- Rotation: generate a new value, update `RUNNER_AUTH_TOKEN` in `.env`, then recreate `api`,
  `celery-worker`, and `worker` together (`docker compose up -d --force-recreate api celery-worker
  worker`). There is no dual-secret grace window, so calls fail until both sides are recreated.

## Worker credential minimization (SEC-01)

The runner receives only what it needs:

| Variable | Purpose |
|---|---|
| `STORAGE_ROOT` | local scratch space for downloaded artifacts and per-model environments |
| `RUNNER_AUTH_TOKEN`, `RUNNER_AUTH_HEADER` | verify the control plane (SEC-02) |
| `MINIO_ENDPOINT`, `MINIO_BUCKET`, `MINIO_USE_SSL` | where artifacts live |
| `MINIO_WORKER_USER`, `MINIO_WORKER_PASSWORD` | **read-only** artifact access |

`MINIO_WORKER_USER` is created by the `minio-init` one-shot job with the canned policy in
`deploy/minio/worker-artifacts-readonly-policy.json`: `s3:ListBucket` + `s3:GetBucketLocation` on
the artifacts bucket and `s3:GetObject` on its objects. No write, no delete, no bucket
administration. The runner authenticates downloads with that identity and can do nothing else with
it: a leaked runner identity cannot modify or remove other users' artifacts.

The scoped identity is deliberately narrow at the storage layer, and that was verified against a
live MinIO (`RELEASE.2026-08-04T00-00-00Z`) rather than assumed: `ListBucket`, `GetObject`, and
`download_file` succeed; `PutObject`, `DeleteObject`, and `CreateBucket` are refused with
`AccessDenied`; `ListBuckets` returns only the artifacts bucket, and reading objects from another
bucket is denied. `minio-init` is also idempotent — re-running it re-applies the same user, policy,
and attachment.

### Subprocess environment

Model code and dependency installation never inherit the runner's environment. `_child_env()` in
`runners/worker.py` builds the child environment from a fixed allowlist (`PATH`, `HOME`, locale,
`TMPDIR`, Python runtime flags, TLS/proxy configuration, `UV_*`/`PIP_*` index overrides) and adds
nothing else. The runner credential, object-store credentials, and any ambient secret are absent by
construction; `runners/tests/test_worker_auth.py` asserts this for both call sites (environment
creation/`uv pip install` and model inference).

## Upload approval and the model-execution trust boundary (SEC-03)

An upload is the entry point for untrusted code: the ZIP declares a requirements file that gets
installed, and an artifact that gets loaded and executed. Upload approval is not containment. A
per-model sandbox does not exist, so the production gate and restricted-deployment exception in
`SEC-01 release gate` apply regardless of whether uploads are invite-only.

- `UPLOAD_APPROVAL_REQUIRED` (default `true`) gates `POST /api/models/upload/`. When enabled, only
  `is_staff` accounts and accounts with `can_upload_models=True` may upload; everyone else receives
  `403` with code `UPLOAD_NOT_APPROVED`. Staff can approve an account in `/admin/` (Users → *can
  upload models*) or with:

  ```sh
  docker compose exec api python manage.py shell -c \
    "from django.contrib.auth import get_user_model; \
     get_user_model().objects.filter(username='USERNAME').update(can_upload_models=True)"
  ```

- Deployments are limited to model versions the caller owns (`DeploymentCreateSerializer`), so an
  unapproved account has nothing it can deploy. There is no path from "registered user" to
  "runs code on this host" without an approval step.
- Archive contents are validated separately (`core/archive.py`, SEC-04) and execution is bounded
  by timeouts and process limits in spec 5. Approval decides *who* may upload; those controls decide
  what an upload may do once accepted.
- Rollout: existing accounts are not approved automatically. A deployment that *wants* open
  uploads can set `UPLOAD_APPROVAL_REQUIRED=false`, but must then accept the residual risk below
  outweighing the upload gate.
- **Future work (documented, not built):** per-model containers running as a non-root user with a
  read-only root filesystem, dropped capabilities, cpu/memory/pids/time limits, no Docker socket,
  a restricted filesystem view, an egress policy, no admin APIs, and separate build vs. runtime
  networks. Public or arbitrary uploads stay disabled until that sandbox is accepted.

## Secret handling rules

1. Secrets live only in `.env` (gitignored) and are injected per service through the explicit
   allowlists above. `.env.example` carries placeholders only.
2. Never log a secret. Request/response logging covers method, path, status, duration, and
   `X-Request-ID` only.
3. Never pass a secret to a subprocess that installs dependencies or runs model code.
4. Never return a secret to a client. API keys are revealed exactly once, at creation.
5. Rotate by replacing the value and recreating the affected services; when in doubt, restart the
   whole stack.

## Error responses and correlation (SEC-06)

- `GET /api/users/@<username>/` is anonymous and returns **no email address**. Account email is
  only visible to the account owner, through the authenticated dashboard.
- Error bodies are stable and safe: `{code, message, request_id}` (with `detail`/`error` aliases
  kept for existing clients). Responses never contain stack traces, SQL, object-store keys, or
  exception text.
- `core/errors.py` installs a DRF exception handler: anything that is not an `APIException`
  becomes `500 INTERNAL_ERROR` with the request id exposed and the exception logged server-side
  under the same id (matched with `X-Request-ID`, set by `core.middleware.RequestIDMiddleware`).
- Raw exception text is not written to `PredictionLog.error_message` either; the diagnostic detail
  stays in the log.
- Deployment diagnostics (`latest_deployment_error`, `latest_deployment_logs`, recent-prediction
  errors) remain restricted to the owner of the model, never exposed publicly. Error *text*
  classification for those fields lands with the runner error taxonomy (spec 5, REL-02).

## Simulated credits (SEC-05)

No money moves through this platform. The wallet is a credit ledger used to meter inference
between users, and `POST /api/wallet/deposit/` mints credits for development and testing.

- `BILLING_DEMO_DEPOSITS` defaults to `false`, so the endpoint is disabled (`403`,
  `DEMO_DEPOSITS_DISABLED`) unless an operator opts in.
- When enabled, only `is_staff` accounts (or a `DJANGO_DEBUG=true` deployment) may deposit; other
  users receive `403` `DEPOSIT_NOT_AUTHORIZED`.
- Amounts must be finite positive decimals within `BILLING_MAX_DEPOSIT_AMOUNT`. `NaN`, `Infinity`,
  negatives, booleans, and non-numeric payloads are rejected with `400`, and the request is
  rate-limited (`deposit` throttle scope).
- A successful deposit writes exactly one `DEPOSIT` ledger entry and updates the wallet balance in
  a single transaction.

## Redis authentication and model pricing (SEC-08)

**Redis.** The `redis` service is started with `--requirepass ${REDIS_PASSWORD}`, so every command must
authenticate. Nothing is published to the host: Redis stays on the Compose network.

- The password is supplied through the environment and is **not** repeated in the healthcheck's
  argument list. `REDISCLI_AUTH` is set for the container, so `redis-cli` (and the healthcheck
  `CMD redis-cli ping`) authenticates from the environment, and the password does not appear in
  `docker inspect` output or in the container's process arguments.
- `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` must carry the same password
  (`redis://:<password>@redis:6379/N`). A URL without it fails closed: the cache backend raises
  `AuthenticationError` and Celery cannot reach the broker, so a half-configured deployment fails
  loudly instead of silently serving unauthenticated traffic.
- Rotate the password by changing `REDIS_PASSWORD` and the three URLs together, then recreating
  `redis`, `api`, and `celery-worker`. Queued Celery tasks under the old password are not migrated.
- The cache holds only derived data (predictions). Losing it costs a cache miss, not correctness.

**Model pricing.** `cost_per_run` is validated in the API *and* constrained in the database, so a
negative or malformed value cannot be stored through either path:

- The model-update serializer declares `cost_per_run` with
  `core/serializers.py::FiniteDecimalField(max_digits=8, decimal_places=4, min_value=0)`. It parses
  the value as a `Decimal` and rejects `NaN`/`Infinity` before DRF's quantization step (which would
  otherwise raise and escape as a `500`). Negatives, non-finite values, booleans, empty strings, and
  non-numeric payloads are rejected with `400`, and the row is left unchanged.
- `model_registry/migrations/0004_model_model_cost_per_run_non_negative.py` adds
  `CheckConstraint(cost_per_run >= 0)`, so the database refuses a negative price from the ORM,
  `bulk_create`, or direct SQL as well.

## Residual risks (not accepted as deployment clearance)

- **Model code is not sandboxed per model.** It runs as the runner container's user with the
  container's filesystem, network, and CPU/memory limits. A hostile model can consume the runner's
  resources or reach other models' artifacts through the same read-only identity. See the SEC-01
  release gate above: no production clearance is implied until that boundary is implemented or a
  specific isolated-host exception is formally justified.
- **The API holds MinIO root credentials.** It uploads and deletes artifacts, so it keeps write
  access. Narrowing this to a per-prefix write identity is future work.
- **Model dependencies are installed from public indexes at deploy time** with `--extra-index-url`
  pointing at the PyTorch CPU wheel index. Dependency-confusion and index-compromise risk is
  accepted; pinning a mirror is future work.
- **The runner shares the Compose network** with `db`, `redis`, and `minio`. No credentials for them
  are present in the runner, but network placement should be split when the per-model sandbox lands
  (spec 4 §3.2 SEC-03 future work).
- **Redis holds only derived state.** It now requires authentication (SEC-08) and is never published
  to the host, but it is not a trust boundary by itself: a client that has the password can read or
  alter cached predictions and Celery tasks. Cache entries are keyed per model version and store no
  user data beyond the request/response payloads that were already cached for that model.
- **Pricing is bounded, not billed.** `cost_per_run` cannot go negative or become non-finite
  (SEC-08), but credits remain simulated, so a large price is a correctness question and not a
  financial control.

## How to verify

```sh
# The runner must not carry control-plane credentials.
docker compose --env-file .env config --format json \
  | python -c "import json,sys; print(sorted(json.load(sys.stdin)['services']['worker']['environment']))"

# Unauthenticated calls to the runner must fail from inside the network (expect 401).
docker compose exec api python - <<'PY'
import requests; print(requests.post("http://worker:8002/teardown", json={"model_id": "x"}).status_code)
PY

# Redis must refuse unauthenticated commands. `redis-cli` exits 0 even when the server
# answers NOAUTH, so check the output, and unset REDISCLI_AUTH first.
docker compose exec redis sh -c 'unset REDISCLI_AUTH; redis-cli ping'   # expect: NOAUTH Authentication required.
docker compose exec redis sh -c 'redis-cli ping'                        # expect: PONG

# A price the API rejects must not change the stored value.
curl -X PATCH http://localhost:8000/api/models/@<user>/<model>/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"cost_per_run": "-1"}'
```

The deployment-configuration invariants (worker allowlist, no `env_file`, read-only policy, private
networking) are asserted by `tests/test_compose_security.py` on every test run; the subprocess
environment and scoped-credential behaviour are asserted by `runners/tests/test_worker_auth.py`.

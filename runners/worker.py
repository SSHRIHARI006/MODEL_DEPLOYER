from __future__ import annotations

import json
import logging
import os
import select
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import yaml
from botocore.client import Config
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .auth import (
    ALLOW_UNAUTHENTICATED_ENV,
    DEFAULT_AUTH_HEADER,
    check_auth_configuration,
    is_unauthenticated_allowed,
    resolve_auth_token,
    verify_token,
)
from core.runner_errors import (
    RUNNER_CODE_CAPACITY_EXHAUSTED,
    RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE,
    RUNNER_CODE_INTERNAL,
    RUNNER_CODE_INVALID_INPUT,
    RUNNER_CODE_INVALID_MANIFEST,
    RUNNER_CODE_INVALID_REQUIREMENTS,
    RUNNER_CODE_MISSING_ARTIFACT,
    RUNNER_CODE_MODEL_LOAD_FAILED,
    RUNNER_CODE_SMOKE_CHECK_FAILED,
    RUNNER_CODE_STORAGE_UNAVAILABLE,
    RUNNER_CODE_UNSUPPORTED_FRAMEWORK,
    RUNNER_CODE_WORKER_TIMEOUT,
    RUNNER_CODE_WORKER_UNAVAILABLE,
)

logger = logging.getLogger(__name__)


# REL-01/REL-03: bounded runner behavior.
RUNNER_INIT_TIMEOUT_SECONDS = int(os.getenv("RUNNER_INIT_TIMEOUT_SECONDS", "300"))
RUNNER_PREDICT_TIMEOUT_SECONDS = int(os.getenv("RUNNER_PREDICT_TIMEOUT_SECONDS", "15"))
RUNNER_HEALTHCHECK_TIMEOUT_SECONDS = int(os.getenv("RUNNER_HEALTHCHECK_TIMEOUT_SECONDS", "30"))
RUNNER_COMMAND_TIMEOUT_SECONDS = int(os.getenv("RUNNER_COMMAND_TIMEOUT_SECONDS", "60"))
RUNNER_MAX_OUTPUT_BYTES = int(os.getenv("RUNNER_MAX_OUTPUT_BYTES", str(128 * 1024)))
RUNNER_MAX_CONCURRENT_BUILDS = int(os.getenv("RUNNER_MAX_CONCURRENT_BUILDS", "1"))
RUNNER_MAX_CONCURRENT_PREDICTIONS = int(os.getenv("RUNNER_MAX_CONCURRENT_PREDICTIONS", "8"))
# Warm IPC remains opt-in until per-model OS isolation is deployed. When explicitly
# enabled, every pipe operation below is still deadline- and byte-bounded.
RUNNER_WARM_RUNTIME_ENABLED = os.getenv("RUNNER_WARM_RUNTIME_ENABLED", "false").lower() in ("true", "1", "yes")
RUNNER_MAX_WARM_MODELS = int(os.getenv("RUNNER_MAX_WARM_MODELS", "5"))

# REL-05: legacy partial-cache reuse is unsafe, so completed downloads are
# marked atomically and re-validated before reuse.
RELIBILITY_STALE_THRESHOLD = timedelta(seconds=int(os.getenv("RUNNER_DOWNLOAD_STALE_SECONDS", "3600")))

# REL-05: legacy partial-cache reuse is unsafe, so completed downloads are
# marked atomically and re-validated before reuse.
RELIBIBILITY_STALE_THRESHOLD = timedelta(seconds=int(os.getenv("RUNNER_DOWNLOAD_STALE_SECONDS", "3600")))

# In-process semaphores bound concurrent env builds and concurrent prediction
# subprocesses for a single shared worker process.
_build_semaphore = threading.BoundedSemaphore(RUNNER_MAX_CONCURRENT_BUILDS)
_predict_semaphore = threading.BoundedSemaphore(RUNNER_MAX_CONCURRENT_PREDICTIONS)


class RunnerCapacityError(Exception):
    """Raised when the shared worker has exhausted the bounded concurrency limit."""

    def __init__(self, message: str, retry_after_seconds: int = 5):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

# SEC-02: internal model-management and inference endpoints require a shared
# secret. Fail closed at import when it is missing, so a misconfigured runner
# never serves anonymous traffic; the opt-out is development-only and explicit.
RUNNER_AUTH_TOKEN = resolve_auth_token(os.getenv("RUNNER_AUTH_TOKEN"))
RUNNER_AUTH_HEADER = os.getenv("RUNNER_AUTH_HEADER") or DEFAULT_AUTH_HEADER
RUNNER_ALLOW_UNAUTHENTICATED = is_unauthenticated_allowed(
    os.getenv(ALLOW_UNAUTHENTICATED_ENV)
)

check_auth_configuration(
    token=RUNNER_AUTH_TOKEN,
    debug=False,
    allow_unauthenticated=RUNNER_ALLOW_UNAUTHENTICATED,
    service="inference runner",
)

if not RUNNER_AUTH_TOKEN:
    logger.warning(
        "%s=true: internal runner endpoints are unauthenticated. "
        "This must never be enabled outside local development.",
        ALLOW_UNAUTHENTICATED_ENV,
    )

app = FastAPI()

DEFAULT_STORAGE = Path(os.getenv("STORAGE_ROOT", "/storage"))
MODELS_ROOT = DEFAULT_STORAGE / "models"
ENVS_ROOT = DEFAULT_STORAGE / "envs"


def _read_manifest(path: Path) -> tuple[str, datetime]:
    _ensure_within_root(path, MODELS_ROOT)
    if not path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=400, detail="manifest is not readable") from exc

    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.now().astimezone().tzinfo)
    except OSError:
        mtime = datetime.now()

    return text, mtime


def _parse_manifest(text: str) -> dict:
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail="manifest is not valid yaml") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="manifest must be a yaml object")

    return parsed


def _readiness_action(
    phase: str,
    manifest: dict,
    manifest_path: Path,
    requirements_path: Path,
) -> tuple[str, str | None]:
    action = "none"
    detail: str | None = None

    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be a yaml object")

    smoke = manifest.get("readiness")
    if smoke is None:
        return "none", None

    if isinstance(smoke, bool):
        smoke = {}

    if not isinstance(smoke, dict):
        raise HTTPException(status_code=400, detail="manifest readiness section must be an object")

    action = smoke.get("type", "smoke")
    if action not in ("smoke", "validate", "none", None):
        raise HTTPException(
            status_code=400,
            detail=f"unknown readiness type: {action!r}. Expected smoke, validate or none.",
        )

    if action == "smoke":
        script = smoke.get("script")
        if not script:
            raise HTTPException(
                status_code=400,
                detail="readiness.smoke requires a script path",
            )
        script_path = (manifest_path.parent / script).resolve()
        _ensure_within_root(script_path, MODELS_ROOT)
        if not script_path.exists():
            raise HTTPException(status_code=404, detail="readiness script not found")
        detail = f"smoke {script_path}"
        return "smoke", detail

    if action == "validate":
        expect = smoke.get("expects")
        if expect is None:
            raise HTTPException(
                status_code=400,
                detail="readiness.validate requires expects",
            )
        detail = f"validate expects={expect!r}"
        return "validate", detail

    if action == "none":
        detail = "readiness none requested"
        return "none", detail

    raise AssertionError(f"unreachable readiness action: {action!r}")


def _run_readiness_probe(
    python_bin: Path,
    model_id: str,
    manifest_path: Path,
    env_dir: Path,
) -> tuple[int, str, str, float] | None:
    action, detail = _readiness_action(
        "predict",
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")),
        manifest_path,
        manifest_path.parent / (yaml.safe_load(manifest_path.read_text(encoding="utf-8")).get("requirements") or "requirements.txt"),
    )
    if action == "smoke":
        smoke = yaml.safe_load(manifest_path.read_text(encoding="utf-8")).get("readiness", {})
        script = smoke.get("script")
        if not script:
            return None
        script_path = (manifest_path.parent / script).resolve()
        if not script_path.exists():
            return None

        cmd = [str(python_bin), str(script_path), str(model_id), str(env_dir)]
        code, out, err, duration_ms = _run_bounded(
            cmd,
            timeout_seconds=RUNNER_INIT_TIMEOUT_SECONDS,
            max_output_bytes=RUNNER_MAX_OUTPUT_BYTES,
        )
        return code, out, err, duration_ms

    return None


def _inference_stderr_is_retryable(stderr: str) -> bool:
    lowered = stderr.lower()

    if any(token in lowered for token in ("timed out", "timeout", "deadline exceeded")):
        return True
    if any(token in lowered for token in ("connection refused", "econnrefused", "connection reset", "econrefused", "econnreset")):
        return True
    if any(token in lowered for token in ("temporary failure", "service unavailable", "503")):
        return True
    if any(token in lowered for token in ("rate limit", "too many requests", "429")):
        return True

    return False


def _pip_stderr_is_retryable(stderr: str) -> bool:
    lowered = stderr.lower()

    if any(token in lowered for token in ("could not fetch", "network is unreachable", "name or service not known")):
        return True
    if any(token in lowered for token in ("timed out", "timeout", "deadline exceeded")):
        return True
    if any(token in lowered for token in ("temporary resolve failure", "failed to resolve", "service temporarily unavailable")):
        return True

    return False


@app.get("/ready")
def ready():
    # Separate from liveness so readiness can be authenticated and scoped in a
    # future iteration without changing the unauthenticated container probe.
    return {"status": "ready", "version": "runner"}

# SEC-01: only these variables may reach subprocesses that install third-party
# dependencies or run model code. Everything else in the runner environment —
# the runner credential, object-store credentials, database URLs — is dropped.
CHILD_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TZ",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
    # Certificate and proxy configuration that legitimate installs require.
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "UV_CACHE_DIR",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
)

# Scoped object-storage identity for downloading artifacts. Never the MinIO root
# credentials; the identity is created read-only by the `minio-init` service.
STORAGE_ACCESS_KEY_ENV = "MINIO_WORKER_USER"
STORAGE_SECRET_KEY_ENV = "MINIO_WORKER_PASSWORD"


def _child_env() -> dict[str, str]:
    """Minimal environment for subprocesses that run model or dependency code."""
    env = {
        name: os.environ[name]
        for name in CHILD_ENV_ALLOWLIST
        if name in os.environ
    }
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return env


def _storage_credentials() -> tuple[str, str]:
    return (
        os.getenv(STORAGE_ACCESS_KEY_ENV, ""),
        os.getenv(STORAGE_SECRET_KEY_ENV, ""),
    )


def require_runner_auth(
    provided: str | None = Header(default=None, alias=RUNNER_AUTH_HEADER),
) -> None:
    """FastAPI dependency protecting the internal runner endpoints.

    Constant-time comparison; missing and incorrect credentials are both
    rejected so the caller learns nothing about the expected value.
    """
    if not RUNNER_AUTH_TOKEN:
        # Only reachable when the development-only opt-out is enabled.
        return
    if not verify_token(provided, RUNNER_AUTH_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="missing or invalid runner credentials",
            headers={"WWW-Authenticate": RUNNER_AUTH_HEADER},
        )


class InitModelRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    manifest_path: str = Field(..., min_length=1)


from typing import Any

class PredictRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    manifest_path: str = Field(..., min_length=1)
    instances: list[Any]


class TeardownRequest(BaseModel):
    model_id: str = Field(..., min_length=1)


def _run_bounded(
    cmd: list[str],
    *,
    timeout_seconds: int,
    input_bytes: bytes | None = None,
    max_output_bytes: int = RUNNER_MAX_OUTPUT_BYTES,
    working_dir: Path | None = None,
) -> tuple[int, str, str, float]:
    """Run a subprocess with a hard deadline and bounded output.

    The child is spawned in a new session/process group so that on timeout we
    can terminate the entire group (the command plus any children it spawns)
    rather than only the leading process. Output is capped to a fixed diagnostic
    budget so a noisy or hostile model cannot consume unbounded memory in the
    worker.
    """
    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if input_bytes is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=_child_env(),
            cwd=str(working_dir) if working_dir is not None else None,
            text=False,
            close_fds=True,
        )
    except OSError as exc:
        raise RuntimeError(f"failed to start command: {exc}") from exc

    try:
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        stdout_bytes = 0
        stderr_bytes = 0
        timed_out = False

        deadline = start + timeout_seconds
        stdin_fd: int | None = None
        stdin_stream = getattr(proc, "stdin", None)
        pending_input = bytearray(input_bytes or b"")
        if stdin_stream is not None:
            try:
                stdin_fd = stdin_stream.fileno()
                os.set_blocking(stdin_fd, False)
            except (OSError, AttributeError, ValueError):
                stdin_fd = None
            if stdin_fd is not None and not pending_input:
                # Nothing to send: give the child EOF immediately.
                try:
                    stdin_stream.close()
                except OSError:
                    pass
                stdin_fd = None

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                timed_out = True
                break

            readable = []
            for stream in (proc.stdout, proc.stderr):
                if stream is None:
                    continue
                try:
                    stream.fileno()
                    readable.append(stream)
                except (OSError, TypeError, ValueError, AttributeError):
                    pass

            writable = [stdin_fd] if (stdin_fd is not None and pending_input) else []
            ready, written, _ = select.select(readable, writable, [], min(remaining, 1.0))

            # Feed the child's stdin from the same deadline-bounded loop so a
            # reader can never block the runner indefinitely (and a child that
            # never reads still hits the command timeout instead of hanging).
            if stdin_fd is not None and stdin_fd in written:
                try:
                    sent = os.write(stdin_fd, pending_input[:65536])
                    if sent > 0:
                        del pending_input[:sent]
                except (BlockingIOError, InterruptedError):
                    pass
                except OSError:
                    # Broken pipe: the child exited without consuming input.
                    pending_input.clear()
                if not pending_input:
                    try:
                        stdin_stream.close()
                    except OSError:
                        pass
                    stdin_fd = None

            for stream in ready:
                try:
                    raw = os.read(stream.fileno(), 64 * 1024)
                except (OSError, ValueError):
                    raw = b""
                if not raw:
                    continue
                if stream is proc.stdout:
                    if stdout_bytes + len(raw) > max_output_bytes:
                        stdout_chunks.append(b"\n<output truncated by runner cap>\n")
                        stdout_bytes = max_output_bytes
                        continue
                    stdout_chunks.append(raw)
                    stdout_bytes += len(raw)
                else:
                    if stderr_bytes + len(raw) > max_output_bytes:
                        stderr_chunks.append(b"\n<output truncated by runner cap>\n")
                        stderr_bytes = max_output_bytes
                        continue
                    stderr_chunks.append(raw)
                    stderr_bytes += len(raw)

            proc_ready = False
            try:
                proc_ready = proc.poll() is not None
            except (OSError, ValueError):
                proc_ready = True

            if proc_ready:
                break

        if stdin_fd is not None and stdin_stream is not None:
            try:
                stdin_stream.close()
            except OSError:
                pass

        if timed_out:
            _terminate_process_group(proc.pid, deadline - time.time())

        stdout_data = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr_data = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        try:
            returncode = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _terminate_process_group(proc.pid, 5.0)
            proc.wait(timeout=5)
            returncode = proc.returncode

        duration_ms = round((time.time() - start) * 1000, 3)
        if timed_out:
            stdout_data += f"\n<runner command timed out after {timeout_seconds}s>"
            stderr_data += f"\n<runner command timed out after {timeout_seconds}s>"

        return returncode, stdout_data, stderr_data, duration_ms
    except BaseException:
        try:
            _terminate_process_group(proc.pid, 2.0)
            proc.wait(timeout=2)
        except Exception:
            pass
        raise


def _terminate_process_group(pid: int, grace_seconds: float) -> None:
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        pass
    deadline = time.time() + max(grace_seconds, 0.0)
    while time.time() < deadline and _process_alive(pid):
        time.sleep(0.1)

    if _process_alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.2)


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _run_cmd(cmd: list[str]) -> tuple[int, str, str, float]:
    start = time.time()
    proc = subprocess.run(
        cmd, capture_output=True, text=True, check=False, env=_child_env()
    )
    duration_ms = round((time.time() - start) * 1000, 3)
    return proc.returncode, proc.stdout, proc.stderr, duration_ms


def _ensure_within_root(path: Path, root: Path) -> None:
    resolved = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Path escapes storage root"
        ) from exc


from botocore.client import Config

def _download_s3_artifact(s3_uri: str, local_dir: Path):
    if _s3_download_complete(local_dir):
        return

    token = os.urandom(8).hex()
    partial_dir = local_dir.with_name(f"{local_dir.name}.partial-{token}")

    try:
        _download_s3_into(partial_dir, s3_uri)
        _mark_s3_download_complete(partial_dir)
        _safe_replace_dir(partial_dir, local_dir)
    except BaseException:
        try:
            _attempt_remove_dir(partial_dir)
        except OSError:
            pass
        raise


def _safe_replace_dir(src: Path, dst: Path) -> None:
    """Atomically move `src` onto `dst`, removing `dst` if needed."""
    if dst.exists():
        _attempt_remove_dir(dst)
    try:
        os.replace(src, dst)
    except OSError:
        # Best-effort cleanup of the source if the replace itself fails.
        try:
            _attempt_remove_dir(src)
        except OSError:
            pass
        raise


def _s3_download_complete(local_dir: Path) -> bool:
    marker = local_dir / ".s3_download_complete"
    if not marker.exists():
        return False
    try:
        marker_text = marker.read_text(encoding="utf-8")
        marker_data = json.loads(marker_text)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(marker_data, dict):
        return False
    try:
        downloaded_at = datetime.fromisoformat(marker_data.get("downloaded_at", ""))
    except (TypeError, ValueError):
        return False
    if datetime.now() - downloaded_at > RELIBILITY_STALE_THRESHOLD:
        return False
    return True


def _download_s3_into(local_dir: Path, s3_uri: str) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip('/')

    access_key, secret_key = _storage_credentials()
    if not access_key or not secret_key:
        raise HTTPException(
            status_code=500,
            detail=f"artifact storage credentials are not configured "
            f"({STORAGE_ACCESS_KEY_ENV}/{STORAGE_SECRET_KEY_ENV})",
        )

    s3_client = boto3.client(
        's3',
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(s3={'addressing_style': 'path'})
    )

    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' not in page:
            continue
        for obj in page['Contents']:
            key = obj['Key']
            rel_path = os.path.relpath(key, prefix)
            target_path = local_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            s3_client.download_file(bucket, key, str(target_path))


def _mark_s3_download_complete(local_dir: Path) -> None:
    marker = local_dir / ".s3_download_complete"
    marker.write_text(
        json.dumps({"downloaded_at": datetime.now().isoformat()}),
        encoding="utf-8",
    )


def _attempt_remove_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            _attempt_remove_dir(child)
        else:
            try:
                child.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        path.rmdir()
    except OSError:
        pass


@app.get("/health")
def health():
    # Liveness only, on purpose: it exposes no model or storage state and is used
    # by container/orchestrator probes. Model readiness is a separate concern
    # (REL-04) and lives behind authentication with the other runner routes.
    return {"status": "ok"}


@app.post("/init-model", dependencies=[Depends(require_runner_auth)])
def init_model(req: InitModelRequest):
    acquired = _build_semaphore.acquire(blocking=True, timeout=10.0)
    if not acquired:
        raise HTTPException(
            status_code=503,
            detail={
                "code": RUNNER_CODE_CAPACITY_EXHAUSTED,
                "error": "runner build capacity exhausted",
                "retryable": True,
            },
        )

    try:
        if req.manifest_path.startswith("s3://"):
            artifact_uri = req.manifest_path.rsplit('/', 1)[0]
            local_model_dir = MODELS_ROOT / req.model_id
            try:
                _download_s3_artifact(artifact_uri, local_model_dir)
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": RUNNER_CODE_STORAGE_UNAVAILABLE,
                        "error": f"artifact download failed: {exc}",
                        "retryable": True,
                    },
                ) from exc
            manifest_path = local_model_dir / "model.yaml"
        else:
            manifest_path = Path(req.manifest_path)

        _ensure_within_root(manifest_path, MODELS_ROOT)

        if not manifest_path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "code": RUNNER_CODE_INVALID_MANIFEST,
                    "error": "manifest not found",
                    "retryable": False,
                },
            )

        env_dir = ENVS_ROOT / req.model_id

        manifest_text, _mtime = _read_manifest(manifest_path)
        manifest = _parse_manifest(manifest_text)

        requirements = manifest.get("requirements")
        if not requirements:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": RUNNER_CODE_INVALID_REQUIREMENTS,
                    "error": "requirements missing in manifest",
                    "retryable": False,
                },
            )

        requirements_path = (manifest_path.parent / requirements).resolve()
        _ensure_within_root(requirements_path, MODELS_ROOT)
        if not requirements_path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "code": RUNNER_CODE_INVALID_REQUIREMENTS,
                    "error": "requirements file not found",
                    "retryable": False,
                },
            )

        env_dir.mkdir(parents=True, exist_ok=True)

        venv_cmd = [
            "uv",
            "venv",
            "--system-site-packages",
            "--python",
            sys.executable,
            str(env_dir),
        ]
        code, out, err, duration_ms = _run_bounded(
            venv_cmd,
            timeout_seconds=RUNNER_INIT_TIMEOUT_SECONDS,
            max_output_bytes=RUNNER_MAX_OUTPUT_BYTES,
        )
        if code != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE,
                    "error": "venv creation failed",
                    "stderr": err,
                    "retryable": False,
                },
            )

        python_bin = env_dir / "bin" / "python"
        pip_cmd = [
            "uv",
            "pip",
            "install",
            "--index-strategy",
            "unsafe-best-match",
            "--extra-index-url",
            "https://download.pytorch.org/whl/cpu",
            "-r",
            str(requirements_path),
            "--python",
            str(python_bin),
        ]
        code, out, err, pip_ms = _run_bounded(
            pip_cmd,
            timeout_seconds=RUNNER_INIT_TIMEOUT_SECONDS,
            max_output_bytes=RUNNER_MAX_OUTPUT_BYTES,
        )
        if code != 0:
            retryable = _pip_stderr_is_retryable(err)
            err_code = (
                RUNNER_CODE_WORKER_UNAVAILABLE
                if retryable
                else RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE
            )
            raise HTTPException(
                status_code=(503 if retryable else 500),
                detail={
                    "code": err_code,
                    "error": "pip install failed",
                    "stderr": err,
                    "retryable": retryable,
                },
            )

        # REL-04: Validate model loading (and smoke test if specified)
        framework = manifest.get("framework", "sklearn") if isinstance(manifest, dict) else "sklearn"
        bridge_name = BRIDGE_MAP.get(framework)
        if not bridge_name:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": RUNNER_CODE_UNSUPPORTED_FRAMEWORK,
                    "error": f"unsupported framework: {framework}",
                    "retryable": False,
                },
            )
        bridge_path = Path(__file__).resolve().parent / bridge_name
        if not bridge_path.exists():
            raise HTTPException(
                status_code=500,
                detail={
                    "code": RUNNER_CODE_INTERNAL,
                    "error": f"bridge script missing: {bridge_name}",
                    "retryable": False,
                },
            )

        model_artifact = manifest.get("model_artifact")
        val_ms = 0.0
        readiness_mode = "environment_only"

        if model_artifact:
            artifact_path = (manifest_path.parent / model_artifact).resolve()
            _ensure_within_root(artifact_path, MODELS_ROOT)
            if not artifact_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": RUNNER_CODE_MISSING_ARTIFACT,
                        "error": "model artifact file not found",
                        "retryable": False,
                    },
                )

            smoke_input = manifest.get("smoke_test_input")
            val_payload: dict[str, Any] = {"validate_only": True}
            readiness_mode = "loaded"
            if smoke_input:
                val_payload = {"instances": smoke_input}
                readiness_mode = "loaded+smoke"

            val_cmd = [str(python_bin), str(bridge_path), str(manifest_path)]
            val_code, val_out, val_err, val_ms = _run_bounded(
                val_cmd,
                timeout_seconds=RUNNER_PREDICT_TIMEOUT_SECONDS,
                input_bytes=json.dumps(val_payload).encode("utf-8"),
                max_output_bytes=RUNNER_MAX_OUTPUT_BYTES,
            )
            if val_code != 0:
                err_code = (
                    RUNNER_CODE_SMOKE_CHECK_FAILED
                    if smoke_input
                    else RUNNER_CODE_MODEL_LOAD_FAILED
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "code": err_code,
                        "error": f"model validation failed: {val_err.strip() or 'unknown error'}",
                        "stderr": val_err,
                        "retryable": False,
                    },
                )

        return {
            "status": "ready",
            "readiness": readiness_mode,
            "venv_ms": duration_ms,
            "pip_ms": pip_ms,
            "validation_ms": val_ms,
            "action": "none",
        }
    finally:
        _build_semaphore.release()


def _predict_envelope(python_bin: Path) -> dict[str, Any]:
    """Extra envelope for predict workers that need a deterministic runtime path."""
    return {"env": {"RUNNER_PYTHON": str(python_bin)}}


BRIDGE_MAP = {
    "sklearn": "worker_bridge.py",
    "pytorch": "pytorch_bridge.py",
}


# ---------------------------------------------------------------------------
# PERF-01: Warm Model Runtime Manager
# ---------------------------------------------------------------------------


class WarmRuntimeState(str, Enum):
    STARTING = "STARTING"
    READY = "READY"
    UNHEALTHY = "UNHEALTHY"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class WarmRuntime:
    def __init__(self, model_id: str, manifest_path: Path, python_bin: Path, bridge_path: Path):
        self.model_id = model_id
        self.manifest_path = manifest_path
        self.python_bin = python_bin
        self.bridge_path = bridge_path
        self.state = WarmRuntimeState.STARTING
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.last_used_at = time.time()
        self.restart_count = 0
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail = bytearray()

    def _drain_stderr(self) -> None:
        proc = self.proc
        if proc is None or proc.stderr is None:
            return
        while True:
            try:
                chunk = os.read(proc.stderr.fileno(), 8192)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            self._stderr_tail.extend(chunk)
            if len(self._stderr_tail) > RUNNER_MAX_OUTPUT_BYTES:
                del self._stderr_tail[:-RUNNER_MAX_OUTPUT_BYTES]

    def _readline_bounded(self, timeout_seconds: float, max_bytes: int) -> bytes:
        proc = self.proc
        if proc is None or proc.stdout is None:
            raise RuntimeError("Warm runtime stdout is unavailable")
        fd = proc.stdout.fileno()
        deadline = time.monotonic() + timeout_seconds
        line = bytearray()
        while len(line) <= max_bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Warm runtime response timed out")
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                raise TimeoutError("Warm runtime response timed out")
            chunk = os.read(fd, min(4096, max_bytes + 1 - len(line)))
            if not chunk:
                raise RuntimeError("Warm runtime closed stdout unexpectedly")
            newline = chunk.find(b"\n")
            if newline >= 0:
                if len(line) + newline > max_bytes:
                    raise RuntimeError("Warm runtime output exceeded configured limit")
                line.extend(chunk[:newline])
                return bytes(line)
            line.extend(chunk)
        raise RuntimeError("Warm runtime output exceeded configured limit")

    def _write_bounded(self, payload: bytes, timeout_seconds: float) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("Warm runtime stdin is unavailable")
        fd = proc.stdin.fileno()
        view = memoryview(payload)
        deadline = time.monotonic() + timeout_seconds
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Warm runtime request pipe write timed out")
            _, writable, _ = select.select([], [fd], [], remaining)
            if not writable:
                raise TimeoutError("Warm runtime request pipe write timed out")
            written = os.write(fd, view[:65536])
            view = view[written:]

    def start(self) -> None:
        self.state = WarmRuntimeState.STARTING
        cmd = [str(self.python_bin), str(self.bridge_path), str(self.manifest_path), "--serve-ipc"]
        self._stderr_tail.clear()
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_child_env(),
                start_new_session=True,
                text=False,
                close_fds=True,
            )
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, name=f"warm-stderr-{self.model_id}", daemon=True
            )
            self._stderr_thread.start()
            ready_line = self._readline_bounded(
                RUNNER_HEALTHCHECK_TIMEOUT_SECONDS, RUNNER_MAX_OUTPUT_BYTES
            )
            ready = json.loads(ready_line.decode("utf-8"))
            if ready.get("status") != "ready":
                raise RuntimeError("Warm runtime returned an invalid readiness frame")
            self.state = WarmRuntimeState.READY
            self.last_used_at = time.time()
        except Exception:
            self.state = WarmRuntimeState.UNHEALTHY
            self.stop()
            raise

    def predict(self, instances: list) -> dict[str, Any]:
        with self.lock:
            self.last_used_at = time.time()
            if self.state != WarmRuntimeState.READY or self.proc is None or self.proc.poll() is not None:
                if self.restart_count < 3:
                    self.restart_count += 1
                    logger.warning("Warm runtime for model %s crashed; restarting (attempt %s)", self.model_id, self.restart_count)
                    self.stop()
                    self.start()
                else:
                    self.state = WarmRuntimeState.UNHEALTHY
                    raise RuntimeError("Warm runtime UNHEALTHY (max restarts exceeded)")

            try:
                payload_line = json.dumps({"instances": instances}, separators=(",", ":")).encode("utf-8") + b"\n"
                if len(payload_line) > RUNNER_MAX_OUTPUT_BYTES:
                    raise RuntimeError("Warm runtime request exceeded configured limit")
                self._write_bounded(payload_line, RUNNER_PREDICT_TIMEOUT_SECONDS)
                out_line = self._readline_bounded(
                    RUNNER_PREDICT_TIMEOUT_SECONDS, RUNNER_MAX_OUTPUT_BYTES
                )
                result = json.loads(out_line.decode("utf-8"))
                if not isinstance(result, dict):
                    raise RuntimeError("Warm runtime returned a non-object response")
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
                return result
            except Exception:
                self.state = WarmRuntimeState.UNHEALTHY
                self.stop()
                raise

    def stop(self) -> None:
        self.state = WarmRuntimeState.STOPPING
        proc = self.proc
        if proc is not None:
            try:
                _terminate_process_group(proc.pid, 0.2)
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
            self.proc = None
        if self._stderr_thread is not None and self._stderr_thread is not threading.current_thread():
            self._stderr_thread.join(timeout=1)
        self._stderr_thread = None
        self.state = WarmRuntimeState.STOPPED


class WarmRuntimeManager:
    def __init__(self, max_models: int = 5):
        self.max_models = max_models
        self.runtimes: dict[str, WarmRuntime] = {}
        self.lock = threading.Lock()

    def get_or_create(self, model_id: str, manifest_path: Path, python_bin: Path, bridge_path: Path) -> WarmRuntime:
        with self.lock:
            if model_id in self.runtimes:
                rt = self.runtimes[model_id]
                if rt.state == WarmRuntimeState.READY and rt.proc is not None and rt.proc.poll() is None:
                    return rt
                rt.stop()
                del self.runtimes[model_id]

            # LRU eviction
            if len(self.runtimes) >= self.max_models:
                lru_id = min(self.runtimes, key=lambda k: self.runtimes[k].last_used_at)
                logger.info("Evicting LRU warm runtime: %s", lru_id)
                self.runtimes[lru_id].stop()
                del self.runtimes[lru_id]

            rt = WarmRuntime(model_id, manifest_path, python_bin, bridge_path)
            rt.start()
            self.runtimes[model_id] = rt
            return rt

    def stop_runtime(self, model_id: str) -> None:
        with self.lock:
            if model_id in self.runtimes:
                self.runtimes[model_id].stop()
                del self.runtimes[model_id]

    def clear(self) -> None:
        with self.lock:
            for rt in self.runtimes.values():
                rt.stop()
            self.runtimes.clear()


warm_runtime_manager = WarmRuntimeManager(RUNNER_MAX_WARM_MODELS)


@app.post("/predict", dependencies=[Depends(require_runner_auth)])
def predict(req: PredictRequest):
    acquired = _predict_semaphore.acquire(blocking=True, timeout=5.0)
    if not acquired:
        raise HTTPException(
            status_code=503,
            detail={
                "code": RUNNER_CODE_CAPACITY_EXHAUSTED,
                "error": "runner predict capacity exhausted",
                "retryable": True,
            },
        )

    try:
        if req.manifest_path.startswith("s3://"):
            artifact_uri = req.manifest_path.rsplit('/', 1)[0]
            local_model_dir = MODELS_ROOT / req.model_id
            _download_s3_artifact(artifact_uri, local_model_dir)
            manifest_path = local_model_dir / "model.yaml"
        else:
            manifest_path = Path(req.manifest_path)

        _ensure_within_root(manifest_path, MODELS_ROOT)

        if not manifest_path.exists():
            raise HTTPException(
                status_code=404,
                detail={
                    "code": RUNNER_CODE_INVALID_MANIFEST,
                    "error": "manifest not found",
                    "retryable": False,
                },
            )

        env_dir = ENVS_ROOT / req.model_id
        python_bin = env_dir / "bin" / "python"
        if not python_bin.exists():
            raise HTTPException(
                status_code=400,
                detail={
                    "code": RUNNER_CODE_INTERNAL,
                    "error": "environment not initialized",
                    "retryable": False,
                },
            )

        bridge_root = Path(__file__).resolve().parent

        manifest_text, _mtime = _read_manifest(manifest_path)
        manifest = _parse_manifest(manifest_text)
        framework = manifest.get("framework", "sklearn") if isinstance(manifest, dict) else "sklearn"
        bridge_name = BRIDGE_MAP.get(framework)

        if not bridge_name:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": RUNNER_CODE_UNSUPPORTED_FRAMEWORK,
                    "error": f"unsupported framework: {framework}",
                    "retryable": False,
                },
            )

        bridge_path = bridge_root / bridge_name
        if not bridge_path.exists():
            raise HTTPException(
                status_code=500,
                detail={
                    "code": RUNNER_CODE_INTERNAL,
                    "error": f"bridge script missing: {bridge_name}",
                    "retryable": False,
                },
            )

        # PERF-01: Persistent warm runtime path
        if RUNNER_WARM_RUNTIME_ENABLED:
            try:
                t0 = time.time()
                rt = warm_runtime_manager.get_or_create(
                    req.model_id, manifest_path, python_bin, bridge_path
                )
                pred_data = rt.predict(req.instances)
                dur_ms = round((time.time() - t0) * 1000, 3)
                pred_data.setdefault("metadata", {})
                pred_data["metadata"]["compute_ms"] = dur_ms
                pred_data["metadata"]["runtime_mode"] = "warm"
                return pred_data
            except Exception as exc:
                logger.warning("Warm runtime predict failed for model %s: %s", req.model_id, exc)
                raise HTTPException(
                    status_code=504 if isinstance(exc, TimeoutError) else 503,
                    detail={
                        "code": RUNNER_CODE_WORKER_TIMEOUT if isinstance(exc, TimeoutError) else RUNNER_CODE_WORKER_UNAVAILABLE,
                        "error": "warm runtime failed; child was terminated",
                        "retryable": True,
                    },
                ) from exc

        # Rollback / fallback path: bounded process-per-request
        cmd = [str(python_bin), str(bridge_path), str(manifest_path)]
        payload = {"instances": req.instances}
        payload.update(_predict_envelope(python_bin))

        start = time.time()
        proc_input = json.dumps(payload).encode("utf-8")
        code, out, err, duration_ms = _run_bounded(
            cmd,
            timeout_seconds=RUNNER_PREDICT_TIMEOUT_SECONDS,
            input_bytes=proc_input,
            max_output_bytes=RUNNER_MAX_OUTPUT_BYTES,
        )

        if code != 0:
            retryable = _inference_stderr_is_retryable(err)
            err_code = (
                RUNNER_CODE_WORKER_TIMEOUT
                if "timed out" in err
                else (RUNNER_CODE_WORKER_UNAVAILABLE if retryable else RUNNER_CODE_INTERNAL)
            )
            raise HTTPException(
                status_code=(503 if retryable else 500),
                detail={
                    "code": err_code,
                    "error": "inference failed",
                    "stderr": err.strip(),
                    "retryable": retryable,
                },
            )

        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": RUNNER_CODE_INTERNAL,
                    "error": "bridge returned invalid json",
                    "retryable": False,
                },
            ) from exc

        data.setdefault("metadata", {})
        data["metadata"]["compute_ms"] = duration_ms
        return data
    finally:
        _predict_semaphore.release()


@app.post("/teardown", dependencies=[Depends(require_runner_auth)])
def teardown(req: TeardownRequest):
    warm_runtime_manager.stop_runtime(req.model_id)
    env_dir = ENVS_ROOT / req.model_id
    _ensure_within_root(env_dir, ENVS_ROOT)

    if env_dir.exists():
        _attempt_remove_dir(env_dir)

    return {"status": "deleted"}


@app.get("/metrics/live")
def live_metrics():
    # Lightweight health endpoint that does not touch storage or the database.
    # Used by the API/outer health checks (REL-10) without coupling the API to
    # inference or artifact state.
    return {
        "alive": True,
        "warm_runtimes": {
            "count": len(warm_runtime_manager.runtimes),
            "max": warm_runtime_manager.max_models,
            "models": list(warm_runtime_manager.runtimes.keys()),
        },
        "concurrency": {
            "build_current": RUNNER_MAX_CONCURRENT_BUILDS - _build_semaphore._value,
            "build_max": RUNNER_MAX_CONCURRENT_BUILDS,
            "prediction_current": RUNNER_MAX_CONCURRENT_PREDICTIONS - _predict_semaphore._value,
            "prediction_max": RUNNER_MAX_CONCURRENT_PREDICTIONS,
        },
        "timeout_seconds": {
            "init": RUNNER_INIT_TIMEOUT_SECONDS,
            "predict": RUNNER_PREDICT_TIMEOUT_SECONDS,
            "healthcheck": RUNNER_HEALTHCHECK_TIMEOUT_SECONDS,
            "command": RUNNER_COMMAND_TIMEOUT_SECONDS,
        },
    }

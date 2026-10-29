"""Endpoint-level tests for runner authentication (SEC-02).

The runner is a plain ASGI app, so these tests drive it through the real routing
and dependency stack instead of calling the view functions directly. `httpx`
(and therefore `fastapi.testclient`) is not a dependency of this project, so the
request is issued with a small in-process ASGI helper.
"""

from __future__ import annotations

import json
import os
import sys

import anyio
import pytest
from fastapi import HTTPException

# The runner reads its credential at import time, so set it before importing.
os.environ.setdefault("RUNNER_AUTH_TOKEN", "unit-test-runner-token")

from runners import worker  # noqa: E402
from runners.auth import DEFAULT_AUTH_HEADER  # noqa: E402

TOKEN = os.environ["RUNNER_AUTH_TOKEN"]
AUTH_HEADERS = {DEFAULT_AUTH_HEADER: TOKEN}

VALID_BODIES = {
    "/init-model": {"model_id": "m1", "manifest_path": "/storage/models/m1/model.yaml"},
    "/predict": {
        "model_id": "m1",
        "manifest_path": "/storage/models/m1/model.yaml",
        "instances": [{"x": 1}],
    },
    "/teardown": {"model_id": "m1"},
}


def call_app(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    """Issue one request against the runner ASGI app and return (status, body)."""
    status, body, _raw_body = call_app_with_raw_body(
        method, path, json_body=json_body, headers=headers
    )
    return status, body


def call_app_with_raw_body(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object, bytes]:
    """Issue one request against the runner ASGI app and return (status, body, raw_body)."""
    body_bytes = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    if json_body is not None:
        raw_headers.append((b"content-type", b"application/json"))
        raw_headers.append((b"content-length", str(len(body_bytes)).encode()))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    sent: list[dict] = []
    received = False

    async def receive() -> dict:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def run() -> None:
        await worker.app(scope, receive, send)

    anyio.run(run)

    start = next(m for m in sent if m["type"] == "http.response.start")
    raw_body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    return start["status"], (json.loads(raw_body) if raw_body else None), raw_body


class TestUnauthenticatedRequests:
    @pytest.mark.parametrize("path", sorted(VALID_BODIES))
    def test_missing_credentials_are_rejected(self, path):
        status, body = call_app("POST", path, json_body=VALID_BODIES[path])
        assert status == 401
        assert body["detail"] == "missing or invalid runner credentials"

    @pytest.mark.parametrize("path", sorted(VALID_BODIES))
    def test_wrong_credentials_are_rejected(self, path):
        status, _ = call_app(
            "POST",
            path,
            json_body=VALID_BODIES[path],
            headers={DEFAULT_AUTH_HEADER: "not-the-token"},
        )
        assert status == 401

    @pytest.mark.parametrize("path", sorted(VALID_BODIES))
    def test_empty_credentials_are_rejected(self, path):
        status, _ = call_app(
            "POST", path, json_body=VALID_BODIES[path], headers={DEFAULT_AUTH_HEADER: ""}
        )
        assert status == 401

    def test_rejection_happens_before_any_subprocess_runs(self, monkeypatch):
        calls: list[tuple] = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("subprocess must not run for a rejected request")

        monkeypatch.setattr(worker.subprocess, "run", spy)

        status, _ = call_app("POST", "/init-model", json_body=VALID_BODIES["/init-model"])

        assert status == 401
        assert calls == []


class TestAuthenticatedRequests:
    def test_health_stays_a_public_liveness_probe(self):
        status, body = call_app("GET", "/health")
        assert status == 200
        assert body == {"status": "ok"}

    def test_authorized_teardown_succeeds(self):
        status, body = call_app(
            "POST", "/teardown", json_body=VALID_BODIES["/teardown"], headers=AUTH_HEADERS
        )
        assert status == 200
        assert body == {"status": "deleted"}

    def test_authorized_request_reaches_the_handler(self, monkeypatch, tmp_path):
        """Authorised requests reach the handler. The test isolates auth from the
        subprocess and storage paths, which is the behaviour this class targets."""
        writable_root = tmp_path / "storage"
        writable_root.mkdir()

        models_root = writable_root / "models"
        model_dir = models_root / "m1"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text("framework: sklearn\nrequirements: requirements.txt\n", encoding="utf-8")
        (model_dir / "requirements.txt").write_text("", encoding="utf-8")

        monkeypatch.setattr(worker, "DEFAULT_STORAGE", writable_root)
        monkeypatch.setattr(worker, "MODELS_ROOT", writable_root / "models")
        monkeypatch.setattr(worker, "ENVS_ROOT", writable_root / "envs")
        monkeypatch.setattr(worker, "RUNNER_INIT_TIMEOUT_SECONDS", 1)
        monkeypatch.setenv("UV_CACHE_DIR", str(writable_root / "uv-cache"))
        monkeypatch.setenv("HOME", str(writable_root))
        monkeypatch.setenv("UV_SYSTEM_PYTHON", "1")
        monkeypatch.setenv("UV_DEFAULT_PYTHON", sys.executable)
        monkeypatch.setenv("VIRTUAL_ENV", str(writable_root / "envs" / "m1"))
        monkeypatch.setenv("PYTHONPATH", str(writable_root))

        captured: dict[str, object] = {"popen_env": None, "popen_cmd": None}

        original_popen = worker.subprocess.Popen

        def _capturing_popen(cmd, *args, **kwargs):
            captured["popen_cmd"] = cmd
            captured["popen_env"] = kwargs.get("env")
            return original_popen(cmd, *args, **kwargs)

        monkeypatch.setattr(worker.subprocess, "Popen", _capturing_popen)

        status, body = call_app(
            "POST",
            "/init-model",
            json_body={
                "model_id": "m1",
                "manifest_path": str(writable_root / "models" / "m1" / "model.yaml"),
            },
            headers=AUTH_HEADERS,
        )

        # Authorised requests reach the handler with a real manifest; that proves
        # auth was accepted before any subprocess work. The subprocess env must
        # stay allowlisted and never leak the runner credential.
        assert status == 200, f"unexpected status={status!r}; body={body!r}"
        assert body["status"] == "ready"
        assert captured["popen_cmd"] is not None
        assert captured["popen_env"] is not None
        assert isinstance(captured["popen_env"], dict)
        assert "RUNNER_AUTH_TOKEN" not in captured["popen_env"]
        assert set(captured["popen_env"]) <= set(worker.CHILD_ENV_ALLOWLIST)


class TestSecretIsolationFromSubprocesses:
    def test_child_environment_is_a_fixed_allowlist(self, monkeypatch):
        monkeypatch.setenv("RUNNER_AUTH_TOKEN", "leaked-if-present")
        monkeypatch.setenv("MINIO_WORKER_PASSWORD", "leaked-if-present")
        monkeypatch.setenv("DJANGO_SECRET_KEY", "leaked-if-present")
        monkeypatch.setenv("POSTGRES_PASSWORD", "leaked-if-present")
        monkeypatch.setenv("REDIS_URL", "redis://user:pass@redis:6379/0")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        monkeypatch.setenv("RUNNER_TEST_UNRELATED", "not-allowlisted")

        env = worker._child_env()

        assert set(env) <= set(worker.CHILD_ENV_ALLOWLIST)
        assert env["PATH"] == "/usr/bin:/bin"
        for name in (
            "RUNNER_AUTH_TOKEN",
            "MINIO_WORKER_PASSWORD",
            "DJANGO_SECRET_KEY",
            "POSTGRES_PASSWORD",
            "REDIS_URL",
            "RUNNER_TEST_UNRELATED",
        ):
            assert name not in env, name
        # The runner process itself keeps its own credentials.
        assert os.environ["RUNNER_AUTH_TOKEN"] == "leaked-if-present"

    def test_bounded_subprocess_cannot_read_the_secret(self, monkeypatch):
        monkeypatch.setenv("RUNNER_AUTH_TOKEN", "leaked-if-present")
        captured: dict = {}

        class Completed:
            returncode = 0
            stdout = b""
            stderr = b""

            def wait(self, timeout=None):
                return self.returncode

            def poll(self):
                return self.returncode

            def fileno(self):
                raise TypeError("no fileno")

        def fake_popen(cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            return Completed()

        monkeypatch.setattr(worker.subprocess, "Popen", fake_popen)

        worker._run_bounded(["uv", "--version"], timeout_seconds=5)

        assert captured["env"], "subprocesses must receive an explicit environment"
        assert "RUNNER_AUTH_TOKEN" not in captured["env"]


class TestScopedStorageCredentials:
    """SEC-01: artifacts are fetched with a read-only identity, never root."""

    def test_download_uses_the_scoped_identity(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MINIO_WORKER_USER", "runner-user")
        monkeypatch.setenv("MINIO_WORKER_PASSWORD", "runner-secret")
        monkeypatch.setenv("MINIO_ROOT_USER", "root-user")
        monkeypatch.setenv("MINIO_ROOT_PASSWORD", "root-secret")

        captured = {}

        class FakePaginator:
            def paginate(self, Bucket, Prefix):
                captured["list"] = (Bucket, Prefix)
                return [{"Contents": []}]

        class FakeClient:
            def get_paginator(self, name):
                captured["paginator"] = name
                return FakePaginator()

        def fake_client(service, **kwargs):
            captured["service"] = service
            captured["kwargs"] = kwargs
            return FakeClient()

        monkeypatch.setattr(worker.boto3, "client", fake_client)

        worker._download_s3_artifact("s3://artifacts/model-1/v1", tmp_path / "download")

        assert captured["service"] == "s3"
        assert captured["kwargs"]["aws_access_key_id"] == "runner-user"
        assert captured["kwargs"]["aws_secret_access_key"] == "runner-secret"
        assert captured["list"] == ("artifacts", "model-1/v1")

    def test_partial_download_is_not_reused(self, tmp_path):
        partial = tmp_path / "partial-model"
        partial.mkdir()
        (partial / "stale").write_text("not a real download", encoding="utf-8")

        # A directory without the completion marker must not be treated as cached.
        assert not worker._s3_download_complete(partial)

    def test_completed_download_is_reused_only_with_valid_marker(self, tmp_path):
        completed = tmp_path / "complete-model"
        completed.mkdir()
        (completed / "artifact").write_text("real download", encoding="utf-8")
        worker._mark_s3_download_complete(completed)

        assert worker._s3_download_complete(completed)

    def test_completed_download_is_not_reused_after_marker_refresh(self, tmp_path):
        completed = tmp_path / "stale-model"
        completed.mkdir()
        (completed / "artifact").write_text("old download", encoding="utf-8")
        worker._mark_s3_download_complete(completed)

        # Corrupt the marker so the download is no longer treated as complete.
        (completed / ".s3_download_complete").write_text("{broken", encoding="utf-8")

        assert not worker._s3_download_complete(completed)

    def test_partial_download_recovery_does_not_leave_marked_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MINIO_WORKER_USER", "runner-user")
        monkeypatch.setenv("MINIO_WORKER_PASSWORD", "runner-secret")

        captured_kwargs: dict[str, object] = {}

        class FakePaginator:
            def paginate(self, Bucket, Prefix):
                return [{"Contents": []}]

        class FakeClient:
            def get_paginator(self, name):
                return FakePaginator()

            def download_file(self, Bucket, Key, Filename):
                captured_kwargs["key"] = Key
                captured_kwargs["filename"] = Filename

        def fake_client(service, **kwargs):
            captured_kwargs["service"] = service
            captured_kwargs["kwargs"] = kwargs
            return FakeClient()

        monkeypatch.setattr(worker.boto3, "client", fake_client)

        dest = tmp_path / "models" / "m1"
        worker._download_s3_artifact("s3://artifacts/model-1/v1", dest)

        assert captured_kwargs.get("service") == "s3"
        assert dest.exists()
        assert worker._s3_download_complete(dest)

    def test_partial_download_recovery_cleans_partial_dir_on_failure(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MINIO_WORKER_USER", "runner-user")
        monkeypatch.setenv("MINIO_WORKER_PASSWORD", "runner-secret")

        captured: dict[str, object] = {}

        class FakePaginator:
            def paginate(self, Bucket, Prefix):
                captured["page"] = (Bucket, Prefix)
                return [{"Contents": [{"Key": f"{Prefix}/model.yaml"}]}]

        class FakeClient:
            def get_paginator(self, name):
                captured["paginator"] = name
                return FakePaginator()

            def download_file(self, Bucket, Key, Filename):
                captured["download_file"] = (Bucket, Key, Filename)
                raise RuntimeError("simulated s3 failure")

        def fake_client(service, **kwargs):
            captured["service"] = service
            captured["kwargs"] = kwargs
            return FakeClient()

        monkeypatch.setattr(worker.boto3, "client", fake_client)

        dest = tmp_path / "models" / "m1"

        try:
            worker._download_s3_artifact("s3://artifacts/model-1/v1", dest)
        except (RuntimeError, HTTPException):
            pass
        else:
            pytest.fail("expected _download_s3_artifact to raise on simulated S3 failure")

        # On failure the partial download should be cleaned up, not marked complete.
        partial_candidates = list(tmp_path.glob("*.partial-*"))
        assert partial_candidates == [], f"unexpected partial dirs: {partial_candidates}"

    def test_download_fails_closed_without_scoped_credentials(
        self, monkeypatch, tmp_path
    ):
        from fastapi import HTTPException

        monkeypatch.setenv("MINIO_WORKER_USER", "")
        monkeypatch.setenv("MINIO_WORKER_PASSWORD", "")
        monkeypatch.setenv("MINIO_ROOT_USER", "root-user")
        monkeypatch.setenv("MINIO_ROOT_PASSWORD", "root-secret")

        with pytest.raises(HTTPException) as exc:
            worker._download_s3_artifact(
                "s3://artifacts/model-1/v1", tmp_path / "download"
            )

        assert exc.value.status_code == 500
        assert "MINIO_WORKER_USER" in str(exc.value.detail)

    def test_download_does_not_reuse_partial_dir(self, monkeypatch, tmp_path):
        partial = tmp_path / "partial-model"
        partial.mkdir()
        (partial / "stale").write_text("not a real download", encoding="utf-8")

        monkeypatch.setenv("MINIO_WORKER_USER", "runner-user")
        monkeypatch.setenv("MINIO_WORKER_PASSWORD", "runner-secret")

        captured_kwargs: dict[str, object] = {}

        class FakePaginator:
            def paginate(self, Bucket, Prefix):
                captured_kwargs["paginator_kwargs"] = (Bucket, Prefix)
                return [{"Contents": []}]

        class FakeClient:
            def get_paginator(self, name):
                captured_kwargs["paginator_name"] = name
                return FakePaginator()

            def download_file(self, Bucket, Key, Filename):
                captured_kwargs["downloaded"] = (Bucket, Key, Filename)

        def fake_client(service, **kwargs):
            captured_kwargs["client_kwargs"] = kwargs
            return FakeClient()

        monkeypatch.setattr(worker.boto3, "client", fake_client)

        worker._download_s3_artifact("s3://artifacts/model-1/v1", partial)

        # The stale partial dir should not be reused; a fresh (temp) download path
        # must be used, then renamed into place.
        assert captured_kwargs.get("client_kwargs", {}).get("aws_access_key_id") == "runner-user"
        assert (partial / ".s3_download_complete").exists()
        assert not (partial / "stale").exists()

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Deterministic model/package errors. These are **not** retried automatically by
# the deployment build path; they indicate the requested model/artifact is invalid
# or incompatible for this runtime, not that the worker was briefly unavailable.
RUNNER_CODE_INVALID_MANIFEST = "RUNNER_INVALID_MANIFEST"
RUNNER_CODE_UNSUPPORTED_FRAMEWORK = "RUNNER_UNSUPPORTED_FRAMEWORK"
RUNNER_CODE_MISSING_ARTIFACT = "RUNNER_MISSING_ARTIFACT"
RUNNER_CODE_INVALID_REQUIREMENTS = "RUNNER_INVALID_REQUIREMENTS"
RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE = "RUNNER_DETERMINISTIC_INSTALL_FAILURE"
RUNNER_CODE_MODEL_LOAD_FAILED = "RUNNER_MODEL_LOAD_FAILED"
RUNNER_CODE_SMOKE_CHECK_FAILED = "RUNNER_SMOKE_CHECK_FAILED"
RUNNER_CODE_INVALID_INPUT = "RUNNER_INVALID_INPUT"

# Transient infrastructure / temporary-unavailability errors. These may be retried
# within the bounded deployment retry policy.
RUNNER_CODE_WORKER_UNAVAILABLE = "RUNNER_WORKER_UNAVAILABLE"
RUNNER_CODE_STORAGE_UNAVAILABLE = "RUNNER_STORAGE_UNAVAILABLE"
RUNNER_CODE_WORKER_TIMEOUT = "RUNNER_WORKER_TIMEOUT"
RUNNER_CODE_CAPACITY_EXHAUSTED = "RUNNER_CAPACITY_EXHAUSTED"

# Generic fallback for unexpected runner errors that does not declare retryability.
RUNNER_CODE_INTERNAL = "RUNNER_INTERNAL"


@dataclass(frozen=True)
class RunnerError:
    """A structured runner failure suitable for mapping to deployment behavior.

    The runner API returns these as JSON with ``code``/``message`` shapes. The
    control plane maps ``retryable`` and the error code to retryable vs
    non-retryable deployment failures and stores a compact diagnostic reference
    rather than the full payload in public responses.
    """

    code: str
    message: str
    retryable: bool
    request_id: str | None = None
    diagnostics: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        payload = {
            "code": self.code,
            "message": self.message,
        }
        if self.request_id:
            payload["request_id"] = self.request_id
        if self.diagnostics:
            payload["diagnostics"] = self.diagnostics
        return payload

    @classmethod
    def from_runner_payload(cls, payload: dict, request_id: str | None = None) -> RunnerError:
        """Best-effort decoding of a runner JSON error payload.

        Runners may return ``{"code":..., "message":...}`` already. When they do
        not, we still keep a stable shape so the control plane can classify and
        log without exposing raw internals to the client.
        """
        code = payload.get("code") or payload.get("error") or RUNNER_CODE_INTERNAL
        message = payload.get("message") or payload.get("detail") or ""
        diagnostics = {k: v for k, v in payload.items() if k not in {"code", "message", "error", "detail", "request_id"}}
        return cls(
            code=str(code),
            message=str(message) if message else "runner error",
            retryable=False,
            request_id=request_id,
            diagnostics=diagnostics or None,
        )

    @classmethod
    def invalid_manifest(cls, message: str = "manifest is invalid", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_INVALID_MANIFEST, message=message, retryable=False, request_id=request_id)

    @classmethod
    def unsupported_framework(cls, framework: str, request_id: str | None = None) -> RunnerError:
        return cls(
            code=RUNNER_CODE_UNSUPPORTED_FRAMEWORK,
            message=f"unsupported framework: {framework}",
            retryable=False,
            request_id=request_id,
        )

    @classmethod
    def missing_artifact(cls, message: str = "model artifact not found", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_MISSING_ARTIFACT, message=message, retryable=False, request_id=request_id)

    @classmethod
    def invalid_requirements(cls, message: str = "requirements are invalid", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_INVALID_REQUIREMENTS, message=message, retryable=False, request_id=request_id)

    @classmethod
    def deterministic_install_failure(cls, message: str = "dependency installation failed", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE, message=message, retryable=False, request_id=request_id)

    @classmethod
    def model_load_failed(cls, message: str = "model failed to load", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_MODEL_LOAD_FAILED, message=message, retryable=False, request_id=request_id)

    @classmethod
    def smoke_check_failed(cls, message: str = "smoke prediction did not pass", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_SMOKE_CHECK_FAILED, message=message, retryable=False, request_id=request_id)

    @classmethod
    def invalid_input(cls, message: str = "prediction input is invalid", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_INVALID_INPUT, message=message, retryable=False, request_id=request_id)

    @classmethod
    def worker_unavailable(cls, message: str = "runner is unavailable", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_WORKER_UNAVAILABLE, message=message, retryable=True, request_id=request_id)

    @classmethod
    def storage_unavailable(cls, message: str = "artifact storage is unavailable", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_STORAGE_UNAVAILABLE, message=message, retryable=True, request_id=request_id)

    @classmethod
    def worker_timeout(cls, message: str = "runner action timed out", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_WORKER_TIMEOUT, message=message, retryable=True, request_id=request_id)

    @classmethod
    def capacity_exhausted(cls, message: str = "runner capacity exhausted", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_CAPACITY_EXHAUSTED, message=message, retryable=True, request_id=request_id)

    @classmethod
    def internal(cls, message: str = "unexpected runner error", request_id: str | None = None) -> RunnerError:
        return cls(code=RUNNER_CODE_INTERNAL, message=message, retryable=False, request_id=request_id)


# Non-retryable codes as a quick reference for the control plane.
NON_RETRYABLE_CODES = {
    RUNNER_CODE_INVALID_MANIFEST,
    RUNNER_CODE_UNSUPPORTED_FRAMEWORK,
    RUNNER_CODE_MISSING_ARTIFACT,
    RUNNER_CODE_INVALID_REQUIREMENTS,
    RUNNER_CODE_DETERMINISTIC_INSTALL_FAILURE,
    RUNNER_CODE_MODEL_LOAD_FAILED,
    RUNNER_CODE_SMOKE_CHECK_FAILED,
    RUNNER_CODE_INVALID_INPUT,
    RUNNER_CODE_INTERNAL,
}

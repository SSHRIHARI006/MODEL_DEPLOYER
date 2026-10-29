"""Shared-secret authentication for the internal runner HTTP API (SEC-02).

This module is deliberately free of Django (and any project) imports: it is used
by the FastAPI runner process, which verifies the credential, and by the Django
control plane, which sends it. The runner must stay importable without a
configured Django project.

The credential is a single shared secret sent in a header. It is only a service
credential between two internal components; it is not a user credential and must
never reach model code or dependency-installation subprocesses.
"""

from __future__ import annotations

import secrets

DEFAULT_AUTH_HEADER = "X-Runner-Token"
ALLOW_UNAUTHENTICATED_ENV = "RUNNER_ALLOW_UNAUTHENTICATED"


class RunnerAuthConfigurationError(RuntimeError):
    """Runner authentication is required but no shared secret is configured."""


def resolve_auth_token(raw: str | None) -> str:
    """Normalise a token read from the environment (whitespace is not a secret)."""
    return (raw or "").strip()


def is_unauthenticated_allowed(raw: str | None) -> bool:
    """Whether the explicit development-only opt-out is enabled."""
    return (raw or "").strip().lower() == "true"


def auth_headers(token: str, header: str = DEFAULT_AUTH_HEADER) -> dict[str, str]:
    """Headers a control-plane client must send for a protected runner route.

    Returns an empty mapping when no token is configured; the runner then rejects
    the call, so a misconfigured client fails closed instead of calling anonymously.
    """
    token = resolve_auth_token(token)
    if not token:
        return {}
    return {header or DEFAULT_AUTH_HEADER: token}


def verify_token(provided: str | None, expected: str) -> bool:
    """Constant-time comparison so the secret cannot be probed byte by byte."""
    expected = resolve_auth_token(expected)
    if not expected or provided is None:
        return False
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def check_auth_configuration(
    *,
    token: str,
    debug: bool = False,
    allow_unauthenticated: bool = False,
    service: str,
) -> None:
    """Fail closed when the shared secret is missing outside development.

    ``debug``/``allow_unauthenticated`` are the only accepted escape hatches and
    are for local development; both default to disabled.
    """
    if resolve_auth_token(token) or debug or allow_unauthenticated:
        return
    raise RunnerAuthConfigurationError(
        f"{service}: RUNNER_AUTH_TOKEN is required so internal runner endpoints are "
        "never reachable without credentials. Set a long random shared secret, or "
        f"set {ALLOW_UNAUTHENTICATED_ENV}=true for local development only."
    )

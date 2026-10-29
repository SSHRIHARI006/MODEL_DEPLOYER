"""Unit tests for the shared runner credential (SEC-02).

Covers the helper module plus the two fail-closed wiring points: the FastAPI
runner refuses to import without a secret, and the Django settings module
refuses to load without one outside development.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from runners.auth import (
    ALLOW_UNAUTHENTICATED_ENV,
    DEFAULT_AUTH_HEADER,
    RunnerAuthConfigurationError,
    auth_headers,
    check_auth_configuration,
    is_unauthenticated_allowed,
    resolve_auth_token,
    verify_token,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_TOKEN = "unit-test-runner-token"


class TestResolveAuthToken:
    def test_strips_surrounding_whitespace(self):
        assert resolve_auth_token("  secret  ") == "secret"

    def test_missing_value_becomes_empty(self):
        assert resolve_auth_token(None) == ""
        assert resolve_auth_token("") == ""


class TestVerifyToken:
    def test_accepts_matching_token(self):
        assert verify_token(TEST_TOKEN, TEST_TOKEN) is True

    def test_rejects_missing_token(self):
        assert verify_token(None, TEST_TOKEN) is False

    def test_rejects_wrong_token(self):
        assert verify_token("wrong-token", TEST_TOKEN) is False

    def test_rejects_prefix_and_suffix_of_the_real_token(self):
        assert verify_token(TEST_TOKEN[:-1], TEST_TOKEN) is False
        assert verify_token(TEST_TOKEN + "x", TEST_TOKEN) is False

    def test_fails_closed_when_no_token_is_configured(self):
        assert verify_token("anything", "") is False
        assert verify_token(None, "") is False

    def test_handles_non_ascii_input_without_raising(self):
        assert verify_token("sécret", "sécret") is True
        assert verify_token("sécret", "secret") is False


class TestAuthHeaders:
    def test_sends_the_configured_token(self):
        assert auth_headers(TEST_TOKEN) == {DEFAULT_AUTH_HEADER: TEST_TOKEN}

    def test_no_header_without_a_token(self):
        assert auth_headers("") == {}

    def test_honours_a_custom_header_name(self):
        assert auth_headers(TEST_TOKEN, "X-Custom-Runner") == {"X-Custom-Runner": TEST_TOKEN}

    def test_falls_back_to_the_default_header_name(self):
        assert auth_headers(TEST_TOKEN, "") == {DEFAULT_AUTH_HEADER: TEST_TOKEN}


class TestAuthConfiguration:
    def test_configured_token_is_accepted(self):
        check_auth_configuration(token=TEST_TOKEN, service="test")

    def test_fails_closed_without_token_outside_development(self):
        with pytest.raises(RunnerAuthConfigurationError) as exc:
            check_auth_configuration(token="", debug=False, service="test")
        assert "RUNNER_AUTH_TOKEN" in str(exc.value)

    def test_whitespace_only_token_is_not_a_secret(self):
        with pytest.raises(RunnerAuthConfigurationError):
            check_auth_configuration(token="   ", debug=False, service="test")

    def test_blank_token_is_allowed_in_debug(self):
        check_auth_configuration(token="", debug=True, service="test")

    def test_explicit_development_opt_out_is_allowed(self):
        check_auth_configuration(token="", debug=False, allow_unauthenticated=True, service="test")

    def test_opt_out_requires_an_explicit_true(self):
        assert is_unauthenticated_allowed("true") is True
        assert is_unauthenticated_allowed("TRUE") is True
        assert is_unauthenticated_allowed("1") is False
        assert is_unauthenticated_allowed("yes") is False
        assert is_unauthenticated_allowed(None) is False
        assert ALLOW_UNAUTHENTICATED_ENV == "RUNNER_ALLOW_UNAUTHENTICATED"


def _subprocess_env(**overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(overrides)
    return env


def _import_in_subprocess(target: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    # An explicitly empty value wins over any developer .env (python-dotenv does
    # not override variables already present in the environment), so these tests
    # are stable no matter what is configured locally.
    return subprocess.run(
        [sys.executable, "-c", f"import {target}"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


class TestFailClosedStartup:
    def test_runner_imports_with_a_configured_token(self):
        proc = _import_in_subprocess(
            "runners.worker",
            _subprocess_env(RUNNER_AUTH_TOKEN=TEST_TOKEN, RUNNER_ALLOW_UNAUTHENTICATED="false"),
        )
        assert proc.returncode == 0, proc.stderr

    def test_runner_refuses_to_start_without_a_token(self):
        proc = _import_in_subprocess(
            "runners.worker",
            _subprocess_env(RUNNER_AUTH_TOKEN="", RUNNER_ALLOW_UNAUTHENTICATED="false"),
        )
        assert proc.returncode != 0
        assert "RUNNER_AUTH_TOKEN" in proc.stderr
        assert "RunnerAuthConfigurationError" in proc.stderr

    def test_runner_starts_when_the_development_opt_out_is_explicit(self):
        proc = _import_in_subprocess(
            "runners.worker",
            _subprocess_env(RUNNER_AUTH_TOKEN="", RUNNER_ALLOW_UNAUTHENTICATED="true"),
        )
        assert proc.returncode == 0, proc.stderr

    def test_django_settings_import_with_a_configured_token(self):
        proc = _import_in_subprocess(
            "config.settings",
            _subprocess_env(
                DJANGO_SECRET_KEY="subprocess-test-secret-key",
                DJANGO_DEBUG="false",
                RUNNER_AUTH_TOKEN=TEST_TOKEN,
                RUNNER_ALLOW_UNAUTHENTICATED="false",
            ),
        )
        assert proc.returncode == 0, proc.stderr

    def test_django_settings_refuse_to_load_without_a_token_outside_development(self):
        proc = _import_in_subprocess(
            "config.settings",
            _subprocess_env(
                DJANGO_SECRET_KEY="subprocess-test-secret-key",
                DJANGO_DEBUG="false",
                RUNNER_AUTH_TOKEN="",
                RUNNER_ALLOW_UNAUTHENTICATED="false",
            ),
        )
        assert proc.returncode != 0
        assert "RUNNER_AUTH_TOKEN" in proc.stderr
        assert "RunnerAuthConfigurationError" in proc.stderr

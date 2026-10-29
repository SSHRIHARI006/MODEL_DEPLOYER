"""SEC-06: safe, correlated error responses."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from rest_framework import exceptions

from core.errors import (
    INTERNAL_ERROR_CODE,
    api_exception_handler,
    error_response,
    internal_error_response,
)


def _request(request_id: str = "req-123"):
    return SimpleNamespace(request_id=request_id)


class TestErrorResponse:
    def test_shape_carries_code_message_and_request_id(self):
        response = error_response(
            code="INVALID_ARCHIVE",
            message="archive is missing required file(s): model.yaml",
            status_code=400,
            request=_request(),
        )

        assert response.status_code == 400
        assert response.data["code"] == "INVALID_ARCHIVE"
        assert response.data["message"].startswith("archive is missing")
        assert response.data["request_id"] == "req-123"

    def test_request_id_is_omitted_when_unknown(self):
        response = error_response(code="X", message="y", status_code=400, request=None)

        assert "request_id" not in response.data

    def test_internal_error_never_includes_details(self):
        response = internal_error_response(request=_request())

        assert response.status_code == 500
        assert response.data["code"] == INTERNAL_ERROR_CODE
        assert "traceback" not in str(response.data).lower()
        assert response.data["request_id"] == "req-123"


class TestApiExceptionHandler:
    def test_unhandled_exception_is_replaced_with_a_safe_envelope(self, caplog):
        with caplog.at_level(logging.ERROR, logger="core.errors"):
            response = api_exception_handler(
                RuntimeError("psycopg2: password authentication failed for user ml_user"),
                {"request": _request("req-500")},
            )

        assert response.status_code == 500
        assert response.data["code"] == INTERNAL_ERROR_CODE
        assert "psycopg2" not in str(response.data)
        assert "password" not in str(response.data)
        assert response.data["request_id"] == "req-500"
        # The detail is retained server-side for diagnosis.
        assert "password authentication failed" in caplog.text
        error_record = next(
            record for record in caplog.records if record.name == "core.errors"
        )
        assert error_record.request_id == "req-500"

    def test_api_exception_keeps_detail_and_gains_correlation(self):
        response = api_exception_handler(
            exceptions.NotAuthenticated(), {"request": _request("req-401")}
        )

        assert response.status_code == 401
        assert response.data["detail"]
        assert response.data["message"] == response.data["error"]
        assert response.data["code"] == "NOT_AUTHENTICATED"
        assert response.data["request_id"] == "req-401"

    def test_field_validation_errors_are_left_alone(self):
        exc = exceptions.ValidationError({"amount": ["A valid number is required."]})

        response = api_exception_handler(exc, {"request": _request()})

        assert response.status_code == 400
        assert response.data == {"amount": ["A valid number is required."]}

    def test_handler_tolerates_a_missing_request(self):
        response = api_exception_handler(RuntimeError("boom"), {})

        assert response.status_code == 500
        assert response.data["code"] == INTERNAL_ERROR_CODE

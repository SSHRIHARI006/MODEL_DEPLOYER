"""Standard, safe API error responses (SEC-06).

Clients get a stable shape — ``{code, message, request_id}`` — while the details
needed to diagnose a failure stay in the server log, correlated by the same
request id. Raw exception text, stack traces, and infrastructure messages are
never returned.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

__all__ = [
    "INTERNAL_ERROR_MESSAGE",
    "api_exception_handler",
    "error_response",
    "internal_error_response",
    "log_exception",
]

logger = logging.getLogger("core.errors")

INTERNAL_ERROR_CODE = "INTERNAL_ERROR"
INTERNAL_ERROR_MESSAGE = (
    "An unexpected error occurred. Quote the request id when reporting it."
)


def _request_id(request) -> str | None:
    if request is None:
        return None
    return getattr(request, "request_id", None)


def log_exception(message: str, exc: BaseException, request=None) -> None:
    """Log the detailed failure server-side, tagged with the request id."""
    logger.error(
        message,
        exc_info=exc,
        extra={"request_id": _request_id(request) or "-"},
    )


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    request=None,
    extra: dict | None = None,
) -> Response:
    payload = {"error": message, "message": message, "code": code}
    request_id = _request_id(request)
    if request_id:
        payload["request_id"] = request_id
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)


def internal_error_response(
    request=None,
    *,
    code: str = INTERNAL_ERROR_CODE,
    message: str = INTERNAL_ERROR_MESSAGE,
    extra: dict | None = None,
) -> Response:
    return error_response(
        code=code,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request=request,
        extra=extra,
    )


def api_exception_handler(exc, context):
    """DRF exception handler: standardize errors, hide internals, correlate ids."""
    request = context.get("request") if isinstance(context, dict) else None
    response = drf_exception_handler(exc, context)

    if response is None:
        # Not an APIException: the detail belongs in the log, not in the body.
        log_exception("unhandled API exception", exc, request=request)
        return internal_error_response(request=request)

    data = response.data
    if isinstance(data, dict) and set(data) == {"detail"}:
        detail = str(data["detail"])
        payload = {"detail": detail, "error": detail, "message": detail}
        payload["code"] = str(getattr(exc, "default_code", "error")).upper()
        request_id = _request_id(request)
        if request_id:
            payload["request_id"] = request_id
        response.data = payload

    return response

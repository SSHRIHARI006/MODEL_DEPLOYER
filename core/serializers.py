"""Shared serializer fields."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

__all__ = ["FiniteDecimalField"]


class FiniteDecimalField(serializers.DecimalField):
    """A ``DecimalField`` that rejects NaN and Infinity cleanly.

    DRF quantizes the parsed value before comparing it to its bounds, and
    quantizing ``NaN``/``Infinity`` raises ``decimal.InvalidOperation``, which
    would escape as a 500 instead of a validation error.
    """

    default_error_messages = {
        "not_finite": "Must be a finite decimal number.",
    }

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")

        try:
            value = Decimal(str(data).strip())
        except (InvalidOperation, ValueError, TypeError, AttributeError):
            self.fail("invalid")

        if not value.is_finite():
            self.fail("not_finite")

        return super().to_internal_value(data)

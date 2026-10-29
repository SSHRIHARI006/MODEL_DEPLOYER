"""Project throttle class (SEC-07).

DRF's throttles bind their rate table to a class attribute at import time and
SimpleJWT's token views disable throttling by overriding ``throttle_classes``,
so every protected view uses this class explicitly. Reading the on/off switch
from settings at request time keeps the suite (and self-hosted deployments that
front the API themselves) able to switch throttling off deliberately.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle

__all__ = ["ConfigurableScopedRateThrottle"]


class ConfigurableScopedRateThrottle(ScopedRateThrottle):
    def allow_request(self, request, view):
        if not getattr(settings, "THROTTLING_ENABLED", True):
            return True
        return super().allow_request(request, view)

"""SEC-07: registration validation, auth throttling, rotation, and revocation."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings

from core.throttling import ConfigurableScopedRateThrottle

pytestmark = pytest.mark.django_db


def register(client, *, username="newuser", email="new@example.com", password="TestPass123!"):
    return client.post(
        "/api/auth/register/",
        {"username": username, "email": email, "password": password},
        format="json",
    )


def login(client, *, email="new@example.com", password="TestPass123!"):
    return client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    )


def refresh(client, token):
    return client.post("/api/auth/refresh/", {"refresh": token}, format="json")


class TestPasswordValidation:
    @pytest.mark.parametrize(
        "username,password,expected",
        [
            ("newuser", "password", "too common"),
            ("newuser", "12345678", "entirely numeric"),
            ("newuser", "short1!", "at least 8 characters"),
            ("testuser12", "testuser12", "too similar"),
        ],
    )
    def test_weak_passwords_are_rejected(self, api_client, username, password, expected):
        res = register(api_client, username=username, password=password)

        assert res.status_code == 400
        assert any(expected in message for message in res.data["password"])

    def test_weak_password_does_not_create_the_account(self, api_client):
        register(api_client, password="password")

        from django.contrib.auth import get_user_model

        assert not get_user_model().objects.filter(username="newuser").exists()

    def test_strong_password_still_works(self, api_client):
        assert register(api_client, password="TestPass123!").status_code == 201


class TestAuthThrottling:
    @override_settings(THROTTLING_ENABLED=True)
    def test_repeated_failed_logins_are_throttled(self, api_client, monkeypatch):
        monkeypatch.setattr(
            ConfigurableScopedRateThrottle, "THROTTLE_RATES", {"auth": "2/min"}
        )
        cache.clear()
        try:
            assert login(api_client, password="wrong-password").status_code == 401
            assert login(api_client, password="wrong-password").status_code == 401
            assert login(api_client, password="wrong-password").status_code == 429
        finally:
            cache.clear()

    @override_settings(THROTTLING_ENABLED=True)
    def test_registration_is_throttled(self, api_client, monkeypatch):
        monkeypatch.setattr(
            ConfigurableScopedRateThrottle, "THROTTLE_RATES", {"auth": "2/min"}
        )
        cache.clear()
        try:
            codes = [
                register(
                    api_client,
                    username=f"user{index}",
                    email=f"user{index}@example.com",
                ).status_code
                for index in range(3)
            ]

            assert codes == [201, 201, 429]
        finally:
            cache.clear()


class TestRefreshLifecycle:
    def test_refresh_rotates_the_token_and_revokes_the_previous_one(self, api_client):
        register(api_client)
        original = login(api_client).data["refresh"]

        rotated = refresh(api_client, original)

        assert rotated.status_code == 200
        assert rotated.data["refresh"] != original
        assert rotated.data["access"]

        replay = refresh(api_client, original)
        assert replay.status_code == 401

        assert refresh(api_client, rotated.data["refresh"]).status_code == 200

    def test_refresh_rejects_a_garbage_token(self, api_client):
        assert refresh(api_client, "not-a-token").status_code == 401


class TestLogout:
    def test_logout_revokes_the_refresh_token(self, api_client):
        register(api_client)
        token = login(api_client).data["refresh"]

        res = api_client.post("/api/auth/logout/", {"refresh": token}, format="json")

        assert res.status_code == 200
        assert refresh(api_client, token).status_code == 401

    def test_logout_requires_a_refresh_token(self, api_client):
        assert api_client.post("/api/auth/logout/", {}, format="json").status_code == 400

    def test_logout_rejects_an_invalid_token(self, api_client):
        res = api_client.post(
            "/api/auth/logout/", {"refresh": "nonsense"}, format="json"
        )

        assert res.status_code == 400
        assert res.data["code"] == "INVALID_REFRESH"

    def test_logout_is_idempotent_for_an_already_revoked_token(self, api_client):
        register(api_client)
        token = login(api_client).data["refresh"]
        api_client.post("/api/auth/logout/", {"refresh": token}, format="json")

        second = api_client.post("/api/auth/logout/", {"refresh": token}, format="json")

        assert second.status_code == 400
        assert second.data["code"] == "INVALID_REFRESH"

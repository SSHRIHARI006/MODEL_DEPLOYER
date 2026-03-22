import pytest

pytestmark = pytest.mark.django_db


def test_register_success(api_client):
    res = api_client.post(
        "/api/auth/register/",
        {"email": "new@example.com", "password": "TestPass123!"},
        format="json",
    )
    assert res.status_code in (200, 201)
    assert "message" in res.data


def test_register_duplicate_email(api_client):
    api_client.post(
        "/api/auth/register/",
        {"email": "dup@example.com", "password": "TestPass123!"},
        format="json",
    )
    res = api_client.post(
        "/api/auth/register/",
        {"email": "dup@example.com", "password": "TestPass123!"},
        format="json",
    )
    assert res.status_code == 400


def test_login_success(api_client):
    api_client.post(
        "/api/auth/register/",
        {"email": "login@example.com", "password": "TestPass123!"},
        format="json",
    )
    res = api_client.post(
        "/api/auth/login/",
        {"email": "login@example.com", "password": "TestPass123!"},
        format="json",
    )
    assert res.status_code == 200
    assert "access" in res.data
    assert "refresh" in res.data


def test_login_wrong_password(api_client):
    api_client.post(
        "/api/auth/register/",
        {"email": "wrong@example.com", "password": "TestPass123!"},
        format="json",
    )
    res = api_client.post(
        "/api/auth/login/",
        {"email": "wrong@example.com", "password": "badpass"},
        format="json",
    )
    assert res.status_code == 401
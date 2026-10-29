"""SEC-07: model API keys are stored as digests, never as reusable plaintext."""

from __future__ import annotations

import importlib
import re

import pytest

from api_keys.models import APIKey, generate_api_key, hash_api_key, hashed_key_fields

pytestmark = pytest.mark.django_db

HEX64 = re.compile(r"^[0-9a-f]{64}$")


class TestKeyGeneration:
    def test_raw_keys_are_long_random_hex(self):
        raw = generate_api_key()

        assert HEX64.match(raw), raw
        assert generate_api_key() != raw

    def test_hash_is_a_stable_sha256_digest(self):
        assert HEX64.match(hash_api_key("abc"))
        assert hash_api_key("abc") == hash_api_key("abc")
        assert hash_api_key("abc") != hash_api_key("abd")

    def test_stored_fields_are_the_digest_and_a_display_prefix(self):
        fields = hashed_key_fields("abcdefghijklmnop")

        assert fields["key_hash"] == hash_api_key("abcdefghijklmnop")
        assert fields["key_prefix"] == "abcdefgh"


class TestStorage:
    def test_plaintext_column_is_gone(self):
        assert "key" not in {field.name for field in APIKey._meta.get_fields()}

    def test_created_key_stores_only_a_digest(self, model_obj, user):
        key = APIKey.objects.create(user=user, model=model_obj, name="hashed")

        raw = key.raw_key
        assert HEX64.match(raw)
        assert key.key_hash == hash_api_key(raw)
        assert key.key_prefix == raw[:8]

        stored = APIKey.objects.get(pk=key.pk)
        assert stored.key_hash == hash_api_key(raw)
        # The raw value is not part of the persisted row at all.
        assert raw not in [str(getattr(stored, f.name)) for f in stored._meta.get_fields()]

    def test_raw_key_is_not_recoverable_from_the_database(self, model_obj, user):
        key = APIKey.objects.create(user=user, model=model_obj, name="hashed")
        raw = key.raw_key

        with pytest.raises(APIKey.DoesNotExist):
            APIKey.objects.get(key_hash=raw)  # the raw value is not a digest

        assert APIKey.objects.filter(key_hash=hash_api_key(raw)).count() == 1


class TestMigrationParity:
    def test_migration_hasher_matches_the_model_hasher(self):
        """The data migration keeps its own copy of the hashing rule."""
        migration = importlib.import_module("api_keys.migrations.0004_hash_api_keys")

        for raw in ("legacy-plaintext-key-aaaa", "", "z" * 64):
            assert migration.hashed_fields(raw) == hashed_key_fields(raw)


class TestKeyLifecycleApi:
    def test_creation_returns_the_raw_key_once(self, auth_client, model_obj):
        res = auth_client.post(
            "/api/keys/", {"model_id": model_obj.id, "name": "once"}, format="json"
        )

        assert res.status_code == 201
        assert HEX64.match(res.data["key"])
        assert res.data["prefix"] == res.data["key"][:8]

        listed = auth_client.get("/api/keys/")
        assert listed.status_code == 200
        row = next(item for item in listed.data if item["name"] == "once")
        assert "key" not in row
        assert "key_hash" not in row
        assert row["key_prefix"] == res.data["prefix"]

    def test_deactivated_keys_are_rejected(
        self, auth_client, model_obj, model_version, api_key, user
    ):
        from deployments.models import Deployment

        Deployment.objects.create(
            model_version=model_version,
            status=Deployment.Status.RUNNING,
            internal_url="http://model_test:5000",
        )
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])

        auth_client.credentials(
            HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_API_KEY=api_key.raw_key,
        )
        res = auth_client.post(
            f"/api/predict/{model_obj.id}/", {"instances": [{"x": 1}]}, format="json"
        )

        assert res.status_code == 403

    def test_unknown_key_is_rejected(self, auth_client, model_obj, model_version, api_key):
        from deployments.models import Deployment

        Deployment.objects.create(
            model_version=model_version,
            status=Deployment.Status.RUNNING,
            internal_url="http://model_test:5000",
        )
        auth_client.credentials(
            HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_API_KEY="not-a-real-key",
        )

        res = auth_client.post(
            f"/api/predict/{model_obj.id}/", {"instances": [{"x": 1}]}, format="json"
        )

        assert res.status_code == 403

    def test_key_for_a_different_model_is_rejected(
        self, auth_client, model_obj, model_version, api_key, user
    ):
        from deployments.models import Deployment
        from model_registry.models import Model

        Deployment.objects.create(
            model_version=model_version,
            status=Deployment.Status.RUNNING,
            internal_url="http://model_test:5000",
        )
        other_model = Model.objects.create(
            id="other-model",
            name="other",
            framework="sklearn",
            task_type="regression",
            owner=user,
        )
        other_key = APIKey.objects.create(user=user, model=other_model, name="other")

        auth_client.credentials(
            HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_API_KEY=other_key.raw_key,
        )
        res = auth_client.post(
            f"/api/predict/{model_obj.id}/", {"instances": [{"x": 1}]}, format="json"
        )

        assert res.status_code == 403

    def test_key_owned_by_another_user_is_rejected(
        self, auth_client, model_obj, model_version, api_key, user2
    ):
        from deployments.models import Deployment

        Deployment.objects.create(
            model_version=model_version,
            status=Deployment.Status.RUNNING,
            internal_url="http://model_test:5000",
        )
        foreign = APIKey.objects.create(user=user2, model=model_obj, name="foreign")

        auth_client.credentials(
            HTTP_AUTHORIZATION=auth_client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_API_KEY=foreign.raw_key,
        )
        res = auth_client.post(
            f"/api/predict/{model_obj.id}/", {"instances": [{"x": 1}]}, format="json"
        )

        assert res.status_code == 403

"""SEC-08: model pricing is rejected when malformed, non-finite, or out of range."""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from model_registry.models import Model

pytestmark = pytest.mark.django_db


def patch_price(client, model, value):
    return client.patch(
        f"/api/models/@{model.owner.username}/{model.name}/",
        {"cost_per_run": value},
        format="json",
    )


@pytest.mark.parametrize(
    "value",
    [
        "-1",
        "-0.0001",
        "nan",
        "NaN",
        "inf",
        "-Infinity",
        "abc",
        "",
        {},
        [],
        True,
    ],
)
def test_api_rejects_invalid_prices(auth_client, model_obj, value):
    res = patch_price(auth_client, model_obj, value)

    assert res.status_code == 400, res.data
    model_obj.refresh_from_db()
    assert model_obj.cost_per_run == Decimal("1")


def test_api_accepts_a_valid_price(auth_client, model_obj):
    res = patch_price(auth_client, model_obj, "2.5")

    assert res.status_code == 200
    model_obj.refresh_from_db()
    assert model_obj.cost_per_run == Decimal("2.5")


def test_api_accepts_zero(auth_client, model_obj):
    res = patch_price(auth_client, model_obj, "0")

    assert res.status_code == 200
    model_obj.refresh_from_db()
    assert model_obj.cost_per_run == Decimal("0")


def test_api_rejects_an_out_of_range_price(auth_client, model_obj):
    # max_digits=8, decimal_places=4 -> 9999.9999 is the largest representable value.
    res = patch_price(auth_client, model_obj, "100000")

    assert res.status_code == 400


def test_other_fields_are_still_editable(auth_client, model_obj):
    res = auth_client.patch(
        f"/api/models/@{model_obj.owner.username}/{model_obj.name}/",
        {"description": "hello", "is_public": True},
        format="json",
    )

    assert res.status_code == 200
    model_obj.refresh_from_db()
    assert model_obj.description == "hello"
    assert model_obj.is_public is True


def test_non_owner_cannot_change_the_price(auth_client, model_obj_user2):
    res = patch_price(auth_client, model_obj_user2, "0")

    assert res.status_code in (403, 404)
    model_obj_user2.refresh_from_db()
    assert model_obj_user2.cost_per_run == Decimal("1")


def test_database_refuses_a_negative_price(user):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Model.objects.create(
                id="negative-price",
                name="negative-price",
                framework="sklearn",
                task_type="regression",
                owner=user,
                cost_per_run=Decimal("-1"),
            )


def test_negative_price_constraint_is_declared():
    names = {constraint.name for constraint in Model._meta.constraints}

    assert "model_cost_per_run_non_negative" in names


class TestConstraintMigration:
    """The migration must survive a database that already holds bad data."""

    migration = importlib.import_module(
        "model_registry.migrations.0004_model_model_cost_per_run_non_negative"
    )

    def test_existing_negative_prices_are_repaired_before_the_constraint(self):
        operations = [type(op).__name__ for op in self.migration.Migration.operations]

        assert operations.index("RunPython") < operations.index("AddConstraint")

    def test_repair_targets_only_negative_prices_and_sets_them_to_zero(self):
        calls = []

        class FakeQuerySet:
            def filter(self, **kwargs):
                calls.append(kwargs)
                return self

            def update(self, **kwargs):
                calls.append(kwargs)

        class FakeModel:
            objects = FakeQuerySet()

        class FakeApps:
            def get_model(self, app_label, model_name):
                assert (app_label, model_name) == ("model_registry", "Model")
                return FakeModel

        self.migration.clamp_negative_prices(FakeApps(), schema_editor=None)

        assert calls == [
            {"cost_per_run__lt": 0},
            {"cost_per_run": Decimal("0")},
        ]

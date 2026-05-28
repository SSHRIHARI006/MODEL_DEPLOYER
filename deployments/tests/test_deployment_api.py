from unittest.mock import patch

import pytest

from deployments.models import Deployment

pytestmark = pytest.mark.django_db


@patch("deployments.views.start_deployment_async")
def test_create_deployment_returns_202(start_async, auth_client, model_version):
    res = auth_client.post(
        "/api/deployments/",
        {"model_version_id": str(model_version.id)},
        format="json",
    )

    assert res.status_code == 202
    assert res.data["status"] == Deployment.Status.PENDING
    start_async.assert_called_once()


@patch("deployments.views.start_deployment_async")
def test_create_deployment_rejects_other_users_model(
    start_async, auth_client, model_obj_user2
):
    mv = model_obj_user2.versions.create(
        version="v1", artifact_path="/tmp/x", status="READY"
    )

    res = auth_client.post(
        "/api/deployments/",
        {"model_version_id": str(mv.id)},
        format="json",
    )

    assert res.status_code == 400
    start_async.assert_not_called()


@patch("deployments.views.start_deployment_async")
def test_get_deployment_status(start_async, auth_client, model_version):
    dep = Deployment.objects.create(model_version=model_version)

    res = auth_client.get(f"/api/deployments/{dep.id}/")

    assert res.status_code == 200
    assert res.data["id"] == str(dep.id)
    assert res.data["status"] == Deployment.Status.PENDING


@patch("deployments.views.start_deployment_async")
def test_get_deployment_status_not_found_for_other_user(
    start_async, auth_client, model_obj_user2
):
    mv = model_obj_user2.versions.create(
        version="v1", artifact_path="/tmp/x", status="READY"
    )
    dep = Deployment.objects.create(model_version=mv)

    res = auth_client.get(f"/api/deployments/{dep.id}/")

    assert res.status_code == 404


def test_list_deployments_filtered(auth_client, model_version, model_obj_user2):
    # Create a deployment for auth_client (the owner)
    dep1 = Deployment.objects.create(model_version=model_version)

    # Create a deployment for user2's model version
    mv2 = model_obj_user2.versions.create(
        version="v1", artifact_path="/tmp/x2", status="READY"
    )
    dep2 = Deployment.objects.create(model_version=mv2)

    # List all deployments for auth_client
    res = auth_client.get("/api/deployments/")
    assert res.status_code == 200
    ids = [d["id"] for d in res.data]
    assert str(dep1.id) in ids
    assert str(dep2.id) not in ids  # other user's deployment must not be returned

    # Filter by model_id
    res_filtered = auth_client.get(
        f"/api/deployments/?model_id={model_version.model.id}"
    )
    assert res_filtered.status_code == 200
    ids_filtered = [d["id"] for d in res_filtered.data]
    assert str(dep1.id) in ids_filtered
    assert len(ids_filtered) == 1

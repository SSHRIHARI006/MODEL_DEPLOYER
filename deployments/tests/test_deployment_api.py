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
def test_create_deployment_rejects_other_users_model(start_async, auth_client, model_obj_user2):
    mv = model_obj_user2.versions.create(version="v1", artifact_path="/tmp/x", status="READY")

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
def test_get_deployment_status_not_found_for_other_user(start_async, auth_client, model_obj_user2):
    mv = model_obj_user2.versions.create(version="v1", artifact_path="/tmp/x", status="READY")
    dep = Deployment.objects.create(model_version=mv)

    res = auth_client.get(f"/api/deployments/{dep.id}/")

    assert res.status_code == 404

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from core.storage import delete_prefix_paginated
from deployments.models import Deployment
from model_registry.models import Model

pytestmark = pytest.mark.django_db


def test_delete_prefix_paginated():
    """REL-08: Paginated deletion batches keys and deletes all pages."""
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator

    # Mock 2 pages of objects
    page1 = {"Contents": [{"Key": f"prefix/obj_{i}.txt"} for i in range(1000)]}
    page2 = {"Contents": [{"Key": f"prefix/obj_{i}.txt"} for i in range(1000, 1250)]}
    mock_paginator.paginate.return_value = [page1, page2]

    total = delete_prefix_paginated(mock_s3, "test-bucket", "prefix/", batch_size=1000)

    assert total == 1250
    assert mock_s3.delete_objects.call_count == 2
    # First batch was 1000
    first_call_args = mock_s3.delete_objects.call_args_list[0][1]
    assert len(first_call_args["Delete"]["Objects"]) == 1000
    # Second batch was 250
    second_call_args = mock_s3.delete_objects.call_args_list[1][1]
    assert len(second_call_args["Delete"]["Objects"]) == 250


def test_delete_prefix_paginated_dry_run():
    """REL-08: Dry run calculates total without calling delete_objects."""
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Key": "k1"}, {"Key": "k2"}]}
    ]

    total = delete_prefix_paginated(mock_s3, "test-bucket", "prefix/", dry_run=True)
    assert total == 2
    mock_s3.delete_objects.assert_not_called()


def test_model_deletion_stops_active_deployments(auth_client, model_obj):
    """REL-09: Deleting a model stops active deployments and triggers runner teardown."""
    mv = model_obj.versions.create(version="v1", artifact_path="s3://b/m1/v1", status="READY")
    dep = Deployment.objects.create(
        model_version=mv,
        status=Deployment.Status.RUNNING,
    )

    mock_runner = MagicMock()
    with patch("runners.factory.RunnerFactory.get_runner", return_value=mock_runner), \
         patch("model_registry.views.get_s3_client"):
        res = auth_client.delete(f"/api/models/{model_obj.id}/")

    assert res.status_code == 200
    mock_runner.teardown.assert_called_once_with({"model_id": str(mv.id)})
    assert not Deployment.objects.filter(id=dep.id).exists()
    assert not Model.objects.filter(id=model_obj.id).exists()


def test_upload_failure_compensating_cleanup(auth_client, user):
    """REL-08: Failure during database record creation cleans up uploaded S3 objects."""
    # User must have upload approval (SEC-03)
    user.can_upload_models = True
    user.save(update_fields=["can_upload_models"])

    # Build a minimal valid zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("model.yaml", "framework: sklearn\npython_version: '3.12'\nrequirements: requirements.txt\nmodel_artifact: model.pkl\n")
        zf.writestr("requirements.txt", "scikit-learn\n")
        zf.writestr("model.pkl", b"fake pickle data")
    buf.seek(0)
    buf.name = "model.zip"

    mock_s3 = MagicMock()
    with patch("model_registry.views.get_s3_client", return_value=mock_s3), \
         patch("model_registry.views.Model.objects.create", side_effect=RuntimeError("simulated DB crash")), \
         patch("model_registry.views.delete_prefix_paginated") as mock_delete:
        res = auth_client.post(
            "/api/models/upload/",
            {"file": buf},
            format="multipart",
        )

    assert res.status_code == 500
    # Confirm compensating cleanup was invoked
    mock_delete.assert_called_once()


def test_reconcile_orphans_command():
    """REL-08: reconcile_orphans management command runs without errors."""
    mock_s3 = MagicMock()
    mock_paginator = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {"CommonPrefixes": [{"Prefix": "orphaned-id-123/"}]}
    ]

    with patch("model_registry.management.commands.reconcile_orphans.get_s3_client", return_value=mock_s3):
        call_command("reconcile_orphans", dry_run=True)

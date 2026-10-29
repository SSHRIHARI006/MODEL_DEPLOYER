import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import boto3
import yaml
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.archive import ArchiveError, ArchiveLimits, safe_extract_zip
from core.errors import error_response, internal_error_response, log_exception
from core.storage import delete_prefix_paginated
from core.throttling import ConfigurableScopedRateThrottle

from .manifest import ManifestValidationError, validate_bundle_files, validate_manifest
from .models import Model, ModelVersion
from .serializers import ModelUploadSerializer

from botocore.client import Config


def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        use_ssl=settings.AWS_S3_USE_SSL,
        config=Config(s3={'addressing_style': 'path'})
    )


def may_upload_models(user) -> bool:
    """SEC-03: uploading means handing this platform code to execute.

    Uploads are limited to staff and to accounts explicitly approved by an
    administrator, unless the deployment has opted out of the approval policy.
    """
    if not getattr(settings, "UPLOAD_APPROVAL_REQUIRED", True):
        return True
    return bool(user.is_staff or user.can_upload_models)


def get_next_version(model: Model) -> str:
    """Calculates the next version string (v1, v2, v3...) for a model."""
    existing_versions = list(
        ModelVersion.objects.filter(model=model).values_list("version", flat=True)
    )
    numeric_versions = []
    for v in existing_versions:
        match = re.match(r"^v(\d+)$", v)
        if match:
            numeric_versions.append(int(match.group(1)))
    if numeric_versions:
        return f"v{max(numeric_versions) + 1}"
    return f"v{len(existing_versions) + 1}"


def _process_and_upload_bundle(
    upload_file, model_id: str, version: str
) -> tuple[dict, str, Path | None]:
    """SEC-04 / API-01: Extracts, validates manifest and bundle files, and uploads to S3 under model_id/version/."""
    work_dir = Path(tempfile.mkdtemp(prefix="model-upload-"))
    bundle_dir = work_dir / "bundle"

    try:
        zip_path = work_dir / "model.zip"
        with open(zip_path, "wb") as dest:
            for chunk in upload_file.chunks():
                dest.write(chunk)

        limits = ArchiveLimits.from_settings()
        safe_extract_zip(
            zip_path,
            bundle_dir,
            limits=limits,
            required_files=("model.yaml",),
        )
        zip_path.unlink(missing_ok=True)

        yaml_path = bundle_dir / "model.yaml"
        try:
            with open(yaml_path, "r") as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ArchiveError(f"Invalid YAML syntax in model.yaml: {exc}") from exc

        if not isinstance(config, dict):
            raise ArchiveError("model.yaml must contain a valid object")

        # API-01: Schema validation against canonical JSON Schema
        validate_manifest(config)

        # API-01: Validate all declared bundle files and optional schema.json
        schema_path = validate_bundle_files(bundle_dir, config, limits=limits)

        # MinIO / S3 Upload
        s3_client = get_s3_client()
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        s3_prefix = f"{model_id}/{version}/"

        for root, dirs, files in os.walk(bundle_dir):
            for file_name in files:
                local_file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(local_file_path, bundle_dir)
                s3_key = f"{s3_prefix}{relative_path}"
                s3_client.upload_file(local_file_path, bucket_name, s3_key)

        return config, s3_prefix, schema_path
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


class ModelUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "upload"

    def post(self, request):
        if not may_upload_models(request.user):
            return Response(
                {
                    "error": "Model uploads are invite-only. Ask an administrator to "
                    "approve this account for uploads.",
                    "code": "UPLOAD_NOT_APPROVED",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ModelUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload_file = serializer.validated_data["file"]

        if upload_file.size > settings.MAX_MODEL_ZIP_BYTES:
            return Response(
                {"error": "Uploaded zip exceeds max allowed size"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_id = str(uuid.uuid4())
        version = "v1"

        try:
            config, s3_prefix, schema_file = _process_and_upload_bundle(
                upload_file, model_id, version
            )
            s3_client = get_s3_client()
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            s3_uri = f"s3://{bucket_name}/{s3_prefix.rstrip('/')}"
            schema_s3_uri = (
                f"s3://{bucket_name}/{s3_prefix}schema.json" if schema_file else None
            )

            model_name = config.get("name") or f"model-{model_id[:8]}"
            framework = config.get("framework")
            task_type = config.get("task_type") or "unknown"

            try:
                with transaction.atomic():
                    model = Model.objects.create(
                        id=model_id,
                        name=model_name,
                        framework=framework,
                        task_type=task_type,
                        owner=request.user,
                    )
                    version_obj = ModelVersion.objects.create(
                        model=model,
                        version=version,
                        artifact_path=s3_uri,
                        schema_path=schema_s3_uri,
                        status="READY",
                    )
            except Exception as db_exc:
                # REL-08: Compensating cleanup of S3 objects if DB creation fails
                try:
                    delete_prefix_paginated(s3_client, bucket_name, s3_prefix)
                except Exception:
                    pass
                raise db_exc

            return Response(
                {
                    "message": "Model uploaded successfully",
                    "model_id": model_id,
                    "model_version_id": str(version_obj.id),
                    "version": version,
                },
                status=status.HTTP_201_CREATED,
            )

        except (ArchiveError, ManifestValidationError) as e:
            code = getattr(e, "code", "INVALID_ARCHIVE")
            extra = (
                {"field_errors": getattr(e, "field_errors", {})}
                if getattr(e, "field_errors", None)
                else None
            )
            return error_response(
                code=code,
                message=str(e),
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request,
                extra=extra,
            )
        except Exception as exc:
            # SEC-06: log the detail, return a stable message with the request id.
            log_exception("model upload failed", exc, request=request)
            return internal_error_response(request=request, code="UPLOAD_FAILED")


class ModelDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, model_id):
        try:
            model = Model.objects.get(id=model_id, owner=request.user)

            # REL-09: Stop active deployments and teardown runners before deleting
            from deployments.models import Deployment
            from runners.factory import RunnerFactory

            active_deployments = Deployment.objects.filter(
                model_version__model=model,
                status__in=[
                    Deployment.Status.PENDING,
                    Deployment.Status.BUILDING,
                    Deployment.Status.RUNNING,
                ],
            )
            runner = None
            try:
                runner = RunnerFactory.get_runner(framework=model.framework)
            except Exception:
                pass

            for dep in active_deployments:
                dep.transition_to(Deployment.Status.STOPPED)
                dep.stopped_at = timezone.now()
                dep.save(update_fields=["status", "stopped_at", "updated_at"])

                if runner:
                    try:
                        runner.teardown({"model_id": str(dep.model_version_id)})
                    except Exception:
                        pass

            # REL-08 / REL-09: Clean up all S3 objects with pagination
            s3_client = get_s3_client()
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            delete_prefix_paginated(s3_client, bucket_name, f"{model_id}/")

            model.delete()
            return Response(
                {"message": "Model and remote artifacts deleted successfully"},
                status=status.HTTP_200_OK,
            )
        except Model.DoesNotExist:
            return error_response(
                code="MODEL_NOT_FOUND",
                message="Model not found",
                status_code=status.HTTP_404_NOT_FOUND,
                request=request,
            )
        except Exception as exc:
            log_exception("model deletion failed", exc, request=request)
            return internal_error_response(request=request, code="DELETE_FAILED")


class ModelVersionListCreateAPIView(APIView):
    """API-02: List and create versions for a specific model."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ConfigurableScopedRateThrottle]
    throttle_scope = "upload"

    def get(self, request, model_id):
        try:
            model = Model.objects.get(id=model_id)
        except Model.DoesNotExist:
            return error_response(
                code="MODEL_NOT_FOUND",
                message="Model not found",
                status_code=status.HTTP_404_NOT_FOUND,
                request=request,
            )

        if not model.is_public and model.owner != request.user and not request.user.is_staff:
            return error_response(
                code="FORBIDDEN",
                message="Permission denied",
                status_code=status.HTTP_403_FORBIDDEN,
                request=request,
            )

        versions = ModelVersion.objects.filter(model=model).order_by("created_at")
        data = [
            {
                "id": str(v.id),
                "version": v.version,
                "artifact_path": v.artifact_path,
                "schema_path": v.schema_path,
                "status": v.status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]
        return Response({"model_id": model_id, "versions": data}, status=status.HTTP_200_OK)

    def post(self, request, model_id):
        if not may_upload_models(request.user):
            return error_response(
                code="UPLOAD_NOT_APPROVED",
                message="Model uploads are invite-only. Ask an administrator to approve this account for uploads.",
                status_code=status.HTTP_403_FORBIDDEN,
                request=request,
            )

        try:
            model = Model.objects.get(id=model_id)
        except Model.DoesNotExist:
            return error_response(
                code="MODEL_NOT_FOUND",
                message="Model not found",
                status_code=status.HTTP_404_NOT_FOUND,
                request=request,
            )

        if model.owner != request.user and not request.user.is_staff:
            return error_response(
                code="FORBIDDEN",
                message="You do not own this model",
                status_code=status.HTTP_403_FORBIDDEN,
                request=request,
            )

        serializer = ModelUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload_file = serializer.validated_data["file"]

        if upload_file.size > settings.MAX_MODEL_ZIP_BYTES:
            return error_response(
                code="FILE_TOO_LARGE",
                message="Uploaded zip exceeds max allowed size",
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request,
            )

        s3_client = get_s3_client()
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        try:
            # Serialize version allocation and creation to avoid concurrent uploads
            # selecting the same next version number for a model.
            try:
                with transaction.atomic():
                    model = Model.objects.select_for_update().get(pk=model.pk)
                    next_version = get_next_version(model)
                    config, s3_prefix, schema_file = _process_and_upload_bundle(
                        upload_file, model_id, next_version
                    )
                    s3_uri = f"s3://{bucket_name}/{s3_prefix.rstrip('/')}"
                    schema_s3_uri = (
                        f"s3://{bucket_name}/{s3_prefix}schema.json" if schema_file else None
                    )
                    version_obj = ModelVersion.objects.create(
                        model=model,
                        version=next_version,
                        artifact_path=s3_uri,
                        schema_path=schema_s3_uri,
                        status="READY",
                    )
            except Exception:
                # The DB transaction rolls back before compensating S3 cleanup.
                # This prefix belongs only to the newly allocated version.
                if "next_version" in locals():
                    try:
                        delete_prefix_paginated(
                            s3_client, bucket_name, f"{model_id}/{next_version}/"
                        )
                    except Exception:
                        pass
                raise

            return Response(
                {
                    "message": "Model version uploaded successfully",
                    "model_id": model_id,
                    "model_version_id": str(version_obj.id),
                    "version": next_version,
                },
                status=status.HTTP_201_CREATED,
            )
        except (ArchiveError, ManifestValidationError) as e:
            code = getattr(e, "code", "INVALID_ARCHIVE")
            extra = (
                {"field_errors": getattr(e, "field_errors", {})}
                if getattr(e, "field_errors", None)
                else None
            )
            return error_response(
                code=code,
                message=str(e),
                status_code=status.HTTP_400_BAD_REQUEST,
                request=request,
                extra=extra,
            )
        except Exception as exc:
            log_exception("model version upload failed", exc, request=request)
            return internal_error_response(request=request, code="UPLOAD_FAILED")


class ModelVersionDetailAPIView(APIView):
    """API-02: Manage and delete a specific model version."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, model_id, version):
        try:
            model = Model.objects.get(id=model_id)
        except Model.DoesNotExist:
            return error_response(
                code="MODEL_NOT_FOUND",
                message="Model not found",
                status_code=status.HTTP_404_NOT_FOUND,
                request=request,
            )

        if model.owner != request.user and not request.user.is_staff:
            return error_response(
                code="FORBIDDEN",
                message="You do not own this model",
                status_code=status.HTTP_403_FORBIDDEN,
                request=request,
            )

        try:
            version_obj = ModelVersion.objects.get(model=model, version=version)
        except ModelVersion.DoesNotExist:
            return error_response(
                code="VERSION_NOT_FOUND",
                message=f"Version '{version}' not found for model",
                status_code=status.HTTP_404_NOT_FOUND,
                request=request,
            )

        # API-02: Active deployment check
        from deployments.models import Deployment

        active_deps = Deployment.objects.filter(
            model_version=version_obj,
            status__in=[
                Deployment.Status.PENDING,
                Deployment.Status.BUILDING,
                Deployment.Status.RUNNING,
            ],
        )
        if active_deps.exists():
            return error_response(
                code="VERSION_IN_USE",
                message=f"Cannot delete version '{version}' with active deployments. Stop deployments first.",
                status_code=status.HTTP_409_CONFLICT,
                request=request,
            )

        # Delete remote artifacts first and fail closed: a storage error must not
        # silently remove the database record that identifies the artifacts.
        s3_client = get_s3_client()
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        s3_prefix = f"{model_id}/{version}/"
        delete_prefix_paginated(s3_client, bucket_name, s3_prefix)
        version_obj.delete()
        return Response(
            {"message": f"Version '{version}' deleted successfully"},
            status=status.HTTP_200_OK,
        )

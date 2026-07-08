import os
import shutil
import uuid
import zipfile
from pathlib import Path

import tempfile
import boto3
import yaml
from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Model, ModelVersion
from .serializers import ModelUploadSerializer

BASE_STORAGE = Path(settings.BASE_DIR) / "storage" / "models"

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

class ModelUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ModelUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload_file = serializer.validated_data["file"]

        if upload_file.size > settings.MAX_MODEL_ZIP_BYTES:
            return Response(
                {"error": "Uploaded zip exceeds max allowed size"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_id = str(uuid.uuid4())
        model_root = BASE_STORAGE / model_id
        version = "v1"
        version_path = model_root / version
        zip_path = version_path / "model.zip"

        try:
            version_path.mkdir(parents=True, exist_ok=True)

            with open(zip_path, "wb+") as dest:
                for chunk in upload_file.chunks():
                    dest.write(chunk)

            base = version_path.resolve()
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for member in zip_ref.namelist():
                    target = (version_path / member).resolve()
                    try:
                        target.relative_to(base)
                    except ValueError:
                        raise ValueError("Unsafe file path in zip")
                zip_ref.extractall(version_path)

            zip_path.unlink(missing_ok=True)

            yaml_path = version_path / "model.yaml"
            if not yaml_path.exists():
                raise ValueError("model.yaml missing")

            with open(yaml_path, "r") as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                raise ValueError("model.yaml must contain a valid object")

            framework = config.get("framework")
            python_version = config.get("python_version")
            requirements = config.get("requirements")
            model_artifact = config.get("model_artifact")
            model_name = config.get("name") or f"model-{model_id[:8]}"
            task_type = config.get("task_type") or "unknown"

            if not framework:
                raise ValueError("framework missing")
            if not python_version:
                raise ValueError("python_version missing")
            if not requirements:
                raise ValueError("requirements missing")
            if not model_artifact:
                raise ValueError("model_artifact missing")

            requirements_path = version_path / requirements
            if not requirements_path.exists():
                raise ValueError("requirements file not found")

            artifact_path = version_path / model_artifact
            if not artifact_path.exists():
                raise ValueError("model artifact not found")

            # MinIO / S3 Upload
            s3_client = get_s3_client()
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            s3_prefix = f"{model_id}/{version}/"
            
            # Walk the temp directory and upload all files
            for root, dirs, files in os.walk(version_path):
                for file_name in files:
                    local_file_path = os.path.join(root, file_name)
                    # Calculate relative path to maintain folder structure
                    relative_path = os.path.relpath(local_file_path, version_path)
                    s3_key = f"{s3_prefix}{relative_path}"
                    
                    s3_client.upload_file(
                        local_file_path, 
                        bucket_name, 
                        s3_key
                    )

            model = Model.objects.create(
                id=model_id,
                name=model_name,
                framework=framework,
                task_type=task_type,
                owner=request.user,
            )

            # Store the S3 URI instead of a local path
            s3_uri = f"s3://{bucket_name}/{s3_prefix.rstrip('/')}"
            version_obj = ModelVersion.objects.create(
                model=model,
                version=version,
                artifact_path=s3_uri,
                status="READY",
            )

            return Response(
                {
                    "message": "Model uploaded successfully",
                    "model_id": model_id,
                    "model_version_id": str(version_obj.id),
                    "version": version,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        finally:
            if model_root.exists():
                shutil.rmtree(model_root)


class ModelDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, model_id):
        try:
            model = Model.objects.get(id=model_id, owner=request.user)
            
            # Clean up S3 objects
            s3_client = get_s3_client()
            bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            
            # Delete all versions from S3
            response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f"{model_id}/")
            if 'Contents' in response:
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': objects_to_delete}
                )

            model.delete()
            return Response(
                {"message": "Model and remote artifacts deleted successfully"}, status=status.HTTP_200_OK
            )
        except Model.DoesNotExist:
            return Response(
                {"error": "Model not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

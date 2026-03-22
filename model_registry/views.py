import os
import shutil
import uuid
import zipfile
from pathlib import Path

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


class ModelUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ModelUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload_file = serializer.validated_data["file"]

        if upload_file.size > settings.MAX_MODEL_ZIP_BYTES:
            return Response({"error": "Uploaded zip exceeds max allowed size"}, status=status.HTTP_400_BAD_REQUEST)

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

            model_cfg = config.get("model")
            runtime = config.get("runtime")
            artifacts = config.get("artifacts")

            if not isinstance(model_cfg, dict):
                raise ValueError("model section missing")
            for field in ["name", "framework", "task"]:
                if field not in model_cfg:
                    raise ValueError(f"model.{field} missing")

            if not isinstance(runtime, dict):
                raise ValueError("runtime section missing")
            entry_point = runtime.get("entry_point")
            if not entry_point:
                raise ValueError("runtime.entry_point missing")

            if not isinstance(artifacts, dict):
                raise ValueError("artifacts section missing")

            # Validate required artifact files by runtime entry point
            if entry_point == "pipeline.py":
                if not (version_path / "pipeline.py").exists():
                    raise ValueError("pipeline.py not found")
            elif entry_point == "pipeline.pkl":
                pipeline_file = artifacts.get("pipeline_file", "pipeline.pkl")
                if not (version_path / pipeline_file).exists():
                    raise ValueError(f"{pipeline_file} not found")
            elif entry_point == "model.pkl":
                model_file = artifacts.get("model_file", "model.pkl")
                if not (version_path / model_file).exists():
                    raise ValueError(f"{model_file} not found")
            else:
                raise ValueError(f"Invalid runtime.entry_point: {entry_point}")

            model = Model.objects.create(
                id=model_id,
                name=model_cfg["name"],
                framework=model_cfg["framework"],
                task_type=model_cfg["task"],
                owner=request.user,
            )

            ModelVersion.objects.create(
                model=model,
                version=version,
                artifact_path=str(version_path),
                status="READY",
            )

            return Response(
                {"message": "Model uploaded successfully", "model_id": model_id, "version": version},
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            if model_root.exists():
                shutil.rmtree(model_root)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
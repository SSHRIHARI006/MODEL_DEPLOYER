import os
import zipfile
import uuid
import yaml
import shutil

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from .models import Model, ModelVersion
from users.models import User

BASE_STORAGE = os.path.join(settings.BASE_DIR, "storage", "models")


@csrf_exempt
def upload_model(request):

    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    file = request.FILES.get("file")

    if not file:
        return JsonResponse({"error": "No file uploaded"}, status=400)

    if not file.name.endswith(".zip"):
        return JsonResponse({"error": "Only .zip files allowed"}, status=400)

    model_id = str(uuid.uuid4())

    try:
        # Create model directory
        model_root = os.path.join(BASE_STORAGE, model_id)
        os.makedirs(model_root, exist_ok=True)

        # Version logic
        existing_versions = os.listdir(model_root)
        version = f"v{len(existing_versions) + 1}"

        version_path = os.path.join(model_root, version)
        os.makedirs(version_path, exist_ok=True)

        zip_path = os.path.join(version_path, "model.zip")

        # Save zip
        with open(zip_path, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        # Extract safely
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                member_path = os.path.join(version_path, member)
                if not os.path.abspath(member_path).startswith(os.path.abspath(version_path)):
                    raise Exception("Unsafe file path in zip")

            zip_ref.extractall(version_path)

        os.remove(zip_path)

        # Validate YAML
        yaml_path = os.path.join(version_path, "model.yaml")

        if not os.path.exists(yaml_path):
            raise Exception("model.yaml missing")

        with open(yaml_path, "r") as f:
            try:
                config = yaml.safe_load(f)
            except Exception:
                raise Exception("Invalid YAML format")

        # Required fields
        # ---- MODEL SECTION ----
            if "model" not in config:
                raise Exception("model section missing")

            for field in ["name", "framework", "task"]:
                if field not in config["model"]:
                    raise Exception(f"model.{field} missing")

            # ---- RUNTIME SECTION ----
            if "runtime" not in config:
                raise Exception("runtime section missing")

            if "entry_point" not in config["runtime"]:
                raise Exception("runtime.entry_point missing")

            # ---- ARTIFACTS (optional but recommended) ----
            if "artifacts" not in config:
                raise Exception("artifacts section missing")

        # Get user (temporary)
        user = User.objects.first()
        if not user:
            return JsonResponse({"error": "No users found"}, status=400)

        # Create Model
        model = Model.objects.create(
            id=model_id,
            name=config["model"]["name"],
            framework=config["model"]["framework"],
            task_type=config["model"]["task"],
            owner=user
        )

        # Create Version
        ModelVersion.objects.create(
            model=model,
            version=version,
            artifact_path=version_path,
            status="READY"
        )

        return JsonResponse({
            "message": "Model uploaded successfully",
            "model_id": model_id,
            "version": version
        })

    except Exception as e:
        if os.path.exists(os.path.join(BASE_STORAGE, model_id)):
            shutil.rmtree(os.path.join(BASE_STORAGE, model_id))

        return JsonResponse({"error": str(e)}, status=400)
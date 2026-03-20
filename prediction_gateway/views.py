import os
import json
import time
import importlib.util
import joblib
import yaml

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from model_registry.models import Model
from .models import PredictionLog
from api_keys.models import APIKey


@csrf_exempt
def predict(request, model_id):

    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    # ---------------- MODEL FETCH ----------------
    try:
        model = Model.objects.get(id=model_id)
    except Model.DoesNotExist:
        return JsonResponse({"error": "Model not found"}, status=404)

    # ---------------- AUTH ----------------
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    api_key = auth_header.split("Bearer ")[-1].strip()

    try:
        key_obj = APIKey.objects.get(
            key=api_key,
            is_active=True,
            model_id=model_id
        )
    except APIKey.DoesNotExist:
        return JsonResponse({"error": "Invalid API key"}, status=403)

    # ---------------- VERSION ----------------
    version = model.versions.order_by("-created_at").first()

    if not version:
        return JsonResponse({"error": "No version found"}, status=404)

    model_path = version.artifact_path

    # ---------------- INPUT ----------------
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    # ---------------- INFERENCE ----------------
    try:
        start = time.time()

        result = run_inference(model_path, data)

        latency = (time.time() - start) * 1000

        PredictionLog.objects.create(
            uid=str(time.time()),
            user=key_obj.user,
            model=model,
            deployment=None,
            input_data=data,
            output_data={"prediction": result},
            latency_ms=latency,
            status="SUCCESS"
        )

        return JsonResponse({
            "prediction": result,
            "latency_ms": latency
        })

    except Exception as e:

        PredictionLog.objects.create(
            uid=str(time.time()),
            user=key_obj.user,
            model=model,
            deployment=None,
            input_data=data,
            output_data={},
            latency_ms=0,
            status="ERROR",
            error_message=str(e)
        )

        return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------
# CORE INFERENCE ENGINE
# ---------------------------------------------------

def run_inference(model_path, data):

    yaml_path = os.path.join(model_path, "model.yaml")

    if not os.path.exists(yaml_path):
        raise Exception("model.yaml not found")

    with open(yaml_path, "r") as f:
        try:
            config = yaml.safe_load(f)
        except Exception:
            raise Exception("Invalid YAML format")

    if "runtime" not in config:
        raise Exception("runtime section missing in model.yaml")

    runtime = config["runtime"]
    artifacts = config.get("artifacts", {})

    # ---------------- SCHEMA VALIDATION ----------------
    schema_path = os.path.join(model_path, "schema.json")

    if os.path.exists(schema_path):
        import jsonschema

        with open(schema_path, "r") as f:
            schema = json.load(f)

        try:
            jsonschema.validate(instance=data, schema=schema)
        except Exception as e:
            raise Exception(f"Invalid input: {str(e)}")

    entry_point = runtime.get("entry_point")

    if not entry_point:
        raise Exception("runtime.entry_point missing")

    # ---------------- CASE 1: pipeline.py ----------------
    if entry_point == "pipeline.py":

        file_path = os.path.join(model_path, "pipeline.py")

        if not os.path.exists(file_path):
            raise Exception("pipeline.py not found")

        spec = importlib.util.spec_from_file_location("pipeline", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        func_name = runtime.get("predict_function", "predict")

        if not hasattr(module, func_name):
            raise Exception(f"{func_name} not found in pipeline.py")

        return getattr(module, func_name)(data, model_path)

    # ---------------- CASE 2: pipeline.pkl ----------------
    elif entry_point == "pipeline.pkl":

        file_name = artifacts.get("pipeline_file", "pipeline.pkl")
        file_path = os.path.join(model_path, file_name)

        if not os.path.exists(file_path):
            raise Exception("pipeline.pkl not found")

        obj = joblib.load(file_path)

        X = data.get("input")

        if X is None:
            raise Exception("Missing 'input' field")

        return obj.predict([X]).tolist()

    # ---------------- CASE 3: model.pkl ----------------
    elif entry_point == "model.pkl":

        file_name = artifacts.get("model_file", "model.pkl")
        file_path = os.path.join(model_path, file_name)

        if not os.path.exists(file_path):
            raise Exception("model.pkl not found")

        obj = joblib.load(file_path)

        X = data.get("input")

        if X is None:
            raise Exception("Missing 'input' field")

        return obj.predict([X]).tolist()

    # ---------------- INVALID ----------------
    else:
        raise Exception(f"Invalid entry_point: {entry_point}")
import importlib.util
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import joblib
import yaml
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from model_registry.models import Model
from .models import PredictionLog
from .permissions import HasValidModelAPIKey
from .serializers import PredictRequestSerializer


class InferenceClientError(Exception):
    pass


class InferenceServerError(Exception):
    pass


class PredictAPIView(APIView):
    permission_classes = [IsAuthenticated, HasValidModelAPIKey]

    def post(self, request, model_id):
        model = get_object_or_404(Model, id=model_id)

        version = model.versions.order_by("-created_at").first()
        if not version:
            return Response({"error": "No version found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PredictRequestSerializer(data={"payload": request.data})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data["payload"]

        start = time.time()
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(run_inference, version.artifact_path, data)
            result = future.result(timeout=settings.INFERENCE_TIMEOUT_SECONDS)
            latency = (time.time() - start) * 1000

            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=None,
                input_data=data,
                output_data={"prediction": result},
                latency_ms=latency,
                status="SUCCESS",
            )
            return Response({"prediction": result, "latency_ms": latency}, status=status.HTTP_200_OK)

        except FuturesTimeoutError:
            latency = (time.time() - start) * 1000
            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=None,
                input_data=data,
                output_data={},
                latency_ms=latency,
                status="ERROR",
                error_message="Inference timed out",
            )
            return Response({"error": "Inference timed out"}, status=status.HTTP_504_GATEWAY_TIMEOUT)

        except InferenceClientError as e:
            latency = (time.time() - start) * 1000
            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=None,
                input_data=data,
                output_data={},
                latency_ms=latency,
                status="ERROR",
                error_message=str(e),
            )
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            latency = (time.time() - start) * 1000
            PredictionLog.objects.create(
                uid=str(time.time()),
                user=request.user,
                model=model,
                deployment=None,
                input_data=data,
                output_data={},
                latency_ms=latency,
                status="ERROR",
                error_message=str(e),
            )
            error_msg = str(e) if settings.DEBUG else "Internal server error"
            return Response({"error": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        finally:
            executor.shutdown(wait=False, cancel_futures=True)


def run_inference(model_path, data):
    yaml_path = os.path.join(model_path, "model.yaml")
    if not os.path.exists(yaml_path):
        raise InferenceServerError("model.yaml not found")

    with open(yaml_path, "r") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise InferenceServerError("Invalid YAML format")

    runtime = config.get("runtime")
    if not isinstance(runtime, dict):
        raise InferenceServerError("runtime section missing in model.yaml")

    artifacts = config.get("artifacts", {})

    schema_path = os.path.join(model_path, "schema.json")
    if os.path.exists(schema_path):
        import jsonschema

        with open(schema_path, "r") as f:
            schema = json.load(f)
        try:
            jsonschema.validate(instance=data, schema=schema)
        except Exception as e:
            raise InferenceClientError(f"Invalid input: {str(e)}")

    entry_point = runtime.get("entry_point")
    if not entry_point:
        raise InferenceServerError("runtime.entry_point missing")

    if entry_point == "pipeline.py":
        file_path = os.path.join(model_path, "pipeline.py")
        if not os.path.exists(file_path):
            raise InferenceServerError("pipeline.py not found")

        spec = importlib.util.spec_from_file_location("pipeline", file_path)
        if spec is None or spec.loader is None:
            raise InferenceServerError("Failed to load pipeline.py")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        func_name = runtime.get("predict_function", "predict")
        if not hasattr(module, func_name):
            raise InferenceServerError(f"{func_name} not found in pipeline.py")

        return getattr(module, func_name)(data, model_path)

    if entry_point == "pipeline.pkl":
        file_name = artifacts.get("pipeline_file", "pipeline.pkl")
        file_path = os.path.join(model_path, file_name)
        if not os.path.exists(file_path):
            raise InferenceServerError(f"{file_name} not found")

        x = data.get("input")
        if x is None:
            raise InferenceClientError("Missing 'input' field")

        obj = joblib.load(file_path)
        return obj.predict([x]).tolist()

    if entry_point == "model.pkl":
        file_name = artifacts.get("model_file", "model.pkl")
        file_path = os.path.join(model_path, file_name)
        if not os.path.exists(file_path):
            raise InferenceServerError(f"{file_name} not found")

        x = data.get("input")
        if x is None:
            raise InferenceClientError("Missing 'input' field")

        obj = joblib.load(file_path)
        return obj.predict([x]).tolist()

    raise InferenceServerError(f"Invalid entry_point: {entry_point}")
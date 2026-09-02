"""Shared end-to-end validation harness for the model zoos.

Runs against a live Model Deployer stack: register -> upload -> deploy ->
poll -> create API key -> predict -> repeat predict (cache check).
"""
import csv
import json
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import requests
import yaml

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEPLOY_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 2
PREDICT_MAX_ATTEMPTS = 5
PREDICT_FALLBACK_RETRY_AFTER = 10
RESULTS_DIR = Path(__file__).resolve().parent / "results"

TABULAR_PAYLOAD = {"instances": [{"f1": 0.5, "f2": -0.3, "f3": 1.2, "f4": 0.7}]}
SEQUENCE_PAYLOAD = {"instances": [[0.5, -0.3, 1.2, 0.7]]}

RESULT_FIELDS = [
    "name",
    "framework",
    "task_type",
    "input_type",
    "upload_status",
    "deploy_status",
    "final_status",
    "last_error",
    "deploy_seconds",
    "predict_seconds",
    "cache_hit_seconds",
    "prediction_count",
    "all_finite",
    "cache_match",
    "passed",
    "detail",
]

PYTORCH_SELECTED = [
    "01_linear_regression",
    "02_logistic_regression",
    "05_deep_mlp_regressor",
    "06_dropout_classifier",
    "10_shallow_ann",
    "15_cnn_1d_classifier",
    "17_rnn_classifier",
    "18_lstm_classifier",
]


@dataclass
class ModelTarget:
    framework: str
    model_dir: Path
    task_type: str = ""
    input_type: str = "tabular"
    payload: dict = field(default_factory=lambda: dict(TABULAR_PAYLOAD))

    @property
    def name(self) -> str:
        return self.model_dir.name

    @property
    def zip_path(self) -> Path:
        return self.model_dir / f"{self.model_dir.name}.zip"


def base_url() -> str:
    return os.getenv("MODEL_DEPLOYER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def load_manifest(model_dir: Path) -> dict:
    manifest_path = model_dir / "model.yaml"
    with manifest_path.open() as stream:
        manifest = yaml.safe_load(stream)
    if not isinstance(manifest, dict):
        raise ValueError(f"model.yaml in {model_dir} is not a mapping")
    return manifest


def payload_for_input_type(input_type: str) -> dict:
    if input_type == "tabular":
        return dict(TABULAR_PAYLOAD)
    return dict(SEQUENCE_PAYLOAD)


def discover_targets(zoo_root: Path, framework: str, names=None):
    targets = []
    for name in sorted(p.name for p in zoo_root.iterdir() if p.is_dir()):
        if names is not None and name not in names:
            continue
        model_dir = zoo_root / name
        if not model_dir.name[:2].isdigit():
            continue
        manifest = load_manifest(model_dir)
        input_type = manifest.get("input_type", "tabular")
        targets.append(
            ModelTarget(
                framework=framework,
                model_dir=model_dir,
                task_type=manifest.get("task_type", ""),
                input_type=input_type,
                payload=payload_for_input_type(input_type),
            )
        )
    if names is not None:
        found = {t.name for t in targets}
        missing = [name for name in names if name not in found]
        if missing:
            raise FileNotFoundError(f"Missing zoo models: {', '.join(missing)}")
    return targets


def register_and_login(base=None):
    base = base or base_url()
    suffix = uuid.uuid4().hex[:8]
    email = f"zoo_{suffix}@example.com"
    username = f"zoo_user_{suffix}"
    password = "ZooTestPass123!"

    register = requests.post(
        f"{base}/api/auth/register/",
        json={"email": email, "username": username, "password": password},
    )
    if register.status_code not in (200, 201):
        raise RuntimeError(f"register failed: {register.status_code} {register.text[:200]}")

    login = requests.post(
        f"{base}/api/auth/login/",
        json={"email": email, "password": password},
    )
    if login.status_code != 200:
        raise RuntimeError(f"login failed: {login.status_code} {login.text[:200]}")
    return login.json()["access"]


def validate_predictions(body: dict, expected_count: int):
    if not isinstance(body, dict):
        return False, "response body is not an object"
    predictions = body.get("predictions")
    if not isinstance(predictions, list):
        return False, "response has no predictions array"
    if len(predictions) != expected_count:
        return False, (
            f"predictions length {len(predictions)} != instances length {expected_count}"
        )

    def walk(value):
        if isinstance(value, list):
            for item in value:
                ok, detail = walk(item)
                if not ok:
                    return False, detail
            return True, ""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, f"non-numeric prediction value: {value!r}"
        number = float(value)
        if not math.isfinite(number):
            return False, f"non-finite prediction value: {value!r}"
        return True, ""

    for item in predictions:
        ok, detail = walk(item)
        if not ok:
            return False, detail
    return True, ""


def deploy_and_wait(token, version_id, base=None, timeout=DEPLOY_TIMEOUT_SECONDS):
    base = base or base_url()
    headers = {"Authorization": f"Bearer {token}"}

    start = time.time()
    create = requests.post(
        f"{base}/api/deployments/",
        headers=headers,
        json={"model_version_id": str(version_id)},
    )
    if create.status_code != 202:
        return {
            "deploy_status": create.status_code,
            "final_status": "SUBMIT_FAILED",
            "last_error": create.text[:300],
            "deploy_seconds": round(time.time() - start, 3),
        }

    deployment_id = create.json().get("id")
    deadline = start + timeout
    last_status = "PENDING"
    last_error = None

    while time.time() < deadline:
        poll = requests.get(f"{base}/api/deployments/{deployment_id}/", headers=headers)
        if poll.status_code != 200:
            return {
                "deploy_status": create.status_code,
                "final_status": "POLL_FAILED",
                "last_error": f"poll HTTP {poll.status_code}: {poll.text[:300]}",
                "deploy_seconds": round(time.time() - start, 3),
            }
        body = poll.json()
        last_status = body.get("status", "UNKNOWN")
        last_error = body.get("last_error") or None
        if last_status == "RUNNING":
            return {
                "deploy_status": create.status_code,
                "final_status": last_status,
                "last_error": last_error,
                "deploy_seconds": round(time.time() - start, 3),
            }
        if last_status == "FAILED":
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    detail = last_error or f"timed out after {timeout}s in status {last_status}"
    return {
        "deploy_status": create.status_code,
        "final_status": last_status,
        "last_error": detail,
        "deploy_seconds": round(time.time() - start, 3),
    }


def post_predict(base, headers, model_id, payload):
    """POST one predict request, backing off on the per-user rate limit.

    The gateway throttles predictions per user ("predict": 20/min). A real
    client honors Retry-After and retries, so the harness does too; the
    returned elapsed time covers only the attempt that actually ran.
    """
    for attempt in range(1, PREDICT_MAX_ATTEMPTS + 1):
        start = time.time()
        response = requests.post(
            f"{base}/api/predict/{model_id}/",
            headers=headers,
            json=payload,
        )
        elapsed = round(time.time() - start, 3)
        if response.status_code != 429 or attempt == PREDICT_MAX_ATTEMPTS:
            return response, elapsed
        try:
            wait = float(response.headers.get("Retry-After") or PREDICT_FALLBACK_RETRY_AFTER)
        except ValueError:
            wait = PREDICT_FALLBACK_RETRY_AFTER
        time.sleep(min(wait, 65.0))


def run_model(target: ModelTarget, token, base=None):
    base = base or base_url()
    headers = {"Authorization": f"Bearer {token}"}
    result = {field_name: None for field_name in RESULT_FIELDS}
    result.update(
        {
            "name": target.name,
            "framework": target.framework,
            "task_type": target.task_type,
            "input_type": target.input_type,
            "all_finite": False,
            "cache_match": False,
            "passed": False,
        }
    )

    def fail(detail):
        result["detail"] = detail
        return result

    if not target.zip_path.exists():
        return fail(f"missing zip: {target.zip_path}")

    with target.zip_path.open("rb") as upload_file:
        upload = requests.post(
            f"{base}/api/models/upload/",
            headers=headers,
            files={"file": (target.zip_path.name, upload_file, "application/zip")},
        )
    result["upload_status"] = upload.status_code
    if upload.status_code != 201:
        return fail(f"upload HTTP {upload.status_code}: {upload.text[:300]}")

    upload_body = upload.json()
    model_id = upload_body["model_id"]
    version_id = upload_body["model_version_id"]

    deploy = deploy_and_wait(token, version_id, base=base)
    result.update(
        {
            "deploy_status": deploy["deploy_status"],
            "final_status": deploy["final_status"],
            "last_error": deploy["last_error"],
            "deploy_seconds": deploy["deploy_seconds"],
        }
    )
    if deploy["final_status"] != "RUNNING":
        return fail(f"deployment ended in {deploy['final_status']}: {deploy['last_error']}")
    if deploy["last_error"]:
        return fail(f"deployment succeeded but last_error is set: {deploy['last_error']}")

    key_response = requests.post(
        f"{base}/api/keys/",
        headers=headers,
        json={"model_id": model_id, "name": f"zoo-{target.name}"},
    )
    if key_response.status_code != 201:
        return fail(f"api key creation HTTP {key_response.status_code}: {key_response.text[:300]}")
    api_key = key_response.json()["key"]

    predict_headers = {
        "Authorization": f"Bearer {token}",
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = target.payload

    first, predict_seconds = post_predict(base, predict_headers, model_id, payload)
    result["predict_seconds"] = predict_seconds
    if first.status_code != 200:
        return fail(f"cold predict HTTP {first.status_code}: {first.text[:300]}")

    first_body = first.json()
    expected_count = len(payload["instances"])
    ok, detail = validate_predictions(first_body, expected_count)
    result["prediction_count"] = (
        len(first_body.get("predictions", [])) if isinstance(first_body, dict) else None
    )
    if not ok:
        return fail(f"cold prediction invalid: {detail}")
    result["all_finite"] = True

    second, cache_hit_seconds = post_predict(base, predict_headers, model_id, payload)
    result["cache_hit_seconds"] = cache_hit_seconds
    if second.status_code != 200:
        return fail(f"repeat predict HTTP {second.status_code}: {second.text[:300]}")
    if second.json() != first_body:
        return fail("repeat prediction response differs from cold response")
    result["cache_match"] = True

    result["passed"] = True
    result["detail"] = ""
    return result


def write_report(records, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        json.dump(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "base_url": base_url(),
                "model_count": len(records),
                "passed": sum(1 for record in records if record.get("passed")),
                "results": records,
            },
            stream,
            indent=2,
        )

    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in RESULT_FIELDS})
    return csv_path


def print_table(records):
    header = (
        f"{'model':<34}{'framework':<10}{'deploy s':>9}{'predict s':>10}"
        f"{'cache s':>9}  status"
    )
    print(header)
    print("-" * len(header))
    for record in records:
        status = "PASS" if record.get("passed") else f"FAIL: {record.get('detail', '')[:60]}"
        print(
            f"{record['name']:<34}{record['framework']:<10}"
            f"{record.get('deploy_seconds') or 0:>9.2f}"
            f"{record.get('predict_seconds') or 0:>10.3f}"
            f"{record.get('cache_hit_seconds') or 0:>9.3f}  {status}"
        )
    passed = sum(1 for record in records if record.get("passed"))
    print("-" * len(header))
    print(f"{passed}/{len(records)} models passed")

"""End-to-end test: upload, deploy, generate API key, and run inference
for all 20 PyTorch zoo models.

Usage:
  1. Start Django:  .venv/bin/python manage.py runserver 8000
  2. Start Worker:  STORAGE_ROOT=./storage .venv/bin/uvicorn runners.worker:app --port 8002
  3. Run script:    .venv/bin/python test_models/pytorch_zoo/test_all_models.py
"""
import sys
import time
import uuid
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
ZOO_ROOT = Path(__file__).resolve().parent
TIMEOUT = 120  # max seconds to wait for deployment

# 4-feature sample payload for tabular models
TABULAR_PAYLOAD = {"instances": [{"f1": 0.5, "f2": -0.3, "f3": 1.2, "f4": 0.7}]}
# same as list for sequence/image_1d models
SEQ_PAYLOAD = {"instances": [[0.5, -0.3, 1.2, 0.7]]}


def get_model_dirs():
    dirs = sorted(d for d in ZOO_ROOT.iterdir() if d.is_dir() and d.name[0].isdigit())
    return dirs


def register_and_login():
    email = f"zoo_{uuid.uuid4().hex[:8]}@test.com"
    pw = "ZooTestPass123!"
    requests.post(f"{BASE_URL}/api/auth/register/", json={"email": email, "password": pw}).raise_for_status()
    res = requests.post(f"{BASE_URL}/api/auth/login/", json={"email": email, "password": pw})
    res.raise_for_status()
    return res.json()["access"]


def test_model(model_dir: Path, token: str):
    name = model_dir.name
    zip_path = model_dir / f"{name}.zip"
    if not zip_path.exists():
        return "SKIP", "no zip found"

    headers = {"Authorization": f"Bearer {token}"}

    # Upload
    with open(zip_path, "rb") as f:
        res = requests.post(f"{BASE_URL}/api/models/upload/", headers=headers, files={"file": f})
    if res.status_code != 201:
        return "UPLOAD_FAIL", res.text[:200]
    data = res.json()
    model_id = data["model_id"]
    version_id = data["model_version_id"]

    # Deploy
    res = requests.post(f"{BASE_URL}/api/deployments/", headers=headers, json={"model_version_id": version_id})
    if res.status_code not in (201, 202):
        return "DEPLOY_FAIL", res.text[:200]
    dep_id = res.json()["id"]

    # Poll
    deadline = time.time() + TIMEOUT
    status = "PENDING"
    while time.time() < deadline:
        res = requests.get(f"{BASE_URL}/api/deployments/{dep_id}/", headers=headers)
        status = res.json().get("status", "UNKNOWN")
        if status in ("RUNNING", "FAILED"):
            break
        time.sleep(2)

    if status != "RUNNING":
        err = res.json().get("last_error", "unknown")
        return "BUILD_FAIL", str(err)[:200]

    # API Key
    res = requests.post(f"{BASE_URL}/api/keys/", headers=headers, json={"model_id": model_id, "name": f"key-{name}"})
    if res.status_code != 201:
        return "KEY_FAIL", res.text[:200]
    api_key = res.json()["key"]

    # Read manifest to determine input type
    import yaml
    manifest = yaml.safe_load((model_dir / "model.yaml").read_text())
    input_type = manifest.get("input_type", "tabular")
    payload = TABULAR_PAYLOAD if input_type == "tabular" else SEQ_PAYLOAD

    # Predict
    pred_headers = {**headers, "X-API-Key": api_key, "Content-Type": "application/json"}
    res = requests.post(f"{BASE_URL}/api/predict/{model_id}/", headers=pred_headers, json=payload)
    if res.status_code != 200:
        return "PREDICT_FAIL", res.text[:200]

    body = res.json()
    return "PASS", f"predictions={str(body.get('predictions', []))[:60]}"


def main():
    model_dirs = get_model_dirs()
    print(f"Found {len(model_dirs)} models in zoo\n")

    print("Registering test user...")
    token = register_and_login()
    print("Logged in.\n")

    results = []
    passed = 0
    failed = 0

    for i, d in enumerate(model_dirs, 1):
        name = d.name
        print(f"[{i:2}/{len(model_dirs)}] {name}...", end=" ", flush=True)
        status, detail = test_model(d, token)
        results.append((name, status, detail))
        if status == "PASS":
            passed += 1
            print(f"PASS  ({detail})")
        else:
            failed += 1
            print(f"{status}  ({detail})")

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(model_dirs)}")
    print(f"{'='*60}")

    if failed > 0:
        print("\nFailed models:")
        for name, status, detail in results:
            if status != "PASS":
                print(f"  {name}: {status} — {detail}")
        sys.exit(1)
    else:
        print("\nAll models passed end-to-end verification!")


if __name__ == "__main__":
    main()

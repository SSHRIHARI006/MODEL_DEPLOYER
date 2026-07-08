from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import yaml
import boto3
from urllib.parse import urlparse

app = FastAPI()

DEFAULT_STORAGE = Path(os.getenv("STORAGE_ROOT", "/storage"))
MODELS_ROOT = DEFAULT_STORAGE / "models"
ENVS_ROOT = DEFAULT_STORAGE / "envs"


class InitModelRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    manifest_path: str = Field(..., min_length=1)


from typing import Any

class PredictRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    manifest_path: str = Field(..., min_length=1)
    instances: list[Any]


class TeardownRequest(BaseModel):
    model_id: str = Field(..., min_length=1)


def _run_cmd(cmd: list[str]) -> tuple[int, str, str, float]:
    start = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    duration_ms = round((time.time() - start) * 1000, 3)
    return proc.returncode, proc.stdout, proc.stderr, duration_ms


def _ensure_within_root(path: Path, root: Path) -> None:
    resolved = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Path escapes storage root"
        ) from exc


from botocore.client import Config

def _download_s3_artifact(s3_uri: str, local_dir: Path):
    if local_dir.exists() and list(local_dir.iterdir()):
        return  # Already cached

    local_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip('/')

    s3_client = boto3.client(
        's3',
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("MINIO_ROOT_USER", "admin"),
        aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "adminpassword"),
        config=Config(s3={'addressing_style': 'path'})
    )

    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' not in page:
            continue
        for obj in page['Contents']:
            key = obj['Key']
            rel_path = os.path.relpath(key, prefix)
            target_path = local_dir / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            s3_client.download_file(bucket, key, str(target_path))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/init-model")
def init_model(req: InitModelRequest):
    if req.manifest_path.startswith("s3://"):
        artifact_uri = req.manifest_path.rsplit('/', 1)[0]
        local_model_dir = MODELS_ROOT / req.model_id
        _download_s3_artifact(artifact_uri, local_model_dir)
        manifest_path = local_model_dir / "model.yaml"
    else:
        manifest_path = Path(req.manifest_path)

    _ensure_within_root(manifest_path, MODELS_ROOT)

    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")

    env_dir = ENVS_ROOT / req.model_id
    env_dir.mkdir(parents=True, exist_ok=True)

    venv_cmd = ["uv", "venv", "--system-site-packages", str(env_dir)]
    code, out, err, duration_ms = _run_cmd(venv_cmd)
    if code != 0:
        raise HTTPException(
            status_code=500, detail={"error": "venv creation failed", "stderr": err}
        )

    try:
        manifest = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=400, detail="manifest is not valid yaml"
        ) from exc

    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest must be a yaml object")

    requirements = manifest.get("requirements")
    if not requirements:
        raise HTTPException(status_code=400, detail="requirements missing in manifest")

    requirements_path = (manifest_path.parent / requirements).resolve()
    _ensure_within_root(requirements_path, MODELS_ROOT)
    if not requirements_path.exists():
        raise HTTPException(status_code=404, detail="requirements file not found")

    python_bin = env_dir / "bin" / "python"
    pip_cmd = [
        "uv",
        "pip",
        "install",
        "-r",
        str(requirements_path),
        "--python",
        str(python_bin),
    ]
    code, out, err, pip_ms = _run_cmd(pip_cmd)
    if code != 0:
        raise HTTPException(
            status_code=500, detail={"error": "pip install failed", "stderr": err}
        )

    return {"status": "ready", "venv_ms": duration_ms, "pip_ms": pip_ms}


BRIDGE_MAP = {
    "sklearn": "worker_bridge.py",
    "pytorch": "pytorch_bridge.py",
}


@app.post("/predict")
def predict(req: PredictRequest):
    if req.manifest_path.startswith("s3://"):
        artifact_uri = req.manifest_path.rsplit('/', 1)[0]
        local_model_dir = MODELS_ROOT / req.model_id
        _download_s3_artifact(artifact_uri, local_model_dir)
        manifest_path = local_model_dir / "model.yaml"
    else:
        manifest_path = Path(req.manifest_path)
        
    _ensure_within_root(manifest_path, MODELS_ROOT)

    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")

    env_dir = ENVS_ROOT / req.model_id
    python_bin = env_dir / "bin" / "python"
    if not python_bin.exists():
        raise HTTPException(status_code=400, detail="environment not initialized")

    # Determine framework from manifest to select the correct bridge
    try:
        manifest = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=400, detail="manifest is not valid yaml"
        ) from exc

    framework = manifest.get("framework", "sklearn") if isinstance(manifest, dict) else "sklearn"
    bridge_name = BRIDGE_MAP.get(framework)

    if not bridge_name:
        raise HTTPException(
            status_code=400, detail=f"unsupported framework: {framework}"
        )

    bridge_path = Path(__file__).resolve().parent / bridge_name
    if not bridge_path.exists():
        raise HTTPException(status_code=500, detail=f"bridge script missing: {bridge_name}")

    cmd = [str(python_bin), str(bridge_path), str(manifest_path)]
    payload = {"instances": req.instances}

    start = time.time()
    proc = subprocess.run(
        cmd, input=json.dumps(payload), capture_output=True, text=True, check=False
    )
    duration_ms = round((time.time() - start) * 1000, 3)

    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={"error": "inference failed", "stderr": proc.stderr.strip()},
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail="bridge returned invalid json"
        ) from exc

    data.setdefault("metadata", {})
    data["metadata"]["compute_ms"] = duration_ms
    return data


@app.post("/teardown")
def teardown(req: TeardownRequest):
    env_dir = ENVS_ROOT / req.model_id
    if env_dir.exists():
        for child in env_dir.iterdir():
            if child.is_dir():
                for nested in child.rglob("*"):
                    if nested.is_file():
                        nested.unlink(missing_ok=True)
                child.rmdir()
            else:
                child.unlink(missing_ok=True)
        env_dir.rmdir()

    return {"status": "deleted"}

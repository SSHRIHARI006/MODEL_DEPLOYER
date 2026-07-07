from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import yaml

app = FastAPI()

DEFAULT_STORAGE = Path(os.getenv("STORAGE_ROOT", "/storage"))
MODELS_ROOT = DEFAULT_STORAGE / "models"
ENVS_ROOT = DEFAULT_STORAGE / "envs"


class InitModelRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    manifest_path: str = Field(..., min_length=1)


class PredictRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    manifest_path: str = Field(..., min_length=1)
    instances: list[dict]


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/init-model")
def init_model(req: InitModelRequest):
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

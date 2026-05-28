from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import yaml


def _sanitize_sys_path() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    cwd = Path.cwd().resolve()
    blocked = {str(script_dir), str(repo_root), str(cwd)}
    sys.path = [path for path in sys.path if path not in blocked]


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("manifest path required\n")
        return 1

    manifest_path = Path(sys.argv[1]).resolve()
    if not manifest_path.exists():
        sys.stderr.write("manifest not found\n")
        return 1

    try:
        manifest = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError:
        sys.stderr.write("manifest is not valid yaml\n")
        return 1

    if not isinstance(manifest, dict):
        sys.stderr.write("manifest must be a yaml object\n")
        return 1

    model_artifact = manifest.get("model_artifact")
    if not model_artifact:
        sys.stderr.write("model_artifact missing in manifest\n")
        return 1

    artifact_path = (manifest_path.parent / model_artifact).resolve()
    if not artifact_path.exists():
        sys.stderr.write("model artifact not found\n")
        return 1

    raw = sys.stdin.read() or "{}"
    payload = json.loads(raw)
    instances = payload.get("instances", [])

    df = pd.DataFrame(instances)
    _sanitize_sys_path()
    model = joblib.load(artifact_path)

    predictions = model.predict(df).tolist()
    probabilities = None
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(df).tolist()

    output = {
        "predictions": predictions,
        "probabilities": probabilities,
        "metadata": {},
    }

    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

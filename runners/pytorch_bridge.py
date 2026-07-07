from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def _sanitize_sys_path() -> None:
    """Remove repo / script directories from sys.path so that the
    isolated venv packages are resolved first."""
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    cwd = Path.cwd().resolve()
    blocked = {str(script_dir), str(repo_root), str(cwd)}
    sys.path = [path for path in sys.path if path not in blocked]


def _load_model(manifest: dict, manifest_path: Path):
    """Load a PyTorch model from the manifest specification.

    Supports two serialization patterns:
      1. Full model saved via ``torch.save(model, path)``  (default)
      2. Architecture class + state_dict via ``torch.load(path)``

    The manifest may specify:
      - ``load_method``: "full" (default) or "state_dict"
      - ``model_class_file``: Python file containing the model class definition
      - ``model_class_name``: Name of the nn.Module subclass in that file
      - ``device``: "cpu" (default) or "cuda"
    """
    import torch

    model_artifact = manifest.get("model_artifact")
    if not model_artifact:
        sys.stderr.write("model_artifact missing in manifest\n")
        raise SystemExit(1)

    artifact_path = (manifest_path.parent / model_artifact).resolve()
    if not artifact_path.exists():
        sys.stderr.write("model artifact not found\n")
        raise SystemExit(1)

    device = manifest.get("device", "cpu")
    if device == "cuda" and not torch.cuda.is_available():
        sys.stderr.write(
            "CUDA requested but not available. Falling back to CPU.\n"
        )
        device = "cpu"

    load_method = manifest.get("load_method", "full")

    if load_method == "state_dict":
        # Need to import the model class from user-provided file
        model_class_file = manifest.get("model_class_file")
        model_class_name = manifest.get("model_class_name")

        if not model_class_file or not model_class_name:
            sys.stderr.write(
                "state_dict loading requires model_class_file and model_class_name\n"
            )
            raise SystemExit(1)

        class_path = (manifest_path.parent / model_class_file).resolve()
        if not class_path.exists():
            sys.stderr.write(f"model class file not found: {model_class_file}\n")
            raise SystemExit(1)

        # Dynamically import the user's module
        import importlib.util

        spec = importlib.util.spec_from_file_location("user_model", str(class_path))
        user_module = importlib.util.module_from_spec(spec)
        sys.modules["user_model"] = user_module

        # Add the model directory to sys.path so relative imports work
        model_dir = str(manifest_path.parent.resolve())
        if model_dir not in sys.path:
            sys.path.insert(0, model_dir)

        spec.loader.exec_module(user_module)

        model_cls = getattr(user_module, model_class_name, None)
        if model_cls is None:
            sys.stderr.write(
                f"class {model_class_name} not found in {model_class_file}\n"
            )
            raise SystemExit(1)

        # Instantiate and load weights
        model_instance = model_cls()
        state = torch.load(artifact_path, map_location=device, weights_only=True)
        model_instance.load_state_dict(state)
        model_instance.to(device)
    else:
        # Full model load (torch.save(model, path))
        model_instance = torch.load(artifact_path, map_location=device, weights_only=False)

    model_instance.eval()
    return model_instance, device


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

    raw = sys.stdin.read() or "{}"
    payload = json.loads(raw)
    instances = payload.get("instances", [])

    _sanitize_sys_path()

    import torch

    model, device = _load_model(manifest, manifest_path)

    # Determine input shape handling from manifest
    input_type = manifest.get("input_type", "tabular")  # tabular, sequence, image_1d

    if input_type == "tabular":
        # Flat feature vectors: [[f1, f2, ...], ...]
        rows = []
        for inst in instances:
            if isinstance(inst, dict):
                rows.append(list(inst.values()))
            elif isinstance(inst, list):
                rows.append(inst)
            else:
                rows.append([inst])
        tensor_input = torch.tensor(rows, dtype=torch.float32).to(device)

    elif input_type == "sequence":
        # Sequential data: instances is a list of sequences
        # Each instance is a list of timestep feature vectors
        rows = []
        for inst in instances:
            if isinstance(inst, dict):
                rows.append(list(inst.values()))
            elif isinstance(inst, list):
                rows.append(inst)
            else:
                rows.append([inst])
        tensor_input = torch.tensor(rows, dtype=torch.float32).to(device)
        # Reshape to (batch, seq_len, features) if needed
        if tensor_input.dim() == 2:
            tensor_input = tensor_input.unsqueeze(-1)

    elif input_type == "image_1d":
        # 1D signal data treated as Conv1d input: (batch, channels, length)
        rows = []
        for inst in instances:
            if isinstance(inst, dict):
                rows.append(list(inst.values()))
            elif isinstance(inst, list):
                rows.append(inst)
            else:
                rows.append([inst])
        tensor_input = torch.tensor(rows, dtype=torch.float32).to(device)
        # Conv1d expects (batch, channels, length)
        if tensor_input.dim() == 2:
            tensor_input = tensor_input.unsqueeze(1)

    else:
        sys.stderr.write(f"unsupported input_type: {input_type}\n")
        return 1

    # Run inference
    with torch.no_grad():
        raw_output = model(tensor_input)

    # Convert output to JSON-safe format
    predictions = raw_output.cpu().numpy().tolist()

    # Determine if we should compute probabilities
    task_type = manifest.get("task_type", "regression")
    probabilities = None

    if task_type == "classification":
        import torch.nn.functional as F

        probs = F.softmax(raw_output, dim=-1)
        probabilities = probs.cpu().numpy().tolist()
        # For classification, return predicted class indices
        predictions = raw_output.argmax(dim=-1).cpu().numpy().tolist()

    elif task_type == "binary_classification":
        probs = torch.sigmoid(raw_output)
        probabilities = probs.cpu().numpy().tolist()
        predictions = (probs > 0.5).int().cpu().numpy().tolist()

    output = {
        "predictions": predictions,
        "probabilities": probabilities,
        "metadata": {},
    }

    sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from core.archive import ArchiveError, ArchiveLimits, resolve_declared_path

SUPPORTED_FRAMEWORKS = ("sklearn", "pytorch")
SUPPORTED_PYTHON_VERSIONS = ("3.10", "3.11", "3.12", "3.13", "3.14")
SUPPORTED_TASK_TYPES = (
    "regression",
    "classification",
    "binary_classification",
    "multiclass_classification",
    "unknown",
)
SUPPORTED_INPUT_TYPES = ("tabular", "sequence", "image_1d")

MANIFEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ModelManifest",
    "type": "object",
    "required": ["framework", "python_version", "requirements", "model_artifact"],
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 100},
        "framework": {"type": "string", "enum": list(SUPPORTED_FRAMEWORKS)},
        "python_version": {"type": "string", "enum": list(SUPPORTED_PYTHON_VERSIONS)},
        "requirements": {"type": "string", "minLength": 1},
        "model_artifact": {"type": "string", "minLength": 1},
        "task_type": {"type": "string"},
        "input_type": {"type": "string", "enum": list(SUPPORTED_INPUT_TYPES)},
        "device": {"type": "string", "enum": ["cpu", "cuda"]},
        "load_method": {"type": "string", "enum": ["full", "state_dict"]},
        "model_class_file": {"type": "string"},
        "model_class_name": {"type": "string"},
        "smoke_test_input": {"type": ["array", "object"]},
        "input_schema": {"type": "object"},
    },
    "additionalProperties": True,
}


class ManifestValidationError(ArchiveError):
    """Raised when a model manifest violates the specification."""

    def __init__(self, message: str, code: str = "INVALID_MANIFEST", field_errors: dict | None = None):
        super().__init__(message)
        self.code = code
        self.field_errors = field_errors or {}


def validate_manifest(manifest: Any) -> None:
    """Validates the parsed model.yaml manifest against the canonical JSON Schema."""
    if not isinstance(manifest, dict):
        raise ManifestValidationError("Manifest must be a YAML mapping/object", code="MALFORMED_MANIFEST")

    validator = jsonschema.Draft7Validator(MANIFEST_SCHEMA)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: e.path)
    if errors:
        first_err = errors[0]
        field = ".".join(str(p) for p in first_err.path) if first_err.path else "root"
        msg = f"Validation failed at '{field}': {first_err.message}"
        raise ManifestValidationError(msg, code="INVALID_MANIFEST", field_errors={field: first_err.message})


def validate_bundle_files(bundle_dir: Path, manifest: dict, limits: ArchiveLimits | None = None) -> Path | None:
    """Resolves and validates all paths declared in the manifest against the bundle root.

    Returns the path to schema.json if found.
    """
    limits = limits or ArchiveLimits.from_settings()

    req_path = resolve_declared_path(bundle_dir, manifest["requirements"], label="requirements", limits=limits)
    if not req_path.is_file():
        raise ManifestValidationError(f"requirements file not found: {manifest['requirements']}", code="MISSING_REQUIREMENTS")

    art_path = resolve_declared_path(bundle_dir, manifest["model_artifact"], label="model_artifact", limits=limits)
    if not art_path.is_file():
        raise ManifestValidationError(f"model artifact not found: {manifest['model_artifact']}", code="MISSING_ARTIFACT")

    if manifest.get("load_method") == "state_dict":
        class_file = manifest.get("model_class_file")
        if not class_file:
            raise ManifestValidationError("load_method 'state_dict' requires 'model_class_file'", code="MISSING_CLASS_FILE")
        cls_path = resolve_declared_path(bundle_dir, class_file, label="model_class_file", limits=limits)
        if not cls_path.is_file():
            raise ManifestValidationError(f"model class file not found: {class_file}", code="MISSING_CLASS_FILE")

    schema_json_path = bundle_dir / "schema.json"
    if schema_json_path.is_file():
        try:
            with open(schema_json_path, "r") as f:
                schema_data = json.load(f)
            if not isinstance(schema_data, dict):
                raise ManifestValidationError("schema.json must contain a valid JSON Schema object", code="INVALID_INPUT_SCHEMA")
            jsonschema.Draft7Validator.check_schema(schema_data)
        except Exception as exc:
            raise ManifestValidationError(f"Invalid schema.json: {exc}", code="INVALID_INPUT_SCHEMA") from exc
        return schema_json_path

    return None


def validate_prediction_instances(instances: Any, input_schema: dict | None = None) -> None:
    """Validates prediction input instances for row consistency and optional schema match."""
    if not isinstance(instances, list) or len(instances) == 0:
        raise ValueError("instances must be a non-empty array")

    first_type = type(instances[0])
    if first_type not in (dict, list):
        raise ValueError("Each instance must be an object (feature mapping) or array (feature vector)")

    if first_type is dict:
        expected_keys = set(instances[0].keys())
        for idx, inst in enumerate(instances):
            if not isinstance(inst, dict):
                raise ValueError(f"Instance at index {idx} is not an object; all instances must be consistent")
            if set(inst.keys()) != expected_keys:
                raise ValueError(f"Instance at index {idx} has mismatched keys: expected {sorted(expected_keys)}, got {sorted(inst.keys())}")

    elif first_type is list:
        expected_len = len(instances[0])
        for idx, inst in enumerate(instances):
            if not isinstance(inst, list):
                raise ValueError(f"Instance at index {idx} is not an array; all instances must be consistent")
            if len(inst) != expected_len:
                raise ValueError(f"Instance at index {idx} has mismatched length: expected {expected_len}, got {len(inst)}")

    if input_schema is not None:
        try:
            jsonschema.validate(instances, input_schema)
        except jsonschema.ValidationError as err:
            raise ValueError(f"Input schema validation failed: {err.message}") from err

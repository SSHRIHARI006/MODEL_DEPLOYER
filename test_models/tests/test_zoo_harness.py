import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import zoo_harness


def test_validate_predictions_accepts_finite_values():
    ok, detail = zoo_harness.validate_predictions({"predictions": [1, 2.5]}, 2)
    assert ok
    assert detail == ""


def test_validate_predictions_accepts_nested_outputs():
    ok, detail = zoo_harness.validate_predictions({"predictions": [[0.5], [1.5]]}, 2)
    assert ok
    assert detail == ""


def test_validate_predictions_rejects_nan():
    ok, detail = zoo_harness.validate_predictions({"predictions": [float("nan")]}, 1)
    assert not ok
    assert "non-finite" in detail


def test_validate_predictions_rejects_infinity():
    ok, detail = zoo_harness.validate_predictions({"predictions": [float("inf")]}, 1)
    assert not ok
    assert "non-finite" in detail


def test_validate_predictions_rejects_non_numeric():
    ok, detail = zoo_harness.validate_predictions({"predictions": ["1.0"]}, 1)
    assert not ok
    assert "non-numeric" in detail


def test_validate_predictions_rejects_length_mismatch():
    ok, detail = zoo_harness.validate_predictions({"predictions": [1.0]}, 2)
    assert not ok
    assert "length" in detail


def test_validate_predictions_requires_predictions_array():
    ok, detail = zoo_harness.validate_predictions({"result": [1.0]}, 1)
    assert not ok
    assert "no predictions array" in detail


def test_payload_selection_by_input_type():
    assert zoo_harness.payload_for_input_type("tabular") == zoo_harness.TABULAR_PAYLOAD
    assert zoo_harness.payload_for_input_type("sequence") == zoo_harness.SEQUENCE_PAYLOAD
    assert zoo_harness.payload_for_input_type("image_1d") == zoo_harness.SEQUENCE_PAYLOAD


def test_pytorch_allowlist_matches_spec():
    assert len(zoo_harness.PYTORCH_SELECTED) == 8
    assert zoo_harness.PYTORCH_SELECTED == [
        "01_linear_regression",
        "02_logistic_regression",
        "05_deep_mlp_regressor",
        "06_dropout_classifier",
        "10_shallow_ann",
        "15_cnn_1d_classifier",
        "17_rnn_classifier",
        "18_lstm_classifier",
    ]


def test_discover_targets_applies_allowlist(tmp_path):
    for name in ("01_a", "02_b", "03_c"):
        model_dir = tmp_path / name
        model_dir.mkdir()
        (model_dir / "model.yaml").write_text("name: x\nframework: pytorch\n")
        (model_dir / f"{name}.zip").write_bytes(b"")

    targets = zoo_harness.discover_targets(tmp_path, "pytorch", names=["01_a", "03_c"])
    assert [target.name for target in targets] == ["01_a", "03_c"]


def test_discover_targets_raises_on_missing_allowlist_entry(tmp_path):
    model_dir = tmp_path / "01_a"
    model_dir.mkdir()
    (model_dir / "model.yaml").write_text("name: x\nframework: pytorch\n")

    with pytest.raises(FileNotFoundError, match="02_missing"):
        zoo_harness.discover_targets(tmp_path, "pytorch", names=["01_a", "02_missing"])


def test_deploy_and_wait_requires_202(monkeypatch):
    class FakeResponse:
        status_code = 201
        text = "created"

        def json(self):
            return {"id": "dep-1"}

    monkeypatch.setattr(zoo_harness.requests, "post", lambda *args, **kwargs: FakeResponse())
    result = zoo_harness.deploy_and_wait("token", "version-id", base="http://example", timeout=1)

    assert result["final_status"] == "SUBMIT_FAILED"
    assert result["deploy_status"] == 201


def test_deploy_and_wait_reports_failure_state(monkeypatch):
    class CreateResponse:
        status_code = 202

        def json(self):
            return {"id": "dep-1"}

    class PollResponse:
        status_code = 200

        def json(self):
            return {"status": "FAILED", "last_error": "boom"}

    monkeypatch.setattr(zoo_harness.requests, "post", lambda *args, **kwargs: CreateResponse())
    monkeypatch.setattr(zoo_harness.requests, "get", lambda *args, **kwargs: PollResponse())
    result = zoo_harness.deploy_and_wait("token", "version-id", base="http://example", timeout=1)

    assert result["final_status"] == "FAILED"
    assert result["last_error"] == "boom"
    assert result["deploy_status"] == 202


def test_write_report_persists_json_and_csv(tmp_path):
    records = [
        {
            "name": "01_demo",
            "framework": "sklearn",
            "task_type": "regression",
            "input_type": "tabular",
            "upload_status": 201,
            "deploy_status": 202,
            "final_status": "RUNNING",
            "last_error": None,
            "deploy_seconds": 1.25,
            "predict_seconds": 0.2,
            "cache_hit_seconds": 0.01,
            "prediction_count": 1,
            "all_finite": True,
            "cache_match": True,
            "passed": True,
            "detail": "",
        }
    ]
    report_path = tmp_path / "report.json"
    csv_path = zoo_harness.write_report(records, report_path)

    assert report_path.exists()
    assert csv_path.exists()
    assert csv_path.suffix == ".csv"

    import json

    body = json.loads(report_path.read_text())
    assert body["model_count"] == 1
    assert body["passed"] == 1
    assert body["results"][0]["name"] == "01_demo"

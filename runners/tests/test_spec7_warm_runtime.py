from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from runners import worker
from runners.worker import (
    PredictRequest,
    WarmRuntime,
    WarmRuntimeManager,
    WarmRuntimeState,
    live_metrics,
)


def test_warm_runtime_states():
    assert WarmRuntimeState.STARTING.value == "STARTING"
    assert WarmRuntimeState.READY.value == "READY"
    assert WarmRuntimeState.UNHEALTHY.value == "UNHEALTHY"
    assert WarmRuntimeState.STOPPING.value == "STOPPING"
    assert WarmRuntimeState.STOPPED.value == "STOPPED"


def test_warm_runtime_disabled_by_default():
    assert worker.RUNNER_WARM_RUNTIME_ENABLED is False


def test_warm_runtime_manager_lru_eviction(monkeypatch):
    mgr = WarmRuntimeManager(max_models=2)

    rt1 = MagicMock(spec=WarmRuntime)
    rt1.model_id = "m1"
    rt1.state = WarmRuntimeState.READY
    rt1.last_used_at = 100.0
    rt1.proc = MagicMock()
    rt1.proc.poll.return_value = None

    rt2 = MagicMock(spec=WarmRuntime)
    rt2.model_id = "m2"
    rt2.state = WarmRuntimeState.READY
    rt2.last_used_at = 200.0
    rt2.proc = MagicMock()
    rt2.proc.poll.return_value = None
    mgr.runtimes.update({"m1": rt1, "m2": rt2})

    class FakeRuntime(MagicMock):
        def __init__(self, model_id, *args, **kwargs):
            super().__init__()
            self.model_id = model_id
            self.state = WarmRuntimeState.READY
            self.last_used_at = 300.0
            self.proc = MagicMock()
            self.proc.poll.return_value = None

        def start(self):
            pass

    monkeypatch.setattr(worker, "WarmRuntime", FakeRuntime)
    mgr.get_or_create("m3", Path("/fake/manifest.yaml"), Path("/fake/python"), Path("/fake/bridge.py"))

    rt1.stop.assert_called_once()
    assert set(mgr.runtimes) == {"m2", "m3"}


def test_live_metrics_reports_warm_runtimes():
    metrics = live_metrics()
    assert "alive" in metrics
    assert "warm_runtimes" in metrics
    assert "count" in metrics["warm_runtimes"]
    assert "max" in metrics["warm_runtimes"]
    assert "models" in metrics["warm_runtimes"]


def _make_child(tmp_path: Path, body: str) -> WarmRuntime:
    script = tmp_path / "fake_bridge.py"
    script.write_text(body)
    return WarmRuntime("test-version", tmp_path / "model.yaml", Path(sys.executable), script)


def test_hung_child_times_out_and_is_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "RUNNER_PREDICT_TIMEOUT_SECONDS", 0.1)
    runtime = _make_child(
        tmp_path,
        "import sys, time\n"
        "print('{\\\"status\\\": \\\"ready\\\"}', flush=True)\n"
        "sys.stdin.readline()\n"
        "time.sleep(30)\n",
    )
    monkeypatch.setattr(worker, "RUNNER_HEALTHCHECK_TIMEOUT_SECONDS", 1)
    runtime.start()
    child = runtime.proc

    with pytest.raises(TimeoutError, match="timed out"):
        runtime.predict([{"x": 1}])

    assert runtime.state == WarmRuntimeState.STOPPED
    assert child is not None and child.poll() is not None


def test_hung_startup_is_timed_out_and_cleaned_up(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "RUNNER_HEALTHCHECK_TIMEOUT_SECONDS", 0.1)
    runtime = _make_child(tmp_path, "import time\ntime.sleep(30)\n")

    with pytest.raises(TimeoutError, match="timed out"):
        runtime.start()

    assert runtime.state == WarmRuntimeState.STOPPED
    assert runtime.proc is None


def test_stdout_and_stderr_are_bounded_and_large_response_kills_child(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "RUNNER_MAX_OUTPUT_BYTES", 128)
    monkeypatch.setattr(worker, "RUNNER_HEALTHCHECK_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(worker, "RUNNER_PREDICT_TIMEOUT_SECONDS", 1)
    runtime = _make_child(
        tmp_path,
        "import sys\n"
        "print('{\\\"status\\\": \\\"ready\\\"}', flush=True)\n"
        "while True:\n"
        " line=sys.stdin.readline()\n"
        " if not line: break\n"
        " sys.stderr.write('e'*4096); sys.stderr.flush()\n"
        " sys.stdout.write('x'*1024+'\\n'); sys.stdout.flush()\n",
    )
    runtime.start()
    child = runtime.proc

    with pytest.raises(RuntimeError, match="output exceeded"):
        runtime.predict([{"x": 1}])

    assert len(runtime._stderr_tail) <= worker.RUNNER_MAX_OUTPUT_BYTES
    assert runtime.state == WarmRuntimeState.STOPPED
    assert child is not None and child.poll() is not None


def test_prediction_permit_is_released_when_request_fails(monkeypatch, tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    monkeypatch.setattr(worker, "MODELS_ROOT", root)
    before = worker._predict_semaphore._value

    with pytest.raises(HTTPException):
        worker.predict(
            PredictRequest(
                model_id="version-1",
                manifest_path=str(tmp_path / "outside" / "model.yaml"),
                instances=[{"x": 1}],
            )
        )

    assert worker._predict_semaphore._value == before

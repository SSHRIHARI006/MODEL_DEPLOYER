"""REL-01/REL-03: `_run_bounded` must deliver stdin as well as bound the child.

Regression coverage for the defect where `input_bytes` was accepted and passed as
a pipe but never written, so any child that read stdin (the inference bridge and
the model validation step) blocked until the deadline and was killed.
"""

from __future__ import annotations

import sys

from runners.worker import _run_bounded


def _python(script: str) -> list[str]:
    return [sys.executable, "-c", script]


def test_delivers_stdin_to_the_child():
    code, out, err, duration_ms = _run_bounded(
        _python("import sys; sys.stdout.write('GOT:' + sys.stdin.read())"),
        timeout_seconds=10,
        input_bytes=b"hello",
    )

    assert code == 0, err
    assert out == "GOT:hello"
    assert duration_ms < 10_000


def test_closes_stdin_so_an_empty_payload_still_reads_as_eof():
    code, out, err, _ = _run_bounded(
        _python("import sys; sys.stdout.write('EMPTY:' + repr(sys.stdin.read()))"),
        timeout_seconds=10,
        input_bytes=b"",
    )

    assert code == 0, err
    assert out == "EMPTY:''"


def test_child_that_never_reads_stdin_still_hits_the_deadline():
    code, out, err, duration_ms = _run_bounded(
        _python("import sys, time; time.sleep(30)"),
        timeout_seconds=2,
        input_bytes=b"never consumed",
    )

    assert code != 0
    assert "<runner command timed out after 2s>" in out
    assert "<runner command timed out after 2s>" in err
    assert duration_ms >= 2_000


def test_output_is_still_capped_when_stdin_is_used():
    script = (
        "import sys; sys.stdin.read(); "
        "sys.stdout.write('x' * 4096)"
    )
    code, out, err, _ = _run_bounded(
        _python(script),
        timeout_seconds=10,
        input_bytes=b"go",
        max_output_bytes=128,
    )

    assert code == 0, err
    assert len(out) <= 128 + len("\n<output truncated by runner cap>\n")
    assert "<output truncated by runner cap>" in out

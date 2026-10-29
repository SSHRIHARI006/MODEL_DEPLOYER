#!/usr/bin/env python3
"""Concurrency and load test harness for Model Deployer (Spec 6 / 3E).

Includes safety guards: refuses non-localhost targets unless --allow-remote is provided.
Outputs structured JSON performance metrics.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests


def get_git_sha() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return "unknown"


def is_local_target(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname in ("127.0.0.1", "localhost", "::1", "0.0.0.0")


def run_load_test(
    target_url: str,
    endpoint: str,
    method: str,
    api_key: str | None,
    payload: dict[str, Any],
    concurrency: int,
    duration: float,
    output_path: Path | None = None,
) -> dict[str, Any]:
    url = f"{target_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    latencies_ms: list[float] = []
    status_counts: dict[int, int] = {}
    total_requests = 0
    start_time = time.time()
    end_time = start_time + duration

    def worker_loop() -> list[tuple[int, float]]:
        session = requests.Session()
        results: list[tuple[int, float]] = []
        is_get = method.upper() == "GET"
        while time.time() < end_time:
            t0 = time.time()
            try:
                if is_get:
                    res = session.get(url, headers=headers, timeout=10.0)
                else:
                    res = session.post(url, json=payload, headers=headers, timeout=10.0)
                dur = (time.time() - t0) * 1000.0
                results.append((res.status_code, dur))
            except Exception:
                dur = (time.time() - t0) * 1000.0
                results.append((599, dur))
        return results

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker_loop) for _ in range(concurrency)]
        for f in as_completed(futures):
            worker_results = f.result()
            for status_code, dur in worker_results:
                total_requests += 1
                latencies_ms.append(dur)
                status_counts[status_code] = status_counts.get(status_code, 0) + 1

    elapsed_actual = time.time() - start_time
    latencies_sorted = sorted(latencies_ms) if latencies_ms else [0.0]

    def percentile(p: float) -> float:
        if not latencies_sorted:
            return 0.0
        k = (len(latencies_sorted) - 1) * p
        f = int(k)
        c = f + 1
        if c < len(latencies_sorted):
            return latencies_sorted[f] + (k - f) * (latencies_sorted[c] - latencies_sorted[f])
        return latencies_sorted[f]

    metrics = {
        "commit_sha": get_git_sha(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": url,
        "concurrency": concurrency,
        "planned_duration_sec": duration,
        "actual_duration_sec": round(elapsed_actual, 3),
        "total_requests": total_requests,
        "rps": round(total_requests / elapsed_actual, 2) if elapsed_actual > 0 else 0.0,
        "status_distribution": status_counts,
        "latencies_ms": {
            "min": round(latencies_sorted[0], 2) if latencies_sorted else 0.0,
            "mean": round(sum(latencies_sorted) / len(latencies_sorted), 2) if latencies_sorted else 0.0,
            "p50": round(percentile(0.50), 2),
            "p95": round(percentile(0.95), 2),
            "p99": round(percentile(0.99), 2),
            "max": round(latencies_sorted[-1], 2) if latencies_sorted else 0.0,
        },
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(metrics, f, indent=2)

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Model Deployer Load Testing Harness (3E)")
    parser.add_argument("--target", default="http://127.0.0.1:8000", help="Base URL")
    parser.add_argument("--endpoint", default="/api/metrics/live/", help="Endpoint path")
    parser.add_argument("--method", default="POST", choices=["GET", "POST", "get", "post"], help="HTTP method")
    parser.add_argument("--api-key", default=None, help="X-API-Key token if required")
    parser.add_argument("--concurrency", type=int, default=5, help="Worker concurrency")
    parser.add_argument("--duration", type=float, default=3.0, help="Test duration in seconds")
    parser.add_argument("--allow-remote", action="store_true", help="Explicit opt-in to target non-localhost URLs")
    parser.add_argument("--output", default="test-results/loadtest.json", help="Path to write JSON results")

    args = parser.parse_args()

    if not is_local_target(args.target) and not args.allow_remote:
        sys.stderr.write(
            f"ERROR: Target '{args.target}' is not localhost.\n"
            "Safety guard: Load tests against remote hosts require explicit '--allow-remote'.\n"
        )
        sys.exit(1)

    print(f"Starting load test on {args.target}{args.endpoint} (method={args.method.upper()}, concurrency={args.concurrency}, duration={args.duration}s)...")
    payload = {"instances": [{"x": 1.0}]}
    metrics = run_load_test(
        target_url=args.target,
        endpoint=args.endpoint,
        method=args.method,
        api_key=args.api_key,
        payload=payload,
        concurrency=args.concurrency,
        duration=args.duration,
        output_path=Path(args.output),
    )

    print("\n--- Load Test Results ---")
    print(f"Total Requests: {metrics['total_requests']}")
    print(f"RPS:            {metrics['rps']}")
    print(f"Status codes:   {metrics['status_distribution']}")
    print(f"Latency p50:    {metrics['latencies_ms']['p50']} ms")
    print(f"Latency p95:    {metrics['latencies_ms']['p95']} ms")
    print(f"Latency p99:    {metrics['latencies_ms']['p99']} ms")
    print(f"Report saved:   {args.output}")


if __name__ == "__main__":
    main()

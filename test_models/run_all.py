"""Combined end-to-end validation of both model zoos.

Runs the 12 sklearn models and the 8 curated PyTorch models back-to-back
against one live stack and writes a single persisted report to
test_models/results/model_zoo_results.json (plus a CSV companion).

Usage:
  MODEL_DEPLOYER_BASE_URL=http://127.0.0.1:8000 \
    .venv/bin/python test_models/run_all.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import zoo_harness


def main():
    zoo_base = Path(__file__).resolve().parent
    print(f"Target stack: {zoo_harness.base_url()}\n")

    sklearn_targets = zoo_harness.discover_targets(zoo_base / "sklearn_zoo", "sklearn")
    pytorch_targets = zoo_harness.discover_targets(
        zoo_base / "pytorch_zoo", "pytorch", names=zoo_harness.PYTORCH_SELECTED
    )

    records = []
    # Model names are unique per owner and both zoos use numbered names, so
    # each zoo validates under its own freshly registered user.
    for zoo_label, targets in (("sklearn", sklearn_targets), ("pytorch", pytorch_targets)):
        token = zoo_harness.register_and_login()
        print(f"Validating {len(targets)} {zoo_label} models\n")
        for index, target in enumerate(targets, 1):
            print(f"[{index:2}/{len(targets)}] {target.name}...", end=" ", flush=True)
            record = zoo_harness.run_model(target, token)
            records.append(record)
            print("PASS" if record["passed"] else f"FAIL: {record['detail'][:80]}")
        print()
    zoo_harness.print_table(records)
    report_path = zoo_harness.RESULTS_DIR / "model_zoo_results.json"
    csv_path = zoo_harness.write_report(records, report_path)
    print(f"\nReport written to {report_path} and {csv_path}")

    failed = sum(1 for record in records if not record["passed"])
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

"""End-to-end validation of the sklearn zoo.

Runs all 12 generated sklearn models against a live stack:
register -> upload -> deploy -> poll -> create API key -> predict ->
repeat predict (cache check).

Usage:
  1. Start the stack (docker compose up or local API + worker).
  2. Run: .venv/bin/python test_models/sklearn_zoo/test_all_models.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import zoo_harness


def main():
    zoo_root = Path(__file__).resolve().parent
    token = zoo_harness.register_and_login()
    targets = zoo_harness.discover_targets(zoo_root, "sklearn")
    print(f"Validating {len(targets)} sklearn models\n")

    records = []
    for index, target in enumerate(targets, 1):
        print(f"[{index:2}/{len(targets)}] {target.name}...", end=" ", flush=True)
        record = zoo_harness.run_model(target, token)
        records.append(record)
        print("PASS" if record["passed"] else f"FAIL: {record['detail'][:80]}")

    print()
    zoo_harness.print_table(records)
    report_path = zoo_harness.RESULTS_DIR / "sklearn_zoo_results.json"
    csv_path = zoo_harness.write_report(records, report_path)
    print(f"\nReport written to {report_path} and {csv_path}")

    failed = sum(1 for record in records if not record["passed"])
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

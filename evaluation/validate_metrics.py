from __future__ import annotations
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

CORE = [
    ("integration_process", "read", "read_act_total_ms", "health-registry-service"),
    ("integration_process", "write", "write_act_total_ms", "hospital-service"),
    ("integration_process", "write", "write_act_total_ms", "messaging-service"),
    ("integration_process", "execute", "execute_total_ms", ""),
    ("digital_service", "request", "request_total_ms", "health-registry-service"),
    ("digital_service", "post", "post_total_ms", "hospital-service"),
    ("digital_service", "post", "post_total_ms", "messaging-service"),
]


def validate(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_run = defaultdict(list)
    for row in rows:
        if row.get("run_id"):
            by_run[row["run_id"]].append(row)

    complete = []
    incomplete = []
    for run_id, run_rows in sorted(by_run.items()):
        counts = Counter((r["component"], r["operation"], r["metric"], r["service_id"]) for r in run_rows)
        missing_or_duplicate = [(key, counts[key]) for key in CORE if counts[key] != 1]
        failed = any(r["metric"] == "execute_failed_ms" for r in run_rows)
        if not missing_or_duplicate and not failed:
            complete.append(run_id)
        else:
            incomplete.append((run_id, missing_or_duplicate, failed))
    return rows, complete, incomplete


def main():
    parser = argparse.ArgumentParser(description="Validate iDevS metric campaign completeness.")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--expected-runs", type=int, default=None)
    args = parser.parse_args()

    rows, complete, incomplete = validate(args.csv_file)
    print(f"CSV rows: {len(rows)}")
    print(f"Complete successful runs: {len(complete)}")
    print(f"Incomplete/failed runs: {len(incomplete)}")
    if incomplete:
        for run_id, problems, failed in incomplete[:10]:
            print(f"  {run_id}: failed={failed}; core-count problems={problems}")
    if args.expected_runs is not None and len(complete) != args.expected_runs:
        raise SystemExit(f"Expected {args.expected_runs} complete runs, found {len(complete)}")
    if incomplete:
        raise SystemExit("Campaign contains incomplete or failed runs.")
    print("Metric campaign is complete and internally consistent.")


if __name__ == "__main__":
    main()

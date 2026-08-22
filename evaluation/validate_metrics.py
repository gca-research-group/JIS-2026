from __future__ import annotations
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from metric_schema import CORE_FLOW, TRUSTED_INTERNAL, TRUSTED_FORBIDDEN_METRICS


def _normalise_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("component", ""),
        row.get("operation", ""),
        row.get("metric", ""),
        row.get("service_id", ""),
    )


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
        counts = Counter(_normalise_key(r) for r in run_rows)
        trusted = any(r.get("component") == "launcher" for r in run_rows)
        required = list(CORE_FLOW) + (list(TRUSTED_INTERNAL) if trusted else [])
        missing_or_duplicate = [(key, counts[key]) for key in required if counts[key] != 1]

        forbidden = []
        for row in run_rows:
            metric = row.get("metric", "")
            if metric == "execute_failed_ms" or (trusted and metric in TRUSTED_FORBIDDEN_METRICS):
                forbidden.append(metric)

        if not missing_or_duplicate and not forbidden:
            complete.append(run_id)
        else:
            incomplete.append((run_id, trusted, missing_or_duplicate, forbidden))

    return rows, complete, incomplete


def main():
    parser = argparse.ArgumentParser(description="Validate healthcare integration metric campaign completeness.")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--expected-runs", type=int, default=None)
    args = parser.parse_args()

    rows, complete, incomplete = validate(args.csv_file)
    print(f"CSV rows: {len(rows)}")
    print(f"Complete successful runs: {len(complete)}")
    print(f"Incomplete/failed runs: {len(incomplete)}")
    if incomplete:
        for run_id, trusted, problems, forbidden in incomplete[:10]:
            mode = "trusted" if trusted else "conventional"
            print(f"  {run_id} ({mode}): core/internal-count problems={problems}; forbidden metrics={forbidden}")
    if args.expected_runs is not None and len(complete) != args.expected_runs:
        raise SystemExit(f"Expected {args.expected_runs} complete runs, found {len(complete)}")
    if incomplete:
        raise SystemExit("Campaign contains incomplete, contaminated, or failed runs.")
    print("Metric campaign is complete and internally consistent.")


if __name__ == "__main__":
    main()

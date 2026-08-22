from __future__ import annotations
import argparse
import os
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "outside-proof-of-concept" / "sources" / "integration_process"
DEFAULT_METRICS = ROOT / "outside-proof-of-concept" / "metrics" / "all_metrics.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the conventional healthcare workflow repeatedly.")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--patient-id", default="P001")
    parser.add_argument("--program-id", default="2")
    parser.add_argument("--executable", type=Path, default=DEFAULT_EXE)
    args = parser.parse_args()

    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    exe = args.executable.resolve()
    if not exe.exists():
        raise SystemExit(f"Executable not found: {exe}. Compile it before starting the campaign.")

    for index in range(1, args.runs + 1):
        run_id = f"outside-{args.program_id}-{uuid.uuid4().hex}"
        env = os.environ.copy()
        env.update({
            "METRICS_FILE": str(DEFAULT_METRICS),
            "PROGRAM_ID": str(args.program_id),
            "PATIENT_ID": args.patient_id,
            "RUN_ID": run_id,
        })
        result = subprocess.run([str(exe)], env=env)
        if result.returncode != 0:
            raise SystemExit(f"Run {index}/{args.runs} failed: {run_id}. Reset the campaign before collecting the final dataset.")
        print(f"Run {index:02d}/{args.runs}: {run_id}")
    print("Conventional campaign completed successfully.")


if __name__ == "__main__":
    main()

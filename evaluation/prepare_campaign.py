from __future__ import annotations
import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

HEADER = "ts,run_id,component,operation,metric,value_ms,program_id,service_id\n"
ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_ROOT = ROOT / "campaign-archive"


def archive_if_nonempty(path: Path, archive_dir: Path, name: str) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > 1:
        archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, archive_dir / name)


def reset_environment(env_dir: Path, label: str, archive_dir: Path) -> None:
    metrics = env_dir / "metrics" / "all_metrics.csv"
    archive_if_nonempty(metrics, archive_dir, f"{label}_all_metrics.csv")
    metrics.parent.mkdir(parents=True, exist_ok=True)
    metrics.write_text(HEADER, encoding="utf-8")

    hospital = env_dir / "app-hospital" / "data_access" / "hospital_records.json"
    messaging = env_dir / "app-messaging" / "data_access" / "notifications.json"
    hospital.write_text(json.dumps({"Patients": [], "AuditLog": []}, indent=2) + "\n", encoding="utf-8")
    messaging.write_text("[]\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a clean performance campaign without deleting previous measurements.")
    parser.add_argument("environment", choices=["trusted", "conventional", "both"])
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = ARCHIVE_ROOT / stamp

    if args.environment in {"trusted", "both"}:
        reset_environment(ROOT / "inside-proof-of-concept", "inside", archive_dir)
        print("Trusted metrics and mutable service data reset.")
    if args.environment in {"conventional", "both"}:
        reset_environment(ROOT / "outside-proof-of-concept", "outside", archive_dir)
        print("Conventional metrics and mutable service data reset.")

    log = ROOT / "evaluation" / "analysis_results.log"
    archive_if_nonempty(log, archive_dir, "analysis_results.log")
    log.write_text("Run `python3 evaluation/script.py` after both campaigns have been validated.\n", encoding="utf-8")

    if archive_dir.exists():
        print(f"Previous active results archived in: {archive_dir}")
    print("Campaign preparation complete.")


if __name__ == "__main__":
    main()

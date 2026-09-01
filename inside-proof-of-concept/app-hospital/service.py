"""Hospital persistence and request orchestration."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, ContextManager

from config import ENVIRONMENT
from metrics import emit_metric, now_ms
from security import decrypt, verify_certificate


def default_hospital_data() -> dict[str, Any]:
    return {"Patients": [], "AuditLog": []}


def load_hospital_data(data_path: str | Path) -> dict[str, Any]:
    path = Path(data_path)
    if not path.exists():
        return default_hospital_data()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON file: {path}") from exc


def save_hospital_data(data: dict[str, Any], data_path: str | Path) -> None:
    path = Path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def store_local_data(
    patient: dict[str, Any], data_path: str | Path, data_lock: ContextManager[Any]
) -> None:
    patient_id = str(patient.get("patientId", "")).strip()
    if not patient_id:
        raise ValueError("patientId is required by Hospital Service.")
    with data_lock:
        db = load_hospital_data(data_path)
        patients = db.setdefault("Patients", [])
        stored = dict(patient)
        stored["recordStatus"] = "available"
        stored["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        index = next(
            (i for i, row in enumerate(patients) if str(row.get("patientId")) == patient_id),
            None,
        )
        if index is None:
            patients.append(stored)
        else:
            patients[index] = stored
        logs = db.setdefault("AuditLog", [])
        logs.append(
            {
                "id": len(logs) + 1,
                "patientId": patient_id,
                "event": "Patient record updated from Health Registry Service",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        save_hospital_data(db, data_path)


def post_action(
    payload: dict[str, Any],
    data_path: str | Path,
    metrics_file: str,
    data_lock: ContextManager[Any],
) -> tuple[dict[str, Any], int]:
    if payload.get("environment") != ENVIRONMENT:
        return {"error": f"Environment mismatch: service is {ENVIRONMENT!r}."}, 409
    total_t0 = now_ms()
    run_id = str(payload.get("runId", ""))
    program_id = str(payload.get("programId", ""))

    t0 = now_ms()
    ok, message = verify_certificate(payload.get("signedCert", ""))
    emit_metric(metrics_file, "verifyCertificate_ms", now_ms() - t0, run_id, program_id)
    if not ok:
        return {"error": message}, 403

    t0 = now_ms()
    data_json = decrypt("", payload.get("dataEnc", ""))
    emit_metric(metrics_file, "decrypt_ms", now_ms() - t0, run_id, program_id)
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        return {"error": "Invalid patient dataset."}, 400

    t0 = now_ms()
    try:
        store_local_data(data, data_path, data_lock)
    except ValueError as exc:
        return {"error": str(exc)}, 400
    emit_metric(metrics_file, "storeLocalData_ms", now_ms() - t0, run_id, program_id)
    emit_metric(metrics_file, "post_total_ms", now_ms() - total_t0, run_id, program_id)
    return {"status": "ok", "patientId": data.get("patientId")}, 200

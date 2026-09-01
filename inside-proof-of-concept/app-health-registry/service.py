"""Read registry data and orchestrate verification, retrieval, and encryption."""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Any, ContextManager

from config import ENVIRONMENT
from metrics import MetricsCollector, emit_metric
from security import encrypt, verify_certificate


def default_registry_data() -> dict[str, Any]:
    return {"Patients": [], "AuditLog": []}


def load_registry_data(data_path: str | Path, data_lock: ContextManager[Any]) -> dict[str, Any]:
    """Read the registry while holding the caller's read lock."""
    path = Path(data_path)
    with data_lock:
        if not path.exists():
            return default_registry_data()
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON file: {path}") from exc


def retrieve_local_data(
    patient_id: str, data_path: str | Path, data_lock: ContextManager[Any]
) -> str:
    """Return the requested patient as compact Unicode JSON."""
    data = load_registry_data(data_path, data_lock)
    patients = data.get("Patients", [])
    patient = next((row for row in patients if str(row.get("patientId")) == str(patient_id)), None)
    if patient is None:
        raise RuntimeError(f"Patient {patient_id!r} was not found in Health Registry Service.")
    return json.dumps(patient, ensure_ascii=False, separators=(",", ":"))


def request_action(
    payload: dict[str, Any],
    data_path: str | Path,
    metrics_file: str,
    data_lock: ContextManager[Any],
) -> tuple[dict[str, Any], int]:
    if payload.get("environment") != ENVIRONMENT:
        return {"error": f"Environment mismatch: service is {ENVIRONMENT!r}."}, 409

    collector = MetricsCollector(
        partial(emit_metric, metrics_file),
        run_id=str(payload.get("runId", "")),
        program_id=str(payload.get("programId", "")),
    )
    patient_id = str(payload.get("patientId", "")).strip()
    if not patient_id:
        collector.flush("request_total_ms")
        return {"error": "patientId is required."}, 400

    with collector.time_block("verifyCertificate_ms"):
        ok, message = verify_certificate(payload.get("signedCert", ""))
        if not ok:
            # Preserve the legacy flush boundary: this branch omits verification timing.
            collector.flush("request_total_ms")
            return {"error": message}, 403

    try:
        with collector.time_block("retrieveLocalData_ms"):
            data = retrieve_local_data(patient_id, data_path, data_lock)
    except RuntimeError as exc:
        collector.flush("request_total_ms")
        return {"error": str(exc)}, 404

    with collector.time_block("encrypt_ms"):
        data_enc = encrypt(payload.get("puK", ""), data)
    collector.flush("request_total_ms")
    return {"dataEnc": data_enc, "status": "ok"}, 200

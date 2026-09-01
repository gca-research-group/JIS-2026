"""Messaging persistence and request orchestration."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, ContextManager

from config import ENVIRONMENT
from metrics import emit_metric, now_ms
from security import decrypt, verify_certificate


def load_notifications(data_path: str | Path) -> list[dict[str, Any]]:
    path = Path(data_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON file: {path}") from exc
    return data if isinstance(data, list) else []


def save_notifications(notifications: list[dict[str, Any]], data_path: str | Path) -> None:
    path = Path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notifications, ensure_ascii=False, indent=2), encoding="utf-8")


def store_local_data(
    data: dict[str, Any], data_path: str | Path, data_lock: ContextManager[Any]
) -> None:
    with data_lock:
        notifications = load_notifications(data_path)
        item = dict(data)
        item.setdefault("id", len(notifications) + 1)
        item.setdefault("storedAt", time.strftime("%Y-%m-%d %H:%M:%S"))
        item.setdefault("status", "delivered")
        notifications.append(item)
        save_notifications(notifications, data_path)


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
        return {"error": "Invalid notification dataset."}, 400

    t0 = now_ms()
    store_local_data(data, data_path, data_lock)
    emit_metric(metrics_file, "storeLocalData_ms", now_ms() - t0, run_id, program_id)
    emit_metric(metrics_file, "post_total_ms", now_ms() - total_t0, run_id, program_id)
    return {"status": "ok"}, 200

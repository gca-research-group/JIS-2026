from __future__ import annotations
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

try:
    from flask import Flask, jsonify, request
    try:
        from flask_talisman import Talisman
    except Exception:
        Talisman = None
except Exception:  # pragma: no cover
    Flask = None
    request = None
    jsonify = None
    Talisman = None

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.metrics import append_metric, default_metrics_file
from verifyCertificate import verifyCertificate, encrypt

app = Flask(__name__) if Flask else None
if app and Talisman:
    Talisman(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
data_lock = threading.Lock()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / 'data_access' / 'health_registry.json'
METRICS_FILE = os.environ.get('METRICS_FILE', str(default_metrics_file(__file__)))
ENVIRONMENT = 'inside'
SERVICE_ID = 'health-registry-service'
PORT = int(os.environ.get('HEALTH_REGISTRY_SERVICE_PORT', '8100'))


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def metric(name: str, value_ms: float, run_id: str = '', program_id: str = '') -> None:
    append_metric(
        __file__,
        'digital_service',
        'request',
        name,
        value_ms,
        run_id=run_id,
        program_id=program_id,
        service_id=SERVICE_ID,
        metrics_file=METRICS_FILE,
    )


def _default_registry_data() -> dict:
    return {'Patients': [], 'AuditLog': []}


def load_registry_data() -> dict:
    if not DATA_PATH.exists():
        return _default_registry_data()
    try:
        return json.loads(DATA_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid JSON file: {DATA_PATH}') from exc


def retrieveLocalData(patient_id: str) -> str:
    """Return the patient record explicitly requested by the Integration Process."""
    with data_lock:
        data = load_registry_data()
    patients = data.get('Patients', [])
    patient = next((row for row in patients if str(row.get('patientId')) == str(patient_id)), None)
    if patient is None:
        raise RuntimeError(f'Patient {patient_id!r} was not found in Health Registry Service.')
    return json.dumps(patient, ensure_ascii=False, separators=(',', ':'))


def request_action(payload: dict) -> tuple[dict, int]:
    if payload.get('environment') != ENVIRONMENT:
        return {'error': f"Environment mismatch: service is {ENVIRONMENT!r}."}, 409

    total_t0 = now_ms()
    run_id = str(payload.get('runId', ''))
    program_id = str(payload.get('programId', ''))

    t0 = now_ms()
    ok, message = verifyCertificate(payload.get('signedCert', ''))
    metric('verifyCertificate_ms', now_ms() - t0, run_id, program_id)
    if not ok:
        return {'error': message}, 403

    patient_id = str(payload.get('patientId', '')).strip()
    if not patient_id:
        return {'error': 'patientId is required.'}, 400

    t0 = now_ms()
    try:
        data = retrieveLocalData(patient_id)
    except RuntimeError as exc:
        return {'error': str(exc)}, 404
    metric('retrieveLocalData_ms', now_ms() - t0, run_id, program_id)

    t0 = now_ms()
    data_enc = encrypt(payload.get('puK', ''), data)
    metric('encrypt_ms', now_ms() - t0, run_id, program_id)

    metric('request_total_ms', now_ms() - total_t0, run_id, program_id)
    return {'dataEnc': data_enc, 'status': 'ok'}, 200


if app:
    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'serviceId': SERVICE_ID, 'environment': ENVIRONMENT}), 200

    @app.route('/api/request', methods=['POST'])
    def request_dataset():
        payload = request.get_json(force=True, silent=True) or {}
        body, status = request_action(payload)
        return jsonify(body), status

    @app.route('/api/patients', methods=['GET'])
    def list_patients():
        with data_lock:
            data = load_registry_data()
        return jsonify({'patients': data.get('Patients', [])}), 200


if __name__ == '__main__':
    if not app:
        raise RuntimeError('Flask is required to run the Health Registry Service.')
    context = (str(BASE_DIR / 'keys' / 'cert.pem'), str(BASE_DIR / 'keys' / 'priv.pem'))
    app.run(host='127.0.0.1', port=PORT, ssl_context=context, debug=False, use_reloader=False)

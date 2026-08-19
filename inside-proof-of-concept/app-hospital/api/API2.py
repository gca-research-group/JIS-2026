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
except Exception:
    Flask = None
    request = None
    jsonify = None

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.metrics import append_metric, default_metrics_file
from verifyCertificate import verifyCertificate, decrypt

app = Flask(__name__) if Flask else None
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
data_lock = threading.Lock()

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / 'data_access' / 'hospital_records.json'
METRICS_FILE = os.environ.get('METRICS_FILE', str(default_metrics_file(__file__)))
ENVIRONMENT = 'inside'
SERVICE_ID = 'hospital-service'
PORT = int(os.environ.get('HOSPITAL_SERVICE_PORT', '8101'))


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def metric(name: str, value_ms: float, run_id: str = '', program_id: str = '') -> None:
    append_metric(
        __file__,
        'digital_service',
        'post',
        name,
        value_ms,
        run_id=run_id,
        program_id=program_id,
        service_id=SERVICE_ID,
        metrics_file=METRICS_FILE,
    )


def _default_hospital_data() -> dict:
    return {'Patients': [], 'AuditLog': []}


def load_hospital_data() -> dict:
    if not DATA_PATH.exists():
        return _default_hospital_data()
    try:
        return json.loads(DATA_PATH.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Invalid JSON file: {DATA_PATH}') from exc


def save_hospital_data(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def storeLocalData(patient: dict) -> None:
    """Update the hospital copy of the patient record and append an audit entry."""
    patient_id = str(patient.get('patientId', '')).strip()
    if not patient_id:
        raise ValueError('patientId is required by Hospital Service.')

    with data_lock:
        db = load_hospital_data()
        patients = db.setdefault('Patients', [])
        stored = dict(patient)
        stored['recordStatus'] = 'available'
        stored['updatedAt'] = time.strftime('%Y-%m-%d %H:%M:%S')

        idx = next((i for i, row in enumerate(patients) if str(row.get('patientId')) == patient_id), None)
        if idx is None:
            patients.append(stored)
        else:
            patients[idx] = stored

        logs = db.setdefault('AuditLog', [])
        logs.append({
            'id': len(logs) + 1,
            'patientId': patient_id,
            'event': 'Patient record updated from Health Registry Service',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        })
        save_hospital_data(db)


def post_action(payload: dict) -> tuple[dict, int]:
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

    t0 = now_ms()
    data_json = decrypt('', payload.get('dataEnc', ''))
    metric('decrypt_ms', now_ms() - t0, run_id, program_id)
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        return {'error': 'Invalid patient dataset.'}, 400

    t0 = now_ms()
    try:
        storeLocalData(data)
    except ValueError as exc:
        return {'error': str(exc)}, 400
    metric('storeLocalData_ms', now_ms() - t0, run_id, program_id)

    metric('post_total_ms', now_ms() - total_t0, run_id, program_id)
    return {'status': 'ok', 'patientId': data.get('patientId')}, 200


if app:
    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'serviceId': SERVICE_ID, 'environment': ENVIRONMENT}), 200

    @app.route('/api/post', methods=['POST'])
    def post_dataset():
        payload = request.get_json(force=True, silent=True) or {}
        body, status = post_action(payload)
        return jsonify(body), status

    @app.route('/api/patients', methods=['GET'])
    def list_patients():
        with data_lock:
            db = load_hospital_data()
        return jsonify({'patients': db.get('Patients', [])}), 200


if __name__ == '__main__':
    if not app:
        raise RuntimeError('Flask is required to run the Hospital Service.')
    context = (str(BASE_DIR / 'keys' / 'cert.pem'), str(BASE_DIR / 'keys' / 'priv.pem'))
    app.run(host='127.0.0.1', port=PORT, ssl_context=context, debug=False, use_reloader=False)

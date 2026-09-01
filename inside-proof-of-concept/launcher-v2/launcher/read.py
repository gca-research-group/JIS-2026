from __future__ import annotations

import json
import os
import ssl
import urllib.request
from functools import partial
from pathlib import Path

from .metrics import MetricsCollector, default_launcher_metrics_file, emit_metric

INSIDE_ROOT = Path(__file__).resolve().parents[2]
LEGACY_LAUNCHER_DIR = INSIDE_ROOT / "launcher"
PROGRAM_DATABASE_DIR = LEGACY_LAUNCHER_DIR / "programs-data-base"
SOURCE_FOLDER = PROGRAM_DATABASE_DIR / "sources"
CERTIFICATE_FOLDER = PROGRAM_DATABASE_DIR / "certificates"

FILE_DATABASE = Path(
    os.environ.get(
        "LAUNCHER_FILE_DATABASE",
        str(PROGRAM_DATABASE_DIR / "file_database.json"),
    )
)
SERVICE_URLS = {
    "health-registry-service": os.environ.get(
        "HEALTH_REGISTRY_SERVICE_URL", "https://127.0.0.1:8100/api/request"
    ),
    "hospital-service": os.environ.get(
        "HOSPITAL_SERVICE_URL", "https://127.0.0.1:8101/api/post"
    ),
    "messaging-service": os.environ.get(
        "MESSAGING_SERVICE_URL", "https://127.0.0.1:9100/api/post"
    ),
}

file_db: dict[int, dict] = {}


def load_file_database() -> dict[int, dict]:
    """Load the persisted launcher program metadata used by read and write."""
    global file_db
    path = FILE_DATABASE
    if not path.exists():
        file_db = {}
        return file_db

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        file_db = {}
        return file_db

    base = path.parent.parent
    loaded: dict[int, dict] = {}
    for key, value in raw.items():
        entry = dict(value)
        for field in ("file_path",):
            if field in entry:
                item = Path(entry[field])
                resolved = item if item.is_absolute() else (base / item).resolve()
                if not resolved.exists():
                    local_candidate = SOURCE_FOLDER / item.name
                    if local_candidate.exists():
                        resolved = local_candidate.resolve()
                entry[field] = str(resolved)
        for field in ("executables", "certificates"):
            if field in entry:
                repaired = []
                for item in map(Path, entry[field]):
                    resolved = item if item.is_absolute() else (base / item).resolve()
                    if not resolved.exists() and field == "certificates":
                        local_candidate = CERTIFICATE_FOLDER / item.name
                        if local_candidate.exists():
                            resolved = local_candidate.resolve()
                    repaired.append(str(resolved))
                entry[field] = repaired
        loaded[int(key)] = entry

    file_db = loaded
    return file_db


def lookup_service(srv_id: str, services_url: dict[str, str] | None = None) -> str:
    urls = SERVICE_URLS if services_url is None else services_url
    if srv_id not in urls:
        raise KeyError(f"Unknown service id: {srv_id}")
    return urls[srv_id]


def get_latest_certificate_dir(program_id: int) -> Path:
    if program_id not in file_db:
        raise FileNotFoundError("Invalid program selected")
    certificates = file_db[program_id].get("certificates", [])
    if not certificates:
        raise FileNotFoundError("No certificate directory registered for this program")
    cert_dir = Path(certificates[-1])
    if not cert_dir.exists():
        raise FileNotFoundError("Certificate directory path does not exist")
    return cert_dir


def _read_credential(program_id: int, filename: str, label: str) -> str:
    path = get_latest_certificate_dir(program_id) / filename
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    return path.read_text(encoding="utf-8")


def get_certificate(program_id: int) -> str:
    return _read_credential(program_id, "certificate.pem", "Certificate")


def get_program_public_key(program_id: int) -> str:
    return _read_credential(program_id, "public_key.pem", "Public key")


def post_json(url: str, payload: dict) -> dict:
    context = ssl._create_unverified_context()
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def read(
    srv_id: str,
    program_id: int,
    run_id: str = "",
    patient_id: str = "P001",
    metrics_file: str | None = None,
) -> dict:
    """Read patient data through a configured healthcare service."""
    destination = metrics_file or default_launcher_metrics_file()
    collector = MetricsCollector(
        partial(emit_metric, destination, "read", srv_id),
        run_id=run_id,
        program_id=str(program_id),
    )

    with collector.time_block("lookupService_ms"):
        service_url = lookup_service(srv_id)

    with collector.time_block("getCertificate_ms"):
        signed_cert = get_certificate(program_id)

    with collector.time_block("getProgramPublicKey_ms"):
        program_public_key = get_program_public_key(program_id)

    with collector.time_block("request_ms"):
        response = post_json(
            service_url,
            {
                "signedCert": signed_cert,
                "puK": program_public_key,
                "serviceId": srv_id,
                "programId": program_id,
                "runId": run_id,
                "patientId": patient_id,
                "environment": "inside",
            },
        )

    collector.flush("launcher_read_total_ms")
    return response

import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from threading import RLock

import pytest

from app import create_app
from config import BASE_DIR, default_config
from security import decrypt, encrypt, verify_certificate
from service import load_hospital_data, store_local_data

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8101
PAYLOAD = {
    "environment": "inside",
    "signedCert": "cert",
    "dataEnc": '{"patientId":"P1","name":"João"}',
    "runId": "r1",
    "programId": 2,
}


def rows(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@pytest.fixture
def service(tmp_path):
    data = tmp_path / "hospital.json"
    data.write_text('{"Patients":[],"AuditLog":[]}', encoding="utf-8")
    metrics = tmp_path / "metrics.csv"
    app = create_app({"DATA_PATH": data, "METRICS_FILE": str(metrics)})
    return app, app.test_client(), data, metrics


@pytest.mark.parametrize(
    "changes,status,error,names",
    [
        (
            {},
            200,
            None,
            ["verifyCertificate_ms", "decrypt_ms", "storeLocalData_ms", "post_total_ms"],
        ),
        ({"environment": "outside"}, 409, "Environment mismatch: service is 'inside'.", []),
        ({"signedCert": ""}, 403, "Missing simulated certificate", ["verifyCertificate_ms"]),
        ({"dataEnc": "{"}, 400, "Invalid patient dataset.", ["verifyCertificate_ms", "decrypt_ms"]),
        (
            {"dataEnc": "{}"},
            400,
            "patientId is required by Hospital Service.",
            ["verifyCertificate_ms", "decrypt_ms"],
        ),
    ],
)
def test_post_contract(service, changes, status, error, names):
    _, client, _, destination = service
    response = client.post("/api/post", json={**PAYLOAD, **changes}, base_url="https://localhost")
    assert response.status_code == status
    if error:
        assert response.json == {"error": error}
    else:
        assert response.json == {"status": "ok", "patientId": "P1"}
    emitted = rows(destination)
    assert [row["metric"] for row in emitted] == names
    for row in emitted:
        assert (row["run_id"], row["program_id"], row["operation"], row["service_id"]) == (
            "r1",
            "2",
            "post",
            "hospital-service",
        )
        assert float(row["value_ms"]) >= 0


def test_health_storage_and_upsert(service):
    app, client, data, _ = service
    assert client.get("/api/health", base_url="https://localhost").json == {
        "status": "ok",
        "serviceId": "hospital-service",
        "environment": "inside",
    }
    assert client.post("/api/post", json=PAYLOAD, base_url="https://localhost").status_code == 200
    second = {**PAYLOAD, "dataEnc": '{"patientId":"P1","name":"Second"}'}
    assert client.post("/api/post", json=second, base_url="https://localhost").status_code == 200
    stored = json.loads(data.read_text(encoding="utf-8"))
    assert len(stored["Patients"]) == 1 and stored["Patients"][0]["name"] == "Second"
    assert stored["Patients"][0]["recordStatus"] == "available"
    assert len(stored["AuditLog"]) == 2
    assert (
        client.get("/api/patients", base_url="https://localhost").json["patients"]
        == stored["Patients"]
    )
    assert (
        "Content-Security-Policy" in client.get("/api/health", base_url="https://localhost").headers
    )
    assert app.extensions["hospital_data_lock"]


def test_missing_and_invalid_storage(tmp_path):
    path = tmp_path / "missing.json"
    assert load_hospital_data(path) == {"Patients": [], "AuditLog": []}
    store_local_data({"patientId": 1}, path, RLock())
    assert json.loads(path.read_text())["Patients"][0]["patientId"] == 1
    path.write_text("{", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid JSON file"):
        load_hospital_data(path)


@pytest.mark.parametrize(
    "body,status", [("", 409), ("{", 409), ("[]", 409), ("null", 409), ("[1]", 500)]
)
def test_invalid_http_body(service, body, status):
    assert (
        service[1].post("/api/post", data=body, base_url="https://localhost").status_code == status
    )


def test_security():
    assert verify_certificate("cert") == (True, "Simulated certificate accepted")
    assert verify_certificate(" ") == (False, "Missing simulated certificate")
    assert encrypt("", "João") == decrypt("", "João") == "João"


def test_factory_isolation(tmp_path):
    apps = []
    for i in range(2):
        path = tmp_path / f"{i}.json"
        path.write_text('{"Patients":[],"AuditLog":[]}', encoding="utf-8")
        apps.append(create_app({"DATA_PATH": path, "METRICS_FILE": str(tmp_path / f"{i}.csv")}))
    for i, app in enumerate(apps):
        payload = {**PAYLOAD, "dataEnc": json.dumps({"patientId": str(i)})}
        assert (
            app.test_client().post("/api/post", json=payload, base_url="https://x").status_code
            == 200
        )
    assert apps[0].extensions["hospital_data_lock"] is not apps[1].extensions["hospital_data_lock"]


def run(code, cwd=ROOT, **values):
    environment = {
        k: v for k, v in os.environ.items() if k not in {"METRICS_FILE", "HOSPITAL_SERVICE_PORT"}
    }
    environment.update(values)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def test_config_and_startup(tmp_path, monkeypatch):
    monkeypatch.delenv("METRICS_FILE", raising=False)
    monkeypatch.delenv("HOSPITAL_SERVICE_PORT", raising=False)
    settings = default_config()
    assert (
        settings["PORT"] == 8101
        and settings["DATA_PATH"] == BASE_DIR / "data" / "hospital_records.json"
    )
    result = json.loads(
        run(
            "import json,runpy; from flask import Flask; Flask.run=lambda s,**k:print(json.dumps(k)); runpy.run_path('main.py',run_name='__main__')",
            HOSPITAL_SERVICE_PORT="8201",
        )
    )
    assert result == {
        "host": "127.0.0.1",
        "port": 8201,
        "ssl_context": [str(ROOT / "keys" / "cert.pem"), str(ROOT / "keys" / "priv.pem")],
        "debug": False,
        "use_reloader": False,
        "load_dotenv": False,
    }


def test_dotenv_precedence(tmp_path, monkeypatch):
    import config

    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.delenv("HOSPITAL_SERVICE_PORT", raising=False)
    monkeypatch.delenv("METRICS_FILE", raising=False)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    (tmp_path / ".env").write_text("HOSPITAL_SERVICE_PORT=8200\nMETRICS_FILE=file.csv\n")
    assert config.default_config()["PORT"] == 8200
    monkeypatch.setenv("HOSPITAL_SERVICE_PORT", "8300")
    assert config.default_config()["PORT"] == 8300
    assert create_app({"PORT": 8400}).config["PORT"] == 8400


def test_pure_service_without_flask():
    assert (
        run(
            "import sys; sys.modules['flask']=None; from service import post_action; from threading import RLock; print(post_action({},'x','x',RLock())[1])"
        )
        == "409"
    )


def test_absolute_script_startup(tmp_path):
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "sitecustomize.py").write_text(
        "import json\nfrom flask import Flask\n"
        "Flask.run=lambda self,**kwargs:print(json.dumps(kwargs))\n"
    )
    environment = dict(os.environ)
    environment.pop("HOSPITAL_SERVICE_PORT", None)
    environment["PYTHONPATH"] = str(bootstrap)
    result = subprocess.run(
        [sys.executable, str(ROOT / "main.py")],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["port"] == DEFAULT_PORT


@pytest.mark.parametrize("dependency", ["flask", "flask_talisman"])
def test_required_dependencies_propagate(dependency):
    code = f"""
import builtins
original = builtins.__import__
expected = ImportError('broken dependency')
def guarded(name, *args, **kwargs):
    if name == {dependency!r}:
        raise expected
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
try:
    from app import create_app
    create_app()
except ImportError as exc:
    assert exc is expected
    print('propagated')
"""
    assert run(code) == "propagated"

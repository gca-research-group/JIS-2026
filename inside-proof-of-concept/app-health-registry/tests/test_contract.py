"""HTTP and CSV contracts characterized before extracting the service."""

import csv
import json

import pytest
from health_registry.service import load_registry_data, retrieve_local_data

PATIENT = {"patientId": "P001", "name": "João"}
PAYLOAD = {
    "environment": "inside",
    "patientId": "P001",
    "signedCert": "cert",
    "puK": "key",
    "runId": "r1",
    "programId": 2,
}
SUCCESS_METRICS = ["verifyCertificate_ms", "retrieveLocalData_ms", "encrypt_ms", "request_total_ms"]


@pytest.fixture
def service(tmp_path):
    from health_registry import create_app

    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"Patients": [PATIENT], "AuditLog": []}), encoding="utf-8")
    metrics = tmp_path / "metrics.csv"
    app = create_app({"DATA_PATH": path, "METRICS_FILE": str(metrics)})
    data_lock = app.extensions["health_registry_data_lock"]
    return data_lock, app.test_client(), path, metrics


def rows(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize(
    "changes,status,error,metrics",
    [
        ({}, 200, None, SUCCESS_METRICS),
        ({"environment": "outside"}, 409, "Environment mismatch: service is 'inside'.", []),
        ({"patientId": " "}, 400, "patientId is required.", ["request_total_ms"]),
        ({"signedCert": " "}, 403, "Missing simulated certificate", ["request_total_ms"]),
        (
            {"patientId": "missing"},
            404,
            "Patient 'missing' was not found in Health Registry Service.",
            ["verifyCertificate_ms", "retrieveLocalData_ms", "request_total_ms"],
        ),
    ],
)
def test_request_contract(service, changes, status, error, metrics):
    _, client, _, destination = service
    response = client.post(
        "/api/request", json={**PAYLOAD, **changes}, base_url="https://localhost"
    )
    assert response.status_code == status
    if error:
        assert response.json == {"error": error}
    else:
        assert response.json == {"status": "ok", "dataEnc": '{"patientId":"P001","name":"João"}'}
    emitted = rows(destination)
    assert [row["metric"] for row in emitted] == metrics
    for row in emitted:
        assert list(row) == [
            "ts",
            "run_id",
            "component",
            "operation",
            "metric",
            "value_ms",
            "program_id",
            "service_id",
        ]
        assert (
            row["run_id"],
            row["program_id"],
            row["component"],
            row["operation"],
            row["service_id"],
        ) == ("r1", "2", "digital_service", "request", "health-registry-service")
        assert float(row["value_ms"]) >= 0


def test_reads(service):
    data_lock, client, path, _ = service
    assert client.get("/api/health", base_url="https://localhost").json == {
        "status": "ok",
        "serviceId": "health-registry-service",
        "environment": "inside",
    }
    assert client.get("/api/patients", base_url="https://localhost").json == {"patients": [PATIENT]}
    path.unlink()
    assert load_registry_data(path, data_lock) == {"Patients": [], "AuditLog": []}
    assert client.get("/api/patients", base_url="https://localhost").json == {"patients": []}
    assert (
        client.post("/api/request", json=PAYLOAD, base_url="https://localhost").status_code == 404
    )


def test_invalid_storage(service):
    data_lock, client, path, _ = service
    path.write_text("{", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Invalid JSON file"):
        load_registry_data(path, data_lock)
    response = client.post("/api/request", json=PAYLOAD, base_url="https://localhost")
    assert response.status_code == 404
    assert response.json == {"error": f"Invalid JSON file: {path}"}
    assert client.get("/api/patients", base_url="https://localhost").status_code == 500


@pytest.mark.parametrize(
    "body,status",
    [("", 409), ("{", 409), ("[]", 409), ("null", 409), ("[1]", 500), ('"text"', 500)],
)
def test_invalid_body(service, body, status):
    _, client, _, metrics = service
    assert (
        client.post("/api/request", data=body, base_url="https://localhost").status_code == status
    )
    assert rows(metrics) == []


@pytest.mark.parametrize(
    "cert,ok", [("cert", True), ("", False), ("  ", False), (None, False), (123, False)]
)
def test_security(cert, ok):
    from health_registry.security import decrypt, encrypt, verify_certificate

    assert verify_certificate(cert) == (
        ok,
        "Simulated certificate accepted" if ok else "Missing simulated certificate",
    )
    assert encrypt("unused", "João") == "João"
    assert decrypt("unused", "João") == "João"
    assert encrypt("unused", None) == ""


def test_numeric_patient_id(service):
    data_lock, _, path, _ = service
    path.write_text('{"Patients":[{"patientId":123}]}', encoding="utf-8")
    assert retrieve_local_data("123", path, data_lock) == '{"patientId":123}'

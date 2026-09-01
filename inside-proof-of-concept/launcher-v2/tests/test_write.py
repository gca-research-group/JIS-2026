import csv
import importlib
import json

import pytest

from app import create_app

write_module = importlib.import_module("launcher.write")
read_module = importlib.import_module("launcher.read")
metrics_module = importlib.import_module("launcher.metrics")
app_module = importlib.import_module("app")


@pytest.fixture
def credentials(tmp_path, monkeypatch):
    cert = tmp_path / "latest"
    cert.mkdir()
    (cert / "certificate.pem").write_text("certificate", encoding="utf-8")
    monkeypatch.setattr(read_module, "file_db", {7: {"certificates": ["old", str(cert)]}})
    return cert


def test_write_payload_and_timing(credentials, monkeypatch):
    posted, metrics = [], []
    ticks = iter([0, 1, 3, 4, 7, 8, 12, 20])
    monkeypatch.setattr(metrics_module, "now_ms", lambda: next(ticks))
    monkeypatch.setattr(write_module, "post_json", lambda url, payload: posted.append((url, payload)) or {"ok": True})
    monkeypatch.setattr(write_module, "emit_metric", lambda *args: metrics.append(args))
    assert write_module.write("hospital-service", 7, "encrypted", "run", "test.csv") == {"ok": True}
    assert posted == [(read_module.SERVICE_URLS["hospital-service"], {
        "signedCert": "certificate", "dataEnc": "encrypted", "serviceId": "hospital-service",
        "programId": 7, "runId": "run", "environment": "inside",
    })]
    assert [(m[3], m[4]) for m in metrics] == [
        ("lookupService_ms", 2), ("getCertificate_ms", 3), ("post_ms", 4), ("launcher_write_total_ms", 20),
    ]
    assert all(m[:3] == ("test.csv", "write", "hospital-service") and m[5:] == ("run", "7") for m in metrics)


@pytest.mark.parametrize("dependency", ["lookup_service", "get_certificate", "post_json"])
def test_failed_write_does_not_flush(credentials, monkeypatch, dependency):
    metrics = []
    def fail(*args):
        raise RuntimeError("failed")
    monkeypatch.setattr(write_module, dependency, fail)
    monkeypatch.setattr(write_module, "emit_metric", lambda *args: metrics.append(args))
    with pytest.raises(RuntimeError, match="failed"):
        write_module.write("hospital-service", 7, "data")
    assert metrics == []


def test_reload_is_shared(tmp_path, monkeypatch):
    database = tmp_path / "db.json"
    monkeypatch.setattr(read_module, "FILE_DATABASE", database)
    for value in ["first", "second"]:
        cert = tmp_path / value
        cert.mkdir()
        (cert / "certificate.pem").write_text(value, encoding="utf-8")
        database.write_text(json.dumps({"7": {"certificates": [str(cert)]}}))
        read_module.load_file_database()
        assert read_module.get_certificate(7) == value
        assert write_module.get_certificate(7) == value


def test_write_destination_resolved_at_call_time(credentials, tmp_path, monkeypatch):
    destinations = []
    monkeypatch.setattr(write_module, "post_json", lambda *args: {})
    monkeypatch.setattr(write_module, "emit_metric", lambda *args: destinations.append(args[0]))
    for name in ["first.csv", "second.csv"]:
        monkeypatch.setenv("METRICS_FILE", str(tmp_path / name))
        write_module.write("hospital-service", 7, "data")
    assert destinations == [str(tmp_path / "first.csv")] * 4 + [str(tmp_path / "second.csv")] * 4


@pytest.mark.parametrize("body", [None, "", "not-json", "null", "false", "0", "[]", '""', '{}'])
def test_write_http_defaults(monkeypatch, body):
    calls = []
    monkeypatch.setattr(app_module, "write", lambda *args, **kwargs: calls.append(args) or {})
    response = create_app().test_client().post("/api/write/hospital-service/7", data=body, content_type="application/json")
    assert response.status_code == 200
    assert calls == [("hospital-service", 7, "", "")]


@pytest.mark.parametrize("value", [" encrypted ", None, "", 42])
def test_write_http_preserves_fields(monkeypatch, value):
    calls = []
    monkeypatch.setattr(app_module, "write", lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True})
    response = create_app({"METRICS_FILE": "custom.csv"}).test_client().post(
        "/api/write/hospital-service/7", json={"dataEnc": value, "runId": value})
    assert response.status_code == 200
    assert response.json == {"ok": True}
    assert calls == [(("hospital-service", 7, value, value), {"metrics_file": "custom.csv"})]


@pytest.mark.parametrize("body", [[1], "text", True, 1])
def test_write_http_rejects_truthy_non_objects(monkeypatch, body):
    calls = []
    monkeypatch.setattr(app_module, "write", lambda *args, **kwargs: calls.append(args))
    response = create_app().test_client().post("/api/write/hospital-service/7", json=body)
    assert response.status_code == 500
    assert "get" in response.json["error"]
    assert calls == []


@pytest.mark.parametrize("case", ["unknown", "program", "empty", "directory", "file", "transport"])
def test_write_http_execution_errors(tmp_path, monkeypatch, case):
    app = create_app()
    cert = tmp_path / "cert"
    cert.mkdir()
    metadata = {7: {"certificates": [str(cert)]}}
    if case == "program":
        metadata = {}
    elif case == "empty":
        metadata[7]["certificates"] = []
    elif case == "directory":
        metadata[7]["certificates"] = [str(tmp_path / "absent")]
    monkeypatch.setattr(read_module, "file_db", metadata)
    posted = []
    def post(*args):
        posted.append(args)
        raise RuntimeError("downstream failed")
    monkeypatch.setattr(write_module, "post_json", post)
    if case == "transport":
        (cert / "certificate.pem").write_text("certificate")
    service = "unknown" if case == "unknown" else "hospital-service"
    response = app.test_client().post(f"/api/write/{service}/7", json={})
    assert response.status_code == 500
    assert response.json["error"]
    assert len(posted) == (1 if case == "transport" else 0)


def test_write_apps_isolate_metrics(tmp_path, monkeypatch):
    apps = [create_app({"METRICS_FILE": str(tmp_path / f"{i}.csv")}) for i in [1, 2]]
    monkeypatch.setattr(write_module, "get_certificate", lambda _: "certificate")
    monkeypatch.setattr(write_module, "post_json", lambda *args: {"ok": True})
    for i, app in enumerate(apps, 1):
        response = app.test_client().post(f"/api/write/hospital-service/{i}", json={"runId": f"run-{i}"})
        assert response.status_code == 200
        with (tmp_path / f"{i}.csv").open() as source:
            rows = list(csv.DictReader(source))
        assert len(rows) == 4
        assert all(r["component"] == "launcher" and r["operation"] == "write" and r["program_id"] == str(i) and r["run_id"] == f"run-{i}" for r in rows)

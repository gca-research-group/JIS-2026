from __future__ import annotations

import json
import importlib
from pathlib import Path

import pytest

read_module = importlib.import_module("launcher.read")
metrics_module = importlib.import_module("launcher.metrics")


def test_launcher_package_contains_no_flask_or_class_declarations():
    package_dir = Path(read_module.__file__).parent
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in package_dir.glob("*.py")
    )
    assert "from flask" not in source
    assert "import flask" not in source
    assert "class Launcher" not in source
    assert "class Service" not in source


def test_load_file_database_exposes_fixture_metadata(tmp_path):
    cert_dir = tmp_path / "certificates" / "program"
    cert_dir.mkdir(parents=True)
    database = tmp_path / "programs-data-base" / "file_database.json"
    database.parent.mkdir()
    database.write_text(
        json.dumps({"7": {"certificates": [str(cert_dir)]}}), encoding="utf-8"
    )

    loaded = read_module.load_file_database(database)

    assert loaded[7]["certificates"] == [str(cert_dir)]


def test_load_file_database_repairs_stale_certificate_path(tmp_path, monkeypatch):
    cert_root = tmp_path / "certificates"
    local_cert = cert_root / "program"
    local_cert.mkdir(parents=True)
    database = tmp_path / "programs-data-base" / "file_database.json"
    database.parent.mkdir()
    database.write_text(
        json.dumps({"7": {"certificates": ["/stale/path/program"]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(read_module, "CERTIFICATE_FOLDER", cert_root)

    loaded = read_module.load_file_database(database)

    assert loaded[7]["certificates"] == [str(local_cert.resolve())]


def test_credentials_are_loaded_from_latest_certificate_directory(tmp_path):
    cert_dir = tmp_path / "certificates"
    cert_dir.mkdir()
    (cert_dir / "certificate.pem").write_text("certificate", encoding="utf-8")
    (cert_dir / "public_key.pem").write_text("public-key", encoding="utf-8")
    read_module.file_db = {2: {"certificates": [str(cert_dir)]}}

    assert read_module.get_certificate(2) == "certificate"
    assert read_module.get_program_public_key(2) == "public-key"


@pytest.mark.parametrize(
    ("database", "message"),
    [
        ({}, "Invalid program selected"),
        ({2: {"certificates": []}}, "No certificate directory registered"),
    ],
)
def test_certificate_metadata_failures(database, message):
    read_module.file_db = database
    with pytest.raises(FileNotFoundError, match=message):
        read_module.get_certificate(2)


def test_lookup_service_rejects_unknown_service():
    with pytest.raises(KeyError, match="Unknown service id"):
        read_module.lookup_service("missing", {})


def test_read_preserves_payload_response_and_metrics(monkeypatch):
    posted = []
    metrics = []
    ticks = iter([0.0, 1.0, 2.0, 3.0, 5.0, 6.0, 9.0, 10.0, 14.0, 20.0])
    monkeypatch.setattr(metrics_module, "now_ms", lambda: next(ticks))
    monkeypatch.setattr(
        read_module, "lookup_service", lambda _service: "https://service/api/request"
    )
    monkeypatch.setattr(read_module, "get_certificate", lambda _program: "certificate")
    monkeypatch.setattr(
        read_module, "get_program_public_key", lambda _program: "public-key"
    )
    monkeypatch.setattr(
        read_module,
        "post_json",
        lambda url, payload: posted.append((url, payload)) or {"dataEnc": "patient"},
    )
    monkeypatch.setattr(read_module, "emit_metric", lambda *args: metrics.append(args))

    response = read_module.read(
        "health-registry-service",
        9,
        "run-1",
        "P009",
        metrics_file="metrics.csv",
    )

    assert response == {"dataEnc": "patient"}
    assert posted == [
        (
            "https://service/api/request",
            {
                "signedCert": "certificate",
                "puK": "public-key",
                "serviceId": "health-registry-service",
                "programId": 9,
                "runId": "run-1",
                "patientId": "P009",
                "environment": "inside",
            },
        )
    ]
    assert [metric[3] for metric in metrics] == [
        "lookupService_ms",
        "getCertificate_ms",
        "getProgramPublicKey_ms",
        "request_ms",
        "launcher_read_total_ms",
    ]
    assert [metric[4] for metric in metrics] == [1.0, 2.0, 3.0, 4.0, 20.0]
    assert all(
        metric[:3] == ("metrics.csv", "read", "health-registry-service")
        for metric in metrics
    )
    assert all(metric[5:] == ("run-1", "9") for metric in metrics)


def test_read_propagates_dependency_failure_without_any_metrics(monkeypatch):
    metrics = []
    monkeypatch.setattr(
        read_module, "lookup_service", lambda _service: "https://service/api/request"
    )
    monkeypatch.setattr(read_module, "get_certificate", lambda _program: "certificate")
    monkeypatch.setattr(
        read_module, "get_program_public_key", lambda _program: "public-key"
    )
    monkeypatch.setattr(
        read_module,
        "post_json",
        lambda _url, _payload: (_ for _ in ()).throw(
            RuntimeError("downstream unavailable")
        ),
    )
    monkeypatch.setattr(read_module, "emit_metric", lambda *args: metrics.append(args))

    with pytest.raises(RuntimeError, match="downstream unavailable"):
        read_module.read(
            "health-registry-service",
            2,
            metrics_file="metrics.csv",
        )

    assert metrics == []

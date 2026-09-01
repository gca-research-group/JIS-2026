from __future__ import annotations

import csv
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from app import create_app

app_module = importlib.import_module("app")
read_module = importlib.import_module("launcher.read")


def test_api_read_forwards_explicit_values(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module,
        "read",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"dataEnc": "patient"},
    )
    app = create_app(
        database_path=tmp_path / "missing.json",
        config={"METRICS_FILE": "configured.csv"},
    )

    response = app.test_client().post(
        "/api/read/health-registry-service/7",
        json={"runId": "run-7", "patientId": " P007 "},
    )

    assert response.status_code == 200
    assert response.json == {"dataEnc": "patient"}
    assert calls == [
        (
            ("health-registry-service", 7, "run-7", "P007"),
            {"metrics_file": "configured.csv"},
        )
    ]


@pytest.mark.parametrize(
    ("request_kwargs", "expected_patient"),
    [
        ({}, "P001"),
        ({"json": {}}, "P001"),
        ({"json": {"patientId": "   "}}, "P001"),
        ({"data": "not-json", "content_type": "application/json"}, "P001"),
        ({"json": ["not", "an", "object"]}, "P001"),
    ],
)
def test_api_read_defaults_missing_or_unusable_payload(
    tmp_path, monkeypatch, request_kwargs, expected_patient
):
    calls = []
    monkeypatch.setattr(
        app_module,
        "read",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {},
    )
    app = create_app(database_path=tmp_path / "missing.json")

    response = app.test_client().post(
        "/api/read/health-registry-service/2", **request_kwargs
    )

    assert response.status_code == 200
    assert calls[0][0] == ("health-registry-service", 2, "", expected_patient)


def test_api_read_translates_exception_to_json_500(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("read failed")

    monkeypatch.setattr(app_module, "read", fail)
    app = create_app(database_path=tmp_path / "missing.json")
    response = app.test_client().post("/api/read/health-registry-service/2", json={})

    assert response.status_code == 500
    assert response.json == {"error": "read failed"}


def test_launcher_v2_is_sole_owner_after_legacy_removal(tmp_path):
    app = create_app(database_path=tmp_path / "missing.json")
    routes = {
        (rule.rule, tuple(sorted(rule.methods - {"HEAD", "OPTIONS"})))
        for rule in app.url_map.iter_rules()
    }
    assert ("/api/read/<srv_id>/<int:program_id>", ("POST",)) in routes


def test_create_app_loads_fixture_database(tmp_path):
    database = tmp_path / "file_database.json"
    database.write_text(json.dumps({"4": {"certificates": []}}), encoding="utf-8")

    create_app(database_path=database)

    assert 4 in read_module.file_db


def test_main_bind_configuration_uses_environment(monkeypatch):
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("launcher_v2_main", main_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    monkeypatch.setenv("LAUNCHER_V2_HOST", "0.0.0.0")
    monkeypatch.setenv("LAUNCHER_V2_PORT", "5501")
    monkeypatch.setenv("LAUNCHER_V2_TLS_CERT", "certificate.pem")
    monkeypatch.setenv("LAUNCHER_V2_TLS_KEY", "private-key.pem")

    assert module.bind_configuration() == (
        "0.0.0.0",
        5501,
        ("certificate.pem", "private-key.pem"),
    )


def test_read_smoke_success_metrics_and_http_500(tmp_path, monkeypatch):
    posted = []
    metrics = []
    monkeypatch.setattr(
        read_module, "lookup_service", lambda _service: "https://registry/api/request"
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
    app = create_app(database_path=tmp_path / "missing.json")

    success = app.test_client().post(
        "/api/read/health-registry-service/2",
        json={"runId": "smoke-run", "patientId": "P002"},
    )

    assert success.status_code == 200
    assert success.json == {"dataEnc": "patient"}
    assert posted[0][0] == "https://registry/api/request"
    assert posted[0][1]["patientId"] == "P002"
    assert [entry[3] for entry in metrics][-2:] == [
        "request_ms",
        "launcher_read_total_ms",
    ]

    monkeypatch.setattr(
        read_module,
        "post_json",
        lambda _url, _payload: (_ for _ in ()).throw(
            RuntimeError("smoke downstream failure")
        ),
    )
    failing_app = create_app(database_path=tmp_path / "missing.json")
    failure = failing_app.test_client().post(
        "/api/read/health-registry-service/2", json={}
    )

    assert failure.status_code == 500
    assert failure.json == {"error": "smoke downstream failure"}


def test_application_factories_isolate_metrics_destinations(tmp_path, monkeypatch):
    first_metrics = tmp_path / "first.csv"
    second_metrics = tmp_path / "second.csv"
    monkeypatch.setattr(
        read_module, "lookup_service", lambda _service: "https://registry/api/request"
    )
    monkeypatch.setattr(read_module, "get_certificate", lambda _program: "certificate")
    monkeypatch.setattr(
        read_module, "get_program_public_key", lambda _program: "public-key"
    )
    monkeypatch.setattr(
        read_module, "post_json", lambda _url, _payload: {"dataEnc": "patient"}
    )
    first = create_app(
        database_path=tmp_path / "missing.json",
        config={"METRICS_FILE": str(first_metrics)},
    )
    second = create_app(
        database_path=tmp_path / "missing.json",
        config={"METRICS_FILE": str(second_metrics)},
    )

    assert (
        first.test_client()
        .post("/api/read/health-registry-service/1", json={})
        .status_code
        == 200
    )
    assert (
        second.test_client()
        .post("/api/read/health-registry-service/2", json={})
        .status_code
        == 200
    )

    with first_metrics.open(newline="", encoding="utf-8") as source:
        first_rows = list(csv.DictReader(source))
    with second_metrics.open(newline="", encoding="utf-8") as source:
        second_rows = list(csv.DictReader(source))
    assert {row["program_id"] for row in first_rows} == {"1"}
    assert {row["program_id"] for row in second_rows} == {"2"}

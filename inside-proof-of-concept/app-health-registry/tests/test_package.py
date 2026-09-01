"""Factory isolation and package entry-point regression checks."""

import json
from pathlib import Path
from threading import RLock

from test_startup import SERVICE_ROOT, run

from app import create_app
from config import BASE_DIR, default_config
from service import request_action


def test_factory_isolation(tmp_path):
    apps = []
    for index in range(2):
        path = tmp_path / f"registry{index}.json"
        path.write_text(json.dumps({"Patients": [{"patientId": str(index)}]}), encoding="utf-8")
        apps.append(create_app({"DATA_PATH": path, "METRICS_FILE": str(tmp_path / f"{index}.csv")}))
    for index, app in enumerate(apps):
        response = app.test_client().post(
            "/api/request",
            base_url="https://localhost",
            json={"environment": "inside", "patientId": str(index), "signedCert": "cert"},
        )
        assert response.status_code == 200
        assert json.loads(response.json["dataEnc"]) == {"patientId": str(index)}
        assert len((tmp_path / f"{index}.csv").read_text().splitlines()) == 5
    from routes import routes

    for index in (0, 1, 0, 1):
        app = apps[index]
        assert app.blueprints["health_registry"] is routes
        assert app.test_client().get("/api/patients", base_url="https://localhost").json == {
            "patients": [{"patientId": str(index)}]
        }
        assert {
            rule.endpoint: rule.rule
            for rule in app.url_map.iter_rules()
            if rule.endpoint.startswith("health_registry.")
        } == {
            "health_registry.health": "/api/health",
            "health_registry.request_dataset": "/api/request",
            "health_registry.list_patients": "/api/patients",
        }
    assert (
        apps[0].extensions["health_registry_data_lock"]
        is not apps[1].extensions["health_registry_data_lock"]
    )


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("METRICS_FILE", raising=False)
    monkeypatch.delenv("HEALTH_REGISTRY_SERVICE_PORT", raising=False)
    settings = default_config()
    assert settings["PORT"] == 8100
    assert settings["DATA_PATH"] == BASE_DIR / "data" / "health_registry.json"
    assert Path(settings["METRICS_FILE"]) == BASE_DIR.parent / "metrics" / "all_metrics.csv"


def test_module_startup():
    settings = json.loads(
        run(
            """
import json, runpy
from flask import Flask
Flask.run = lambda self, **kwargs: print(json.dumps(kwargs))
runpy.run_path('main.py', run_name='__main__')
""",
            HEALTH_REGISTRY_SERVICE_PORT="8300",
        )
    )
    assert settings == {
        "host": "127.0.0.1",
        "port": 8300,
        "ssl_context": [
            str(SERVICE_ROOT / "keys" / "cert.pem"),
            str(SERVICE_ROOT / "keys" / "priv.pem"),
        ],
        "debug": False,
        "use_reloader": False,
        "load_dotenv": False,
    }


def test_imports_and_shared_resolution():
    assert run("""
import logging, sys
logging.basicConfig = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('logging configured'))
from flask import Flask
Flask.run = lambda *a, **kw: (_ for _ in ()).throw(AssertionError('server started'))
import app, main
from _shared import verify_certificate
print(sys.modules[verify_certificate.__module__].__file__)
""") == str(BASE_DIR.parent / "common" / "security.py")


def test_pure_service_without_flask():
    assert (
        run("""
import sys
sys.modules['flask'] = None
from threading import RLock
from service import request_action
print(request_action({}, 'unused', 'unused', RLock())[1])
""")
        == "409"
    )


def test_request_collectors_are_independent(tmp_path):
    from test_contract import rows

    data_path = tmp_path / "absent.json"
    data_lock = RLock()
    for run_id in ("first", "second"):
        assert (
            request_action(
                {"environment": "inside", "patientId": "p", "signedCert": "c", "runId": run_id},
                data_path,
                str(tmp_path / "m.csv"),
                data_lock,
            )[1]
            == 404
        )
    emitted = rows(tmp_path / "m.csv")
    assert [row["run_id"] for row in emitted] == ["first"] * 3 + ["second"] * 3


def test_talisman_headers():
    client = create_app().test_client()
    assert client.get("/api/health").status_code == 302
    assert (
        "Content-Security-Policy" in client.get("/api/health", base_url="https://localhost").headers
    )

"""Configuration precedence and explicit dotenv discovery boundaries."""

import json
import os

import pytest
from health_registry import config, create_app
from test_startup import API, run


@pytest.fixture
def local_env(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    for name in ("METRICS_FILE", "HEALTH_REGISTRY_SERVICE_PORT"):
        # Register restoration even if dotenv later creates an initially absent key.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    return tmp_path / ".env"


def test_absent_file(local_env):
    settings = config.default_config()
    assert settings["PORT"] == 8100
    assert settings["METRICS_FILE"] == str(API.parent.parent / "metrics" / "all_metrics.csv")


def test_file_values(local_env):
    local_env.write_text("HEALTH_REGISTRY_SERVICE_PORT=8200\nMETRICS_FILE=relative.csv\n")
    settings = config.default_config()
    assert settings["PORT"] == 8200
    assert settings["METRICS_FILE"] == "relative.csv"
    assert os.environ["HEALTH_REGISTRY_SERVICE_PORT"] == "8200"


def test_precedence(local_env, monkeypatch):
    local_env.write_text("HEALTH_REGISTRY_SERVICE_PORT=8200\nMETRICS_FILE=file.csv\n")
    monkeypatch.setenv("HEALTH_REGISTRY_SERVICE_PORT", "8300")
    monkeypatch.setenv("METRICS_FILE", "environment.csv")
    settings = config.default_config()
    assert (settings["PORT"], settings["METRICS_FILE"]) == (8300, "environment.csv")
    app = create_app({"PORT": 8400, "METRICS_FILE": "explicit.csv"})
    assert (app.config["PORT"], app.config["METRICS_FILE"]) == (8400, "explicit.csv")


@pytest.mark.parametrize("source", ["file", "environment"])
def test_invalid_port(local_env, monkeypatch, source):
    if source == "file":
        local_env.write_text("HEALTH_REGISTRY_SERVICE_PORT=invalid\n")
    else:
        monkeypatch.setenv("HEALTH_REGISTRY_SERVICE_PORT", "invalid")
    with pytest.raises(ValueError):
        config.default_config()


@pytest.mark.parametrize("entry", ["factory", "module"])
@pytest.mark.parametrize("has_file", [False, True])
def test_entry_points_ignore_unrelated_files(tmp_path, entry, has_file):
    service_root = tmp_path / "service"
    service_root.mkdir()
    working = tmp_path / "working"
    working.mkdir()
    for directory in (tmp_path, working):
        (directory / ".env").write_text("HEALTH_REGISTRY_SERVICE_PORT=9999\nUNRELATED_DOTENV=yes\n")
    if has_file:
        (service_root / ".env").write_text(
            "HEALTH_REGISTRY_SERVICE_PORT=8500\nMETRICS_FILE=local.csv\n"
        )
    code = f"""
import json, os, runpy, sys
from pathlib import Path
sys.path.insert(0, {str(API)!r})
os.environ.pop('UNRELATED_DOTENV', None)
from health_registry import config
config.BASE_DIR = Path({str(service_root)!r})
def report(app):
    print(json.dumps([app.config['PORT'], app.config['METRICS_FILE'],
                      os.environ.get('UNRELATED_DOTENV')]))
import werkzeug.serving
werkzeug.serving.run_simple = lambda host, port, app, **kwargs: report(app)
if {entry!r} == 'factory':
    from health_registry import create_app
    report(create_app())
else:
    runpy.run_module('health_registry', run_name='__main__')
"""
    output = run(code, cwd=working, PYTHON_DOTENV_DISABLED="0", FLASK_RUN_FROM_CLI="false")
    # Flask may print a startup banner before the intercepted server invocation.
    settings = json.loads(output.splitlines()[-1])
    assert settings == [
        8500 if has_file else 8100,
        "local.csv" if has_file else str(API.parent.parent / "metrics" / "all_metrics.csv"),
        None,
    ]


def test_import_does_not_load_dotenv():
    assert (
        run(
            """
import dotenv
def unexpected_load(*args, **kwargs):
    raise AssertionError('dotenv loaded at import time')
dotenv.load_dotenv = unexpected_load
import health_registry.config, health_registry.service, health_registry.app
print('imports only')
""",
            PYTHON_DOTENV_DISABLED="0",
        )
        == "imports only"
    )

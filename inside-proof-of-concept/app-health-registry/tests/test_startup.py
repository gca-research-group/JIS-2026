"""Check launch behavior in fresh interpreters without binding a socket."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1] / "api"


def run(code, cwd=API, **overrides):
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"METRICS_FILE", "HEALTH_REGISTRY_SERVICE_PORT"}
    }
    environment.update(overrides)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize("port", [None, "8200"])
def test_module_startup_settings(port, tmp_path):
    code = f"""
import json, runpy, sys
from flask import Flask
sys.path.insert(0, {str(API)!r})
Flask.run = lambda self, **kwargs: print(json.dumps(kwargs))
runpy.run_module('health_registry', run_name='__main__')
"""
    settings = json.loads(
        run(code, cwd=tmp_path, **({"HEALTH_REGISTRY_SERVICE_PORT": port} if port else {}))
    )
    assert settings == {
        "host": "127.0.0.1",
        "port": int(port or 8100),
        "ssl_context": [
            str(API.parent / "keys" / "cert.pem"),
            str(API.parent / "keys" / "priv.pem"),
        ],
        "debug": False,
        "use_reloader": False,
        "load_dotenv": False,
    }


@pytest.mark.parametrize("dependency", ["flask", "flask_talisman"])
@pytest.mark.parametrize("failure", ["missing", "broken"])
@pytest.mark.parametrize(
    "entry",
    [
        "from health_registry import create_app; create_app()",
        "runpy.run_module('health_registry', run_name='__main__')",
    ],
)
def test_required_dependency(dependency, failure, entry):
    code = f"""
import builtins, runpy
original_import = builtins.__import__
expected = (ModuleNotFoundError({dependency!r}) if {failure!r} == 'missing'
            else ImportError('broken dependency'))
def guarded_import(name, *args, **kwargs):
    if name == {dependency!r}:
        raise expected
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
if {dependency!r} != 'flask':
    from flask import Flask
    def unexpected_start(*args, **kwargs):
        raise AssertionError('Server started despite broken dependency')
    Flask.run = unexpected_start
try:
    {entry}
except ImportError as exc:
    assert exc is expected
    print('original error propagated')
else:
    raise AssertionError('Dependency failure was swallowed')
"""
    assert run(code) == "original error propagated"


def test_metrics_override(tmp_path):
    destination = str(tmp_path / "override.csv")
    assert (
        run(
            "from health_registry import create_app; print(create_app().config['METRICS_FILE'])",
            METRICS_FILE=destination,
        )
        == destination
    )

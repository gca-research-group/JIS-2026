"""Check launch behavior in fresh interpreters without binding a socket."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("absolute", [False, True])
def test_script_invocation_without_import_path_setup(tmp_path, absolute):
    """Let Python resolve the script's imports, intercepting only the server call."""
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "sitecustomize.py").write_text(
        "import json\nfrom flask import Flask\n"
        "Flask.run = lambda self, **kwargs: print(json.dumps(kwargs))\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment.pop("HEALTH_REGISTRY_SERVICE_PORT", None)
    environment["PYTHONPATH"] = str(bootstrap)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    script = str(SERVICE_ROOT / "main.py") if absolute else "main.py"
    result = subprocess.run(
        [sys.executable, script],
        cwd=tmp_path if absolute else SERVICE_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    settings = json.loads(result.stdout)
    assert settings["port"] == 8100
    assert settings["ssl_context"] == [
        str(SERVICE_ROOT / "keys" / "cert.pem"),
        str(SERVICE_ROOT / "keys" / "priv.pem"),
    ]
    assert settings["load_dotenv"] is False


def run(code, cwd=SERVICE_ROOT, **overrides):
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
sys.path.insert(0, {str(SERVICE_ROOT)!r})
Flask.run = lambda self, **kwargs: print(json.dumps(kwargs))
runpy.run_path({str(SERVICE_ROOT / "main.py")!r}, run_name='__main__')
"""
    settings = json.loads(
        run(code, cwd=tmp_path, **({"HEALTH_REGISTRY_SERVICE_PORT": port} if port else {}))
    )
    assert settings == {
        "host": "127.0.0.1",
        "port": int(port or 8100),
        "ssl_context": [
            str(SERVICE_ROOT / "keys" / "cert.pem"),
            str(SERVICE_ROOT / "keys" / "priv.pem"),
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
        "from app import create_app; create_app()",
        "runpy.run_path('main.py', run_name='__main__')",
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
            "from app import create_app; print(create_app().config['METRICS_FILE'])",
            METRICS_FILE=destination,
        )
        == destination
    )

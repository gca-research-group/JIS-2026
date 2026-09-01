from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


INSIDE_ROOT = Path(__file__).resolve().parents[2]
LEGACY_LAUNCHER = INSIDE_ROOT / "launcher" / "launcher.py"
INTEGRATION_PROCESS = (
    INSIDE_ROOT
    / "launcher"
    / "programs-data-base"
    / "sources"
    / "integration_process.c"
)


def load_legacy_launcher():
    spec = importlib.util.spec_from_file_location("legacy_launcher", LEGACY_LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_legacy_launcher_has_no_data_routes_or_methods():
    legacy = load_legacy_launcher()
    routes = {rule.rule for rule in legacy.app.url_map.iter_rules()}

    assert "/api/read/<srv_id>/<int:program_id>" not in routes
    assert "/api/write/<srv_id>/<int:program_id>" not in routes
    assert not hasattr(legacy.Launcher, "read")
    assert not hasattr(legacy.Launcher, "write")
    assert {"/upload", "/files", "/files/<int:program_id>", "/compile/<int:program_id>", "/execute/<int:program_id>"} <= routes


def test_integration_process_shares_read_and_write_routing():
    source = INTEGRATION_PROCESS.read_text(encoding="utf-8")

    assert 'getenv("LAUNCHER_HOST")' in source
    assert 'getenv("LAUNCHER_PORT")' in source
    assert 'return (host && *host) ? host : "127.0.0.1";' in source
    assert 'return (port && *port) ? port : "5001";' in source
    assert source.count("http_post_json(launcher_host(), launcher_port(), endpoint, payload)") == 2
    assert "LAUNCHER_READ_" not in source
    assert "LAUNCHER_WRITE_" not in source


@pytest.mark.parametrize("host,port", [(None, None), ("", ""), ("gateway", "5555")])
def test_start_passes_shared_callback_environment(tmp_path, monkeypatch, host, port):
    legacy = load_legacy_launcher()
    launcher = legacy.Launcher()
    source, executable = tmp_path / "program.c", tmp_path / "program"
    source.write_text("source")
    executable.write_text("executable")
    os.utime(source, (1, 1))
    os.utime(executable, (2, 2))
    monkeypatch.setattr(legacy, "file_db", {7: {"file_path": str(source), "executables": [str(executable)]}})
    for method in ["retrieveProgram", "createCompartment", "deploy", "exchangeKeys", "generateAttestableDoc", "generateCertificate", "sign"]:
        monkeypatch.setattr(launcher, method, lambda *args: None)
    monkeypatch.setattr(launcher, "get_latest_executable", lambda _: str(executable))
    monkeypatch.setattr(launcher, "get_latest_certificate_dir", lambda _: str(tmp_path))
    monkeypatch.setattr(launcher, "getIntegratedServices", lambda *args: [])
    monkeypatch.setattr(legacy, "_metric", lambda *args: None)
    captured = []
    monkeypatch.setattr(legacy, "run_shell_command", lambda cmd, env: captured.append(env) or SimpleNamespace(stdout=b"", stderr=b"", returncode=0))
    for name, value in [("LAUNCHER_HOST", host), ("LAUNCHER_PORT", port)]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setenv("LAUNCHER_READ_HOST", "ignored-read")
    monkeypatch.setenv("LAUNCHER_WRITE_HOST", "ignored-write")
    launcher.start(7, run_id="test")
    assert captured[0]["LAUNCHER_HOST"] == ("127.0.0.1" if host is None else host)
    assert captured[0]["LAUNCHER_PORT"] == ("5001" if port is None else port)

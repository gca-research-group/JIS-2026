from __future__ import annotations

import importlib.util
from pathlib import Path


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


def test_legacy_launcher_has_no_read_route_or_method():
    legacy = load_legacy_launcher()
    routes = {rule.rule for rule in legacy.app.url_map.iter_rules()}

    assert "/api/read/<srv_id>/<int:program_id>" not in routes
    assert "/api/write/<srv_id>/<int:program_id>" in routes
    assert not hasattr(legacy.Launcher, "read")


def test_integration_process_splits_read_and_write_routing():
    source = INTEGRATION_PROCESS.read_text(encoding="utf-8")

    assert 'getenv("LAUNCHER_READ_HOST")' in source
    assert 'getenv("LAUNCHER_READ_PORT")' in source
    assert (
        "http_post_json(read_launcher_host(), read_launcher_port(), endpoint, payload)"
        in source
    )
    assert "http_post_json(LAUNCHER_HOST, LAUNCHER_PORT, endpoint, payload)" in source

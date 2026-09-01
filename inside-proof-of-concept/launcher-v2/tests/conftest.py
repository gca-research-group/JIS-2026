from __future__ import annotations

import sys
import importlib
from pathlib import Path

import pytest

LAUNCHER_V2_ROOT = Path(__file__).resolve().parents[1]
if str(LAUNCHER_V2_ROOT) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_V2_ROOT))


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    module = importlib.import_module("launcher.read")
    monkeypatch.setattr(module, "FILE_DATABASE", tmp_path / "missing.json")
    monkeypatch.setattr(module, "file_db", {})

"""Keep developer dotenv files out of regression tests unless explicitly enabled."""

import pytest


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")

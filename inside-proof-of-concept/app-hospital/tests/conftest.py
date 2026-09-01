import pytest


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")

"""Service defaults anchored to the repository, independent of the working directory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from _shared import default_metrics_file

BASE_DIR = Path(__file__).resolve().parent
ENVIRONMENT = "inside"
SERVICE_ID = "health-registry-service"


def default_config() -> dict[str, Any]:
    """Load local defaults without replacing existing environment values."""
    load_dotenv(BASE_DIR / ".env", override=False)
    return {
        "DATA_PATH": BASE_DIR / "data" / "health_registry.json",
        "METRICS_FILE": os.environ.get("METRICS_FILE", str(default_metrics_file(__file__))),
        "PORT": int(os.environ.get("HEALTH_REGISTRY_SERVICE_PORT", "8100")),
    }

"""Messaging settings anchored to the service directory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from _shared import default_metrics_file

BASE_DIR = Path(__file__).resolve().parent
ENVIRONMENT = "inside"
SERVICE_ID = "messaging-service"


def default_config() -> dict[str, Any]:
    load_dotenv(BASE_DIR / ".env", override=False)
    return {
        "DATA_PATH": BASE_DIR / "data" / "notifications.json",
        "METRICS_FILE": os.environ.get("METRICS_FILE", str(default_metrics_file(__file__))),
        "PORT": int(os.environ.get("MESSAGING_SERVICE_PORT", "9100")),
    }

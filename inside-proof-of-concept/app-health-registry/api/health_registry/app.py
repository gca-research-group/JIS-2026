"""Flask application construction and dependency wiring."""

from __future__ import annotations

from threading import RLock
from typing import Any

from flask import Flask
from flask_talisman import Talisman

from .config import default_config
from .routes import routes


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(default_config())
    app.config.update(config or {})
    app.extensions["health_registry_data_lock"] = RLock()
    Talisman(app)
    app.register_blueprint(routes)
    return app

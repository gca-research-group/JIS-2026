"""Inside proof-of-concept Health Registry Service."""

from __future__ import annotations

from typing import Any

from flask import Flask


def create_app(config: dict[str, Any] | None = None) -> Flask:
    """Create an independent app with all required web dependencies."""
    from .app import create_app as factory

    return factory(config)

"""Run with python -m health_registry from the API directory."""

from __future__ import annotations

import logging

from . import create_app
from .config import BASE_DIR

from flask import Flask


def main(app: Flask | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    if app is None:
        app = create_app()
    context = (str(BASE_DIR / "keys" / "cert.pem"), str(BASE_DIR / "keys" / "priv.pem"))
    app.run(
        host="127.0.0.1",
        port=app.config["PORT"],
        ssl_context=context,
        debug=False,
        use_reloader=False,
        load_dotenv=False,
    )


if __name__ == "__main__":
    main()

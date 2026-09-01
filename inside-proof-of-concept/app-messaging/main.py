"""Run the Messaging service with ``python main.py``."""

from __future__ import annotations

import logging

from flask import Flask

from app import create_app
from config import BASE_DIR


def main(app: Flask | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    if app is None:
        app = create_app()
    app.run(
        host="127.0.0.1",
        port=app.config["PORT"],
        ssl_context=(str(BASE_DIR / "keys" / "cert.pem"), str(BASE_DIR / "keys" / "priv.pem")),
        debug=False,
        use_reloader=False,
        load_dotenv=False,
    )


if __name__ == "__main__":
    main()

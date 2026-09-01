from __future__ import annotations

import os
from pathlib import Path

from app import app

ROOT = Path(__file__).resolve().parent
LEGACY_KEYS = ROOT.parent / "launcher" / "keys"


def bind_configuration() -> tuple[str, int, tuple[str, str]]:
    host = os.environ.get("LAUNCHER_V2_HOST", "127.0.0.1")
    port = int(os.environ.get("LAUNCHER_V2_PORT", "5000"))
    certificate = os.environ.get("LAUNCHER_V2_TLS_CERT", str(LEGACY_KEYS / "cert.pem"))
    private_key = os.environ.get("LAUNCHER_V2_TLS_KEY", str(LEGACY_KEYS / "prk.pem"))
    return host, port, (certificate, private_key)


if __name__ == "__main__":
    bind_host, bind_port, tls_context = bind_configuration()
    app.run(
        debug=False,
        ssl_context=tls_context,
        host=bind_host,
        port=bind_port,
        use_reloader=False,
        threaded=True,
    )

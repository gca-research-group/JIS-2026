# Inside Messaging Service

Run from this directory with `python3 main.py`. The service binds HTTPS to `127.0.0.1:9100` using `keys/cert.pem` and `keys/priv.pem`. `MESSAGING_SERVICE_PORT` and `METRICS_FILE` retain their existing meanings; data is stored in `data/notifications.json`.

Configuration construction optionally loads this directory's `.env`. Precedence is explicit `create_app(config)` values, process environment, `.env`, then defaults. Copy `.env.example` when local overrides are useful; `.env` is ignored and never created automatically. Restart after changing it.

Modules follow the Health Registry layout: `app.py` constructs Flask applications, `routes.py` translates HTTP, `service.py` owns persistence and orchestration, `security.py` and `metrics.py` adapt shared helpers, `config.py` resolves resources, `_shared.py` contains the repository import bridge, and `main.py` starts HTTPS. Imports do not start the server or configure root logging.

The legacy `api/API3.py` and `api/verifyCertificate.py` interfaces are retired. Put this service root on the Python path to import `create_app` from `app` or `post_action` from `service`.

Development checks:

```sh
python -m pytest -q
python -m ruff check app.py config.py main.py metrics.py routes.py security.py service.py _shared.py tests
python -m ruff format --check app.py config.py main.py metrics.py routes.py security.py service.py _shared.py tests
```

Tests use temporary data and metrics files and intercept startup; they do not bind sockets or modify the tracked dataset and keys.

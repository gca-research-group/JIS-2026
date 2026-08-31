# Inside Health Registry Service

Run from this service's `api` directory:

```sh
python3 -m health_registry
```

The module command is the supported entry point. The server binds HTTPS on `127.0.0.1:8100`, using `keys/cert.pem` and
`keys/priv.pem` relative to this service. `HEALTH_REGISTRY_SERVICE_PORT` and
`METRICS_FILE` retain their existing meanings. Registry data stays in
`data_access/health_registry.json`. Shared helpers are loaded from the inside
proof-of-concept directory through one private import bridge; this package is
intended to run from this checkout, not as an independently installed wheel.

Flask and Flask-Talisman are required for application creation and module startup. Missing or broken imports propagate their original errors; the service
does not return an absent app or start with Talisman silently disabled. Both
packages are already listed in the root runtime requirements.

## Local environment configuration

From this service directory, optionally copy the example before launching:

```sh
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env`. The application reads only
this service directory's `.env`, independent of the working directory, when
configuration is constructed. No file is required or created automatically.
The real `.env` is ignored by Git; `.env.example` is versioned.

Settings take precedence in this order: explicit `create_app(config)` overrides,
existing process environment, `.env`, then built-in defaults. The port defaults
to `8100`. `METRICS_FILE` is optional and defaults to
`inside-proof-of-concept/metrics/all_metrics.csv`. Prefer an absolute override
path; relative paths remain relative to the process working directory.

Restart after editing `.env`: loaded values enter the process environment and
are not overwritten by later configuration calls. Flask's additional dotenv
search is disabled, preventing unrelated working-directory or parent files from
being loaded. Install the updated root requirements to obtain `python-dotenv`.

## Modules

| Module | Responsibility |
| --- | --- |
| `health_registry/app.py` | `create_app(config=None)` and per-app dependency wiring |
| `health_registry/routes.py` | Shared module-level Blueprint and top-level HTTP handlers |
| `health_registry/service.py` | Locked JSON reads, patient serialization, and request orchestration |
| `health_registry/security.py` | Existing simulated-security adapters |
| `health_registry/metrics.py` | Per-request timing and shared CSV emission |
| `health_registry/config.py` | Paths, environment settings, and service identity |
| `health_registry/_shared.py` | Repository-local common imports |
| `health_registry/__main__.py` | Logging setup and local HTTPS startup |

Imports do not start a server or configure root logging. Use `create_app` and
the package interfaces. Factory configuration accepts `DATA_PATH`, `METRICS_FILE`,
and `PORT` as well as Flask settings. Each app owns its read lock and metrics
destination; each request owns its timing collector.

Each app registers the same Blueprint. Handlers read `DATA_PATH` and
`METRICS_FILE` from `current_app.config` and use the per-app lock stored in
`current_app.extensions["health_registry_data_lock"]`. The functions
`load_registry_data(data_path, data_lock)`,
`retrieve_local_data(patient_id, data_path, data_lock)`, and
`request_action(payload, data_path, metrics_file, data_lock)` live in
`health_registry.service`. Reuse the same lock for reads of the same app's data.
There is no repository or service object, and the module remains importable
without web dependencies.

## Development and verification

The root README specifies `python3` without a deployment minor version. This
refactor was verified on CPython 3.12.13; the Morello deployment interpreter was
not available for execution here. Source linting targets Python 3.9 syntax,
preserving the existing postponed-annotation style. No runtime upgrade is
required by this refactor. Development tools are pinned separately from runtime
dependencies; choose a compatible root runtime dependency set for your platform.

From this service directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r ../../requirements.txt -r requirements-dev.txt
python -m pytest -q
python -m ruff check api tests
python -m ruff format --check api tests
```

On Windows, use `.venv\Scripts\Activate.ps1` to activate the environment.
The local validation environment installed Flask, Flask-Talisman, python-dotenv, and the
development requirements; other root dependencies belong to other components.

Tests first characterized the old service (24 passing cases), then reused its
HTTP/storage/metrics expectations against the application factory.
Additional checks exercise factory isolation, shared-helper resolution, module
startup, environment overrides, and explicit missing/broken dependency failures. All fixtures
use temporary registry/CSV files, and startup checks intercept `Flask.run` or the underlying server binding
without opening sockets or reading TLS key material.

Behavior deliberately preserved includes simulated plaintext encryption,
malformed-registry error handling, and the missing verification timing on
certificate rejection (the legacy collector flushes before the timed context
exits). Metric labels and JSON keys retain camelCase where the experiment
expects it, even though internal Python names use snake_case.

## Migration from legacy interfaces

`API1.py`, `verifyCertificate.py`, and `RegistryService` have been retired.
Launch with `python3 -m health_registry` from the API directory. Call
`health_registry.service.request_action(payload, data_path, metrics_file, data_lock)`
directly when HTTP is unnecessary. Import `verify_certificate`, `encrypt`, and
`decrypt` from `health_registry.security`; these remain security simulations.

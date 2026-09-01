# Launcher v2 read service

Launcher v2 owns the trusted proof-of-concept read endpoint while the original
Launcher continues to serve lifecycle and write endpoints.

## Layout

- `app.py` contains the Flask application and `api_read` HTTP adapter.
- `main.py` contains process startup and bind/TLS configuration.
- `launcher/read.py` contains the function-based read workflow migrated from
  `Launcher.read`.
- `launcher/metrics.py` contains the launcher-specific metric emitter and the
  same per-operation collector pattern used by `app-health-registry`.

The inner `launcher` package contains no Flask code or Launcher/service domain
class. `MetricsCollector` is infrastructure for named timing blocks and flush
ordering.

The public Python operation is:

```python
from launcher.read import read

result = read(
    service_id,
    program_id,
    run_id="",
    patient_id="P001",
    metrics_file="/path/to/all_metrics.csv",  # optional
)
```

When `metrics_file` is omitted, the destination is resolved at call time from
`METRICS_FILE` or the proof-of-concept default. The Flask adapter always passes its own
`app.config["METRICS_FILE"]`, so separate application instances can use
separate CSV files.

## Metrics collection

Each read creates one `MetricsCollector`. It measures these blocks in order:

1. `lookupService_ms`
2. `getCertificate_ms`
3. `getProgramPublicKey_ms`
4. `request_ms`

After a successful downstream response, `flush("launcher_read_total_ms")`
emits the four buffered stages in that order and the total last. All rows retain
component `launcher`, operation `read`, and the read's run, program, and service
identifiers. If an unexpected exception occurs before flush, none of that read's
buffered stage or total metrics are written; the Flask adapter still returns its
existing JSON HTTP 500 response.

## Start

Start the original launcher on port 5000 first, then start this read service:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher-v2
python3 main.py
```

The defaults bind HTTPS to `127.0.0.1:5001` and reuse the proof-of-concept TLS
key pair from `../launcher/keys`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LAUNCHER_V2_HOST` | `127.0.0.1` | Flask bind host |
| `LAUNCHER_V2_PORT` | `5001` | Flask bind port |
| `LAUNCHER_V2_TLS_CERT` | `../launcher/keys/cert.pem` | TLS certificate |
| `LAUNCHER_V2_TLS_KEY` | `../launcher/keys/prk.pem` | TLS private key |
| `LAUNCHER_FILE_DATABASE` | `../launcher/programs-data-base/file_database.json` | Shared persisted program metadata |
| `METRICS_FILE` | `../metrics/all_metrics.csv` | Per-application metrics destination |
| `LAUNCHER_READ_HOST` | `127.0.0.1` | Read callback host passed to the Integration Process |
| `LAUNCHER_READ_PORT` | `5001` | Read callback port passed to the Integration Process |

Service URLs and `METRICS_FILE` retain the environment variables supported by
the original launcher.

Program metadata is loaded when launcher-v2 starts. Restart launcher-v2 after
uploading, compiling, or deleting a program so it reloads the persisted file
database.

## Test

```sh
cd /home/regis/JIS-2026-main
python3 -m pytest -q inside-proof-of-concept/launcher-v2/tests
```

For rollback, stop launcher-v2, restore the original launcher's `api_read` route
and `Launcher.read` method, and route reads back to `127.0.0.1:5000`. No data
conversion is necessary.

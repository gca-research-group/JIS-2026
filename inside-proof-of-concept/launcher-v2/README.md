# Launcher v2 read and write service

Launcher v2 owns the trusted proof-of-concept read and write endpoints while the original
Launcher continues to serve lifecycle endpoints.

## Layout

- `app.py` contains the Flask application and `api_read` and `api_write` HTTP adapters.
- `main.py` contains process startup and bind/TLS configuration.
- `launcher/read.py` contains the function-based read workflow migrated from
  `Launcher.read`.
- `launcher/write.py` contains the function-based write workflow migrated from
  `Launcher.write`, reusing the metadata and transport helpers in `read.py`.
- `launcher/metrics.py` contains the launcher-specific metric emitter and the
  same per-operation collector pattern used by `app-health-registry`.

The inner `launcher` package contains no Flask code or Launcher/service domain
class. `MetricsCollector` is infrastructure for named timing blocks and flush
ordering.

The public Python operations are:

```python
from launcher.read import read
from launcher.write import write

result = read(
    service_id,
    program_id,
    run_id="",
    patient_id="P001",
    metrics_file="/path/to/all_metrics.csv",  # optional
)

written = write(service_id, program_id, data_enc="encrypted", run_id="")
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

Each write measures `lookupService_ms`, `getCertificate_ms`, and `post_ms`,
then flushes `launcher_write_total_ms` last. Rows use operation `write`.
As with reads, failures before flush emit no buffered metrics; this replaces
the legacy write operation's partial failure metrics.

## Start

Start the original launcher on port 5000 first, then start this read/write service:

```sh
cd /home/regis/JIS-2026-main/inside-proof-of-concept/launcher-v2
LAUNCHER_V2_PORT=5001 python3 main.py
```

The command binds HTTPS to `127.0.0.1:5001` and reuses the proof-of-concept TLS
key pair from `../launcher/keys`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LAUNCHER_V2_HOST` | `127.0.0.1` | Flask bind host |
| `LAUNCHER_V2_PORT` | `5000` | Flask bind port; set to `5001` alongside the original launcher |
| `LAUNCHER_V2_TLS_CERT` | `../launcher/keys/cert.pem` | TLS certificate |
| `LAUNCHER_V2_TLS_KEY` | `../launcher/keys/prk.pem` | TLS private key |
| `LAUNCHER_FILE_DATABASE` | `../launcher/programs-data-base/file_database.json` | Shared persisted program metadata |
| `METRICS_FILE` | `../metrics/all_metrics.csv` | Per-application metrics destination |
| `LAUNCHER_HOST` | `127.0.0.1` | Shared read/write callback host passed to the Integration Process |
| `LAUNCHER_PORT` | `5001` | Shared read/write callback port passed to the Integration Process |

Set `LAUNCHER_HOST` and `LAUNCHER_PORT` in the original launcher process
environment; both Integration Process callbacks use this destination. Unset or
empty values use `127.0.0.1:5001`. Match these to launcher-v2's bind address.
Rename old read-specific callback settings to these shared names; operation-specific
settings are no longer used. No write-specific variables are needed.

After updating the Integration Process source, rebuild it with the existing
`command-line-interface.py compile <program_id>` command and attestation flow
before measured runs. Restart launcher-v2 after compilation to reload the new
certificate metadata. Existing executables still contain the old routing.

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

For rollback of the write migration, restore the original `api_write` route and
`Launcher.write` method together with the pre-migration Integration Process
source, executable, and launcher environment propagation. Restore its previous
read-specific callback configuration so reads still reach launcher-v2 and writes
reach port 5000. The new shared resolver cannot express that split. No data
conversion is necessary.

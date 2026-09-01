"""Controlled HTTP read/write cycle; no live healthcare data or attestation."""

import csv
import importlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from app import create_app
from werkzeug.serving import make_server

read_module = importlib.import_module("launcher.read")


def test_http_read_write_cycle(tmp_path, monkeypatch):
    received = []

    class HealthcareStub(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, payload))
            result = (
                {"dataEnc": json.dumps({"patientId": "P-test", "hospitalId": "H-test"})}
                if self.path == "/read" else {"ok": True}
            )
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    downstream = ThreadingHTTPServer(("127.0.0.1", 0), HealthcareStub)
    downstream_thread = Thread(target=downstream.serve_forever, daemon=True)
    downstream_thread.start()
    launcher = None
    try:
        cert = tmp_path / "credentials"
        cert.mkdir()
        (cert / "certificate.pem").write_text("test-certificate")
        (cert / "public_key.pem").write_text("test-public-key")
        database = tmp_path / "db.json"
        database.write_text(json.dumps({"7": {"certificates": [str(cert)]}}))
        monkeypatch.setattr(read_module, "FILE_DATABASE", database)
        base = f"http://127.0.0.1:{downstream.server_port}"
        monkeypatch.setattr(read_module, "SERVICE_URLS", {
            "health-registry-service": base + "/read",
            "hospital-service": base + "/write",
        })
        metrics = tmp_path / "metrics.csv"
        app = create_app({"METRICS_FILE": str(metrics)})
        keys = read_module.LEGACY_LAUNCHER_DIR / "keys"
        launcher = make_server("127.0.0.1", 0, app, ssl_context=(str(keys / "cert.pem"), str(keys / "prk.pem")))
        launcher_thread = Thread(target=launcher.serve_forever, daemon=True)
        launcher_thread.start()
        destination = f"https://127.0.0.1:{launcher.server_port}"
        result = read_module.post_json(destination + "/api/read/health-registry-service/7", {"runId": "smoke", "patientId": "P-test"})
        written = read_module.post_json(destination + "/api/write/hospital-service/7", {"runId": "smoke", "dataEnc": result["dataEnc"]})
        assert written == {"ok": True}
        assert [path for path, _ in received] == ["/read", "/write"]
        assert received[1][1] == {
            "signedCert": "test-certificate", "dataEnc": result["dataEnc"],
            "serviceId": "hospital-service", "programId": 7, "runId": "smoke", "environment": "inside",
        }
        with metrics.open() as source:
            rows = list(csv.DictReader(source))
        assert len(rows) == 9
        assert [row["operation"] for row in rows] == ["read"] * 5 + ["write"] * 4
        assert rows[4]["metric"] == "launcher_read_total_ms"
        assert rows[-1]["metric"] == "launcher_write_total_ms"
        assert all(row["run_id"] == "smoke" and row["program_id"] == "7" for row in rows)
    finally:
        if launcher is not None:
            launcher.shutdown()
            launcher.server_close()
            launcher_thread.join(timeout=5)
        downstream.shutdown()
        downstream.server_close()
        downstream_thread.join(timeout=5)

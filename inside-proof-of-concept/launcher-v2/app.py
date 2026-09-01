from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, request

from launcher.read import load_file_database, read
from launcher.write import write
from launcher.metrics import default_launcher_metrics_file


def create_app(
    config: dict[str, Any] | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["METRICS_FILE"] = os.environ.get(
        "METRICS_FILE", default_launcher_metrics_file()
    )
    if config:
        app.config.update(config)
    load_file_database()

    @app.post("/api/read/<srv_id>/<int:program_id>")
    def api_read(srv_id: str, program_id: int):
        candidate = request.get_json(force=True, silent=True)
        payload = candidate if isinstance(candidate, dict) else {}
        run_id = payload.get("runId", "")
        try:
            patient_id = str(payload.get("patientId", "P001")).strip() or "P001"
            return jsonify(
                read(
                    srv_id,
                    program_id,
                    run_id,
                    patient_id,
                    metrics_file=app.config["METRICS_FILE"],
                )
            ), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/write/<srv_id>/<int:program_id>")
    def api_write(srv_id: str, program_id: int):
        payload = request.get_json(force=True, silent=True) or {}
        try:
            return jsonify(
                write(
                    srv_id,
                    program_id,
                    payload.get("dataEnc", ""),
                    payload.get("runId", ""),
                    metrics_file=app.config["METRICS_FILE"],
                )
            ), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app


app = create_app()

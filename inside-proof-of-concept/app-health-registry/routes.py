"""HTTP translation for the registry service."""

from flask import Blueprint, Response, current_app, jsonify, request

from config import ENVIRONMENT, SERVICE_ID
from service import load_registry_data, request_action

routes = Blueprint("health_registry", __name__)


@routes.get("/api/health")
def health() -> tuple[Response, int]:
    return jsonify(status="ok", serviceId=SERVICE_ID, environment=ENVIRONMENT), 200


@routes.post("/api/request")
def request_dataset() -> tuple[Response, int]:
    payload = request.get_json(force=True, silent=True) or {}
    body, status = request_action(
        payload,
        current_app.config["DATA_PATH"],
        current_app.config["METRICS_FILE"],
        current_app.extensions["health_registry_data_lock"],
    )
    return jsonify(body), status


@routes.get("/api/patients")
def list_patients() -> tuple[Response, int]:
    data = load_registry_data(
        current_app.config["DATA_PATH"], current_app.extensions["health_registry_data_lock"]
    )
    return jsonify(patients=data.get("Patients", [])), 200

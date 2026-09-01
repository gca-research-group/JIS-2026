"""HTTP translation for the Hospital service."""

from flask import Blueprint, Response, current_app, jsonify, request

from config import ENVIRONMENT, SERVICE_ID
from service import load_hospital_data, post_action

routes = Blueprint("hospital", __name__)


@routes.get("/api/health")
def health() -> tuple[Response, int]:
    return jsonify(status="ok", serviceId=SERVICE_ID, environment=ENVIRONMENT), 200


@routes.post("/api/post")
def post_dataset() -> tuple[Response, int]:
    payload = request.get_json(force=True, silent=True) or {}
    body, status = post_action(
        payload,
        current_app.config["DATA_PATH"],
        current_app.config["METRICS_FILE"],
        current_app.extensions["hospital_data_lock"],
    )
    return jsonify(body), status


@routes.get("/api/patients")
def list_patients() -> tuple[Response, int]:
    with current_app.extensions["hospital_data_lock"]:
        data = load_hospital_data(current_app.config["DATA_PATH"])
    return jsonify(patients=data.get("Patients", [])), 200

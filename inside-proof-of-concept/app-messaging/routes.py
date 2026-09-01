"""HTTP translation for the Messaging service."""

from flask import Blueprint, Response, current_app, jsonify, request

from config import ENVIRONMENT, SERVICE_ID
from service import load_notifications, post_action

routes = Blueprint("messaging", __name__)


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
        current_app.extensions["messaging_data_lock"],
    )
    return jsonify(body), status


@routes.get("/api/notifications")
def list_notifications() -> tuple[Response, int]:
    with current_app.extensions["messaging_data_lock"]:
        notifications = load_notifications(current_app.config["DATA_PATH"])
    return jsonify(notifications=notifications), 200

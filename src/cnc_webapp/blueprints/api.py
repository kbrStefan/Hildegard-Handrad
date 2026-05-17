from __future__ import annotations

from http import HTTPStatus
from typing import Any

from flask import Blueprint, jsonify, request
from serial import SerialException
from werkzeug.exceptions import HTTPException

from ..extensions import get_controller

api_bp = Blueprint("api", __name__)


@api_bp.errorhandler(HTTPException)
def handle_http_exception(err: HTTPException):
    return jsonify({"ok": False, "error": err.description}), err.code


@api_bp.errorhandler(Exception)
def handle_unexpected_exception(err: Exception):
    return jsonify({"ok": False, "error": f"Unexpected API error: {err}"}), HTTPStatus.INTERNAL_SERVER_ERROR


@api_bp.post("/serial/connect")
def serial_connect():
    payload = request.get_json(silent=True) or {}
    port = payload.get("port")
    baudrate = payload.get("baudrate")

    try:
        baudrate_value = int(baudrate) if baudrate is not None else None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "baudrate must be numeric"}), HTTPStatus.BAD_REQUEST

    controller = get_controller()
    try:
        controller.connect(port=port, baudrate=baudrate_value)
    except (RuntimeError, ValueError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST
    except Exception as err:
        return jsonify({"ok": False, "error": f"Unexpected connect error: {err}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.post("/serial/disconnect")
def serial_disconnect():
    controller = get_controller()
    try:
        controller.disconnect()
    except (RuntimeError, ValueError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST
    except Exception as err:
        return jsonify({"ok": False, "error": f"Unexpected disconnect error: {err}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.post("/gcode/upload")
def gcode_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file part in request"}), HTTPStatus.BAD_REQUEST

    file_storage = request.files["file"]
    if not file_storage.filename:
        return jsonify({"ok": False, "error": "No file selected"}), HTTPStatus.BAD_REQUEST

    controller = get_controller()
    try:
        details = controller.upload_gcode(file_storage)
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST

    return jsonify({"ok": True, "details": details, "status": controller.status()})


@api_bp.post("/job/start")
def job_start():
    controller = get_controller()
    try:
        controller.start_job()
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.post("/job/stop")
def job_stop():
    controller = get_controller()
    try:
        controller.stop_job()
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.post("/job/pause")
def job_pause():
    controller = get_controller()
    try:
        controller.pause_job()
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.post("/job/resume")
def job_resume():
    controller = get_controller()
    try:
        controller.resume_job()
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.post("/job/estop")
def job_estop():
    controller = get_controller()
    try:
        controller.emergency_stop()
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.get("/status")
def status():
    return jsonify({"ok": True, "status": get_controller().status()})


@api_bp.post("/home")
def home():
    payload = request.get_json(silent=True) or {}
    axes_raw: Any = payload.get("axes")
    axes: list[str] | None = None

    if isinstance(axes_raw, str):
        axes = [axes_raw]
    elif isinstance(axes_raw, list):
        axes = [str(axis) for axis in axes_raw]

    controller = get_controller()
    try:
        controller.home(axes=axes)
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST
    except Exception as err:
        return jsonify({"ok": False, "error": f"Unexpected homing error: {err}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    return jsonify({"ok": True, "status": controller.status()})


@api_bp.post("/jog")
def jog():
    payload = request.get_json(silent=True) or {}
    axis = str(payload.get("axis", "")).upper()

    try:
        distance = float(payload.get("distance"))
        feedrate = float(payload.get("feedrate"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "distance and feedrate must be numeric"}), HTTPStatus.BAD_REQUEST

    if axis not in {"X", "Y", "Z"}:
        return jsonify({"ok": False, "error": "axis must be one of X, Y, Z"}), HTTPStatus.BAD_REQUEST

    controller = get_controller()
    try:
        controller.jog(axis=axis, distance=distance, feedrate=feedrate)
    except (RuntimeError, ValueError, TimeoutError, SerialException) as err:
        return jsonify({"ok": False, "error": str(err)}), HTTPStatus.BAD_REQUEST

    return jsonify({"ok": True, "status": controller.status()})

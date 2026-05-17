from http import HTTPStatus

from flask import Blueprint, jsonify

stubs_bp = Blueprint("stubs", __name__)


@stubs_bp.post("/probe")
def probe_stub():
    return jsonify({"ok": False, "error": "Probing module not implemented yet"}), HTTPStatus.NOT_IMPLEMENTED


@stubs_bp.post("/macros/run")
def macros_stub():
    return jsonify({"ok": False, "error": "Macros module not implemented yet"}), HTTPStatus.NOT_IMPLEMENTED

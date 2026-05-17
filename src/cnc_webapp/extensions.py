from flask import Flask

from .services.cnc_controller import CNCController

_controller: CNCController | None = None


def init_controller(app: Flask) -> None:
    global _controller
    _controller = CNCController(app.config)


def get_controller() -> CNCController:
    if _controller is None:
        raise RuntimeError("CNC controller is not initialized")
    return _controller

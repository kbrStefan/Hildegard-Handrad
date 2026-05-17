from __future__ import annotations

from typing import Any

from werkzeug.datastructures import FileStorage

from .gcode_parser import parse_gcode_text
from .serial_streamer import SerialStreamer


class CNCController:
    def __init__(self, config: dict[str, Any]) -> None:
        self._streamer = SerialStreamer(
            port=config["SERIAL_PORT"],
            baudrate=config["SERIAL_BAUDRATE"],
            read_timeout=config["SERIAL_READ_TIMEOUT"],
            max_inflight_lines=config["STREAM_MAX_INFLIGHT_LINES"],
            max_inflight_chars=config["STREAM_MAX_INFLIGHT_CHARS"],
        )

    def connect(self, port: str | None = None, baudrate: int | None = None) -> None:
        self._streamer.connect(port=port, baudrate=baudrate)

    def disconnect(self) -> None:
        self._streamer.disconnect()

    def upload_gcode(self, file_storage: FileStorage) -> dict[str, Any]:
        text = file_storage.read().decode("utf-8", errors="ignore")
        lines = parse_gcode_text(text)
        if not lines:
            raise ValueError("Uploaded file does not contain executable G-code after comments are removed")

        self._streamer.load_job(lines)
        return {
            "loaded_lines": len(lines),
            "first_line": lines[0],
            "last_line": lines[-1],
        }

    def start_job(self) -> None:
        self._streamer.start_job()

    def stop_job(self) -> None:
        self._streamer.stop_job()

    def pause_job(self) -> None:
        self._streamer.pause_job()

    def resume_job(self) -> None:
        self._streamer.resume_job()

    def emergency_stop(self) -> None:
        self._streamer.emergency_stop()

    def status(self) -> dict[str, Any]:
        return self._streamer.status()

    def jog(self, axis: str, distance: float, feedrate: float) -> None:
        self._streamer.jog(axis=axis, distance=distance, feedrate=feedrate)

    def home(self, axes: list[str] | None = None) -> None:
        self._streamer.home(axes=axes)

    # Stubs for future modules
    def probe(self, *_: Any, **__: Any) -> None:
        raise NotImplementedError("Probing module not implemented yet")

    def run_macro(self, *_: Any, **__: Any) -> None:
        raise NotImplementedError("Macros module not implemented yet")

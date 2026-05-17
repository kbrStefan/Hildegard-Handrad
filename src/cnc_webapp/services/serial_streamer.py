from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Any

import serial


class MachineMode(str, Enum):
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    RUNNING = "running"
    HOMING = "homing"
    JOGGING = "jogging"
    ALARM = "alarm"
    ERROR = "error"


class JobState(str, Enum):
    EMPTY = "empty"
    LOADED = "loaded"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


class SerialStreamer:
    def __init__(
        self,
        port: str,
        baudrate: int,
        read_timeout: float,
        max_inflight_lines: int,
        max_inflight_chars: int,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.max_inflight_lines = max_inflight_lines
        self.max_inflight_chars = max_inflight_chars

        self._serial_conn: serial.Serial | None = None
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._tx_thread: threading.Thread | None = None

        self._job_lines: list[str] = []
        self._job_index = 0
        self._job_running = False

        self._outstanding_payload_sizes: deque[int] = deque()
        self._outstanding_chars = 0

        self._sent_lines = 0
        self._acked_lines = 0
        self._errors = 0
        self._last_messages: deque[str] = deque(maxlen=30)
        self._mode = MachineMode.DISCONNECTED
        self._job_state = JobState.EMPTY
        self._last_error_message = ""

    def connect(self, port: str | None = None, baudrate: int | None = None) -> None:
        with self._state_lock:
            if self._serial_conn and self._serial_conn.is_open:
                return

            if port:
                self.port = port
            if baudrate:
                self.baudrate = baudrate

            self._serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.read_timeout,
                write_timeout=1.0,
            )
            self._serial_conn.reset_input_buffer()
            self._serial_conn.reset_output_buffer()
            self._stop_event.clear()
            self._mode = MachineMode.IDLE
            self._last_error_message = ""

        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def disconnect(self) -> None:
        self.stop_job()
        self._stop_event.set()

        with self._state_lock:
            conn = self._serial_conn
            self._serial_conn = None
            self._mode = MachineMode.DISCONNECTED
            self._job_state = JobState.STOPPED if self._job_lines else JobState.EMPTY

        if conn and conn.is_open:
            conn.close()

    def load_job(self, lines: list[str]) -> None:
        with self._state_lock:
            self._job_lines = lines
            self._job_index = 0
            self._sent_lines = 0
            self._acked_lines = 0
            self._errors = 0
            self._outstanding_payload_sizes.clear()
            self._outstanding_chars = 0
            self._last_messages.clear()
            self._job_state = JobState.LOADED
            if self._mode not in (MachineMode.ALARM, MachineMode.ERROR):
                self._mode = MachineMode.IDLE

    def start_job(self) -> None:
        with self._state_lock:
            if not self._serial_conn or not self._serial_conn.is_open:
                raise RuntimeError("Serial is not connected")
            if not self._job_lines:
                raise RuntimeError("No G-code loaded")
            if self._job_running:
                return
            self._job_running = True
            self._job_state = JobState.RUNNING
            self._mode = MachineMode.RUNNING

        self._tx_thread = threading.Thread(target=self._tx_loop, daemon=True)
        self._tx_thread.start()

    def stop_job(self) -> None:
        with self._state_lock:
            self._job_running = False
            self._job_state = JobState.STOPPED if self._job_lines else JobState.EMPTY
            if self._mode not in (MachineMode.ALARM, MachineMode.ERROR):
                self._mode = MachineMode.IDLE

    def home(self, axes: list[str] | None = None) -> None:
        normalized_axes = []
        if axes:
            normalized_axes = [axis.upper() for axis in axes if axis.upper() in {"X", "Y", "Z"}]

        with self._state_lock:
            if self._job_running:
                raise RuntimeError("Cannot home while job is running")
            if self._mode in (MachineMode.ALARM, MachineMode.ERROR):
                raise RuntimeError("Cannot home while controller is in alarm/error state")
            self._mode = MachineMode.HOMING

        command = "G28" if not normalized_axes else f"G28 {' '.join(normalized_axes)}"
        try:
            self._send_and_wait_ack(command)
        finally:
            with self._state_lock:
                if self._mode not in (MachineMode.ALARM, MachineMode.ERROR):
                    self._mode = MachineMode.IDLE

    def jog(self, axis: str, distance: float, feedrate: float) -> None:
        normalized_axis = axis.upper()
        if normalized_axis not in {"X", "Y", "Z"}:
            raise ValueError("Jog axis must be one of X, Y, Z")
        if feedrate <= 0:
            raise ValueError("Feedrate must be positive")

        with self._state_lock:
            if self._job_running:
                raise RuntimeError("Cannot jog while job is running")
            if self._mode in (MachineMode.ALARM, MachineMode.ERROR):
                raise RuntimeError("Cannot jog while controller is in alarm/error state")
            self._mode = MachineMode.JOGGING

        commands = [
            "G91",
            f"G0 {normalized_axis}{distance:.4f} F{feedrate:.0f}",
            "G90",
        ]
        try:
            for command in commands:
                self._send_and_wait_ack(command)
        finally:
            with self._state_lock:
                if self._mode not in (MachineMode.ALARM, MachineMode.ERROR):
                    self._mode = MachineMode.IDLE

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            total = len(self._job_lines)
            return {
                "connected": bool(self._serial_conn and self._serial_conn.is_open),
                "port": self.port,
                "baudrate": self.baudrate,
                "job_running": self._job_running,
                "job_total_lines": total,
                "job_current_line": self._job_index,
                "job_progress": 0 if total == 0 else round((self._job_index / total) * 100, 2),
                "sent_lines": self._sent_lines,
                "acked_lines": self._acked_lines,
                "errors": self._errors,
                "machine_mode": self._mode.value,
                "job_state": self._job_state.value,
                "last_error_message": self._last_error_message,
                "outstanding_lines": len(self._outstanding_payload_sizes),
                "outstanding_chars": self._outstanding_chars,
                "last_messages": list(self._last_messages),
            }

    def _send_and_wait_ack(self, line: str, timeout_seconds: float = 3.0) -> None:
        with self._state_lock:
            conn = self._serial_conn
            if not conn or not conn.is_open:
                raise RuntimeError("Serial is not connected")
            expected_ack = self._acked_lines + 1
            errors_before = self._errors

        payload = f"{line}\n".encode("ascii", errors="ignore")
        conn.write(payload)

        with self._state_lock:
            self._outstanding_payload_sizes.append(len(payload))
            self._outstanding_chars += len(payload)
            self._sent_lines += 1

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            with self._state_lock:
                if self._acked_lines >= expected_ack:
                    return
                if self._errors > errors_before:
                    raise RuntimeError("Controller reported an error while executing command")
            time.sleep(0.01)

        raise TimeoutError(f"Timeout waiting for controller acknowledgement for command: {line}")

    def _can_send_more(self) -> bool:
        return (
            len(self._outstanding_payload_sizes) < self.max_inflight_lines
            and self._outstanding_chars < self.max_inflight_chars
            and self._job_index < len(self._job_lines)
        )

    def _tx_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._state_lock:
                if not self._job_running:
                    return
                conn = self._serial_conn

            if not conn or not conn.is_open:
                with self._state_lock:
                    self._job_running = False
                return

            made_progress = False
            while True:
                with self._state_lock:
                    if not self._job_running or not self._can_send_more():
                        break
                    line = self._job_lines[self._job_index]

                payload = f"{line}\n".encode("ascii", errors="ignore")
                conn.write(payload)

                with self._state_lock:
                    self._job_index += 1
                    self._sent_lines += 1
                    self._outstanding_payload_sizes.append(len(payload))
                    self._outstanding_chars += len(payload)
                    made_progress = True

            with self._state_lock:
                is_done = self._job_index >= len(self._job_lines) and not self._outstanding_payload_sizes
                if is_done:
                    self._job_running = False
                    self._job_state = JobState.COMPLETED
                    if self._mode not in (MachineMode.ALARM, MachineMode.ERROR):
                        self._mode = MachineMode.IDLE
                    return

            if not made_progress:
                time.sleep(0.003)

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._state_lock:
                conn = self._serial_conn

            if not conn or not conn.is_open:
                return

            try:
                raw_line = conn.readline()
            except serial.SerialException:
                with self._state_lock:
                    self._job_running = False
                return

            if not raw_line:
                continue

            message = raw_line.decode("utf-8", errors="ignore").strip()
            if not message:
                continue

            lowered = message.lower()
            with self._state_lock:
                self._last_messages.append(message)
                if lowered.startswith("alarm"):
                    self._mode = MachineMode.ALARM
                    self._job_state = JobState.ERROR
                    self._last_error_message = message

                if lowered.startswith("ok"):
                    if self._outstanding_payload_sizes:
                        payload_size = self._outstanding_payload_sizes.popleft()
                        self._outstanding_chars = max(0, self._outstanding_chars - payload_size)
                        self._acked_lines += 1
                elif lowered.startswith("error"):
                    self._errors += 1
                    self._mode = MachineMode.ERROR
                    self._job_state = JobState.ERROR
                    self._last_error_message = message
                    if self._outstanding_payload_sizes:
                        payload_size = self._outstanding_payload_sizes.popleft()
                        self._outstanding_chars = max(0, self._outstanding_chars - payload_size)

from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
import re
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
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"
    ERROR = "error"


class SerialStreamer:
    def __init__(
        self,
        port: str,
        baudrate: int,
        read_timeout: float,
        command_ack_idle_timeout_seconds: float,
        command_ack_default_max_seconds: float,
        command_ack_homing_max_seconds: float,
        max_inflight_lines: int,
        max_inflight_chars: int,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.command_ack_idle_timeout_seconds = command_ack_idle_timeout_seconds
        self.command_ack_default_max_seconds = command_ack_default_max_seconds
        self.command_ack_homing_max_seconds = command_ack_homing_max_seconds
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
        self._job_paused = False

        self._outstanding_payload_sizes: deque[int] = deque()
        self._outstanding_chars = 0

        self._sent_lines = 0
        self._acked_lines = 0
        self._errors = 0
        self._last_messages: deque[str] = deque(maxlen=30)
        self._mode = MachineMode.DISCONNECTED
        self._job_state = JobState.EMPTY
        self._last_error_message = ""
        self._ack_timeout_seconds = 30.0
        self._last_ack_time = time.monotonic()
        self._last_rx_time = time.monotonic()
        self._last_busy_time = time.monotonic()

        self._ok_re = re.compile(r"(^|\s)ok($|\s|:)")
        self._busy_re = re.compile(r"(^|\s)(echo:)?busy:\s*processing|(^|\s)wait($|\s)")

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
            self._last_ack_time = time.monotonic()
            self._last_rx_time = time.monotonic()
            self._last_busy_time = time.monotonic()

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
            self._job_paused = False

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
            self._job_paused = False
            self._last_ack_time = time.monotonic()
            self._last_rx_time = time.monotonic()
            self._last_busy_time = time.monotonic()
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
            self._job_paused = False
            self._job_state = JobState.RUNNING
            self._mode = MachineMode.RUNNING

        self._tx_thread = threading.Thread(target=self._tx_loop, daemon=True)
        self._tx_thread.start()

    def stop_job(self) -> None:
        with self._state_lock:
            self._job_running = False
            self._job_paused = False
            self._job_state = JobState.STOPPED if self._job_lines else JobState.EMPTY
            if self._mode not in (MachineMode.ALARM, MachineMode.ERROR):
                self._mode = MachineMode.IDLE

    def pause_job(self) -> None:
        with self._state_lock:
            if not self._job_running:
                raise RuntimeError("No running job to pause")
            if self._job_paused:
                return
            self._job_paused = True
            self._job_state = JobState.PAUSED
            if self._mode == MachineMode.RUNNING:
                self._mode = MachineMode.IDLE

    def resume_job(self) -> None:
        with self._state_lock:
            if not self._job_running:
                raise RuntimeError("No running job to resume")
            if not self._job_paused:
                return
            self._job_paused = False
            self._job_state = JobState.RUNNING
            if self._mode not in (MachineMode.ALARM, MachineMode.ERROR):
                self._mode = MachineMode.RUNNING

    def emergency_stop(self) -> None:
        with self._state_lock:
            conn = self._serial_conn
            if not conn or not conn.is_open:
                raise RuntimeError("Serial is not connected")

            self._job_running = False
            self._job_paused = False
            self._job_state = JobState.ERROR
            self._mode = MachineMode.ERROR
            self._last_error_message = "Emergency stop triggered"
            self._outstanding_payload_sizes.clear()
            self._outstanding_chars = 0

        conn.write(b"M112\n")
        conn.flush()

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
            self._send_and_wait_ack(
                command,
                timeout_seconds=self.command_ack_idle_timeout_seconds,
                max_wait_seconds=self.command_ack_homing_max_seconds,
                extend_on_busy=True,
            )
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
                self._send_and_wait_ack(
                    command,
                    timeout_seconds=self.command_ack_idle_timeout_seconds,
                    max_wait_seconds=self.command_ack_default_max_seconds,
                    extend_on_busy=True,
                )
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
                "job_paused": self._job_paused,
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

    def _send_and_wait_ack(
        self,
        line: str,
        timeout_seconds: float = 6.0,
        max_wait_seconds: float | None = None,
        extend_on_busy: bool = True,
    ) -> None:
        with self._state_lock:
            conn = self._serial_conn
            if not conn or not conn.is_open:
                raise RuntimeError("Serial is not connected")
            expected_ack = self._acked_lines + 1
            errors_before = self._errors
            last_seen_busy = self._last_busy_time

        payload = f"{line}\n".encode("ascii", errors="ignore")
        conn.write(payload)

        with self._state_lock:
            self._outstanding_payload_sizes.append(len(payload))
            self._outstanding_chars += len(payload)
            self._sent_lines += 1
            self._last_ack_time = time.monotonic()

        start = time.monotonic()
        absolute_deadline = start + (max_wait_seconds if max_wait_seconds is not None else timeout_seconds)
        idle_deadline = start + timeout_seconds

        while True:
            now = time.monotonic()
            if now >= absolute_deadline:
                raise TimeoutError(f"Timeout waiting for controller acknowledgement for command: {line}")
            if now >= idle_deadline:
                raise TimeoutError(f"No busy/ok received within idle timeout while waiting for command: {line}")

            with self._state_lock:
                if self._acked_lines >= expected_ack:
                    return
                if self._errors > errors_before:
                    raise RuntimeError("Controller reported an error while executing command")

                if extend_on_busy and self._last_busy_time > last_seen_busy:
                    last_seen_busy = self._last_busy_time
                    idle_deadline = time.monotonic() + timeout_seconds
            time.sleep(0.01)

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
                is_paused = self._job_paused
                conn = self._serial_conn

            if not conn or not conn.is_open:
                with self._state_lock:
                    self._job_running = False
                return

            if is_paused:
                time.sleep(0.02)
                continue

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

                stalled = (
                    bool(self._outstanding_payload_sizes)
                    and (time.monotonic() - self._last_ack_time) > self._ack_timeout_seconds
                )
                if stalled:
                    self._job_running = False
                    self._job_paused = False
                    self._job_state = JobState.ERROR
                    self._mode = MachineMode.ERROR
                    self._last_error_message = "Streaming stalled: acknowledgement timeout"
                    self._outstanding_payload_sizes.clear()
                    self._outstanding_chars = 0
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

            # Some controllers prepend control chars; normalize first so ack parsing does not miss "ok".
            normalized = re.sub(r"[\x00-\x1f\x7f]", "", message).strip()
            if not normalized:
                continue

            lowered = normalized.lower()
            with self._state_lock:
                self._last_messages.append(normalized)
                self._last_rx_time = time.monotonic()
                if self._busy_re.search(lowered):
                    self._last_busy_time = self._last_rx_time

                if "resend" in lowered or lowered.startswith("rs "):
                    self._errors += 1
                    self._job_running = False
                    self._job_paused = False
                    self._mode = MachineMode.ERROR
                    self._job_state = JobState.ERROR
                    self._last_error_message = normalized
                    continue

                if lowered.startswith("alarm"):
                    self._job_running = False
                    self._job_paused = False
                    self._mode = MachineMode.ALARM
                    self._job_state = JobState.ERROR
                    self._last_error_message = normalized

                if self._ok_re.search(lowered):
                    if self._outstanding_payload_sizes:
                        payload_size = self._outstanding_payload_sizes.popleft()
                        self._outstanding_chars = max(0, self._outstanding_chars - payload_size)
                        self._acked_lines += 1
                        self._last_ack_time = time.monotonic()
                elif lowered.startswith("error"):
                    self._errors += 1
                    self._job_running = False
                    self._job_paused = False
                    self._mode = MachineMode.ERROR
                    self._job_state = JobState.ERROR
                    self._last_error_message = normalized
                    if self._outstanding_payload_sizes:
                        payload_size = self._outstanding_payload_sizes.popleft()
                        self._outstanding_chars = max(0, self._outstanding_chars - payload_size)

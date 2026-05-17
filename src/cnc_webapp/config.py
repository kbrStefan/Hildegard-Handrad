import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-me")
    SERIAL_PORT = os.getenv("CNC_SERIAL_PORT", "/dev/ttyACM0")
    SERIAL_BAUDRATE = int(os.getenv("CNC_SERIAL_BAUDRATE", "115200"))
    SERIAL_READ_TIMEOUT = float(os.getenv("CNC_SERIAL_READ_TIMEOUT", "0.05"))
    STREAM_MAX_INFLIGHT_LINES = int(os.getenv("CNC_STREAM_MAX_INFLIGHT_LINES", "24"))
    STREAM_MAX_INFLIGHT_CHARS = int(os.getenv("CNC_STREAM_MAX_INFLIGHT_CHARS", "512"))

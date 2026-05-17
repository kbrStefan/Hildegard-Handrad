# CNC Web Control (Marlin, Linux-first)

Browser-based CNC control app in Python/Flask, built with modular architecture for future probing and macro workflows.

## Current implemented scope

- Connect/disconnect to Marlin controller via USB serial
- Controller mode and job state tracking (disconnected, idle, running, homing, jogging, alarm, error)
- Upload G-code file
- Mandatory comment stripping before execution
  - Semicolon comments (`; like this`)
  - Parenthesis comments (`(like this)`)
  - Empty/program delimiter lines (`%`)
- Stream G-code with in-flight window control to keep firmware input filled
- Basic status dashboard (sent/acked/progress/errors)
- Homing command (G28)
- Jogging controls (incremental jog with configured step and feedrate)

## Planned modules (stubbed API)

- Touch probing (corners, bores, etc.)
- Macros

## API overview

- `POST /api/serial/connect` connect to controller (`port`, `baudrate` optional)
- `POST /api/serial/disconnect` disconnect controller
- `POST /api/gcode/upload` upload and parse G-code file (`multipart/form-data` with `file`)
- `POST /api/job/start` start streaming loaded job
- `POST /api/job/stop` stop active streaming job
- `POST /api/home` execute homing (`axes` optional, example `{"axes": ["X", "Y"]}`)
- `POST /api/jog` execute jog (`axis`, `distance`, `feedrate`)
- `GET /api/status` current machine + job status

## Project layout

- `run.py` app entrypoint
- `src/cnc_webapp/__init__.py` Flask app factory
- `src/cnc_webapp/blueprints/api.py` active API endpoints
- `src/cnc_webapp/blueprints/stubs.py` future endpoint stubs
- `src/cnc_webapp/services/gcode_parser.py` comment stripping and parsing
- `src/cnc_webapp/services/serial_streamer.py` gapless serial streaming engine
- `src/cnc_webapp/services/cnc_controller.py` orchestration facade
- `src/cnc_webapp/templates/index.html` web UI
- `src/cnc_webapp/static/` styles and JS

## Run

1. Create venv and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Start server:

   ```bash
   python run.py
   ```

3. Open in browser:

   - `http://127.0.0.1:5000`

## Configuration (optional)

Environment variables:

- `CNC_SERIAL_PORT` (default `/dev/ttyACM0`)
- `CNC_SERIAL_BAUDRATE` (default `115200`)
- `CNC_SERIAL_READ_TIMEOUT` (default `0.05`)
- `CNC_STREAM_MAX_INFLIGHT_LINES` (default `24`)
- `CNC_STREAM_MAX_INFLIGHT_CHARS` (default `512`)

## Notes

- Start with conservative feed rates and dry runs.
- For production safety, add E-stop integration, hard/soft limits checks, and state machine guards before machine use.

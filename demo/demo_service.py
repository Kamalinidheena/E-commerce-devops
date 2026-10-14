"""
IncidentPulse Controlled Local Demo Service
A standalone, authentic HTTP service designed for testing monitoring checks,
alert triggers, notifications, and recovery workflows.

Run independently:
    python demo/demo_service.py
"""
import time
import os
from flask import Flask, jsonify, request

app = Flask(__name__)
START_TIME = time.time()

# Runtime simulation state: 'normal', 'slow', 'error'
SIMULATION_MODE = "normal"
SIMULATED_LATENCY_SECONDS = 1.5

@app.route("/")
@app.route("/health")
def health():
    """
    Primary health check endpoint.
    Behavior reflects real service state:
    - Normal: HTTP 200, fast response (<10ms)
    - Slow: sleeps 1.5s then HTTP 200 (triggers latency threshold)
    - Error: HTTP 500 Server Error
    """
    global SIMULATION_MODE
    uptime = round(time.time() - START_TIME, 1)

    if SIMULATION_MODE == "slow":
        time.sleep(SIMULATED_LATENCY_SECONDS)
        return jsonify({
            "status": "degraded",
            "mode": "slow",
            "service": "Demo Inventory Service",
            "version": "1.2.0",
            "uptime_seconds": uptime,
            "latency_injected_ms": int(SIMULATED_LATENCY_SECONDS * 1000)
        }), 200

    if SIMULATION_MODE == "error":
        return jsonify({
            "status": "error",
            "mode": "error",
            "service": "Demo Inventory Service",
            "error": "Internal Database Connection Timeout",
            "uptime_seconds": uptime
        }), 500

    return jsonify({
        "status": "healthy",
        "mode": "normal",
        "service": "Demo Inventory Service",
        "version": "1.2.0",
        "uptime_seconds": uptime,
        "message": "All database and cache systems operational."
    }), 200

@app.route("/api/workflow")
def workflow_endpoint():
    """Sample workflow API for testing workflow health assertions."""
    if SIMULATION_MODE == "error":
        return jsonify({"order_processing": "failed", "queue_depth": 999}), 500
    return jsonify({
        "order_processing": "operational",
        "queue_depth": 0,
        "healthy": True
    }), 200

@app.route("/control/status")
def control_status():
    """Inspect current runtime simulation mode."""
    return jsonify({
        "mode": SIMULATION_MODE,
        "uptime_seconds": round(time.time() - START_TIME, 1)
    })

@app.route("/control/set_mode", methods=["GET", "POST"])
def set_mode():
    """
    Dynamically switches demo behavior for interactive testing:
    ?mode=normal | slow | error
    """
    global SIMULATION_MODE
    mode = request.args.get("mode") or (request.json and request.json.get("mode"))
    if mode in ("normal", "slow", "error"):
        SIMULATION_MODE = mode
        return jsonify({"success": True, "mode": SIMULATION_MODE}), 200
    return jsonify({"error": "Invalid mode. Choose 'normal', 'slow', or 'error'."}), 400

if __name__ == "__main__":
    port = int(os.environ.get("DEMO_PORT", 5050))
    print("=" * 60)
    print(f"INCIDENTPULSE DEMO SERVICE STARTED")
    print(f"Listening on: http://127.0.0.1:{port}/health")
    print("Available endpoints:")
    print(f"  Health Check:   http://127.0.0.1:{port}/health")
    print(f"  Workflow API:   http://127.0.0.1:{port}/api/workflow")
    print(f"  Switch Mode:    http://127.0.0.1:{port}/control/set_mode?mode=normal|slow|error")
    print("To simulate complete outage, press Ctrl+C to terminate this process.")
    print("=" * 60)
    app.run(host="127.0.0.1", port=port, debug=False)

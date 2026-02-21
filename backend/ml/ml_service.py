"""
ml_service.py — Python ML Microservice (Flask)
================================================

Lightweight HTTP service that exposes the ML pipeline to the Node.js
backend. The Node.js server calls this service whenever new telemetry
arrives from the LoRa gateway via Firebase RTDB.

Endpoints:
    POST /process    — Process a telemetry record through the ML pipeline
    POST /train      — Trigger model retraining from Firebase history
    GET  /health     — Service health check
    GET  /status     — ML pipeline status (model loaded, window state)

Run:
    python ml_service.py
    # Starts on port 5050 by default (configurable via ML_SERVICE_PORT env var)
"""

import os
import sys
import json
import logging

from flask import Flask, request, jsonify

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.ml.pipeline import process_incoming_telemetry
from backend.ml.utils import setup_logging, ensure_saved_dir

setup_logging()
ensure_saved_dir()

logger = logging.getLogger("ml.service")
app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "OK",
        "service": "HydroNet ML Pipeline",
    })


@app.route("/process", methods=["POST"])
def process():
    """
    Process incoming telemetry through the ML pipeline.

    Expects JSON body with telemetry data (Firebase format):
        { flow1_Lmin, flow2_Lmin, tankLevelPercent, tdsPpm, timestamp }

    Returns:
        Decision dict or buffering status.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    result = process_incoming_telemetry(data)

    if result is None:
        return jsonify({
            "status": "buffering",
            "message": "Window not ready yet, still collecting data",
        })

    return jsonify({
        "status": "processed",
        "decision": result,
    })


@app.route("/train", methods=["POST"])
def train():
    """Trigger model retraining from Firebase historical data."""
    try:
        from backend.ml.train import train_model_from_database
        success = train_model_from_database()
        if success:
            return jsonify({"status": "success", "message": "Model trained"})
        else:
            return jsonify({"status": "failed", "message": "Training failed"}), 500
    except Exception as e:
        logger.error(f"Training error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("ML_SERVICE_PORT", 5050))
    logger.info(f"Starting ML service on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

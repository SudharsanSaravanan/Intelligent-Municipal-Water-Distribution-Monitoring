"""
pipeline.py — MQTT-to-ML Pipeline Connector
=============================================

Bridges the incoming telemetry (from LoRa Gateway -> MQTT -> Firebase RTDB)
to the ML Inference Engine. When an anomaly is confirmed, publishes a
control command back via MQTT to the LoRa gateway for valve actuation.

Flow:
    MQTT telemetry arrives -> process_incoming_telemetry() called
    -> InferenceEngine processes -> if ANOMALY_CONFIRMED:
       -> publish MQTT: water/control/valve { action: THROTTLE, severity: score }

This module is designed to be called from the Node.js backend via
a Python subprocess/service bridge, or directly if running as a
standalone Python MQTT listener.
"""

import json
import logging
from datetime import datetime

from . import config
from .inference import InferenceEngine
from .control_logic import ANOMALY_CONFIRMED, WARNING

logger = logging.getLogger("ml.pipeline")

# Singleton inference engine (initialized on first call)
_engine = None
_mqtt_client = None


def _get_engine() -> InferenceEngine:
    """Get or create the singleton InferenceEngine."""
    global _engine
    if _engine is None:
        _engine = InferenceEngine()
        _engine.load()
    return _engine


def _get_mqtt_client():
    """
    Get or create MQTT client for publishing control commands.
    Returns None if paho-mqtt is not available (graceful degradation).
    """
    global _mqtt_client
    if _mqtt_client is not None:
        return _mqtt_client

    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(client_id="hydronet-ml-pipeline")
        client.connect(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, 60)
        client.loop_start()
        _mqtt_client = client
        logger.info(
            f"MQTT client connected to {config.MQTT_BROKER_HOST}:"
            f"{config.MQTT_BROKER_PORT}"
        )
        return client
    except ImportError:
        logger.warning("paho-mqtt not installed — control commands disabled")
        return None
    except Exception as e:
        logger.error(f"MQTT connection failed: {e}")
        return None


def _normalize_telemetry(data: dict) -> dict:
    """
    Normalize incoming telemetry to the format expected by the engine.

    Firebase data uses keys like flow1_Lmin, tankLevelPercent, tdsPpm.
    The ML pipeline expects: flow, tank_level, tds, timestamp.

    Args:
        data: Raw telemetry dict from Firebase/MQTT.

    Returns:
        Normalized dict with standard keys.
    """
    flow1 = float(data.get("flow1_Lmin", 0) or 0)
    flow2 = float(data.get("flow2_Lmin", 0) or 0)
    flow = (flow1 + flow2) / 2.0 if (flow1 + flow2) > 0 else flow1

    return {
        "flow": flow,
        "tank_level": float(data.get("tankLevelPercent", 0) or 0),
        "tds": float(data.get("tdsPpm", 0) or 0),
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
    }


def _publish_control_command(score: float, state: str) -> None:
    """
    Publish a valve control command via MQTT to the LoRa gateway.

    Args:
        score: EMA-smoothed anomaly score (0-1).
        state: Control state (ANOMALY_CONFIRMED).
    """
    client = _get_mqtt_client()
    if client is None:
        logger.warning("Cannot publish control command — no MQTT client")
        return

    payload = {
        "action": "THROTTLE",
        "severity": round(score, 4),
        "state": state,
        "timestamp": datetime.utcnow().isoformat(),
        "source": "ml-pipeline",
    }

    try:
        result = client.publish(
            config.MQTT_CONTROL_TOPIC,
            json.dumps(payload),
            qos=1,
        )
        logger.warning(
            f"VALVE CONTROL published: topic={config.MQTT_CONTROL_TOPIC} "
            f"payload={json.dumps(payload)}"
        )
    except Exception as e:
        logger.error(f"Failed to publish control command: {e}")


def process_incoming_telemetry(data: dict) -> dict | None:
    """
    Main entry point: process incoming telemetry through the ML pipeline.

    Called from the Node.js backend (via bridge) whenever new MQTT/Firebase
    telemetry arrives from the LoRa gateway.

    Args:
        data: Raw telemetry dict (Firebase format).

    Returns:
        Decision dict with state and scores, or None if still buffering.
    """
    try:
        engine = _get_engine()

        # Normalize field names
        record = _normalize_telemetry(data)
        logger.debug(f"Processing telemetry: {record}")

        # Run through inference engine
        result = engine.process(record)

        if result is None:
            # Still buffering, window not ready yet
            return None

        # Log window processing
        logger.info(
            f"Window processed: state={result['state']} "
            f"raw={result['raw_score']} ema={result['ema_score']}"
        )

        # If anomaly confirmed, publish control command
        if result["state"] == ANOMALY_CONFIRMED:
            logger.warning("ANOMALY CONFIRMED — publishing valve control")
            _publish_control_command(result["ema_score"], result["state"])

        return result

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        return None

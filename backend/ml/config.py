"""
config.py — ML Pipeline Configuration Constants
================================================

Centralizes all hyperparameters, thresholds, and file paths used by the
anomaly detection pipeline. Tuning these values adjusts how sensitive the
system is to anomalies and how quickly it reacts.

This water monitoring system uses Amrita University campus data:
- Flow sensors (L/min)
- Ultrasonic tank level sensors (cm / %)
- TDS water quality sensors (ppm)
- Telemetry arrives every ~5 seconds via LoRa → MQTT → Firebase RTDB
"""

import os

# ═══════════════════════════════════════════════════════════════════
# SLIDING WINDOW CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

# Duration (in seconds) of each sliding window for feature aggregation.
# 300 s = 5 minutes — long enough to capture meaningful trends in water
# flow / level while still being responsive to abrupt anomalies.
WINDOW_SIZE_SECONDS = 300

# ═══════════════════════════════════════════════════════════════════
# EXPONENTIAL MOVING AVERAGE (EMA) CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

# Smoothing factor (0 < alpha <= 1).
#   Higher alpha → more weight on recent scores → faster reaction.
#   Lower  alpha → smoother curve → fewer false positives.
# 0.3 gives a good balance between responsiveness and stability
# for a campus water distribution system sampled every 5 s.
EMA_ALPHA = 0.3

# ═══════════════════════════════════════════════════════════════════
# ANOMALY DETECTION THRESHOLDS
# ═══════════════════════════════════════════════════════════════════

# Normalized anomaly score above which a window is considered anomalous.
# Isolation Forest decision_function outputs are rescaled to [0, 1]:
#   0.0 = definitely normal
#   1.0 = definitely anomalous
# 0.6 is a moderate threshold — it catches genuine anomalies (pipe bursts,
# unusual night-time usage, TDS spikes) while tolerating normal variance
# in campus water usage patterns.
ANOMALY_THRESHOLD = 0.6

# Number of consecutive anomalous windows required before the system
# confirms the anomaly and triggers a control action (valve throttle).
# With 5-minute windows, 3 consecutive windows = 15 minutes of sustained
# anomaly before actuation — prevents false positives from brief spikes.
SUSTAINED_WINDOW_COUNT = 3

# ═══════════════════════════════════════════════════════════════════
# ISOLATION FOREST HYPERPARAMETERS
# ═══════════════════════════════════════════════════════════════════

# Expected proportion of anomalies in the training data.
# 0.05 = 5%, meaning we expect roughly 5% of historical water usage
# patterns to be abnormal (pipe leaks, sensor faults, night-time watering).
CONTAMINATION = 0.05

# Number of base estimators (isolation trees) in the forest.
# 100 is the sklearn default and works well for moderate-dimensional
# feature vectors (we use ~10 features).
N_ESTIMATORS = 100

# Random seed for reproducibility across training runs.
RANDOM_STATE = 42

# ═══════════════════════════════════════════════════════════════════
# MODEL / SCALER PERSISTENCE PATHS
# ═══════════════════════════════════════════════════════════════════

# Base directory for the ML module (resolves relative to this file)
_ML_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory where trained model and scaler artifacts are saved
SAVED_DIR = os.path.join(_ML_DIR, "saved")

# Path to the serialized Isolation Forest model (joblib format)
MODEL_PATH = os.path.join(SAVED_DIR, "saved_model.pkl")

# Path to the serialized StandardScaler (joblib format)
SCALER_PATH = os.path.join(SAVED_DIR, "saved_scaler.pkl")

# ═══════════════════════════════════════════════════════════════════
# FIREBASE / DATA SOURCE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

# Firebase RTDB paths used by the training script to fetch historical data
FIREBASE_HISTORY_MASTER_PATH = "/waterSystem/history/master"
FIREBASE_HISTORY_SLAVE_PATH = "/waterSystem/history/slave"

# ═══════════════════════════════════════════════════════════════════
# MQTT CONTROL TOPICS (for valve actuation via LoRa gateway)
# ═══════════════════════════════════════════════════════════════════

# Topic on which control commands are published when anomaly is confirmed.
# The LoRa gateway subscribes to this and relays to ESP32 actuator nodes.
MQTT_CONTROL_TOPIC = "water/control/valve"

# MQTT broker connection settings (override via environment variables)
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════

# Log level for the ML pipeline (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL = os.environ.get("ML_LOG_LEVEL", "INFO")

# Feature names used by the model (must match feature_engineering output)
FEATURE_NAMES = [
    "flow_mean",
    "flow_std",
    "flow_rate_change",
    "tank_level_gradient",
    "tank_level_drop_rate",
    "tds_mean",
    "tds_variation",
    "hour_of_day",
    "day_of_week",
]

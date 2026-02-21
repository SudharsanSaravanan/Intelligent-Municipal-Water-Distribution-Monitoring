"""
backend.ml — Machine Learning Pipeline for HydroNet Water Monitoring
=====================================================================

This package implements the complete ML-based anomaly detection pipeline
for the Intelligent Amrita University Water Usage and Distribution Monitor.

Architecture:
    ESP32 Sensors → LoRa → LoRa Gateway → MQTT → Cloud Backend (Node.js)
                                                       ↓
                                                  Python ML Service
                                                       ↓
                                              Anomaly Detection Pipeline:
                                                1. Data Preprocessing
                                                2. Feature Engineering
                                                3. Sliding Window Aggregation
                                                4. Isolation Forest Inference
                                                5. EMA Smoothing
                                                6. Sustained Anomaly Logic
                                                       ↓
                                              Control Decision (NORMAL / WARNING / ANOMALY_CONFIRMED)
                                                       ↓
                                              MQTT → LoRa Gateway → ESP32 Valve Control

Modules:
    config              — Hyperparameters and system constants
    preprocessing       — Data cleaning, outlier removal, normalization
    feature_engineering — Domain-specific feature extraction
    windowing           — Time-based sliding window processor
    model               — Isolation Forest model wrapper
    train               — Model training from historical data
    inference           — Real-time inference engine
    ema                 — Exponential Moving Average smoother
    control_logic       — Sustained anomaly detection state machine
    pipeline            — End-to-end MQTT-to-decision pipeline
    utils               — Shared utility functions and logging helpers
"""

__version__ = "1.0.0"
__author__ = "Water Monitoring IoT Team"

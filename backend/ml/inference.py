"""
inference.py — Real-Time Inference Engine
==========================================

Accepts new telemetry records, buffers them in a sliding window,
and when the window is ready runs the full pipeline:
    window -> feature extraction -> scaling -> anomaly score -> EMA -> control logic

Returns a decision dict with state and score.
"""

import logging
import numpy as np

from . import config
from .preprocessing import DataPreprocessor
from .feature_engineering import extract_features, features_to_array
from .windowing import SlidingWindowProcessor
from .model import IsolationForestModel
from .ema import EMASmoother
from .control_logic import ControlLogic, NORMAL, WARNING, ANOMALY_CONFIRMED

logger = logging.getLogger("ml.inference")


class InferenceEngine:
    """
    End-to-end real-time inference engine for water anomaly detection.

    Orchestrates: windowing -> features -> scaling -> IF score -> EMA -> control.

    Usage:
        engine = InferenceEngine()
        engine.load()
        result = engine.process(telemetry_record)
    """

    def __init__(self):
        self.model = IsolationForestModel()
        self.preprocessor = DataPreprocessor()
        self.window = SlidingWindowProcessor()
        self.ema = EMASmoother()
        self.control = ControlLogic()
        self._loaded = False

    def load(self) -> bool:
        """
        Load trained model and scaler from disk.

        Returns:
            True if loaded successfully, False otherwise.
        """
        try:
            self.model.load_model()
            self.preprocessor.load_scaler()
            self._loaded = True
            logger.info("Inference engine loaded (model + scaler)")
            return True
        except Exception as e:
            logger.error(f"Failed to load model/scaler: {e}")
            self._loaded = False
            return False

    def process(self, record: dict) -> dict | None:
        """
        Process a single telemetry record through the ML pipeline.

        Args:
            record: Dict with keys: flow, tank_level, tds, timestamp.

        Returns:
            Decision dict if window processed, None if still buffering.
            Decision dict keys:
                state: NORMAL | WARNING | ANOMALY_CONFIRMED
                raw_score: Raw IF anomaly score (0-1)
                ema_score: EMA-smoothed score (0-1)
                window_size: Number of records in the window
                features: Extracted feature dict
        """
        if not self._loaded:
            logger.warning("Engine not loaded, attempting to load...")
            if not self.load():
                return None

        # Add record to sliding window
        self.window.add_record(record)

        # Check if window is ready
        if not self.window.is_window_ready():
            return None

        # Get window and extract features
        window_records = self.window.get_window()
        if not window_records:
            return None

        logger.info(f"Processing window of {len(window_records)} records")

        features = extract_features(window_records)
        if features is None:
            logger.warning("Feature extraction failed")
            return None

        # Scale and predict
        X = features_to_array(features).reshape(1, -1)
        X_scaled = self.preprocessor.transform(X)
        raw_score = float(self.model.anomaly_score(X_scaled)[0])

        # Smooth with EMA
        ema_score = self.ema.update(raw_score)

        # Control logic
        state = self.control.update(ema_score)

        result = {
            "state": state,
            "raw_score": round(raw_score, 4),
            "ema_score": round(ema_score, 4),
            "window_size": len(window_records),
            "features": features,
        }

        log_msg = (f"Inference: raw={raw_score:.4f} ema={ema_score:.4f} "
                   f"state={state}")
        if state == ANOMALY_CONFIRMED:
            logger.warning(log_msg)
        elif state == WARNING:
            logger.info(log_msg)
        else:
            logger.debug(log_msg)

        return result

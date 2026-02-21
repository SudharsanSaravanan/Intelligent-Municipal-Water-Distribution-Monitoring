"""
model.py — Isolation Forest Model Wrapper
==========================================

Wraps scikit-learn's IsolationForest to provide:
- Consistent initialization from config
- Training and prediction interfaces
- Normalized anomaly scores (0 = normal, 1 = anomalous)
- Model persistence (save / load via joblib)

Why Isolation Forest?
    - It is an unsupervised algorithm — we don't need labelled anomaly data,
      which is hard to obtain for water distribution systems.
    - It excels at high-dimensional anomaly detection with moderate data sizes.
    - It is computationally efficient (O(n·log(n)) training).
    - It handles the mixed feature types we produce (continuous sensor stats
      + cyclical time features) without special preprocessing.
    - It is robust to the imbalanced nature of anomaly detection (few anomalies
      vs. many normal observations).
"""

import logging
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib

from . import config

logger = logging.getLogger("ml.model")


class IsolationForestModel:
    """
    Production wrapper for the Isolation Forest anomaly detector.

    Provides training, inference, score normalization, and model
    persistence for the HydroNet water monitoring system.

    The model learns what "normal" water usage patterns look like
    from historical telemetry and flags deviations (pipe bursts,
    unusual night-time usage, TDS contamination, sensor faults).

    Attributes:
        model (IsolationForest): Underlying sklearn model.
        is_trained (bool): Whether the model has been fitted.
    """

    def __init__(self):
        """
        Initialize the Isolation Forest with hyperparameters from config.

        Parameters:
            n_estimators:  Number of isolation trees (100).
            contamination: Expected anomaly fraction (0.05 = 5%).
            random_state:  Seed for reproducibility (42).
        """
        self.model = IsolationForest(
            n_estimators=config.N_ESTIMATORS,
            contamination=config.CONTAMINATION,
            random_state=config.RANDOM_STATE,
            # warm_start=False ensures a fresh forest each time
            warm_start=False,
        )
        self.is_trained = False

    def train(self, X: np.ndarray) -> "IsolationForestModel":
        """
        Train (fit) the Isolation Forest on preprocessed feature data.

        Args:
            X: 2-D array of shape (n_samples, n_features).
               Each row is a feature vector from one sliding window.

        Returns:
            self (for method chaining).
        """
        logger.info(f"Training Isolation Forest on {X.shape[0]} samples, "
                    f"{X.shape[1]} features …")
        self.model.fit(X)
        self.is_trained = True
        logger.info("Training complete.")
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict anomaly labels for new data.

        Args:
            X: 2-D array of shape (n_samples, n_features).

        Returns:
            Array of labels: +1 = normal, -1 = anomaly.

        Raises:
            RuntimeError: If the model has not been trained or loaded.
        """
        self._check_trained()
        return self.model.predict(X)

    def anomaly_score(self, X: np.ndarray) -> np.ndarray:
        """
        Compute normalized anomaly scores in the range [0, 1].

        Sklearn's decision_function returns negative scores for anomalies
        and positive scores for normal points.  This method rescales:
            raw_score → normalized_score ∈ [0, 1]
        where:
            0.0 = definitely normal
            1.0 = definitely anomalous

        The normalization uses:
            normalized = 1 − sigmoid(raw_score)
        which provides a smooth, bounded mapping.

        Args:
            X: 2-D array of shape (n_samples, n_features).

        Returns:
            1-D array of anomaly scores in [0, 1].
        """
        self._check_trained()
        raw_scores = self.model.decision_function(X)

        # Sigmoid normalization: more anomalous (more negative raw) → higher score
        # The decision_function returns lower (more negative) values for anomalies
        normalized = 1.0 / (1.0 + np.exp(raw_scores))

        return np.clip(normalized, 0.0, 1.0)

    def _check_trained(self) -> None:
        """Raise if the model hasn't been trained / loaded."""
        if not self.is_trained:
            raise RuntimeError(
                "Model has not been trained yet. "
                "Call train() or load_model() first."
            )

    # ── Persistence ───────────────────────────────────────────────

    def save_model(self, path: str = None) -> None:
        """
        Serialize the trained model to disk using joblib.

        Args:
            path: Output file path.  Defaults to config.MODEL_PATH.
        """
        self._check_trained()
        path = path or config.MODEL_PATH
        joblib.dump(self.model, path)
        logger.info(f"Model saved to {path}")

    def load_model(self, path: str = None) -> None:
        """
        Load a trained model from disk.

        Args:
            path: Input file path.  Defaults to config.MODEL_PATH.
        """
        path = path or config.MODEL_PATH
        self.model = joblib.load(path)
        self.is_trained = True
        logger.info(f"Model loaded from {path}")

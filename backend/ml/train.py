"""
train.py — Model Training from Historical Firebase Data
=========================================================

Fetches historical telemetry from Firebase Realtime Database, applies
the full preprocessing → feature engineering → normalization pipeline,
trains the Isolation Forest model, and saves the trained artifacts.

This script can be run standalone:
    python -m backend.ml.train

Or called programmatically:
    from backend.ml.train import train_model_from_database
    train_model_from_database()

Training flow:
    1. Connect to Firebase RTDB (uses existing credentials from backend/)
    2. Fetch history/master and history/slave telemetry records
    3. Merge and convert to unified record format
    4. Create sliding windows from historical data
    5. Extract features from each window
    6. Remove missing values and IQR outliers
    7. Fit StandardScaler and normalize features
    8. Train Isolation Forest
    9. Save model + scaler to backend/ml/saved/
"""

import os
import sys
import logging
import numpy as np
import pandas as pd

# Ensure the project root is on the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.ml import config
from backend.ml.preprocessing import DataPreprocessor
from backend.ml.feature_engineering import extract_features, features_to_array
from backend.ml.model import IsolationForestModel
from backend.ml.utils import setup_logging, ensure_saved_dir

logger = logging.getLogger("ml.train")


def _fetch_firebase_history() -> list[dict]:
    """
    Fetch historical telemetry records from Firebase RTDB.

    Retrieves both master and slave tank history, merges them,
    and converts to the unified record format expected by the
    feature engineering module.

    Returns:
        List of dicts with keys: flow, tank_level, tds, timestamp.
    """
    try:
        # Import Firebase admin from the existing backend config
        import firebase_admin
        from firebase_admin import credentials, db as firebase_db

        # Check if already initialized by the Node.js side or prior call
        if not firebase_admin._apps:
            # Look for service account key in the backend directory
            key_path = os.path.join(
                os.path.dirname(__file__), "..", "serviceAccountKey.json"
            )
            if not os.path.exists(key_path):
                logger.error(f"Firebase service account key not found at {key_path}")
                return []

            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred, {
                "databaseURL": os.environ.get(
                    "FIREBASE_DATABASE_URL",
                    "https://hydronet-monitor-default-rtdb.firebaseio.com"
                )
            })

        records = []

        # Fetch master history
        logger.info("Fetching master tank history from Firebase …")
        master_ref = firebase_db.reference(config.FIREBASE_HISTORY_MASTER_PATH)
        master_data = master_ref.get() or {}

        for key, entry in master_data.items():
            records.append({
                "flow": 0.0,  # Master node doesn't have flow sensors
                "tank_level": entry.get("tankLevelPercent", 0),
                "tds": entry.get("tdsPpm", 0),
                "timestamp": entry.get("timestamp", ""),
                "node": "master",
            })

        # Fetch slave history
        logger.info("Fetching slave tank history from Firebase …")
        slave_ref = firebase_db.reference(config.FIREBASE_HISTORY_SLAVE_PATH)
        slave_data = slave_ref.get() or {}

        for key, entry in slave_data.items():
            # Slave node has flow sensors (flow1, flow2)
            flow1 = entry.get("flow1_Lmin", 0) or 0
            flow2 = entry.get("flow2_Lmin", 0) or 0
            avg_flow = (float(flow1) + float(flow2)) / 2.0

            records.append({
                "flow": avg_flow,
                "tank_level": entry.get("tankLevelPercent", 0),
                "tds": entry.get("tdsPpm", 0),
                "timestamp": entry.get("timestamp", ""),
                "node": "slave",
            })

        logger.info(f"Fetched {len(records)} total historical records "
                    f"({len(master_data)} master + {len(slave_data)} slave)")
        return records

    except Exception as e:
        logger.error(f"Failed to fetch Firebase history: {e}")
        return []


def _create_training_windows(records: list[dict],
                              window_seconds: int = None) -> list[list[dict]]:
    """
    Split historical records into non-overlapping time windows.

    For training, we use non-overlapping windows (rather than sliding)
    to avoid data leakage between windows.

    Args:
        records: List of record dicts with 'timestamp' key.
        window_seconds: Duration per window.  Defaults to config.WINDOW_SIZE_SECONDS.

    Returns:
        List of windows, each containing a list of record dicts.
    """
    window_seconds = window_seconds or config.WINDOW_SIZE_SECONDS

    # Sort by timestamp
    df = pd.DataFrame(records)
    df["_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["_ts"]).sort_values("_ts").reset_index(drop=True)

    if df.empty:
        return []

    windows = []
    start_time = df["_ts"].iloc[0]
    end_time = df["_ts"].iloc[-1]
    window_start = start_time

    while window_start < end_time:
        window_end = window_start + pd.Timedelta(seconds=window_seconds)
        mask = (df["_ts"] >= window_start) & (df["_ts"] < window_end)
        window_records = df[mask].drop(columns=["_ts"]).to_dict("records")

        if len(window_records) >= 2:  # Need at least 2 records for features
            windows.append(window_records)

        window_start = window_end

    logger.info(f"Created {len(windows)} training windows "
                f"({window_seconds}s each)")
    return windows


def train_model_from_database() -> bool:
    """
    Complete training pipeline: fetch data → features → preprocess → train → save.

    Steps:
        1. Fetch historical telemetry from Firebase RTDB.
        2. Split into non-overlapping time windows.
        3. Extract features from each window.
        4. Remove missing values and IQR outliers.
        5. Fit StandardScaler and normalize features.
        6. Train Isolation Forest model.
        7. Save model + scaler to disk.

    Returns:
        True if training succeeded, False otherwise.
    """
    setup_logging()
    ensure_saved_dir()

    logger.info("=" * 60)
    logger.info("STARTING MODEL TRAINING PIPELINE")
    logger.info("=" * 60)

    # ── Step 1: Fetch historical data ─────────────────────────────
    records = _fetch_firebase_history()
    if not records:
        logger.error("No historical data available. Cannot train model.")
        return False

    # ── Step 2: Create training windows ──────────────────────────
    windows = _create_training_windows(records)
    if not windows:
        logger.error("No valid training windows created. Need more data.")
        return False

    # ── Step 3: Extract features from each window ────────────────
    logger.info("Extracting features from training windows …")
    feature_dicts = []
    for i, window in enumerate(windows):
        feat = extract_features(window)
        if feat is not None:
            feature_dicts.append(feat)
        else:
            logger.warning(f"Window {i} produced no features — skipped")

    if len(feature_dicts) < 10:
        logger.error(f"Only {len(feature_dicts)} valid feature vectors. "
                     "Need at least 10 for meaningful training.")
        return False

    logger.info(f"Extracted features from {len(feature_dicts)} windows")

    # Convert to numpy array
    X = np.array([features_to_array(fd) for fd in feature_dicts])

    # ── Step 4 & 5: Preprocess (outlier removal + normalization) ─
    preprocessor = DataPreprocessor()

    # Convert to DataFrame for IQR filtering
    feature_df = pd.DataFrame(X, columns=config.FEATURE_NAMES)
    feature_df = preprocessor.remove_missing(feature_df)
    feature_df = preprocessor.remove_outliers(feature_df)

    X_clean = feature_df.values
    if X_clean.shape[0] < 10:
        logger.error(f"Only {X_clean.shape[0]} samples after preprocessing. "
                     "Need at least 10.")
        return False

    # Fit scaler and normalize
    X_scaled = preprocessor.fit_transform(X_clean)

    # ── Step 6: Train Isolation Forest ───────────────────────────
    model = IsolationForestModel()
    model.train(X_scaled)

    # Log training statistics
    scores = model.anomaly_score(X_scaled)
    labels = model.predict(X_scaled)
    n_anomalies = int((labels == -1).sum())
    logger.info(f"Training stats: {n_anomalies}/{len(labels)} samples "
                f"flagged as anomalies ({n_anomalies / len(labels) * 100:.1f}%)")
    logger.info(f"Anomaly score range: [{scores.min():.3f}, {scores.max():.3f}]")
    logger.info(f"Anomaly score mean:  {scores.mean():.3f}")

    # ── Step 7: Save artifacts ───────────────────────────────────
    model.save_model()
    preprocessor.save_scaler()

    logger.info("=" * 60)
    logger.info("MODEL TRAINING COMPLETE")
    logger.info(f"  Model saved to:  {config.MODEL_PATH}")
    logger.info(f"  Scaler saved to: {config.SCALER_PATH}")
    logger.info("=" * 60)

    return True


# ── CLI entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    success = train_model_from_database()
    sys.exit(0 if success else 1)

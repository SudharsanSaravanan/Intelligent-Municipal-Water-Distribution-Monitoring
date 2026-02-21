"""
feature_engineering.py — Domain-Specific Feature Extraction
============================================================

Transforms raw sensor telemetry (flow, tank_level, tds, timestamp) into
meaningful features that the Isolation Forest can use to distinguish
normal water usage patterns from anomalies.

Input (per window of raw records):
    flow        — Water flow rate in L/min (from flow sensor on sub-tank node)
    tank_level  — Tank water level in % (from ultrasonic sensor)
    tds         — Total Dissolved Solids in ppm (water quality indicator)
    timestamp   — ISO-8601 datetime string of the reading

Output feature vector (per window):
    flow_mean            — Average flow in the window
    flow_std             — Flow variability (high std → irregular usage)
    flow_rate_change     — Difference between last and first flow reading
    tank_level_gradient  — Slope of tank level over the window
    tank_level_drop_rate — Maximum single-step tank level decrease
    tds_mean             — Average TDS in the window
    tds_variation        — Coefficient of variation of TDS
    hour_of_day          — Hour (0–23) at window midpoint
    day_of_week          — Day of week (0=Mon … 6=Sun) at window midpoint
"""

import logging
import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger("ml.feature_engineering")


def extract_features(records: list[dict]) -> dict:
    """
    Extract anomaly-detection features from a window of raw sensor records.

    This function converts raw time-series telemetry into a fixed-length
    feature vector that captures the statistical behaviour of the water
    distribution system over a sliding window.

    Args:
        records: List of dicts, each containing:
            - flow (float): Water flow rate in L/min.
            - tank_level (float): Tank level in %.
            - tds (float): TDS reading in ppm.
            - timestamp (str): ISO-8601 datetime.

    Returns:
        Dictionary with keys matching config.FEATURE_NAMES and float values.
        Returns None if insufficient data.
    """
    if not records or len(records) < 2:
        logger.warning("Insufficient records for feature extraction "
                       f"(got {len(records) if records else 0}, need ≥2)")
        return None

    df = pd.DataFrame(records)

    # Parse timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    if len(df) < 2:
        return None

    # ── Ensure numeric sensor columns ────────────────────────────
    for col in ["flow", "tank_level", "tds"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            # If column missing, fill with 0 (graceful degradation)
            df[col] = 0.0
            logger.warning(f"Column '{col}' missing from telemetry — defaulting to 0")

    df = df.dropna(subset=["flow", "tank_level", "tds"])

    if len(df) < 2:
        return None

    # ─────────────────────────────────────────────────────────────
    # FEATURE: flow_mean
    # Average water flow rate in this window.
    # Anomalies: unusually high flow may indicate a pipe burst;
    # zero flow when tank is draining indicates a sensor fault.
    # ─────────────────────────────────────────────────────────────
    flow_mean = float(df["flow"].mean())

    # ─────────────────────────────────────────────────────────────
    # FEATURE: flow_std
    # Standard deviation of flow rate.
    # High variability suggests intermittent usage or valve flutter.
    # Normal campus usage has relatively stable flow during periods.
    # ─────────────────────────────────────────────────────────────
    flow_std = float(df["flow"].std(ddof=0))

    # ─────────────────────────────────────────────────────────────
    # FEATURE: flow_rate_change
    # Difference between the last and first flow readings.
    # Large positive = sudden demand increase (possible burst).
    # Large negative = sudden demand decrease (valve closure or outage).
    # ─────────────────────────────────────────────────────────────
    flow_rate_change = float(df["flow"].iloc[-1] - df["flow"].iloc[0])

    # ─────────────────────────────────────────────────────────────
    # FEATURE: tank_level_gradient
    # Slope of tank level over time (% per minute).
    # Steady drain = normal consumption.
    # Rapid drain without corresponding flow = possible leak.
    # ─────────────────────────────────────────────────────────────
    time_span_min = (df["timestamp"].iloc[-1] -
                     df["timestamp"].iloc[0]).total_seconds() / 60.0
    if time_span_min > 0:
        tank_level_gradient = float(
            (df["tank_level"].iloc[-1] - df["tank_level"].iloc[0]) / time_span_min
        )
    else:
        tank_level_gradient = 0.0

    # ─────────────────────────────────────────────────────────────
    # FEATURE: tank_level_drop_rate
    # Maximum single-step decrease in tank level.
    # A sudden large drop can indicate a catastrophic leak or
    # sensor malfunction.  Normal usage causes gradual drain.
    # ─────────────────────────────────────────────────────────────
    level_diffs = df["tank_level"].diff().dropna()
    tank_level_drop_rate = float(level_diffs.min()) if len(level_diffs) > 0 else 0.0

    # ─────────────────────────────────────────────────────────────
    # FEATURE: tds_mean
    # Average Total Dissolved Solids (ppm) in the window.
    # TDS above 500 ppm indicates poor water quality.
    # Sudden spikes may indicate contamination or mixing of sources.
    # ─────────────────────────────────────────────────────────────
    tds_mean = float(df["tds"].mean())

    # ─────────────────────────────────────────────────────────────
    # FEATURE: tds_variation
    # Coefficient of variation (std / mean) of TDS readings.
    # High variation suggests unstable water quality, possibly due
    # to contamination mixing or sensor drift.
    # ─────────────────────────────────────────────────────────────
    tds_std = float(df["tds"].std(ddof=0))
    tds_variation = (tds_std / tds_mean) if tds_mean > 0 else 0.0

    # ─────────────────────────────────────────────────────────────
    # FEATURE: hour_of_day
    # Hour of the day (0–23) at the window midpoint.
    # Water usage follows strong diurnal patterns on campus:
    #   - Low at night (00:00–05:00)
    #   - Peak in mornings (06:00–09:00) and evenings (17:00–21:00)
    # Usage at unusual hours (e.g., 3 AM) at normal flow is suspicious.
    # ─────────────────────────────────────────────────────────────
    midpoint_ts = df["timestamp"].iloc[len(df) // 2]
    hour_of_day = float(midpoint_ts.hour)

    # ─────────────────────────────────────────────────────────────
    # FEATURE: day_of_week
    # Day of the week (0=Monday … 6=Sunday).
    # Campus water usage differs between weekdays and weekends.
    # Weekend usage is lower; weekday anomalies have different norms.
    # ─────────────────────────────────────────────────────────────
    day_of_week = float(midpoint_ts.weekday())

    features = {
        "flow_mean": flow_mean,
        "flow_std": flow_std,
        "flow_rate_change": flow_rate_change,
        "tank_level_gradient": tank_level_gradient,
        "tank_level_drop_rate": tank_level_drop_rate,
        "tds_mean": tds_mean,
        "tds_variation": tds_variation,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
    }

    logger.debug(f"Extracted features: {features}")
    return features


def features_to_array(feature_dict: dict) -> np.ndarray:
    """
    Convert a feature dictionary to a numpy array in the canonical order.

    The order must match config.FEATURE_NAMES so the scaler and model
    receive features in the same order they were trained on.

    Args:
        feature_dict: Dict with keys matching config.FEATURE_NAMES.

    Returns:
        1-D numpy array of shape (n_features,).
    """
    return np.array([feature_dict[name] for name in config.FEATURE_NAMES],
                    dtype=np.float64)


def features_to_dataframe(feature_dict: dict) -> pd.DataFrame:
    """
    Convert a feature dictionary to a single-row DataFrame.

    Useful for feeding into sklearn transformers that expect DataFrames.

    Args:
        feature_dict: Dict with keys matching config.FEATURE_NAMES.

    Returns:
        DataFrame with one row and columns matching config.FEATURE_NAMES.
    """
    return pd.DataFrame([feature_dict], columns=config.FEATURE_NAMES)

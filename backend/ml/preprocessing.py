"""
preprocessing.py — Data Cleaning and Normalization
===================================================

Responsibilities in the water monitoring pipeline:
1. Remove records with missing sensor values (NaN / None).
2. Remove extreme outliers using the Interquartile Range (IQR) method.
3. Normalize features using StandardScaler (zero-mean, unit-variance).
4. Persist and reload the fitted scaler for production inference.

Why each step matters:
- **Missing values**: LoRa packet loss or sensor brownouts can produce
  incomplete telemetry records.  The Isolation Forest cannot handle NaN.
- **IQR outlier removal**: Faulty sensor readings (e.g., −999 flow or
  9999 TDS) would skew the scaler and the model.  IQR clips extremes
  while preserving genuine anomalies in the moderate range.
- **StandardScaler normalization**: Isolation Forest is distance-based;
  features on different scales (flow in L/min vs. TDS in ppm) would bias
  the split selection.  Scaling ensures all features contribute equally.
"""

import logging
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import joblib

from . import config

logger = logging.getLogger("ml.preprocessing")


class DataPreprocessor:
    """
    End-to-end data preprocessor for the HydroNet anomaly detection pipeline.

    Handles missing-value removal, IQR-based outlier filtering, and
    StandardScaler normalization.  The fitted scaler is saved/loaded from
    disk so that production inference uses the same transform as training.

    Attributes:
        scaler (StandardScaler): Fitted scaler instance.
        iqr_multiplier (float): IQR multiplier for outlier fences (default 1.5).
    """

    def __init__(self, iqr_multiplier: float = 1.5):
        """
        Initialize the preprocessor.

        Args:
            iqr_multiplier: Multiplier for the IQR fences.  1.5 is the
                standard Tukey fence; increase to be more lenient.
        """
        self.scaler = StandardScaler()
        self.iqr_multiplier = iqr_multiplier
        self._is_fitted = False

    # ── Missing-value removal ──────────────────────────────────────

    @staticmethod
    def remove_missing(df: pd.DataFrame) -> pd.DataFrame:
        """
        Drop rows that contain any NaN / None values.

        In the water monitoring context, a missing flow or TDS reading
        means the sensor did not respond during that LoRa transmission
        cycle.  These partial records are unusable for feature engineering.

        Args:
            df: Raw sensor DataFrame.

        Returns:
            DataFrame with incomplete rows removed.
        """
        before = len(df)
        df_clean = df.dropna()
        dropped = before - len(df_clean)
        if dropped > 0:
            logger.info(f"Removed {dropped} rows with missing values "
                        f"({dropped / before * 100:.1f}% of data)")
        return df_clean.reset_index(drop=True)

    # ── IQR-based outlier removal ──────────────────────────────────

    def remove_outliers(self, df: pd.DataFrame,
                        columns: list = None) -> pd.DataFrame:
        """
        Remove extreme outliers using the Interquartile Range method.

        For each specified numeric column:
            Q1     = 25th percentile
            Q3     = 75th percentile
            IQR    = Q3 − Q1
            Lower  = Q1 − multiplier × IQR
            Upper  = Q3 + multiplier × IQR
        Rows where ANY specified column is outside [Lower, Upper] are removed.

        Why IQR and not z-score?  Water sensor data is often right-skewed
        (e.g., flow spikes during peak hours).  IQR is robust to skewness.

        Args:
            df: DataFrame to filter.
            columns: Numeric columns to check.  Defaults to all numeric cols.

        Returns:
            DataFrame with extreme outliers removed.
        """
        if columns is None:
            columns = df.select_dtypes(include=[np.number]).columns.tolist()

        mask = pd.Series(True, index=df.index)
        for col in columns:
            if col not in df.columns:
                continue
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - self.iqr_multiplier * iqr
            upper = q3 + self.iqr_multiplier * iqr
            col_mask = (df[col] >= lower) & (df[col] <= upper)
            mask &= col_mask

        before = len(df)
        df_clean = df[mask].reset_index(drop=True)
        dropped = before - len(df_clean)
        if dropped > 0:
            logger.info(f"Removed {dropped} IQR outlier rows "
                        f"({dropped / before * 100:.1f}% of data)")
        return df_clean

    # ── Normalization (StandardScaler) ────────────────────────────

    def fit(self, features: np.ndarray) -> "DataPreprocessor":
        """
        Fit the StandardScaler on training feature data.

        Args:
            features: 2-D array of shape (n_samples, n_features).

        Returns:
            self (for method chaining).
        """
        self.scaler.fit(features)
        self._is_fitted = True
        logger.info(f"Scaler fitted on {features.shape[0]} samples, "
                    f"{features.shape[1]} features")
        return self

    def transform(self, features: np.ndarray) -> np.ndarray:
        """
        Transform features using the already-fitted scaler.

        Args:
            features: 2-D array of shape (n_samples, n_features).

        Returns:
            Scaled feature array (zero-mean, unit-variance).

        Raises:
            RuntimeError: If transform() is called before fit().
        """
        if not self._is_fitted:
            raise RuntimeError(
                "Scaler has not been fitted yet. Call fit() or load_scaler() first."
            )
        return self.scaler.transform(features)

    def fit_transform(self, features: np.ndarray) -> np.ndarray:
        """
        Fit the scaler and transform in a single step.

        Convenience method used during training.

        Args:
            features: 2-D array of shape (n_samples, n_features).

        Returns:
            Scaled feature array.
        """
        self.fit(features)
        return self.transform(features)

    # ── Persistence ───────────────────────────────────────────────

    def save_scaler(self, path: str = None) -> None:
        """
        Serialize the fitted scaler to disk using joblib.

        Args:
            path: File path for the pickle.  Defaults to config.SCALER_PATH.
        """
        path = path or config.SCALER_PATH
        joblib.dump(self.scaler, path)
        logger.info(f"Scaler saved to {path}")

    def load_scaler(self, path: str = None) -> None:
        """
        Load a previously fitted scaler from disk.

        Args:
            path: File path of the pickle.  Defaults to config.SCALER_PATH.
        """
        path = path or config.SCALER_PATH
        self.scaler = joblib.load(path)
        self._is_fitted = True
        logger.info(f"Scaler loaded from {path}")

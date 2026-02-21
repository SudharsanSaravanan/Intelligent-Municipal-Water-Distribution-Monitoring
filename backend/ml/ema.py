"""
ema.py — Exponential Moving Average Smoother
==============================================

Smooths raw anomaly scores to prevent erratic valve actuation
from transient score spikes.

EMA Formula: EMA_t = alpha * current + (1 - alpha) * EMA_(t-1)

Why smoothing matters:
    Raw IF scores fluctuate between windows. Without smoothing,
    a single high-score window could throttle the valve. EMA
    requires sustained anomaly before the score crosses threshold.
"""

import logging
from . import config

logger = logging.getLogger("ml.ema")


class EMASmoother:
    """
    EMA smoother for anomaly score stabilization.

    Attributes:
        alpha (float): Smoothing factor (0 < alpha <= 1).
        _current_ema (float | None): Current EMA value.
    """

    def __init__(self, alpha: float = None):
        """
        Args:
            alpha: Smoothing factor. Defaults to config.EMA_ALPHA (0.3).
        """
        self.alpha = alpha if alpha is not None else config.EMA_ALPHA
        self._current_ema = None

    def update(self, value: float) -> float:
        """
        Update EMA with a new score and return the smoothed result.

        Args:
            value: Raw anomaly score (0-1).
        Returns:
            Smoothed EMA score (0-1).
        """
        if self._current_ema is None:
            self._current_ema = value
        else:
            self._current_ema = (
                self.alpha * value + (1 - self.alpha) * self._current_ema
            )
        logger.debug(f"EMA: raw={value:.4f} -> smoothed={self._current_ema:.4f}")
        return self._current_ema

    def get_current(self):
        """Get current EMA value without updating."""
        return self._current_ema

    def reset(self):
        """Reset EMA state (e.g., after anomaly resolution)."""
        self._current_ema = None
        logger.info("EMA smoother reset")

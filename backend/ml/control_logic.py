"""
control_logic.py — Sustained Anomaly Detection State Machine
==============================================================

Implements a three-state machine that prevents false-positive
valve actuation by requiring SUSTAINED anomalous behavior:

States:
    NORMAL             — All clear, no action needed.
    WARNING            — Anomaly detected but not yet confirmed.
    ANOMALY_CONFIRMED  — Sustained anomaly, trigger valve throttle.

Transition logic:
    If EMA score > threshold for SUSTAINED_WINDOW_COUNT consecutive
    windows -> ANOMALY_CONFIRMED.
    Otherwise -> NORMAL (counter resets).

With 5-min windows and SUSTAINED_WINDOW_COUNT=3, a confirmed anomaly
requires 15 minutes of sustained abnormal behavior.
"""

import logging
from . import config

logger = logging.getLogger("ml.control_logic")

# State constants
NORMAL = "NORMAL"
WARNING = "WARNING"
ANOMALY_CONFIRMED = "ANOMALY_CONFIRMED"


class ControlLogic:
    """
    Sustained anomaly detection state machine.

    Tracks consecutive anomalous windows and transitions between
    NORMAL, WARNING, and ANOMALY_CONFIRMED states.

    Attributes:
        threshold (float): Score above which a window is anomalous.
        sustained_count (int): Required consecutive anomalous windows.
        _consecutive (int): Current streak of anomalous windows.
        _state (str): Current state.
    """

    def __init__(self, threshold: float = None, sustained_count: int = None):
        """
        Args:
            threshold: Anomaly score threshold. Defaults to config value.
            sustained_count: Required consecutive windows. Defaults to config.
        """
        self.threshold = threshold or config.ANOMALY_THRESHOLD
        self.sustained_count = sustained_count or config.SUSTAINED_WINDOW_COUNT
        self._consecutive = 0
        self._state = NORMAL

    def update(self, anomaly_score: float) -> str:
        """
        Update state based on the latest smoothed anomaly score.

        Args:
            anomaly_score: EMA-smoothed anomaly score (0-1).

        Returns:
            Current state: NORMAL, WARNING, or ANOMALY_CONFIRMED.
        """
        if anomaly_score > self.threshold:
            self._consecutive += 1
            logger.info(
                f"Anomalous window #{self._consecutive} "
                f"(score={anomaly_score:.3f}, threshold={self.threshold})"
            )

            if self._consecutive >= self.sustained_count:
                self._state = ANOMALY_CONFIRMED
                logger.warning(
                    f"ANOMALY CONFIRMED after {self._consecutive} "
                    f"consecutive windows!"
                )
            else:
                self._state = WARNING
                logger.info(
                    f"WARNING: {self._consecutive}/{self.sustained_count} "
                    f"consecutive anomalous windows"
                )
        else:
            if self._consecutive > 0:
                logger.info(
                    f"Score below threshold ({anomaly_score:.3f}), "
                    f"resetting counter from {self._consecutive}"
                )
            self._consecutive = 0
            self._state = NORMAL

        return self._state

    @property
    def state(self) -> str:
        """Current state of the control logic."""
        return self._state

    @property
    def consecutive_count(self) -> int:
        """Number of consecutive anomalous windows so far."""
        return self._consecutive

    def reset(self) -> None:
        """Reset to NORMAL state."""
        self._consecutive = 0
        self._state = NORMAL
        logger.info("Control logic reset to NORMAL")

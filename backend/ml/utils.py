"""
utils.py — Shared Utility Functions and Logging Setup
======================================================

Common helpers used across the ML pipeline modules.
"""

import os
import logging

from . import config


def setup_logging(level: str = None) -> None:
    """
    Configure structured logging for the ML pipeline.

    Sets up a console handler with timestamp, logger name, level,
    and message. All ml.* loggers inherit this configuration.

    Args:
        level: Log level string (DEBUG/INFO/WARNING/ERROR/CRITICAL).
               Defaults to config.LOG_LEVEL.
    """
    level = level or config.LOG_LEVEL
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Configure the root ml logger
    ml_logger = logging.getLogger("ml")
    ml_logger.setLevel(numeric_level)

    # Avoid duplicate handlers on repeated calls
    if not ml_logger.handlers:
        ml_logger.addHandler(handler)


def ensure_saved_dir() -> str:
    """
    Ensure the saved model directory exists.

    Creates backend/ml/saved/ if it does not already exist.

    Returns:
        Absolute path to the saved directory.
    """
    os.makedirs(config.SAVED_DIR, exist_ok=True)
    return config.SAVED_DIR


def validate_record(record: dict) -> bool:
    """
    Validate that a telemetry record has the required fields.

    Args:
        record: Telemetry record dict.

    Returns:
        True if valid (has flow, tank_level, tds), False otherwise.
    """
    required = ["flow", "tank_level", "tds"]
    for key in required:
        if key not in record:
            return False
        try:
            float(record[key])
        except (TypeError, ValueError):
            return False
    return True

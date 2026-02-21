"""
windowing.py — Time-Based Sliding Window Processor
====================================================

Collects incoming telemetry records into time-bounded windows for
batch feature extraction.  Unlike count-based windows, time-based
windows ensure consistent temporal coverage regardless of telemetry
arrival rate (which can vary due to LoRa packet loss or duty cycling).

How it works:
    1. Each incoming record is added to an internal buffer with its timestamp.
    2. Records older than WINDOW_SIZE_SECONDS are evicted.
    3. When the window spans at least WINDOW_SIZE_SECONDS (from oldest to
       newest record), is_window_ready() returns True and the full window
       can be retrieved for feature engineering.
    4. After retrieval, the buffer is cleared for the next window.

Why time-based windowing?
    - LoRa transmissions are not perfectly regular (jitter, collisions).
    - A count-based window of N records would represent different real-time
      durations depending on packet loss rate.
    - Time-based windows guarantee that features always represent the same
      physical duration (e.g., 5 minutes), making the trained model
      consistent across varying network conditions.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from . import config

logger = logging.getLogger("ml.windowing")


class SlidingWindowProcessor:
    """
    Time-based sliding window for real-time telemetry aggregation.

    Accumulates sensor records and exposes a ready window when the
    buffer spans at least config.WINDOW_SIZE_SECONDS.

    Attributes:
        window_seconds (int): Duration of each window in seconds.
        _buffer (list[dict]): Internal record buffer.
    """

    def __init__(self, window_seconds: int = None):
        """
        Initialize the sliding window processor.

        Args:
            window_seconds: Window duration in seconds.
                Defaults to config.WINDOW_SIZE_SECONDS (300 s = 5 min).
        """
        self.window_seconds = window_seconds or config.WINDOW_SIZE_SECONDS
        self._buffer: list[dict] = []

    def add_record(self, record: dict) -> None:
        """
        Add a new telemetry record to the window buffer.

        The record must contain a 'timestamp' key (ISO-8601 string or
        datetime object).  Records older than the window duration
        relative to the newest record are automatically evicted.

        In the water monitoring system, each record represents one
        LoRa telemetry packet containing flow, tank_level, and tds.

        Args:
            record: Dict with sensor data and a 'timestamp' key.
        """
        # Ensure timestamp is a datetime object
        ts = record.get("timestamp")
        if ts is None:
            ts = datetime.utcnow()
            record["timestamp"] = ts.isoformat()
        elif isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.utcnow()

        record["_ts"] = ts  # Internal parsed timestamp
        self._buffer.append(record)

        # Evict stale records outside the window
        self._evict_stale()

        logger.debug(f"Window buffer size: {len(self._buffer)} records, "
                     f"span: {self._get_span_seconds():.0f}s")

    def _evict_stale(self) -> None:
        """Remove records that fall outside the window relative to the newest."""
        if not self._buffer:
            return
        newest_ts = self._buffer[-1]["_ts"]
        cutoff = newest_ts - timedelta(seconds=self.window_seconds)
        self._buffer = [r for r in self._buffer if r["_ts"] >= cutoff]

    def _get_span_seconds(self) -> float:
        """Calculate the time span (seconds) from oldest to newest record."""
        if len(self._buffer) < 2:
            return 0.0
        oldest = self._buffer[0]["_ts"]
        newest = self._buffer[-1]["_ts"]
        return (newest - oldest).total_seconds()

    def is_window_ready(self) -> bool:
        """
        Check whether the current buffer spans at least one full window.

        Returns True when the time difference between the oldest and
        newest record in the buffer is ≥ window_seconds.

        Returns:
            True if the window is ready for feature extraction.
        """
        ready = self._get_span_seconds() >= self.window_seconds
        if ready:
            logger.info(f"Window ready: {len(self._buffer)} records, "
                        f"span {self._get_span_seconds():.0f}s")
        return ready

    def get_window(self) -> Optional[list[dict]]:
        """
        Retrieve the current window of records and reset the buffer.

        Returns a copy of the buffered records (without internal metadata)
        and clears the buffer so the next window starts fresh.

        Returns:
            List of record dicts, or None if the window is not ready.
        """
        if not self.is_window_ready():
            return None

        # Strip internal '_ts' key before returning
        window = []
        for r in self._buffer:
            clean = {k: v for k, v in r.items() if k != "_ts"}
            window.append(clean)

        logger.info(f"Emitting window of {len(window)} records")

        # Clear buffer for next window
        self._buffer.clear()

        return window

    def get_buffer_size(self) -> int:
        """
        Get the current number of records in the buffer.

        Returns:
            Number of records currently buffered.
        """
        return len(self._buffer)

    def get_buffer_span_seconds(self) -> float:
        """
        Get the time span of the current buffer in seconds.

        Returns:
            Time span from oldest to newest record in seconds.
        """
        return self._get_span_seconds()

    def reset(self) -> None:
        """
        Clear the buffer entirely.

        Used when the system is restarted or reconfigured.
        """
        self._buffer.clear()
        logger.info("Window buffer reset")

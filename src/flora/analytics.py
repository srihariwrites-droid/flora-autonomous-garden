"""Rule-based analytics helpers for plant data."""
from __future__ import annotations

from flora.db import SensorReading


def estimate_hours_to_threshold(
    readings: list[SensorReading],
    target_min: int,
) -> float | None:
    """Estimate hours until moisture drops to target_min using linear regression on recent readings.

    Returns None if: fewer than 2 readings, moisture is rising, or decline rate < 0.5%/h.
    """
    if len(readings) < 2:
        return None

    # Use oldest and newest to compute decline rate
    oldest = min(readings, key=lambda r: r.timestamp)
    newest = max(readings, key=lambda r: r.timestamp)

    if oldest.moisture is None or newest.moisture is None:
        return None

    elapsed_hours = (newest.timestamp - oldest.timestamp).total_seconds() / 3600
    if elapsed_hours <= 0:
        return None

    rate = (oldest.moisture - newest.moisture) / elapsed_hours  # %/h decline (positive = drying)

    # Not drying meaningfully
    if rate < 0.5:
        return None

    remaining = newest.moisture - target_min
    if remaining <= 0:
        return None

    return remaining / rate

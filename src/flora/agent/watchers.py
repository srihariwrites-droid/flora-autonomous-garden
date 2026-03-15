"""Watchers that detect abnormal plant patterns and trigger escalations."""
from __future__ import annotations

from datetime import datetime, timedelta

from flora.config import PlantConfig
from flora.db import Database


async def check_watering_effectiveness(
    db: Database,
    plant: PlantConfig,
    hours: int = 6,
    min_firings: int = 3,
) -> tuple[bool, int, float | None]:
    """Check whether auto-watering is having no effect.

    Returns (ineffective, count, current_moisture):
    - ineffective=True means min_firings+ auto_waters occurred in the window but
      moisture did not improve by >= 5 percentage points.
    - count is the number of auto_water actions found in the window.
    - current_moisture is the latest sensor reading (None if unavailable).
    """
    count = await db.count_recent_same_action(plant.name, "auto_water", hours=hours)
    if count < min_firings:
        return False, count, None

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    actions = await db.get_recent_actions(limit=200, plant_name=plant.name)
    auto_waters = [
        a for a in actions
        if a.action_type == "auto_water" and a.timestamp >= cutoff
    ]
    if not auto_waters:
        return False, count, None

    earliest = min(auto_waters, key=lambda a: a.timestamp)
    moisture_before = earliest.parameters.get("moisture")

    latest = await db.get_latest_sensor_reading(plant.name)
    if latest is None or latest.moisture is None:
        return False, count, None

    current = latest.moisture
    baseline = moisture_before if moisture_before is not None else (plant.auto_water_if_below or 0.0)
    ineffective = (current - baseline) < 5.0
    return ineffective, count, current


async def check_critical_moisture(
    db: Database,
    plant: PlantConfig,
    hours: int = 2,
    threshold: float = 10.0,
) -> bool:
    """Return True if all readings in the last `hours` are below `threshold`%."""
    readings = await db.get_sensor_history(plant.name, hours=hours, limit=100)
    if not readings:
        return False
    return all(
        r.moisture is not None and r.moisture < threshold
        for r in readings
    )

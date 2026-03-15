"""Tests for the watering-effectiveness watcher (issue #30)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from flora.agent.watchers import check_watering_effectiveness
from flora.config import PlantConfig
from flora.db import ActionRecord, SensorReading


def _plant(auto_water_if_below: int = 30) -> PlantConfig:
    return PlantConfig(
        name="basil",
        species="basil",
        sensor_mac="AA:BB:CC:DD:EE:01",
        pump_gpio=17,
        auto_water_if_below=auto_water_if_below,
    )


def _action(moisture: float, minutes_ago: int) -> ActionRecord:
    return ActionRecord(
        plant_name="basil",
        timestamp=datetime.utcnow() - timedelta(minutes=minutes_ago),
        action_type="auto_water",
        parameters={"moisture": moisture, "duration_seconds": 8, "threshold": 30},
        reasoning="Auto-water rule",
        claude_model="rule",
    )


def _reading(moisture: float) -> SensorReading:
    return SensorReading(
        plant_name="basil",
        timestamp=datetime.utcnow(),
        moisture=moisture,
        temperature=22.0,
        light=None,
        fertility=None,
        battery=None,
    )


async def test_returns_true_when_3_auto_waters_no_moisture_change():
    db = MagicMock()
    db.count_recent_same_action = AsyncMock(return_value=3)
    db.get_recent_actions = AsyncMock(return_value=[
        _action(moisture=25.0, minutes_ago=300),
        _action(moisture=25.0, minutes_ago=180),
        _action(moisture=25.0, minutes_ago=60),
    ])
    db.get_latest_sensor_reading = AsyncMock(return_value=_reading(25.5))

    ineffective, count, moisture = await check_watering_effectiveness(db, _plant())

    assert ineffective is True
    assert count == 3
    assert moisture == pytest.approx(25.5)


async def test_returns_false_when_moisture_improved():
    db = MagicMock()
    db.count_recent_same_action = AsyncMock(return_value=3)
    db.get_recent_actions = AsyncMock(return_value=[
        _action(moisture=25.0, minutes_ago=300),
        _action(moisture=25.0, minutes_ago=180),
        _action(moisture=25.0, minutes_ago=60),
    ])
    # Moisture improved by 10 points
    db.get_latest_sensor_reading = AsyncMock(return_value=_reading(35.0))

    ineffective, count, moisture = await check_watering_effectiveness(db, _plant())

    assert ineffective is False
    assert count == 3
    assert moisture == pytest.approx(35.0)


async def test_returns_false_fewer_than_min_firings():
    db = MagicMock()
    db.count_recent_same_action = AsyncMock(return_value=2)

    ineffective, count, moisture = await check_watering_effectiveness(db, _plant())

    assert ineffective is False
    assert count == 2
    assert moisture is None
    db.get_recent_actions.assert_not_called()


async def test_returns_false_no_latest_reading():
    db = MagicMock()
    db.count_recent_same_action = AsyncMock(return_value=3)
    db.get_recent_actions = AsyncMock(return_value=[
        _action(moisture=25.0, minutes_ago=300),
        _action(moisture=25.0, minutes_ago=180),
        _action(moisture=25.0, minutes_ago=60),
    ])
    db.get_latest_sensor_reading = AsyncMock(return_value=None)

    ineffective, count, moisture = await check_watering_effectiveness(db, _plant())

    assert ineffective is False
    assert count == 3
    assert moisture is None


async def test_returns_false_when_actions_outside_window():
    """Actions older than the hours window should not be counted."""
    db = MagicMock()
    # count_recent_same_action already filters by hours, but get_recent_actions
    # returns all — watcher filters them by timestamp.
    db.count_recent_same_action = AsyncMock(return_value=3)
    # All actions are >6h old — watcher should filter them out
    db.get_recent_actions = AsyncMock(return_value=[
        _action(moisture=25.0, minutes_ago=400),
        _action(moisture=25.0, minutes_ago=420),
        _action(moisture=25.0, minutes_ago=440),
    ])
    db.get_latest_sensor_reading = AsyncMock(return_value=_reading(25.0))

    ineffective, count, moisture = await check_watering_effectiveness(db, _plant())

    # auto_waters list is empty after window filter → returns False
    assert ineffective is False


async def test_exactly_5_point_improvement_is_not_ineffective():
    """Exactly 5% improvement is the boundary — should be effective (not ineffective)."""
    db = MagicMock()
    db.count_recent_same_action = AsyncMock(return_value=3)
    db.get_recent_actions = AsyncMock(return_value=[
        _action(moisture=25.0, minutes_ago=300),
        _action(moisture=25.0, minutes_ago=180),
        _action(moisture=25.0, minutes_ago=60),
    ])
    db.get_latest_sensor_reading = AsyncMock(return_value=_reading(30.0))

    ineffective, count, moisture = await check_watering_effectiveness(db, _plant())

    # 30.0 - 25.0 = 5.0, not < 5.0 → effective
    assert ineffective is False

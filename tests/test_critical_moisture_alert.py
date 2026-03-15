"""Tests for sustained critical moisture alert watcher (issue #43)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flora.agent.watchers import check_critical_moisture
from flora.config import PlantConfig
from flora.db import SensorReading


def _make_plant():
    return PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
        auto_water_if_below=25,
    )


def _r(moisture: float, hours_ago: float) -> SensorReading:
    return SensorReading(
        plant_name="basil",
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        moisture=moisture,
        temperature=22.0,
        light=None,
        fertility=None,
        battery=None,
    )


# ---------------------------------------------------------------------------
# check_critical_moisture unit tests
# ---------------------------------------------------------------------------

async def test_critical_returns_false_when_no_readings():
    db = MagicMock()
    db.get_sensor_history = AsyncMock(return_value=[])
    result = await check_critical_moisture(db, _make_plant())
    assert result is False


async def test_critical_returns_true_when_all_below_threshold():
    db = MagicMock()
    db.get_sensor_history = AsyncMock(return_value=[
        _r(5.0, 1.5),
        _r(7.0, 1.0),
        _r(8.0, 0.5),
        _r(6.0, 0.0),
    ])
    result = await check_critical_moisture(db, _make_plant())
    assert result is True


async def test_critical_returns_false_when_moisture_recovers():
    db = MagicMock()
    db.get_sensor_history = AsyncMock(return_value=[
        _r(5.0, 1.5),
        _r(6.0, 1.0),
        _r(35.0, 0.0),  # recovered after watering
    ])
    result = await check_critical_moisture(db, _make_plant())
    assert result is False


async def test_critical_uses_correct_db_parameters():
    db = MagicMock()
    db.get_sensor_history = AsyncMock(return_value=[_r(5.0, 1.0)])
    await check_critical_moisture(db, _make_plant(), hours=2, threshold=10.0)
    db.get_sensor_history.assert_awaited_once_with("basil", hours=2, limit=100)


# ---------------------------------------------------------------------------
# Scheduler integration: critical alert fires and respects cooldown
# ---------------------------------------------------------------------------

def _make_miflora_reading(moisture=5.0):
    r = MagicMock()
    r.moisture = moisture
    r.temperature = 22.0
    r.light = 500
    r.fertility = 200
    r.battery = 90
    return r


async def test_scheduler_sends_critical_alert_when_sustained():
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant()]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    # auto_water cooldown: no recent firings; critical_alert cooldown: none
    db.count_recent_same_action = AsyncMock(return_value=0)
    # All history readings are critical
    db.get_sensor_history = AsyncMock(return_value=[_r(5.0, 1.0), _r(6.0, 0.5)])
    db.get_recent_actions = AsyncMock(return_value=[])
    db.get_latest_sensor_reading = AsyncMock(return_value=None)

    with patch("flora.scheduler.read_miflora", return_value=_make_miflora_reading(moisture=5.0)), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)), \
         patch("flora.scheduler.send_telegram", new=AsyncMock()) as mock_telegram:
        await _poll_sensors(config, db)

    mock_telegram.assert_awaited_once()
    assert "CRITICAL" in mock_telegram.call_args[0][2]

    # Verify critical_alert was logged
    action_types = [c[0][0].action_type for c in db.log_action.call_args_list]
    assert "critical_alert" in action_types


async def test_scheduler_skips_alert_within_cooldown():
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant()]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    # Simulate cooldown: critical_alert already fired recently (count > 0)
    db.count_recent_same_action = AsyncMock(return_value=1)
    db.get_sensor_history = AsyncMock(return_value=[_r(5.0, 1.0), _r(6.0, 0.5)])
    db.get_recent_actions = AsyncMock(return_value=[])
    db.get_latest_sensor_reading = AsyncMock(return_value=None)

    with patch("flora.scheduler.read_miflora", return_value=_make_miflora_reading(moisture=5.0)), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)), \
         patch("flora.scheduler.send_telegram", new=AsyncMock()) as mock_telegram:
        await _poll_sensors(config, db)

    mock_telegram.assert_not_awaited()

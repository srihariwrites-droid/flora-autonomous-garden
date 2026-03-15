"""Tests for per-plant auto-water minimum interval cooldown (issue #39)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flora.config import PlantConfig


def _make_plant(threshold=25, duration=10, min_interval_minutes=15):
    return PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
        moisture_target_min=40, moisture_target_max=70,
        auto_water_if_below=threshold,
        auto_water_duration_seconds=duration,
        auto_water_min_interval_minutes=min_interval_minutes,
    )


def _make_miflora_reading(moisture=18.0):
    r = MagicMock()
    r.moisture = moisture
    r.temperature = 22.0
    r.light = 500
    r.fertility = 200
    r.battery = 90
    return r


def test_plant_config_min_interval_default():
    p = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
    )
    assert p.auto_water_min_interval_minutes == 15


def test_plant_config_min_interval_custom():
    p = _make_plant(min_interval_minutes=30)
    assert p.auto_water_min_interval_minutes == 30


async def test_auto_water_skipped_when_recent_firing():
    """Pump must not fire if a recent auto_water action is within the interval."""
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant(threshold=25, min_interval_minutes=15)]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    # Simulate a recent firing within the last 15min
    db.count_recent_same_action = AsyncMock(return_value=1)

    with patch("flora.scheduler.read_miflora", return_value=_make_miflora_reading(moisture=10.0)), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)) as mock_pump:
        await _poll_sensors(config, db)

    mock_pump.assert_not_awaited()
    # log_action should not be called for auto_water
    for call in db.log_action.call_args_list:
        assert call[0][0].action_type != "auto_water"


async def test_auto_water_fires_when_interval_elapsed():
    """Pump fires when moisture is below threshold and no recent firing in interval."""
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant(threshold=25, duration=10, min_interval_minutes=15)]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    db.count_recent_same_action = AsyncMock(return_value=0)

    with patch("flora.scheduler.read_miflora", return_value=_make_miflora_reading(moisture=10.0)), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)) as mock_pump:
        await _poll_sensors(config, db)

    mock_pump.assert_awaited_once_with(17, 10)
    db.log_action.assert_awaited()
    action = db.log_action.call_args_list[0][0][0]
    assert action.action_type == "auto_water"


async def test_cooldown_check_uses_correct_interval():
    """The cooldown check is called with the configured interval in hours."""
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant(threshold=25, min_interval_minutes=30)]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    db.count_recent_same_action = AsyncMock(return_value=0)

    with patch("flora.scheduler.read_miflora", return_value=_make_miflora_reading(moisture=10.0)), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)):
        await _poll_sensors(config, db)

    # The first call to count_recent_same_action should be for auto_water with 30min/60 = 0.5h
    first_call = db.count_recent_same_action.call_args_list[0]
    assert first_call[0][1] == "auto_water"
    assert abs(first_call[1]["hours"] - 0.5) < 0.001

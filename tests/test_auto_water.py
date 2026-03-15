"""Tests for auto-water threshold rules (issue #16)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from flora.config import PlantConfig


# ---------------------------------------------------------------------------
# PlantConfig defaults
# ---------------------------------------------------------------------------

def test_plant_config_auto_water_defaults():
    p = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
    )
    assert p.auto_water_if_below is None
    assert p.auto_water_duration_seconds == 8


def test_plant_config_auto_water_set():
    p = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
        auto_water_if_below=25,
        auto_water_duration_seconds=10,
    )
    assert p.auto_water_if_below == 25
    assert p.auto_water_duration_seconds == 10


# ---------------------------------------------------------------------------
# _poll_sensors auto-water trigger
# ---------------------------------------------------------------------------

def _make_plant(threshold=None, duration=8):
    return PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
        moisture_target_min=40, moisture_target_max=70,
        auto_water_if_below=threshold,
        auto_water_duration_seconds=duration,
    )


def _make_miflora_reading(moisture):
    r = MagicMock()
    r.moisture = moisture
    r.temperature = 22.0
    r.light = 500
    r.fertility = 200
    r.battery = 90
    return r


async def test_auto_water_triggers_when_below_threshold():
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant(threshold=25, duration=10)]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    db.count_recent_same_action = AsyncMock(return_value=0)  # watcher: no recent firings

    miflora_reading = _make_miflora_reading(moisture=18.0)

    with patch("flora.scheduler.read_miflora", return_value=miflora_reading), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)) as mock_pump:
        await _poll_sensors(config, db)

    mock_pump.assert_awaited_once_with(17, 10)
    db.log_action.assert_awaited_once()
    action = db.log_action.call_args[0][0]
    assert action.action_type == "auto_water"
    assert action.claude_model == "rule"
    assert action.parameters["threshold"] == 25


async def test_auto_water_not_triggered_when_above_threshold():
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant(threshold=25)]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    db.count_recent_same_action = AsyncMock(return_value=0)  # watcher: no recent firings

    miflora_reading = _make_miflora_reading(moisture=40.0)

    with patch("flora.scheduler.read_miflora", return_value=miflora_reading), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)) as mock_pump:
        await _poll_sensors(config, db)

    mock_pump.assert_not_awaited()
    db.log_action.assert_not_awaited()


async def test_auto_water_not_triggered_when_threshold_is_none():
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant(threshold=None)]
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()

    miflora_reading = _make_miflora_reading(moisture=5.0)

    with patch("flora.scheduler.read_miflora", return_value=miflora_reading), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)) as mock_pump:
        await _poll_sensors(config, db)

    mock_pump.assert_not_awaited()


async def test_auto_water_duration_clamped_to_5_30():
    from flora.scheduler import _poll_sensors

    config = MagicMock()
    config.plants = [_make_plant(threshold=25, duration=99)]  # too high, should clamp to 30
    db = MagicMock()
    db.insert_sensor_reading = AsyncMock()
    db.log_action = AsyncMock()
    db.insert_ambient_reading = AsyncMock()
    db.count_recent_same_action = AsyncMock(return_value=0)  # watcher: no recent firings

    miflora_reading = _make_miflora_reading(moisture=10.0)

    with patch("flora.scheduler.read_miflora", return_value=miflora_reading), \
         patch("flora.scheduler.read_sht31", return_value=None), \
         patch("flora.scheduler.read_bh1750", return_value=None), \
         patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)) as mock_pump:
        await _poll_sensors(config, db)

    mock_pump.assert_awaited_once_with(17, 30)

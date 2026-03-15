"""Tests for ToolExecutor.get_ambient_reading."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from flora.agent.tools import ToolExecutor
from flora.config import AppConfig, PlantConfig
from flora.db import AmbientReading, Database

_CONFIG = AppConfig(
    db_path="test.db",
    dashboard_port=8000,
    sensor_poll_interval=1800,
    agent_loop_interval=7200,
    anthropic_api_key="test-key",
    anthropic_model="claude-haiku-4-5-20251001",
    telegram_token="",
    telegram_chat_id="",
    plants=[
        PlantConfig(
            name="basil-1",
            species="basil",
            sensor_mac="AA:BB:CC:DD:EE:FF",
            pump_gpio=17,
        )
    ],
    smart_plugs=[],
)

_NOW = datetime(2026, 3, 15, 10, 0, 0)


async def test_get_ambient_reading_latest():
    """Returns formatted string with the latest single reading."""
    db = AsyncMock(spec=Database)
    db.get_latest_ambient.return_value = AmbientReading(
        timestamp=_NOW,
        temperature=21.5,
        humidity=55.0,
        light_lux=340.0,
    )
    executor = ToolExecutor(_CONFIG, db)
    result = await executor.execute("get_ambient_reading", {})

    assert "21.5" in result
    assert "55.0" in result
    assert "340.0" in result
    db.get_latest_ambient.assert_awaited_once()


async def test_get_ambient_reading_absent():
    """Returns no-data message when the table is empty."""
    db = AsyncMock(spec=Database)
    db.get_latest_ambient.return_value = None
    executor = ToolExecutor(_CONFIG, db)
    result = await executor.execute("get_ambient_reading", {})

    assert "No ambient reading" in result


async def test_get_ambient_reading_average():
    """Returns averaged values when hours > 1."""
    db = AsyncMock(spec=Database)
    db.get_ambient_readings.return_value = [
        AmbientReading(timestamp=_NOW, temperature=20.0, humidity=50.0, light_lux=200.0),
        AmbientReading(timestamp=_NOW, temperature=22.0, humidity=60.0, light_lux=400.0),
    ]
    executor = ToolExecutor(_CONFIG, db)
    result = await executor.execute("get_ambient_reading", {"hours": 6})

    assert "21.0" in result   # avg temp
    assert "55.0" in result   # avg humidity
    assert "300.0" in result  # avg lux
    db.get_ambient_readings.assert_awaited_once_with(6)


async def test_get_ambient_reading_average_no_data():
    """Returns no-data message when hours > 1 and table is empty."""
    db = AsyncMock(spec=Database)
    db.get_ambient_readings.return_value = []
    executor = ToolExecutor(_CONFIG, db)
    result = await executor.execute("get_ambient_reading", {"hours": 12})

    assert "No ambient readings" in result

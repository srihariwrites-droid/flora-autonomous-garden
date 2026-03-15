"""Tests for stale-reading warning (issue #35)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from flora.config import PlantConfig
from flora.dashboard.routes import _reading_age_hours
from flora.db import SensorReading


def _reading(hours_ago: float) -> SensorReading:
    return SensorReading(
        plant_name="basil",
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        moisture=55.0,
        temperature=22.0,
        light=None,
        fertility=None,
        battery=None,
    )


def test_reading_age_returns_none_when_no_reading():
    assert _reading_age_hours(None) is None


def test_reading_age_returns_correct_hours():
    age = _reading_age_hours(_reading(3.0))
    assert age == pytest.approx(3.0, abs=0.01)


def test_reading_age_recent_reading():
    age = _reading_age_hours(_reading(0.5))
    assert age == pytest.approx(0.5, abs=0.01)


def _make_app(reading: SensorReading | None):
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    from flora.dashboard.routes import create_router

    plant = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17,
    )
    config = MagicMock()
    config.plants = [plant]
    config.plant_by_name = MagicMock(return_value=plant)

    db = MagicMock()
    db.get_latest_sensor_reading = AsyncMock(return_value=reading)
    db.get_latest_ambient = AsyncMock(return_value=None)
    db.get_recent_actions = AsyncMock(return_value=[])
    db.get_journal = AsyncMock(return_value=[])
    db.get_sensor_history = AsyncMock(return_value=[])

    templates_dir = Path(__file__).parent.parent / "src" / "flora" / "dashboard" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    app = FastAPI()
    app.include_router(create_router(config, db, templates))
    return app


def test_index_includes_reading_age_none_when_no_reading():
    client = TestClient(_make_app(reading=None))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "No data</span>" in resp.text


def test_index_includes_stale_warning_for_old_reading():
    client = TestClient(_make_app(reading=_reading(hours_ago=3.0)))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Stale" in resp.text


def test_index_no_warning_for_fresh_reading():
    client = TestClient(_make_app(reading=_reading(hours_ago=0.5)))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Stale" not in resp.text
    # "No data</span>" distinguishes the stale badge from the sparkline "No data yet" text
    assert "No data</span>" not in resp.text


def test_plant_detail_stale_warning():
    client = TestClient(_make_app(reading=_reading(hours_ago=5.0)))
    resp = client.get("/plants/basil")
    assert resp.status_code == 200
    assert "Stale" in resp.text

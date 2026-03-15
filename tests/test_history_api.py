from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from flora.config import PlantConfig
from flora.dashboard.routes import create_router
from flora.db import SensorReading


def _make_reading(fertility: int | None = 120, light: int | None = 800) -> SensorReading:
    return SensorReading(
        plant_name="basil",
        timestamp=datetime.utcnow() - timedelta(hours=1),
        moisture=55.0,
        temperature=22.0,
        light=light,
        fertility=fertility,
        battery=85,
    )


def _make_client(history: list[SensorReading]) -> TestClient:
    plant = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17,
    )
    config = MagicMock()
    config.plants = [plant]
    config.plant_by_name = MagicMock(return_value=plant)

    db = MagicMock()
    db.get_latest_sensor_reading = AsyncMock(return_value=None)
    db.get_latest_ambient = AsyncMock(return_value=None)
    db.get_recent_actions = AsyncMock(return_value=[])
    db.get_journal = AsyncMock(return_value=[])
    db.get_sensor_history = AsyncMock(return_value=history)

    templates_dir = Path(__file__).parent.parent / "src" / "flora" / "dashboard" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    app = FastAPI()
    app.include_router(create_router(config, db, templates))
    return TestClient(app)


def test_history_api_includes_fertility_field():
    client = _make_client([_make_reading(fertility=120)])
    data = client.get("/api/plants/basil/history").json()
    assert "fertility" in data["readings"][0]
    assert data["readings"][0]["fertility"] == 120


def test_history_api_fertility_null_when_not_measured():
    client = _make_client([_make_reading(fertility=None)])
    data = client.get("/api/plants/basil/history").json()
    assert data["readings"][0]["fertility"] is None


def test_history_api_includes_light_field():
    client = _make_client([_make_reading(light=1500)])
    data = client.get("/api/plants/basil/history").json()
    assert data["readings"][0]["light"] == 1500


def test_history_api_empty_when_no_readings():
    client = _make_client([])
    data = client.get("/api/plants/basil/history").json()
    assert data["readings"] == []

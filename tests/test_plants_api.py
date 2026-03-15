from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from flora.config import PlantConfig
from flora.dashboard.routes import create_router
from flora.db import SensorReading


def _reading(plant_name: str, moisture: float, hours_ago: float = 0.5) -> SensorReading:
    return SensorReading(
        plant_name=plant_name,
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        moisture=moisture,
        temperature=22.0,
        light=800,
        fertility=None,
        battery=85,
    )


def _make_app(plants: list[PlantConfig], readings: dict[str, SensorReading | None]):
    config = MagicMock()
    config.plants = plants
    config.plant_by_name = MagicMock(side_effect=lambda n: next((p for p in plants if p.name == n), None))

    db = MagicMock()
    db.get_latest_sensor_reading = AsyncMock(side_effect=lambda name: readings.get(name))
    db.get_latest_ambient = AsyncMock(return_value=None)
    db.get_recent_actions = AsyncMock(return_value=[])
    db.get_journal = AsyncMock(return_value=[])
    db.get_sensor_history = AsyncMock(return_value=[])

    templates_dir = Path(__file__).parent.parent / "src" / "flora" / "dashboard" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    app = FastAPI()
    app.include_router(create_router(config, db, templates))
    return app


def _make_plant(name: str, i: int = 0) -> PlantConfig:
    return PlantConfig(
        name=name, species="basil",
        sensor_mac=f"AA:BB:CC:DD:EE:{i:02d}", pump_gpio=17 + i,
        moisture_target_min=40, moisture_target_max=70,
    )


def test_plants_api_returns_200():
    plant = _make_plant("basil")
    client = TestClient(_make_app([plant], {"basil": _reading("basil", 55.0)}))
    resp = client.get("/api/plants")
    assert resp.status_code == 200


def test_plants_api_single_plant_with_reading():
    plant = _make_plant("basil")
    client = TestClient(_make_app([plant], {"basil": _reading("basil", 55.0)}))
    data = client.get("/api/plants").json()
    assert len(data) == 1
    p = data[0]
    assert p["name"] == "basil"
    assert p["species"] == "basil"
    assert p["status"] == "healthy"
    assert p["moisture"] == pytest.approx(55.0)
    assert p["temperature"] == pytest.approx(22.0)
    assert p["battery"] == 85
    assert p["reading_age_hours"] == pytest.approx(0.5, abs=0.05)
    assert p["moisture_target_min"] == 40
    assert p["moisture_target_max"] == 70


def test_plants_api_plant_with_no_reading():
    plant = _make_plant("basil")
    client = TestClient(_make_app([plant], {"basil": None}))
    data = client.get("/api/plants").json()
    assert len(data) == 1
    p = data[0]
    assert p["moisture"] is None
    assert p["temperature"] is None
    assert p["reading_age_hours"] is None
    assert p["status"] == "unknown"


def test_plants_api_multiple_plants():
    plants = [_make_plant("basil", 0), _make_plant("mint", 1)]
    readings = {
        "basil": _reading("basil", 55.0),
        "mint": _reading("mint", 25.0),  # dry
    }
    client = TestClient(_make_app(plants, readings))
    data = client.get("/api/plants").json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert names == {"basil", "mint"}
    mint = next(p for p in data if p["name"] == "mint")
    assert mint["status"] == "dry"


def test_plants_api_empty_when_no_plants():
    config = MagicMock()
    config.plants = []
    config.plant_by_name = MagicMock(return_value=None)

    db = MagicMock()
    db.get_latest_sensor_reading = AsyncMock(return_value=None)
    db.get_latest_ambient = AsyncMock(return_value=None)
    db.get_recent_actions = AsyncMock(return_value=[])
    db.get_journal = AsyncMock(return_value=[])
    db.get_sensor_history = AsyncMock(return_value=[])

    templates_dir = Path(__file__).parent.parent / "src" / "flora" / "dashboard" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    app = FastAPI()
    app.include_router(create_router(config, db, templates))
    client = TestClient(app)
    data = client.get("/api/plants").json()
    assert data == []

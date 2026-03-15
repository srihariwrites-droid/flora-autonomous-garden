"""Tests for GET /api/health endpoint (issue #36)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from pathlib import Path

from flora.config import PlantConfig
from flora.dashboard.routes import create_router
from flora.db import SensorReading


def _reading(plant_name: str, hours_ago: float) -> SensorReading:
    return SensorReading(
        plant_name=plant_name,
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        moisture=55.0,
        temperature=22.0,
        light=None,
        fertility=None,
        battery=None,
    )


def _make_app(readings: dict[str, SensorReading | None]):
    plant_names = list(readings.keys())
    plants = [
        PlantConfig(
            name=name, species="basil",
            sensor_mac=f"AA:BB:CC:DD:EE:{i:02d}", pump_gpio=17 + i,
        )
        for i, name in enumerate(plant_names)
    ]

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


def test_health_returns_200():
    client = TestClient(_make_app({"basil": _reading("basil", hours_ago=0.5)}))
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_health_ok_when_recent_reading():
    client = TestClient(_make_app({"basil": _reading("basil", hours_ago=0.5)}))
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["plants"] == 1
    assert data["db"] == "connected"
    assert data["latest_reading_age_seconds"] == pytest.approx(1800, abs=60)


def test_health_degraded_when_old_reading():
    client = TestClient(_make_app({"basil": _reading("basil", hours_ago=2.0)}))
    data = client.get("/api/health").json()
    assert data["status"] == "degraded"


def test_health_degraded_when_no_readings():
    client = TestClient(_make_app({"basil": None}))
    data = client.get("/api/health").json()
    assert data["status"] == "degraded"
    assert data["latest_reading_age_seconds"] is None


def test_health_uses_newest_reading_across_plants():
    client = TestClient(_make_app({
        "basil": _reading("basil", hours_ago=3.0),   # old
        "mint":  _reading("mint",  hours_ago=0.25),  # recent
    }))
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["plants"] == 2

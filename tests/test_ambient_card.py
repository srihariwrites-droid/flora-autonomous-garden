from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from flora.config import PlantConfig
from flora.dashboard.routes import create_router
from flora.db import AmbientReading


def _make_client(ambient: AmbientReading | None) -> TestClient:
    config = MagicMock()
    config.plants = []
    config.plant_by_name = MagicMock(return_value=None)

    db = MagicMock()
    db.get_latest_sensor_reading = AsyncMock(return_value=None)
    db.get_latest_ambient = AsyncMock(return_value=ambient)
    db.get_recent_actions = AsyncMock(return_value=[])
    db.get_journal = AsyncMock(return_value=[])
    db.get_sensor_history = AsyncMock(return_value=[])

    templates_dir = Path(__file__).parent.parent / "src" / "flora" / "dashboard" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    app = FastAPI()
    app.include_router(create_router(config, db, templates))
    return TestClient(app)


def _ambient(temperature: float = 22.5, humidity: float = 55.0) -> AmbientReading:
    return AmbientReading(
        timestamp=datetime.utcnow(),
        temperature=temperature,
        humidity=humidity,
        light_lux=None,
    )


def test_ambient_card_renders_when_present():
    client = _make_client(_ambient(temperature=21.3, humidity=60.0))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Ambient Conditions" in resp.text
    assert "21.3" in resp.text
    assert "60" in resp.text


def test_ambient_card_absent_when_no_reading():
    client = _make_client(None)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Ambient Conditions" not in resp.text

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from flora.config import PlantConfig
from flora.dashboard.routes import create_router


def _make_plant(notes: str = "") -> PlantConfig:
    return PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17,
        notes=notes,
    )


def _make_client(plant: PlantConfig) -> TestClient:
    config = MagicMock()
    config.plants = [plant]
    config.plant_by_name = MagicMock(return_value=plant)

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
    return TestClient(app)


def test_plant_notes_default_is_empty_string():
    p = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17,
    )
    assert p.notes == ""


def test_plant_notes_custom_value():
    p = _make_plant(notes="South-facing window, tends to dry fast")
    assert p.notes == "South-facing window, tends to dry fast"


def test_plant_detail_renders_notes_when_set():
    client = _make_client(_make_plant(notes="Gets afternoon sun"))
    resp = client.get("/plants/basil")
    assert resp.status_code == 200
    assert "Gets afternoon sun" in resp.text


def test_plant_detail_skips_notes_when_empty():
    client = _make_client(_make_plant(notes=""))
    resp = client.get("/plants/basil")
    assert resp.status_code == 200
    # No notes div rendered when empty
    assert "Gets afternoon sun" not in resp.text

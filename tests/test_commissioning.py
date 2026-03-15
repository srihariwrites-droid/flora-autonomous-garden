"""Tests for plant commissioning wizard (issue #25)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from flora.config import PlantConfig, append_plant_to_toml


# ---------------------------------------------------------------------------
# append_plant_to_toml
# ---------------------------------------------------------------------------

def test_append_plant_to_toml_creates_file_if_missing(tmp_path):
    toml_path = tmp_path / "flora.toml"
    append_plant_to_toml(toml_path, {"name": "basil-1", "species": "basil", "pump_gpio": 17})
    content = toml_path.read_text()
    assert "[[plants]]" in content
    assert 'name = "basil-1"' in content
    assert "pump_gpio = 17" in content


def test_append_plant_to_toml_preserves_existing_content(tmp_path):
    toml_path = tmp_path / "flora.toml"
    toml_path.write_text('[app]\ndb_path = "flora.db"\n\n[[plants]]\nname = "mint-1"\n')
    append_plant_to_toml(toml_path, {"name": "basil-1", "species": "basil", "pump_gpio": 17})
    content = toml_path.read_text()
    assert 'name = "mint-1"' in content
    assert 'name = "basil-1"' in content
    assert 'db_path = "flora.db"' in content


def test_append_plant_to_toml_skips_none_values(tmp_path):
    toml_path = tmp_path / "flora.toml"
    append_plant_to_toml(toml_path, {"name": "basil-1", "auto_water_if_below": None, "pump_gpio": 17})
    content = toml_path.read_text()
    assert "auto_water_if_below" not in content
    assert "pump_gpio = 17" in content


# ---------------------------------------------------------------------------
# Dashboard routes
# ---------------------------------------------------------------------------

def _make_app():
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates
    from pathlib import Path as P
    from flora.dashboard.routes import create_router

    plant = PlantConfig(
        name="mint", species="mint",
        sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=18,
    )
    config = MagicMock()
    config.plants = [plant]
    db = MagicMock()

    templates_dir = P(__file__).parent.parent / "src" / "flora" / "dashboard" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    app = FastAPI()
    app.include_router(create_router(config, db, templates))
    return app


def test_commissioning_page_renders():
    client = TestClient(_make_app())
    resp = client.get("/plants/new")
    assert resp.status_code == 200
    assert "Commission" in resp.text
    assert "sensor_mac" in resp.text


def test_commissioning_page_excludes_used_gpio():
    """GPIO 18 is used by mint — should not appear in the free pin selector."""
    client = TestClient(_make_app())
    resp = client.get("/plants/new")
    assert resp.status_code == 200
    # GPIO 18 is used by the existing plant — must not appear as an option
    assert "GPIO 18" not in resp.text


async def test_commissioning_test_pump_calls_actuator():
    app = _make_app()
    client = TestClient(app)
    with patch("flora.actuators.pump.water_plant", new=AsyncMock(return_value=True)):
        resp = client.post("/api/commissioning/test-pump", data={"gpio": "22", "duration": "3"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["gpio"] == 22


async def test_commissioning_save_appends_to_toml(tmp_path):
    toml_path = tmp_path / "flora.toml"
    toml_path.write_text('[app]\ndb_path = "flora.db"\n')

    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    with patch("flora.dashboard.routes.append_plant_to_toml") as mock_append, \
         patch("flora.dashboard.routes.Path", return_value=toml_path):
        resp = client.post("/plants/new", data={
            "name": "basil-2",
            "species": "basil",
            "sensor_mac": "CC:DD:EE:FF:00:11",
            "pump_gpio": "22",
            "moisture_target_min": "40",
            "moisture_target_max": "70",
        })

    assert resp.status_code == 303
    assert resp.headers["location"] == "/plants/basil-2"
    mock_append.assert_called_once()
    saved = mock_append.call_args[0][1]
    assert saved["name"] == "basil-2"
    assert saved["sensor_mac"] == "CC:DD:EE:FF:00:11"

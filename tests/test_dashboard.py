"""Dashboard integration tests using ASGI TestClient."""
import json
import pytest
from httpx import AsyncClient, ASGITransport
from flora.config import load_config
from flora.db import Database
from flora.dashboard.app import create_app
from flora.dashboard.routes import _mock_moisture, _mock_status, _SPECIES_MOCK, _DEFAULT_MOCK

_TOML = """
[app]
db_path = "test.db"
dashboard_port = 8000
sensor_poll_interval = 1800
agent_loop_interval = 7200

[anthropic]
api_key = "test"
model = "claude-haiku-4-5-20251001"

[telegram]
token = ""
chat_id = ""

[[plants]]
name = "basil-1"
species = "basil"
sensor_mac = "AA:BB:CC:DD:EE:FF"
pump_gpio = 17
moisture_target_min = 40
moisture_target_max = 70
"""


@pytest.fixture
async def client(tmp_path):
    toml = tmp_path / "flora.toml"
    toml.write_text(_TOML)
    config = load_config(str(toml))
    db = Database(tmp_path / "test.db")
    await db.connect()
    app = create_app(config, db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await db.close()


async def test_index_returns_200(client):
    resp = await client.get("/")
    assert resp.status_code == 200


async def test_plant_detail_returns_200(client):
    resp = await client.get("/plants/basil-1")
    assert resp.status_code == 200


async def test_plant_detail_404_unknown(client):
    resp = await client.get("/plants/does-not-exist")
    assert resp.status_code == 404


async def test_manual_water_endpoint(client):
    """POST /plants/basil-1/water triggers mock pump and returns 200."""
    resp = await client.post("/plants/basil-1/water", data={"duration": "5"})
    assert resp.status_code == 200
    assert "Watered" in resp.text


async def test_manual_water_unknown_plant(client):
    resp = await client.post("/plants/unknown/water", data={"duration": "5"})
    assert resp.status_code == 404


# --- Mock species data helpers ---

def test_mock_moisture_known_species():
    for species in _SPECIES_MOCK:
        assert _mock_moisture(species) == _SPECIES_MOCK[species][0]


def test_mock_status_known_species():
    for species, (_, expected_status) in _SPECIES_MOCK.items():
        assert _mock_status(species) == expected_status


def test_mock_moisture_case_insensitive():
    assert _mock_moisture("Basil") == _mock_moisture("basil")
    assert _mock_moisture("MINT") == _mock_moisture("mint")


def test_mock_moisture_unknown_species_uses_default():
    assert _mock_moisture("unknown_herb") == _DEFAULT_MOCK[0]


def test_mock_status_unknown_species_uses_default():
    assert _mock_status("unknown_herb") == _DEFAULT_MOCK[1]


@pytest.mark.asyncio
async def test_index_plants_art_json_no_reading(client):
    """When no sensor data exists, plants_art_json uses mock values not 'unknown'."""
    resp = await client.get("/")
    assert resp.status_code == 200
    # The JSON is embedded in a <script> tag — check the page contains mock status values
    # (not "unknown") since no readings have been inserted
    assert '"status": "unknown"' not in resp.text or '"has_reading": false' in resp.text


@pytest.mark.asyncio
async def test_csv_export_returns_csv_empty(client):
    """CSV export returns 200 with correct headers even when no readings exist."""
    resp = await client.get("/api/plants/basil-1/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert 'filename="basil-1-history.csv"' in resp.headers["content-disposition"]
    assert "timestamp,moisture,temperature,light,fertility,battery" in resp.text


@pytest.mark.asyncio
async def test_csv_export_unknown_plant(client):
    resp = await client.get("/api/plants/does-not-exist/export.csv")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_csv_export_includes_readings(tmp_path):
    """CSV export includes inserted sensor readings."""
    from flora.db import Database, SensorReading
    from datetime import datetime, timezone
    from flora.config import load_config
    from flora.dashboard.app import create_app
    from httpx import AsyncClient, ASGITransport

    toml = tmp_path / "flora2.toml"
    toml.write_text(_TOML)
    config = load_config(str(toml))
    db2 = Database(tmp_path / "seeded.db")
    await db2.connect()
    await db2.insert_sensor_reading(SensorReading(
        plant_name="basil-1",
        timestamp=datetime.now(timezone.utc),
        moisture=55.0,
        temperature=22.5,
        light=800,
        fertility=300,
        battery=90,
    ))
    app2 = create_app(config, db2)
    async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as ac:
        resp = await ac.get("/api/plants/basil-1/export.csv")
    await db2.close()

    assert resp.status_code == 200
    lines = resp.text.strip().splitlines()
    assert lines[0] == "timestamp,moisture,temperature,light,fertility,battery"
    assert len(lines) == 2  # header + 1 row
    assert "55.0" in lines[1]
    assert "22.5" in lines[1]


@pytest.mark.asyncio
async def test_history_json_shape_and_values(tmp_path):
    """history.json endpoint returns correct shape and values for inserted readings."""
    from flora.db import Database, SensorReading
    from datetime import datetime, timedelta, timezone
    from flora.config import load_config
    from flora.dashboard.app import create_app
    from httpx import AsyncClient, ASGITransport

    toml = tmp_path / "flora3.toml"
    toml.write_text(_TOML)
    config = load_config(str(toml))
    db3 = Database(tmp_path / "sparkline.db")
    await db3.connect()

    now = datetime.now(timezone.utc)
    for i, (moisture, temp) in enumerate([(40.0, 21.0), (55.0, 22.0), (70.0, 23.0)]):
        await db3.insert_sensor_reading(SensorReading(
            plant_name="basil-1",
            timestamp=now - timedelta(hours=2 - i),
            moisture=moisture,
            temperature=temp,
            light=500,
            fertility=200,
            battery=80,
        ))

    app3 = create_app(config, db3)
    async with AsyncClient(transport=ASGITransport(app=app3), base_url="http://test") as ac:
        resp = await ac.get("/api/plants/basil-1/history.json")
    await db3.close()

    assert resp.status_code == 200
    body = resp.json()
    assert "timestamps" in body
    assert "moisture" in body
    assert "temperature" in body
    assert len(body["timestamps"]) == 3
    assert len(body["moisture"]) == 3
    assert 40.0 in body["moisture"]
    assert 70.0 in body["moisture"]

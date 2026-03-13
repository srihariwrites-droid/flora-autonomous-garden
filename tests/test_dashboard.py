"""Dashboard integration tests using ASGI TestClient."""
import pytest
from httpx import AsyncClient, ASGITransport
from flora.config import load_config
from flora.db import Database
from flora.dashboard.app import create_app

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

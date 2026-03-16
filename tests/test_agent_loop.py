"""End-to-end agent loop tests — real API (skipped if key not set) + fallback."""
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from flora.config import load_config
from flora.db import Database
from flora.agent.loop import AgentLoop

SKIP_IF_NO_KEY = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)

_TOML_BASE = """
[app]
db_path = "test.db"
dashboard_port = 8000
sensor_poll_interval = 1800
agent_loop_interval = 7200

[anthropic]
api_key = "{api_key}"
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
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def config(tmp_path):
    toml = tmp_path / "flora.toml"
    toml.write_text(_TOML_BASE.format(api_key="sk-ant-xxxxxxxxxxxxxxxxxxxx"))
    return load_config(str(toml))


@SKIP_IF_NO_KEY
async def test_agent_loop_runs_without_error(config, db):
    """Agent loop completes one cycle with mock data and real Claude API."""
    loop = AgentLoop(config, db)
    # Should not raise — Claude may or may not call tools, both are valid
    await loop.run_once()


async def test_fallback_runs_when_api_key_invalid(tmp_path, db):
    """Fallback rule-based loop runs when API key is invalid."""
    toml = tmp_path / "flora.toml"
    toml.write_text(_TOML_BASE.format(api_key="sk-ant-invalidxxxxxxxxxxxxxxx"))
    config = load_config(str(toml))
    loop = AgentLoop(config, db)
    # Invalid key → fallback. Should not raise.
    await loop.run_once()


async def test_iteration_cap_logs_warning(config, db, caplog):
    """Agent loop logs a warning when the 10-iteration safety cap is hit."""
    # Simulate Claude always returning a tool_use so the cap is reached
    fake_tool_use = MagicMock()
    fake_tool_use.type = "tool_use"
    fake_tool_use.name = "water_plant"
    fake_tool_use.id = "tu_fake"
    fake_tool_use.input = {"plant_name": "basil-1", "duration_seconds": 5}

    fake_response = MagicMock()
    fake_response.stop_reason = "tool_use"
    fake_response.content = [fake_tool_use]

    with patch.object(
        loop := AgentLoop(config, db),
        "_client",
    ):
        loop._client.messages.create = AsyncMock(return_value=fake_response)
        loop._executor.execute = AsyncMock(return_value="ok")
        with caplog.at_level(logging.WARNING, logger="flora.agent.loop"):
            await loop._run_claude_loop()

    assert any("safety cap" in r.message for r in caplog.records)

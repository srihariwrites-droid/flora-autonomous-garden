"""Tests for actuator tool: set_light_schedule with APScheduler + SQLite persistence."""
from __future__ import annotations

import pytest
from datetime import time as dtime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flora.config import AppConfig

from flora.db import Database, PlugSchedule


# ─── Database layer ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_and_get_plug_schedule(tmp_path: Path) -> None:
    """upsert_plug_schedule stores a schedule; get_plug_schedule retrieves it."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    schedule = PlugSchedule(alias="grow_light", on_time="06:00", off_time="22:00", enabled=True)
    await db.upsert_plug_schedule(schedule)
    result = await db.get_plug_schedule("grow_light")
    await db.close()

    assert result is not None
    assert result.alias == "grow_light"
    assert result.on_time == "06:00"
    assert result.off_time == "22:00"
    assert result.enabled is True


@pytest.mark.asyncio
async def test_upsert_plug_schedule_overwrites(tmp_path: Path) -> None:
    """Second upsert for the same alias replaces the previous entry."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.upsert_plug_schedule(PlugSchedule(alias="grow_light", on_time="06:00", off_time="20:00", enabled=True))
    await db.upsert_plug_schedule(PlugSchedule(alias="grow_light", on_time="08:00", off_time="23:00", enabled=False))
    result = await db.get_plug_schedule("grow_light")
    await db.close()

    assert result is not None
    assert result.on_time == "08:00"
    assert result.off_time == "23:00"
    assert result.enabled is False


@pytest.mark.asyncio
async def test_get_plug_schedule_returns_none_when_absent(tmp_path: Path) -> None:
    """get_plug_schedule returns None if the alias has not been stored."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    result = await db.get_plug_schedule("nonexistent")
    await db.close()
    assert result is None


# ─── ToolExecutor._set_light_schedule ─────────────────────────────────────────

def _make_config(tmp_path: Path) -> "AppConfig":
    """Create a minimal AppConfig with a grow_light plug."""
    import textwrap
    toml_text = textwrap.dedent("""\
        [anthropic]
        api_key = "sk-test"
        model   = "claude-haiku-4-5-20251001"

        [telegram]
        token   = ""
        chat_id = ""

        [[plants]]
        name              = "basil-1"
        species           = "basil"
        sensor_mac        = "AA:BB:CC:DD:EE:01"
        pump_gpio         = 17
        moisture_target_min = 40
        moisture_target_max = 70

        [[smart_plugs]]
        alias = "grow_light"
        host  = "192.168.1.50"
        role  = "grow_light"
    """)
    toml_path = tmp_path / "flora.toml"
    toml_path.write_text(toml_text)
    from flora.config import load_config
    return load_config(str(toml_path))


@pytest.mark.asyncio
async def test_set_light_schedule_persists_to_db(tmp_path: Path) -> None:
    """_set_light_schedule stores the schedule in SQLite."""
    from flora.agent.tools import ToolExecutor
    config = _make_config(tmp_path)
    db = Database(tmp_path / "test.db")
    await db.connect()

    executor = ToolExecutor(config, db)
    result = await executor.execute("set_light_schedule", {
        "on_hour": 6, "on_minute": 0,
        "off_hour": 22, "off_minute": 0,
        "reason": "Extending photoperiod for basil growth",
    })
    await db.close()

    assert "06:00" in result
    assert "22:00" in result

    # Re-open to verify persistence
    db2 = Database(tmp_path / "test.db")
    await db2.connect()
    sched = await db2.get_plug_schedule("grow_light")
    await db2.close()
    assert sched is not None
    assert sched.on_time == "06:00"
    assert sched.off_time == "22:00"
    assert sched.enabled is True


@pytest.mark.asyncio
async def test_set_light_schedule_registers_scheduler_jobs(tmp_path: Path) -> None:
    """When a scheduler is provided, two cron jobs are added/replaced."""
    from flora.agent.tools import ToolExecutor
    config = _make_config(tmp_path)
    db = Database(tmp_path / "test.db")
    await db.connect()

    mock_scheduler = MagicMock()
    executor = ToolExecutor(config, db, scheduler=mock_scheduler)
    await executor.execute("set_light_schedule", {
        "on_hour": 7, "on_minute": 30,
        "off_hour": 21, "off_minute": 0,
        "reason": "Adjust for season",
    })
    await db.close()

    assert mock_scheduler.add_job.call_count == 2
    call_kwargs = [c.kwargs for c in mock_scheduler.add_job.call_args_list]
    job_ids = {kw["id"] for kw in call_kwargs}
    assert "grow_light_on" in job_ids
    assert "grow_light_off" in job_ids


@pytest.mark.asyncio
async def test_set_light_schedule_no_plug_configured(tmp_path: Path) -> None:
    """Returns error message when no grow_light plug is configured."""
    import textwrap
    toml_text = textwrap.dedent("""\
        [anthropic]
        api_key = "sk-test"
        model   = "claude-haiku-4-5-20251001"

        [telegram]
        token   = ""
        chat_id = ""

        [[plants]]
        name              = "basil-1"
        species           = "basil"
        sensor_mac        = "AA:BB:CC:DD:EE:01"
        pump_gpio         = 17
        moisture_target_min = 40
        moisture_target_max = 70
    """)
    toml_path = tmp_path / "noplug.toml"
    toml_path.write_text(toml_text)
    from flora.config import load_config
    from flora.agent.tools import ToolExecutor
    config = load_config(str(toml_path))
    db = Database(tmp_path / "test.db")
    await db.connect()

    executor = ToolExecutor(config, db)
    result = await executor.execute("set_light_schedule", {
        "on_hour": 6, "off_hour": 22, "reason": "test",
    })
    await db.close()

    assert "No grow_light" in result


# ─── smartplug.set_schedule mock path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_smartplug_set_schedule_mock_returns_true() -> None:
    """On non-Pi, set_schedule returns True without hitting hardware."""
    from flora.actuators.smartplug import set_schedule
    result = await set_schedule("192.168.1.50", "grow_light", dtime(6, 0), dtime(22, 0))
    assert result is True

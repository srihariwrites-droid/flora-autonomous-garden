"""Tests: scheduler reloads plug schedules from SQLite on startup."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from flora.config import AppConfig, PlantConfig, SmartPlugConfig
from flora.db import Database, PlugSchedule
from flora.scheduler import create_scheduler

_CONFIG = AppConfig(
    db_path="test.db",
    dashboard_port=8000,
    sensor_poll_interval=1800,
    agent_loop_interval=7200,
    anthropic_api_key="test-key",
    anthropic_model="claude-haiku-4-5-20251001",
    telegram_token="",
    telegram_chat_id="",
    plants=[
        PlantConfig(
            name="basil-1",
            species="basil",
            sensor_mac="AA:BB:CC:DD:EE:FF",
            pump_gpio=17,
        )
    ],
    smart_plugs=[
        SmartPlugConfig(alias="grow_light", host="192.168.1.50", role="grow_light")
    ],
)


async def test_create_scheduler_reloads_saved_schedule():
    """create_scheduler registers grow_light cron jobs when a saved schedule exists."""
    db = AsyncMock(spec=Database)
    db.get_plug_schedule.return_value = PlugSchedule(
        alias="grow_light",
        on_time="06:00",
        off_time="22:00",
        enabled=True,
    )

    scheduler = await create_scheduler(_CONFIG, db)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "grow_light_on" in job_ids, f"grow_light_on not found in jobs: {job_ids}"
    assert "grow_light_off" in job_ids, f"grow_light_off not found in jobs: {job_ids}"
    db.get_plug_schedule.assert_awaited_once_with("grow_light")


async def test_create_scheduler_skips_disabled_schedule():
    """create_scheduler skips cron jobs when saved schedule is disabled."""
    db = AsyncMock(spec=Database)
    db.get_plug_schedule.return_value = PlugSchedule(
        alias="grow_light",
        on_time="06:00",
        off_time="22:00",
        enabled=False,
    )

    scheduler = await create_scheduler(_CONFIG, db)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "grow_light_on" not in job_ids
    assert "grow_light_off" not in job_ids


async def test_create_scheduler_no_saved_schedule():
    """create_scheduler adds no light jobs when no schedule is persisted."""
    db = AsyncMock(spec=Database)
    db.get_plug_schedule.return_value = None

    scheduler = await create_scheduler(_CONFIG, db)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "grow_light_on" not in job_ids
    assert "grow_light_off" not in job_ids


async def test_create_scheduler_no_plug_configured():
    """create_scheduler handles config without a grow_light plug gracefully."""
    config_no_plug = AppConfig(
        db_path="test.db",
        dashboard_port=8000,
        sensor_poll_interval=1800,
        agent_loop_interval=7200,
        anthropic_api_key="test-key",
        anthropic_model="claude-haiku-4-5-20251001",
        telegram_token="",
        telegram_chat_id="",
        plants=[],
        smart_plugs=[],
    )
    db = AsyncMock(spec=Database)

    scheduler = await create_scheduler(config_no_plug, db)

    db.get_plug_schedule.assert_not_called()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "grow_light_on" not in job_ids
    assert "grow_light_off" not in job_ids


@pytest.mark.asyncio
async def test_action_log_composite_index_exists(tmp_path):
    """idx_action_plant_type_ts must exist after connect() for efficient count_recent_same_action queries."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    async with db._conn_or_raise().execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_action_plant_type_ts'"
    ) as cursor:
        row = await cursor.fetchone()
    await db.close()
    assert row is not None, "idx_action_plant_type_ts index missing from action_log"

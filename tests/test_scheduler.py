"""Tests: scheduler reloads plug schedules from SQLite on startup."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from flora.config import AppConfig, PlantConfig, SmartPlugConfig
from flora.db import Database, PlugSchedule, SensorReading
from flora.scheduler import create_scheduler, _send_daily_summary

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


_PLANT = PlantConfig(
    name="basil-1",
    species="basil",
    sensor_mac="AA:BB:CC:DD:EE:FF",
    pump_gpio=17,
    moisture_target_min=40,
    moisture_target_max=70,
)

_CONFIG_SUMMARY = AppConfig(
    db_path="test.db",
    dashboard_port=8000,
    sensor_poll_interval=1800,
    agent_loop_interval=7200,
    anthropic_api_key="test-key",
    anthropic_model="claude-haiku-4-5-20251001",
    telegram_token="",
    telegram_chat_id="",
    plants=[_PLANT],
    smart_plugs=[],
)

_TS = datetime(2026, 3, 16, 7, 0, 0)


def _reading(moisture: float) -> SensorReading:
    return SensorReading(
        plant_name="basil-1",
        timestamp=_TS,
        moisture=moisture,
        temperature=22.0,
        light=300,
        fertility=500,
        battery=90,
    )


async def test_daily_summary_reports_critical_below_10():
    """Moisture below 10% must report 'critical' in the daily summary."""
    db = AsyncMock(spec=Database)
    db.get_latest_sensor_reading.return_value = _reading(8.0)
    captured: list[list[dict]] = []

    async def fake_send(token, chat_id, summaries, **kwargs):
        captured.append(summaries)

    with patch("flora.scheduler.send_daily_summary", side_effect=fake_send):
        await _send_daily_summary(_CONFIG_SUMMARY, db)

    assert captured, "send_daily_summary was not called"
    assert captured[0][0]["status"] == "critical"


async def test_daily_summary_reports_dry_at_15_percent():
    """Moisture at 15% (between 10% and target_min=40%) must report 'dry', not 'critical'."""
    db = AsyncMock(spec=Database)
    db.get_latest_sensor_reading.return_value = _reading(15.0)
    captured: list[list[dict]] = []

    async def fake_send(token, chat_id, summaries, **kwargs):
        captured.append(summaries)

    with patch("flora.scheduler.send_daily_summary", side_effect=fake_send):
        await _send_daily_summary(_CONFIG_SUMMARY, db)

    assert captured, "send_daily_summary was not called"
    assert captured[0][0]["status"] == "dry"


async def test_create_scheduler_registers_prune_job():
    """create_scheduler must register a weekly prune_old_readings cron job."""
    db = AsyncMock(spec=Database)
    db.get_plug_schedule.return_value = None

    scheduler = await create_scheduler(_CONFIG, db)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "prune_old_readings" in job_ids, f"prune_old_readings not in jobs: {job_ids}"


@pytest.mark.asyncio
async def test_prune_old_readings_deletes_old_rows(tmp_path):
    """prune_old_readings deletes rows older than the threshold and keeps newer ones."""
    from flora.db import AmbientReading

    db = Database(tmp_path / "test.db")
    await db.connect()

    now = datetime(2026, 3, 16, 12, 0, 0)
    old_ts = now - timedelta(days=100)
    new_ts = now - timedelta(days=10)

    await db.insert_sensor_reading(SensorReading(
        plant_name="basil-1", timestamp=old_ts,
        moisture=40.0, temperature=22.0, light=300, fertility=500, battery=90,
    ))
    await db.insert_sensor_reading(SensorReading(
        plant_name="basil-1", timestamp=new_ts,
        moisture=50.0, temperature=22.0, light=300, fertility=500, battery=90,
    ))
    await db.insert_ambient_reading(AmbientReading(
        timestamp=old_ts, temperature=21.0, humidity=55.0, light_lux=200.0,
    ))
    await db.insert_ambient_reading(AmbientReading(
        timestamp=new_ts, temperature=21.0, humidity=55.0, light_lux=200.0,
    ))

    sensor_del, ambient_del = await db.prune_old_readings(days=90)
    await db.close()

    assert sensor_del == 1, f"Expected 1 sensor row deleted, got {sensor_del}"
    assert ambient_del == 1, f"Expected 1 ambient row deleted, got {ambient_del}"


@pytest.mark.asyncio
async def test_prune_old_readings_keeps_recent_rows(tmp_path):
    """prune_old_readings returns zero counts when all rows are within the threshold."""
    db = Database(tmp_path / "test.db")
    await db.connect()

    recent_ts = datetime(2026, 3, 16, 12, 0, 0) - timedelta(days=5)
    await db.insert_sensor_reading(SensorReading(
        plant_name="basil-1", timestamp=recent_ts,
        moisture=40.0, temperature=22.0, light=300, fertility=500, battery=90,
    ))

    sensor_del, ambient_del = await db.prune_old_readings(days=90)
    await db.close()

    assert sensor_del == 0
    assert ambient_del == 0


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

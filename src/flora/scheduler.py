"""APScheduler setup: sensor polling every 30min, agent loop every 2hr."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import]

from flora.config import AppConfig
from flora.db import ActionRecord, AmbientReading, Database, SensorReading
from flora.sensors.miflora import read_miflora
from flora.sensors.sht31 import read_sht31
from flora.sensors.bh1750 import read_bh1750

from flora.agent.loop import AgentLoop
from flora.agent.watchers import check_watering_effectiveness
from flora.notifications import send_daily_summary, send_telegram
from flora.sensors.camera import capture_photo

logger = logging.getLogger(__name__)


async def _poll_sensors(config: AppConfig, db: Database) -> None:
    """Poll all sensors and store readings."""
    now = datetime.utcnow()
    logger.info("Polling sensors at %s", now.isoformat())

    # Poll each plant's Mi Flora sensor
    for plant in config.plants:
        reading = await read_miflora(plant.sensor_mac)
        if reading is None:
            logger.warning("No reading for %s (%s)", plant.name, plant.sensor_mac)
            continue
        await db.insert_sensor_reading(SensorReading(
            plant_name=plant.name,
            timestamp=now,
            moisture=reading.moisture,
            temperature=reading.temperature,
            light=reading.light,
            fertility=reading.fertility,
            battery=reading.battery,
        ))
        logger.debug("Stored reading for %s: moisture=%.1f%%", plant.name, reading.moisture)

        # Auto-water rule: water immediately if configured threshold is breached
        threshold = plant.auto_water_if_below
        if threshold is not None and reading.moisture is not None and reading.moisture < threshold:
            # Enforce per-plant minimum interval between auto-water firings
            min_interval_hours = plant.auto_water_min_interval_minutes / 60
            recent = await db.count_recent_same_action(plant.name, "auto_water", hours=min_interval_hours)
            if recent > 0:
                logger.debug(
                    "Auto-water skipped for %s: watered within last %d min",
                    plant.name, plant.auto_water_min_interval_minutes,
                )
            else:
                duration = max(5, min(30, plant.auto_water_duration_seconds))
                logger.info(
                    "Auto-water triggered for %s: moisture=%.1f%% < %d%%",
                    plant.name, reading.moisture, threshold,
                )
                from flora.actuators.pump import water_plant as _pump
                await _pump(plant.pump_gpio, duration)
                await db.log_action(ActionRecord(
                    plant_name=plant.name,
                    timestamp=now,
                    action_type="auto_water",
                    parameters={"duration_seconds": duration, "moisture": reading.moisture, "threshold": threshold},
                    reasoning=f"Auto-water rule: moisture {reading.moisture:.1f}% < {threshold}%",
                    claude_model="rule",
                ))

        # Watering-effectiveness watcher — only relevant for plants with auto-water
        if plant.auto_water_if_below is not None:
            ineffective, fire_count, current_moisture = await check_watering_effectiveness(db, plant)
            if ineffective:
                cooldown = await db.count_recent_same_action(plant.name, "pump_alert", hours=12)
                if cooldown == 0:
                    msg = (
                        f"Plant {plant.name}: pump fired {fire_count}\u00d7 in 6h but moisture "
                        f"unchanged ({current_moisture:.0f}%). Check reservoir/pump."
                    )
                    await send_telegram(config.telegram_token, config.telegram_chat_id, msg)
                    await db.log_action(ActionRecord(
                        plant_name=plant.name,
                        timestamp=now,
                        action_type="pump_alert",
                        parameters={"count": fire_count, "moisture": current_moisture},
                        reasoning="Auto-watering ineffective — escalated via Telegram",
                        claude_model="rule",
                    ))
                    logger.warning(
                        "Pump ineffective for %s (%d firings, moisture=%.0f%%)",
                        plant.name, fire_count, current_moisture,
                    )

    # Poll ambient sensors
    sht31 = await read_sht31()
    bh1750 = await read_bh1750()
    if sht31 or bh1750:
        await db.insert_ambient_reading(AmbientReading(
            timestamp=now,
            temperature=sht31.temperature if sht31 else None,
            humidity=sht31.humidity if sht31 else None,
            light_lux=bh1750.light_lux if bh1750 else None,
        ))


async def _run_agent(config: AppConfig, db: Database) -> None:
    """Run one agent reasoning cycle."""
    logger.info("Starting agent reasoning loop")
    agent = AgentLoop(config, db)
    await agent.run_once()


async def _send_daily_summary(config: AppConfig, db: Database) -> None:
    """Collect latest readings and send daily Telegram summary."""
    summaries: list[dict[str, object]] = []
    for plant in config.plants:
        reading = await db.get_latest_sensor_reading(plant.name)
        if reading:
            # Simple health status based on moisture
            if reading.moisture is None:
                status = "unknown"
            elif reading.moisture < 20:
                status = "critical"
            elif reading.moisture < plant.moisture_target_min:
                status = "dry"
            elif reading.moisture > plant.moisture_target_max:
                status = "wet"
            else:
                status = "healthy"
            summaries.append({
                "name": plant.name,
                "moisture": reading.moisture,
                "temperature": reading.temperature,
                "status": status,
            })
    # Collect latest photo per plant
    photos_dir = Path("photos")
    photo_paths: dict[str, Path] = {}
    for plant in config.plants:
        candidates = list(photos_dir.glob(f"{plant.name}_*.jpg")) if photos_dir.is_dir() else []
        if candidates:
            photo_paths[plant.name] = max(candidates, key=lambda p: p.stat().st_mtime)

    await send_daily_summary(
        config.telegram_token,
        config.telegram_chat_id,
        summaries,
        photo_paths=photo_paths or None,
    )


async def _run_photo_capture(config: AppConfig, db: Database) -> None:
    """Capture a daily photo for each plant."""
    photo_dir = Path("photos")
    for plant in config.plants:
        result = await capture_photo(
            plant.name,
            save_dir=photo_dir,
            camera_index=plant.camera_index or 0,
        )
        if result:
            logger.info("Photo captured for %s: %s", plant.name, result.path)


async def create_scheduler(config: AppConfig, db: Database) -> AsyncIOScheduler:
    """Create and configure the APScheduler instance.

    Queries SQLite for any persisted plug schedules and re-registers their
    cron jobs so they survive a Pi reboot.
    """
    from flora.actuators.smartplug import toggle_plug

    scheduler = AsyncIOScheduler()

    # Sensor poll: every 30 minutes (configurable)
    scheduler.add_job(
        _poll_sensors,
        trigger="interval",
        seconds=config.sensor_poll_interval,
        args=[config, db],
        id="sensor_poll",
        name="Sensor poll",
        next_run_time=datetime.now(),  # run immediately on start
    )

    # Agent loop: every 2 hours (configurable)
    scheduler.add_job(
        _run_agent,
        trigger="interval",
        seconds=config.agent_loop_interval,
        args=[config, db],
        id="agent_loop",
        name="Agent reasoning loop",
    )

    # Daily summary: 7am every day
    scheduler.add_job(
        _send_daily_summary,
        trigger="cron",
        hour=7,
        minute=0,
        args=[config, db],
        id="daily_summary",
        name="Daily summary",
        replace_existing=True,
    )

    # Daily photo capture: 7am every day
    scheduler.add_job(
        _run_photo_capture,
        trigger="cron",
        hour=7,
        minute=0,
        args=[config, db],
        id="daily_photo",
        name="Daily photo capture",
        replace_existing=True,
    )

    # Reload persisted plug schedules so cron jobs survive reboots
    plug = config.plug_by_role("grow_light")
    if plug is not None:
        saved = await db.get_plug_schedule(plug.alias)
        if saved is not None and saved.enabled:
            on_h, on_m = (int(x) for x in saved.on_time.split(":"))
            off_h, off_m = (int(x) for x in saved.off_time.split(":"))
            scheduler.add_job(
                toggle_plug,
                trigger="cron",
                hour=on_h,
                minute=on_m,
                args=[plug.host, plug.alias, True],
                id="grow_light_on",
                name="Grow light ON",
                replace_existing=True,
            )
            scheduler.add_job(
                toggle_plug,
                trigger="cron",
                hour=off_h,
                minute=off_m,
                args=[plug.host, plug.alias, False],
                id="grow_light_off",
                name="Grow light OFF",
                replace_existing=True,
            )
            logger.info(
                "Reloaded grow_light schedule from DB: ON=%s OFF=%s",
                saved.on_time,
                saved.off_time,
            )

    return scheduler

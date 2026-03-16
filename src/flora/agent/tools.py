"""Claude tool implementations for Flora agent."""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import]

from flora.actuators.pump import water_plant as _water_plant
from flora.actuators.smartplug import toggle_plug
from flora.config import AppConfig
from flora.db import ActionRecord, Database, JournalEntry, PlugSchedule
from flora.notifications import send_telegram

logger = logging.getLogger(__name__)

# Tool definitions for the Claude API
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "water_plant",
        "description": "Activate the water pump for a specific plant. Use after reviewing sensor history to confirm moisture is below target.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_name": {"type": "string", "description": "Name of the plant to water"},
                "duration_seconds": {"type": "integer", "description": "Pump duration in seconds (5-30)", "minimum": 5, "maximum": 30},
                "reason": {"type": "string", "description": "Brief reason for watering"},
            },
            "required": ["plant_name", "duration_seconds", "reason"],
        },
    },
    {
        "name": "set_light_schedule",
        "description": (
            "Set the daily grow-light on/off schedule. "
            "Registers two APScheduler cron jobs (grow_light_on, grow_light_off) that toggle "
            "the Kasa smart plug at the specified times each day, and persists the schedule to "
            "SQLite so it survives restarts. Call this to extend or shorten the photoperiod."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "on_hour": {"type": "integer", "description": "Hour to turn light ON (0-23)"},
                "on_minute": {"type": "integer", "description": "Minute to turn light ON (0-59)", "default": 0},
                "off_hour": {"type": "integer", "description": "Hour to turn light OFF (0-23)"},
                "off_minute": {"type": "integer", "description": "Minute to turn light OFF (0-59)", "default": 0},
                "reason": {"type": "string", "description": "Reason for schedule change"},
            },
            "required": ["on_hour", "off_hour", "reason"],
        },
    },
    {
        "name": "toggle_device",
        "description": "Turn a smart plug device (humidifier, fan) on or off.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_role": {"type": "string", "description": "Device role: humidifier | fan | grow_light"},
                "on": {"type": "boolean", "description": "True to turn on, False to turn off"},
                "reason": {"type": "string", "description": "Reason for toggling"},
            },
            "required": ["device_role", "on", "reason"],
        },
    },
    {
        "name": "update_plant_journal",
        "description": "Write an observation or action note to a plant's journal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_name": {"type": "string", "description": "Name of the plant"},
                "entry_type": {"type": "string", "description": "Type: observation | action | alert | note"},
                "content": {"type": "string", "description": "Journal entry text (1-2 sentences)"},
            },
            "required": ["plant_name", "entry_type", "content"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Send a Telegram notification to the user for issues requiring human attention.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_name": {"type": "string", "description": "Plant involved (or 'system' for non-plant issues)"},
                "issue": {"type": "string", "description": "What was observed"},
                "tried": {"type": "string", "description": "What Flora already tried"},
                "action_needed": {"type": "string", "description": "What the human should do"},
            },
            "required": ["plant_name", "issue", "tried", "action_needed"],
        },
    },
    {
        "name": "get_ambient_reading",
        "description": "Query the latest ambient room conditions (temperature, humidity, light lux). Call this before making decisions about light schedules or when assessing whether room conditions are affecting plant health.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Number of hours to average (1-48). Default 1 returns only the latest reading.", "default": 1, "minimum": 1, "maximum": 48},
            },
            "required": [],
        },
    },
    {
        "name": "get_sensor_history",
        "description": "Query sensor history for a plant. Always call this before watering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plant_name": {"type": "string", "description": "Name of the plant"},
                "hours": {"type": "integer", "description": "Hours of history to retrieve (1-168)", "default": 24, "minimum": 1, "maximum": 168},
            },
            "required": ["plant_name"],
        },
    },
]


class ToolExecutor:
    """Executes Claude tool calls for the Flora agent."""

    def __init__(
        self,
        config: AppConfig,
        db: Database,
        scheduler: "AsyncIOScheduler | None" = None,
    ) -> None:
        self._config = config
        self._db = db
        self._scheduler = scheduler

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Dispatch a tool call and return the string result."""
        handlers = {
            "water_plant": self._water_plant,
            "set_light_schedule": self._set_light_schedule,
            "toggle_device": self._toggle_device,
            "update_plant_journal": self._update_plant_journal,
            "escalate_to_human": self._escalate_to_human,
            "get_sensor_history": self._get_sensor_history,
            "get_ambient_reading": self._get_ambient_reading,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return f"Unknown tool: {tool_name}"
        try:
            return await handler(tool_input)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return f"Error executing {tool_name}: {exc}"

    async def _water_plant(self, inp: dict[str, Any]) -> str:
        plant_name: str = inp["plant_name"]
        duration: int = max(5, min(30, int(inp["duration_seconds"])))
        reason: str = inp["reason"]

        plant = self._config.plant_by_name(plant_name)
        if plant is None:
            return f"Unknown plant: {plant_name}"

        success = await _water_plant(plant.pump_gpio, duration)
        status = "success" if success else "failed"

        await self._db.log_action(ActionRecord(
            plant_name=plant_name,
            timestamp=datetime.utcnow(),
            action_type="water_plant",
            parameters={"duration_seconds": duration, "gpio": plant.pump_gpio},
            reasoning=reason,
            claude_model=self._config.anthropic_model,
        ))
        return f"Watered {plant_name} for {duration}s: {status}"

    async def _set_light_schedule(self, inp: dict[str, Any]) -> str:
        on_hour: int = int(inp["on_hour"])
        on_minute: int = int(inp.get("on_minute", 0))
        off_hour: int = int(inp["off_hour"])
        off_minute: int = int(inp.get("off_minute", 0))
        reason: str = inp["reason"]

        plug = self._config.plug_by_role("grow_light")
        if plug is None:
            return "No grow_light smart plug configured."

        # dtime() raises ValueError for out-of-range hours/minutes — validates inputs
        on_time = dtime(on_hour, on_minute)
        off_time = dtime(off_hour, off_minute)
        on_str = f"{on_time.hour:02d}:{on_time.minute:02d}"
        off_str = f"{off_time.hour:02d}:{off_time.minute:02d}"

        # Persist schedule to SQLite so it survives restarts
        await self._db.upsert_plug_schedule(PlugSchedule(
            alias=plug.alias,
            on_time=on_str,
            off_time=off_str,
            enabled=True,
        ))

        # Register (or replace) APScheduler cron jobs for the light toggle
        if self._scheduler is not None:
            self._scheduler.add_job(
                toggle_plug,
                trigger="cron",
                hour=on_time.hour,
                minute=on_time.minute,
                args=[plug.host, plug.alias, True],
                id="grow_light_on",
                name="Grow light ON",
                replace_existing=True,
            )
            self._scheduler.add_job(
                toggle_plug,
                trigger="cron",
                hour=off_time.hour,
                minute=off_time.minute,
                args=[plug.host, plug.alias, False],
                id="grow_light_off",
                name="Grow light OFF",
                replace_existing=True,
            )
            logger.info("Registered cron jobs: grow_light ON=%s OFF=%s", on_str, off_str)

        await self._db.log_action(ActionRecord(
            plant_name=None,
            timestamp=datetime.utcnow(),
            action_type="set_light_schedule",
            parameters={"on": on_str, "off": off_str},
            reasoning=reason,
            claude_model=self._config.anthropic_model,
        ))
        return f"Light schedule set ON={on_str} OFF={off_str}: ok"

    async def _toggle_device(self, inp: dict[str, Any]) -> str:
        role: str = inp["device_role"]
        on: bool = bool(inp["on"])
        reason: str = inp["reason"]

        plug = self._config.plug_by_role(role)
        if plug is None:
            return f"No smart plug with role '{role}' configured."

        success = await toggle_plug(plug.host, plug.alias, on)
        await self._db.log_action(ActionRecord(
            plant_name=None,
            timestamp=datetime.utcnow(),
            action_type="toggle_device",
            parameters={"role": role, "on": on},
            reasoning=reason,
            claude_model=self._config.anthropic_model,
        ))
        return f"Device '{role}' {'ON' if on else 'OFF'}: {'ok' if success else 'failed'}"

    async def _update_plant_journal(self, inp: dict[str, Any]) -> str:
        plant_name: str = inp["plant_name"]
        entry_type: str = inp["entry_type"]
        content: str = inp["content"]

        await self._db.add_journal_entry(JournalEntry(
            plant_name=plant_name,
            timestamp=datetime.utcnow(),
            entry_type=entry_type,
            content=content,
        ))
        return f"Journal updated for {plant_name}."

    async def _escalate_to_human(self, inp: dict[str, Any]) -> str:
        plant_name: str = inp["plant_name"]
        issue: str = inp["issue"]
        tried: str = inp["tried"]
        action_needed: str = inp["action_needed"]

        message = (
            f"Flora Alert — {plant_name}\n\n"
            f"Issue: {issue}\n"
            f"Already tried: {tried}\n"
            f"Action needed: {action_needed}"
        )
        success = await send_telegram(
            self._config.telegram_token,
            self._config.telegram_chat_id,
            message,
        )
        await self._db.log_action(ActionRecord(
            plant_name=plant_name,
            timestamp=datetime.utcnow(),
            action_type="escalate_to_human",
            parameters={"issue": issue, "tried": tried, "action_needed": action_needed},
            reasoning=issue,
            claude_model=self._config.anthropic_model,
        ))
        return f"Telegram escalation sent: {'ok' if success else 'failed'}"

    async def _get_sensor_history(self, inp: dict[str, Any]) -> str:
        plant_name: str = inp["plant_name"]
        hours: int = int(inp.get("hours", 24))

        readings = await self._db.get_sensor_history(plant_name, hours=hours, limit=100)
        if not readings:
            return f"No sensor history for {plant_name} in the last {hours} hours."

        lines = [f"Sensor history for {plant_name} (last {hours}h, {len(readings)} readings):"]
        for r in readings[:20]:
            ts = r.timestamp.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"  {ts}: moisture={r.moisture}%, temp={r.temperature}°C, "
                f"light={r.light}lux, fertility={r.fertility}µS/cm"
            )
        if len(readings) > 20:
            lines.append(f"  ... ({len(readings) - 20} more readings)")
        return "\n".join(lines)

    async def _get_ambient_reading(self, inp: dict[str, Any]) -> str:
        hours: int = max(1, min(48, int(inp.get("hours", 1))))

        if hours == 1:
            reading = await self._db.get_latest_ambient()
            if reading is None:
                return "No ambient reading available."
            ts = reading.timestamp.strftime("%Y-%m-%d %H:%M")
            return (
                f"Ambient (latest, {ts}): "
                f"temp={reading.temperature}°C, "
                f"humidity={reading.humidity}%RH, "
                f"light={reading.light_lux}lux"
            )

        readings = await self._db.get_ambient_readings(hours)
        if not readings:
            return f"No ambient readings in the last {hours} hours."

        temps = [r.temperature for r in readings if r.temperature is not None]
        humids = [r.humidity for r in readings if r.humidity is not None]
        luxes = [r.light_lux for r in readings if r.light_lux is not None]

        avg_temp = round(sum(temps) / len(temps), 1) if temps else None
        avg_humid = round(sum(humids) / len(humids), 1) if humids else None
        avg_lux = round(sum(luxes) / len(luxes), 1) if luxes else None

        return (
            f"Ambient average over last {hours}h ({len(readings)} readings): "
            f"temp={avg_temp}°C, "
            f"humidity={avg_humid}%RH, "
            f"light={avg_lux}lux"
        )

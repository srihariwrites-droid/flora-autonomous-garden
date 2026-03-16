"""Async SQLite database layer for Flora sensor time-series and plant journals."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_name  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    moisture    REAL,
    temperature REAL,
    light       INTEGER,
    fertility   INTEGER,
    battery     INTEGER
);

CREATE TABLE IF NOT EXISTS ambient_readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    temperature REAL,
    humidity    REAL,
    light_lux   REAL
);

CREATE TABLE IF NOT EXISTS plant_journals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_name  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    entry_type  TEXT    NOT NULL,
    content     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS action_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_name   TEXT,
    timestamp    TEXT    NOT NULL,
    action_type  TEXT    NOT NULL,
    parameters   TEXT    NOT NULL,
    reasoning    TEXT    NOT NULL,
    claude_model TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plug_schedules (
    alias    TEXT    PRIMARY KEY,
    on_time  TEXT    NOT NULL,
    off_time TEXT    NOT NULL,
    enabled  INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_sensor_plant_ts   ON sensor_readings(plant_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_ambient_ts        ON ambient_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_journal_plant_ts  ON plant_journals(plant_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_action_ts         ON action_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_action_plant_type_ts ON action_log(plant_name, action_type, timestamp);
"""


@dataclass
class SensorReading:
    plant_name: str
    timestamp: datetime
    moisture: float | None
    temperature: float | None
    light: int | None
    fertility: int | None
    battery: int | None


@dataclass
class AmbientReading:
    timestamp: datetime
    temperature: float | None
    humidity: float | None
    light_lux: float | None


@dataclass
class JournalEntry:
    plant_name: str
    timestamp: datetime
    entry_type: str
    content: str


@dataclass
class PlugSchedule:
    alias: str
    on_time: str    # HH:MM
    off_time: str   # HH:MM
    enabled: bool


@dataclass
class ActionRecord:
    plant_name: str | None
    timestamp: datetime
    action_type: str
    parameters: dict[str, Any]
    reasoning: str
    claude_model: str


class Database:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _conn_or_raise(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    # --- Sensor readings ---

    async def insert_sensor_reading(self, r: SensorReading) -> None:
        conn = self._conn_or_raise()
        await conn.execute(
            """INSERT INTO sensor_readings
               (plant_name, timestamp, moisture, temperature, light, fertility, battery)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (r.plant_name, r.timestamp.isoformat(), r.moisture,
             r.temperature, r.light, r.fertility, r.battery),
        )
        await conn.commit()

    async def get_sensor_history(
        self,
        plant_name: str,
        hours: int = 168,  # 7 days
        limit: int = 500,
    ) -> list[SensorReading]:
        conn = self._conn_or_raise()
        cutoff = datetime.utcnow().replace(microsecond=0) - timedelta(hours=hours)
        async with conn.execute(
            """SELECT * FROM sensor_readings
               WHERE plant_name = ? AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (plant_name, cutoff.isoformat(), limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            SensorReading(
                plant_name=row["plant_name"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                moisture=row["moisture"],
                temperature=row["temperature"],
                light=row["light"],
                fertility=row["fertility"],
                battery=row["battery"],
            )
            for row in rows
        ]

    async def get_latest_sensor_reading(self, plant_name: str) -> SensorReading | None:
        conn = self._conn_or_raise()
        async with conn.execute(
            """SELECT * FROM sensor_readings WHERE plant_name = ?
               ORDER BY timestamp DESC LIMIT 1""",
            (plant_name,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return SensorReading(
            plant_name=row["plant_name"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            moisture=row["moisture"],
            temperature=row["temperature"],
            light=row["light"],
            fertility=row["fertility"],
            battery=row["battery"],
        )

    # --- Ambient readings ---

    async def insert_ambient_reading(self, r: AmbientReading) -> None:
        conn = self._conn_or_raise()
        await conn.execute(
            """INSERT INTO ambient_readings (timestamp, temperature, humidity, light_lux)
               VALUES (?, ?, ?, ?)""",
            (r.timestamp.isoformat(), r.temperature, r.humidity, r.light_lux),
        )
        await conn.commit()

    async def get_latest_ambient(self) -> AmbientReading | None:
        conn = self._conn_or_raise()
        async with conn.execute(
            "SELECT * FROM ambient_readings ORDER BY timestamp DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return AmbientReading(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            temperature=row["temperature"],
            humidity=row["humidity"],
            light_lux=row["light_lux"],
        )

    async def get_ambient_readings(self, hours: int) -> list[AmbientReading]:
        conn = self._conn_or_raise()
        async with conn.execute(
            """SELECT * FROM ambient_readings
               WHERE timestamp >= datetime('now', ? || ' hours')
               ORDER BY timestamp DESC""",
            (f"-{hours}",),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            AmbientReading(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                temperature=row["temperature"],
                humidity=row["humidity"],
                light_lux=row["light_lux"],
            )
            for row in rows
        ]

    # --- Plant journals ---

    async def add_journal_entry(self, entry: JournalEntry) -> None:
        conn = self._conn_or_raise()
        await conn.execute(
            """INSERT INTO plant_journals (plant_name, timestamp, entry_type, content)
               VALUES (?, ?, ?, ?)""",
            (entry.plant_name, entry.timestamp.isoformat(), entry.entry_type, entry.content),
        )
        await conn.commit()

    async def get_journal(
        self, plant_name: str, limit: int = 50
    ) -> list[JournalEntry]:
        conn = self._conn_or_raise()
        async with conn.execute(
            """SELECT * FROM plant_journals WHERE plant_name = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (plant_name, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            JournalEntry(
                plant_name=row["plant_name"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                entry_type=row["entry_type"],
                content=row["content"],
            )
            for row in rows
        ]

    # --- Action log ---

    async def log_action(self, record: ActionRecord) -> None:
        conn = self._conn_or_raise()
        await conn.execute(
            """INSERT INTO action_log
               (plant_name, timestamp, action_type, parameters, reasoning, claude_model)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                record.plant_name,
                record.timestamp.isoformat(),
                record.action_type,
                json.dumps(record.parameters),
                record.reasoning,
                record.claude_model,
            ),
        )
        await conn.commit()

    async def get_recent_actions(
        self, limit: int = 100, plant_name: str | None = None
    ) -> list[ActionRecord]:
        conn = self._conn_or_raise()
        if plant_name:
            query = """SELECT * FROM action_log WHERE plant_name = ?
                       ORDER BY timestamp DESC LIMIT ?"""
            params: tuple[Any, ...] = (plant_name, limit)
        else:
            query = "SELECT * FROM action_log ORDER BY timestamp DESC LIMIT ?"
            params = (limit,)
        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [
            ActionRecord(
                plant_name=row["plant_name"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                action_type=row["action_type"],
                parameters=json.loads(row["parameters"]),
                reasoning=row["reasoning"],
                claude_model=row["claude_model"],
            )
            for row in rows
        ]

    async def count_recent_same_action(
        self, plant_name: str, action_type: str, hours: int = 6
    ) -> int:
        """Count how many times the same action was taken recently (for escalation)."""
        conn = self._conn_or_raise()
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        async with conn.execute(
            """SELECT COUNT(*) FROM action_log
               WHERE plant_name = ? AND action_type = ? AND timestamp >= ?""",
            (plant_name, action_type, cutoff),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    # --- Plug schedules ---

    async def upsert_plug_schedule(self, schedule: PlugSchedule) -> None:
        conn = self._conn_or_raise()
        await conn.execute(
            """INSERT INTO plug_schedules (alias, on_time, off_time, enabled)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(alias) DO UPDATE SET
                   on_time  = excluded.on_time,
                   off_time = excluded.off_time,
                   enabled  = excluded.enabled""",
            (schedule.alias, schedule.on_time, schedule.off_time, int(schedule.enabled)),
        )
        await conn.commit()

    async def get_plug_schedule(self, alias: str) -> PlugSchedule | None:
        conn = self._conn_or_raise()
        async with conn.execute(
            "SELECT alias, on_time, off_time, enabled FROM plug_schedules WHERE alias = ?",
            (alias,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return PlugSchedule(
            alias=row["alias"],
            on_time=row["on_time"],
            off_time=row["off_time"],
            enabled=bool(row["enabled"]),
        )

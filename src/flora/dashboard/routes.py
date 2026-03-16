"""Dashboard routes for Flora."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from flora.analytics import estimate_hours_to_threshold
from flora.config import AppConfig, PlantConfig, append_plant_to_toml
from flora.db import Database, SensorReading

# GPIO pins commonly available on Pi for relay use (BCM numbering)
_CANDIDATE_GPIO_PINS = [4, 17, 18, 22, 23, 24, 25, 27]


def create_router(
    config: AppConfig,
    db: Database,
    templates: Jinja2Templates,
) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        plant_data = []
        for plant in config.plants:
            reading = await db.get_latest_sensor_reading(plant.name)
            plant_data.append({
                "config": plant,
                "reading": reading,
                "status": _status(reading.moisture if reading else None, plant.moisture_target_min, plant.moisture_target_max),
                "reading_age_hours": _reading_age_hours(reading),
            })
        ambient = await db.get_latest_ambient()
        actions = await db.get_recent_actions(limit=5)
        plants_art_json = json.dumps([
            {
                "name": p["config"].name,
                "species": p["config"].species,
                # Use real data when available; fall back to species-typical mock values so
                # the canvas shows a plausible plant before any sensor has reported.
                # Both moisture and status use the same branch so canvas and card stay consistent.
                "moisture": p["reading"].moisture if p["reading"] else _mock_moisture(p["config"].species),
                "status": p["status"] if p["reading"] else _mock_status(p["config"].species),
                "has_reading": p["reading"] is not None,
            }
            for p in plant_data
        ])
        return templates.TemplateResponse(
            request,
            "index.html",
            {"plants": plant_data, "ambient": ambient, "actions": actions,
             "plants_art_json": plants_art_json},
        )

    @router.get("/plants/new", response_class=HTMLResponse)
    async def commissioning_page(request: Request) -> HTMLResponse:
        used_gpio = {p.pump_gpio for p in config.plants}
        free_gpio = [p for p in _CANDIDATE_GPIO_PINS if p not in used_gpio]
        used_macs = {p.sensor_mac for p in config.plants}
        return templates.TemplateResponse(
            request,
            "commissioning.html",
            {"free_gpio": free_gpio, "used_macs": used_macs},
        )

    @router.get("/plants/{name}", response_class=HTMLResponse)
    async def plant_detail(request: Request, name: str) -> HTMLResponse:
        plant = config.plant_by_name(name)
        if plant is None:
            return HTMLResponse("<h1>Plant not found</h1>", status_code=404)
        reading = await db.get_latest_sensor_reading(name)
        journal = await db.get_journal(name, limit=30)
        actions = await db.get_recent_actions(limit=20, plant_name=name)
        recent_readings = await db.get_sensor_history(name, hours=6, limit=50)
        hours_to_water = estimate_hours_to_threshold(recent_readings, plant.moisture_target_min)
        return templates.TemplateResponse(
            request,
            "plant.html",
            {
                "plant": plant,
                "reading": reading,
                "journal": journal,
                "actions": actions,
                "status": _status(reading.moisture if reading else None, plant.moisture_target_min, plant.moisture_target_max),
                "reading_age_hours": _reading_age_hours(reading),
                "hours_to_water": hours_to_water,
            },
        )

    @router.post("/plants/{name}/water", response_class=HTMLResponse)
    async def manual_water(name: str, duration: int = Form(default=10)) -> HTMLResponse:
        plant = config.plant_by_name(name)
        if plant is None:
            return HTMLResponse("<p>Plant not found</p>", status_code=404)
        duration = max(5, min(duration, 30))  # clamp 5-30s, matching agent and scheduler
        from flora.actuators.pump import water_plant as _pump
        from flora.db import ActionRecord
        success = await _pump(plant.pump_gpio, duration)
        await db.log_action(ActionRecord(
            plant_name=name,
            timestamp=datetime.utcnow(),
            action_type="manual_water",
            parameters={"duration_seconds": duration},
            reasoning="Manual trigger from dashboard",
            claude_model="manual",
        ))
        status = "success" if success else "failed"
        return HTMLResponse(
            f'<div class="alert alert-info">Watered {name} for {duration}s: {status}</div>'
        )

    @router.get("/api/plants")
    async def plants_api() -> JSONResponse:
        result = []
        for plant in config.plants:
            reading = await db.get_latest_sensor_reading(plant.name)
            age_hours = _reading_age_hours(reading)
            result.append({
                "name": plant.name,
                "species": plant.species,
                "status": _status(reading.moisture if reading else None, plant.moisture_target_min, plant.moisture_target_max),
                "moisture": reading.moisture if reading else None,
                "temperature": reading.temperature if reading else None,
                "light": reading.light if reading else None,
                "battery": reading.battery if reading else None,
                "reading_age_hours": age_hours,
                "moisture_target_min": plant.moisture_target_min,
                "moisture_target_max": plant.moisture_target_max,
            })
        return JSONResponse(result)

    @router.get("/api/health")
    async def health_api() -> JSONResponse:
        """System health check: db connectivity and freshness of sensor data."""
        readings = []
        for plant in config.plants:
            r = await db.get_latest_sensor_reading(plant.name)
            if r is not None:
                readings.append(r)

        if readings:
            newest = max(readings, key=lambda r: r.timestamp)
            age_seconds = (datetime.utcnow() - newest.timestamp).total_seconds()
            status = "ok" if age_seconds < 3600 else "degraded"
        else:
            age_seconds = None
            status = "degraded"

        return JSONResponse({
            "status": status,
            "plants": len(config.plants),
            "latest_reading_age_seconds": age_seconds,
            "db": "connected",
        })

    @router.get("/api/plants/{name}/history")
    async def plant_history_api(name: str, hours: int = 48) -> JSONResponse:
        readings = await db.get_sensor_history(name, hours=hours, limit=200)
        data = [
            {
                "ts": r.timestamp.strftime("%Y-%m-%dT%H:%M"),
                "moisture": r.moisture,
                "temperature": r.temperature,
                "light": r.light,
                "fertility": r.fertility,
            }
            for r in reversed(readings)
        ]
        return JSONResponse({"plant": name, "hours": hours, "readings": data})

    @router.get("/api/plants/{name}/history.json")
    async def plant_history_sparkline(name: str) -> JSONResponse:
        """7-day moisture sparkline data for Chart.js (max 100 data points)."""
        readings = list(reversed(await db.get_sensor_history(name, hours=168, limit=100)))

        return JSONResponse({
            "timestamps": [r.timestamp.strftime("%Y-%m-%dT%H:%M") for r in readings],
            "moisture": [r.moisture for r in readings],
            "temperature": [r.temperature for r in readings],
        })

    @router.get("/api/plants/{name}/export.csv", response_model=None)
    async def export_plant_csv(name: str) -> StreamingResponse | HTMLResponse:
        """CSV download of the last 7 days of sensor readings."""
        plant = config.plant_by_name(name)
        if plant is None:
            return HTMLResponse("<h1>Plant not found</h1>", status_code=404)
        readings = await db.get_sensor_history(name, hours=168, limit=10000)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["timestamp", "moisture", "temperature", "light", "fertility", "battery"])
        for r in reversed(readings):
            writer.writerow([
                r.timestamp.isoformat(),
                r.moisture,
                r.temperature,
                r.light,
                r.fertility,
                r.battery,
            ])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}-history.csv"'},
        )

    @router.get("/actions", response_class=HTMLResponse)
    async def actions_page(request: Request) -> HTMLResponse:
        actions = await db.get_recent_actions(limit=100)
        return templates.TemplateResponse(
            request,
            "actions.html",
            {"actions": actions},
        )

    @router.get("/api/commissioning/scan")
    async def commissioning_scan() -> JSONResponse:
        """Scan for nearby Mi Flora BLE sensors not already assigned."""
        used_macs = {p.sensor_mac for p in config.plants}
        try:
            from flora.sensors.miflora import scan_miflora  # type: ignore[import]
            found = await scan_miflora()
            new_macs = [m for m in found if m not in used_macs]
            return JSONResponse({"macs": new_macs, "scanned": True})
        except Exception:
            # Non-Pi or scan not supported — return empty list with hint
            return JSONResponse({"macs": [], "scanned": False, "hint": "Enter MAC manually"})

    @router.post("/api/commissioning/test-pump")
    async def commissioning_test_pump(
        gpio: int = Form(...),
        duration: int = Form(default=3),
    ) -> JSONResponse:
        from flora.actuators.pump import water_plant as _pump
        duration = max(1, min(5, duration))
        success = await _pump(gpio, duration)
        return JSONResponse({"ok": success, "gpio": gpio, "duration": duration})

    @router.post("/plants/new")
    async def commissioning_save(
        name: str = Form(...),
        species: str = Form(...),
        sensor_mac: str = Form(...),
        pump_gpio: int = Form(...),
        moisture_target_min: int = Form(default=40),
        moisture_target_max: int = Form(default=70),
    ) -> RedirectResponse:
        plant = {
            "name": name.strip(),
            "species": species.strip(),
            "sensor_mac": sensor_mac.strip().upper(),
            "pump_gpio": pump_gpio,
            "moisture_target_min": moisture_target_min,
            "moisture_target_max": moisture_target_max,
        }
        append_plant_to_toml(Path("flora.toml"), plant)
        config.plants.append(PlantConfig(
            name=plant["name"],
            species=plant["species"],
            sensor_mac=plant["sensor_mac"],
            pump_gpio=plant["pump_gpio"],
            moisture_target_min=plant["moisture_target_min"],
            moisture_target_max=plant["moisture_target_max"],
        ))
        return RedirectResponse(url=f"/plants/{name.strip()}", status_code=303)

    @router.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request) -> HTMLResponse:
        all_journals: list[dict] = []
        for plant in config.plants:
            entries = await db.get_journal(plant.name, limit=20)
            for e in entries:
                all_journals.append({
                    "plant_name": e.plant_name,
                    "timestamp": e.timestamp,
                    "entry_type": e.entry_type,
                    "content": e.content,
                })
        all_journals.sort(key=lambda x: x["timestamp"], reverse=True)
        return templates.TemplateResponse(
            request,
            "logs.html",
            {"journals": all_journals[:100]},
        )

    return router


# Species-specific mock values for visualization when no sensor has reported yet.
_SPECIES_MOCK: dict[str, tuple[float, str]] = {
    "basil":     (63.0, "healthy"),
    "mint":      (72.0, "wet"),
    "parsley":   (54.0, "healthy"),
    "chives":    (41.0, "dry"),
    "coriander": (31.0, "dry"),
}
_DEFAULT_MOCK: tuple[float, str] = (55.0, "healthy")


def _mock_moisture(species: str) -> float:
    return _SPECIES_MOCK.get(species.lower(), _DEFAULT_MOCK)[0]


def _mock_status(species: str) -> str:
    return _SPECIES_MOCK.get(species.lower(), _DEFAULT_MOCK)[1]


def _reading_age_hours(reading: SensorReading | None) -> float | None:
    """Return how many hours old a reading is, or None if no reading."""
    if reading is None:
        return None
    delta = datetime.utcnow() - reading.timestamp
    return delta.total_seconds() / 3600


def _status(moisture: float | None, target_min: int, target_max: int) -> str:
    if moisture is None:
        return "unknown"
    if moisture < 10:
        return "critical"
    if moisture < target_min:
        return "dry"
    if moisture > target_max:
        return "wet"
    return "healthy"

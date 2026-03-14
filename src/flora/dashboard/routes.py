"""Dashboard routes for Flora."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from flora.config import AppConfig
from flora.db import Database


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
            })
        ambient = await db.get_latest_ambient()
        actions = await db.get_recent_actions(limit=5)
        plants_art_json = json.dumps([
            {
                "name": p["config"].name,
                "species": p["config"].species,
                "moisture": p["reading"].moisture if p["reading"] else _mock_moisture(p["config"].species),
                "status": p["status"] if p["reading"] else _mock_status(p["config"].species),
            }
            for p in plant_data
        ])
        return templates.TemplateResponse(
            request,
            "index.html",
            {"plants": plant_data, "ambient": ambient, "actions": actions,
             "plants_art_json": plants_art_json},
        )

    @router.get("/plants/{name}", response_class=HTMLResponse)
    async def plant_detail(request: Request, name: str) -> HTMLResponse:
        plant = config.plant_by_name(name)
        if plant is None:
            return HTMLResponse("<h1>Plant not found</h1>", status_code=404)
        reading = await db.get_latest_sensor_reading(name)
        journal = await db.get_journal(name, limit=30)
        actions = await db.get_recent_actions(limit=20, plant_name=name)
        return templates.TemplateResponse(
            request,
            "plant.html",
            {
                "plant": plant,
                "reading": reading,
                "journal": journal,
                "actions": actions,
                "status": _status(reading.moisture if reading else None, plant.moisture_target_min, plant.moisture_target_max),
            },
        )

    @router.post("/plants/{name}/water", response_class=HTMLResponse)
    async def manual_water(name: str, duration: int = Form(default=10)) -> HTMLResponse:
        plant = config.plant_by_name(name)
        if plant is None:
            return HTMLResponse("<p>Plant not found</p>", status_code=404)
        duration = max(1, min(duration, 30))  # clamp 1-30s
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

    @router.get("/api/plants/{name}/history")
    async def plant_history_api(name: str, hours: int = 48) -> JSONResponse:
        """JSON endpoint for Chart.js sensor history."""
        readings = await db.get_sensor_history(name, hours=hours, limit=200)
        data = [
            {
                "ts": r.timestamp.strftime("%Y-%m-%dT%H:%M"),
                "moisture": r.moisture,
                "temperature": r.temperature,
                "light": r.light,
            }
            for r in reversed(readings)
        ]
        return JSONResponse({"plant": name, "hours": hours, "readings": data})

    @router.get("/actions", response_class=HTMLResponse)
    async def actions_page(request: Request) -> HTMLResponse:
        actions = await db.get_recent_actions(limit=100)
        return templates.TemplateResponse(
            request,
            "actions.html",
            {"actions": actions},
        )

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

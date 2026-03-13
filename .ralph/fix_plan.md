# Flora Fix Plan

## Phase 1 — Project Foundation
- [x] pyproject.toml with all dependencies and project metadata
- [x] flora.example.toml with sample plant config (basil, parsley, mint)
- [x] src/flora/config.py — TOML loader, PlantConfig dataclass, AppConfig dataclass
- [x] src/flora/db.py — SQLite schema (sensor_readings, plant_journals, action_log), migrations, async queries

## Phase 2 — Sensors
- [x] src/flora/sensors/miflora.py — BLE Mi Flora polling via `miflora` library + mock fallback
- [x] src/flora/sensors/sht31.py — SHT31 I2C temp/humidity + mock fallback
- [x] src/flora/sensors/bh1750.py — BH1750 I2C light sensor + mock fallback

## Phase 3 — Actuators
- [x] src/flora/actuators/pump.py — GPIO relay pump control via gpiozero + mock fallback
- [x] src/flora/actuators/smartplug.py — python-kasa smart plug on/off + schedule control + mock fallback

## Phase 4 — Claude Agent
- [x] src/flora/agent/prompts.py — system prompt with per-species herb knowledge (basil/parsley/mint/chives/coriander)
- [x] src/flora/agent/tools.py — all 6 tool implementations (water_plant, set_light_schedule, toggle_device, update_plant_journal, escalate_to_human, get_sensor_history)
- [x] src/flora/agent/loop.py — main agent loop: load history → call Claude with tools → execute actions → log reasoning

## Phase 5 — Scheduling + Notifications
- [x] src/flora/scheduler.py — APScheduler: 30min sensor poll, 2hr agent loop, daily photo trigger
- [x] src/flora/notifications.py — Telegram bot: send escalation messages + daily summary

## Phase 6 — Dashboard
- [x] src/flora/dashboard/app.py — FastAPI app setup
- [x] src/flora/dashboard/routes.py — routes: /, /plants/{name}, /api/plants/{name}/history, /actions, /logs
- [x] src/flora/dashboard/templates/ — HTMX templates: plant cards, sensor charts (Chart.js), action log

## Phase 7 — Entry Point + Install
- [x] src/flora/main.py — startup: load config, init DB, start scheduler, start dashboard server
- [x] install.sh — one-command install: deps, systemd service, open browser
- [x] flora.service — systemd unit file for auto-start on boot
- [x] tests/test_config.py — config loading tests with example TOML

## Completed
- [x] Project initialization (ralph-setup)
- [x] PRD in .ralph/specs/PRD.md
- [x] Procurement list in .ralph/specs/PROCUREMENT.md

# Flora Fix Plan — Phase 2 (Pre-Hardware)

## Active Tasks
- [x] Task 1: End-to-end agent loop test — `tests/test_agent_loop.py` with real API + fallback test
- [x] Task 2: Telegram integration test — `tests/test_notifications.py`, real bot send + unconfigured graceful skip
- [x] Task 3: Manual water button — POST `/plants/{name}/water` route + HTMX button in `plant.html` + `tests/test_dashboard.py`
- [x] Task 4: Photo capture pipeline — `src/flora/sensors/camera.py`, mock PNG fallback, wire into scheduler daily job + `tests/test_camera.py`
- [x] Task 5: Setup wizard — `src/flora/cli.py`, `generate_config()` + interactive `wizard()`, `flora-init` entry point + `tests/test_cli.py`
- [ ] Task 6: Push to GitHub — install gh CLI, create public repo, push, add flora.toml/flora.db/photos/ to .gitignore
- [x] Task 7: Mobile responsive view — make all dashboard templates work on small screens (≤480px): stack plant cards to 1 column, collapse nav to hamburger menu, make moisture rings and tables readable on mobile
- [x] Task 8: Algorithmic art animation — add a p5.js generative plant-growth canvas to the overview (index.html) page: animated procedural plants that react to real moisture/health data, dark botanical palette matching existing theme
- [x] Task 9: Playwright webapp tests — add `tests/test_dashboard_e2e.py` using playwright-pytest: test index page loads, plant card links work, manual water button triggers HTMX response, journal and actions pages render correctly

## Implementation Plan
Full plan with code: `docs/plans/2026-03-14-flora-phase2-pre-hardware.md`

## Rules
- TDD: write failing test first, then implement
- One task per loop
- Commit after each task
- Do NOT use real API keys in tests — use env vars with skipif markers
- `IS_PI = platform.machine() == "aarch64"` — all real hardware behind this guard
- Run `python3 -m pytest tests/ -v` after each task to confirm nothing broke

## Completed (Phase 1)
- [x] Project initialization
- [x] pyproject.toml + flora.example.toml
- [x] src/flora/config.py — TOML loader + dataclasses
- [x] src/flora/db.py — SQLite schema + queries
- [x] src/flora/sensors/miflora.py — BLE Mi Flora + bleak backend + mock
- [x] src/flora/sensors/sht31.py — I2C temp/humidity + mock
- [x] src/flora/sensors/bh1750.py — I2C light + mock
- [x] src/flora/actuators/pump.py — GPIO relay + mock
- [x] src/flora/actuators/smartplug.py — python-kasa (fixed for 0.7.x) + mock
- [x] src/flora/agent/prompts.py — herb knowledge system prompt
- [x] src/flora/agent/tools.py — all 6 Claude tools
- [x] src/flora/agent/loop.py — Claude reasoning loop + rule-based fallback
- [x] src/flora/scheduler.py — APScheduler 30min poll + 2hr agent loop
- [x] src/flora/notifications.py — Telegram bot
- [x] src/flora/dashboard/app.py + routes.py — FastAPI + HTMX
- [x] src/flora/dashboard/templates/ — index, plant, actions, logs, base
- [x] src/flora/main.py — entry point
- [x] install.sh + flora.service — systemd
- [x] tests/test_config.py — 13 passing tests
- [x] Code review fixes: kasa 0.7.x API, bluepy→bleak, run_in_executor for BLE

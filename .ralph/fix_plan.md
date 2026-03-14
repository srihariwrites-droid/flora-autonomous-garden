# Flora Fix Plan — Phase 3 (Pre-Hardware Polish)

## Active Tasks

- [x] Task 1: End-to-end agent loop test — `tests/test_agent_loop.py` with real API + fallback test
- [x] Task 2: Telegram integration test — `tests/test_notifications.py`, real bot send + unconfigured graceful skip
- [x] Task 3: Manual water button — POST `/plants/{name}/water` route + HTMX button in `plant.html` + `tests/test_dashboard.py`
- [x] Task 4: Photo capture pipeline — `src/flora/sensors/camera.py`, mock PNG fallback, wire into scheduler daily job + `tests/test_camera.py`
- [x] Task 5: Setup wizard — `src/flora/cli.py`, `generate_config()` + interactive `wizard()`, `flora-init` entry point + `tests/test_cli.py`
- [x] Task 6: Push to GitHub — repo at srihariwrites-droid/flora-autonomous-garden, branch protection on main, PR #1 open
- [x] Task 7: Mobile responsive view — hamburger nav, 1-column plant cards, hide-mobile table columns
- [x] Task 8: Algorithmic art animation — p5.js generative botanical canvas on overview page
- [x] Task 9: Playwright webapp tests — `tests/test_dashboard_e2e.py` covering index, plant detail, water button, journal, actions
- [ ] Task 10: GitHub Actions CI — add `.github/workflows/test.yml` that runs `python3 -m pytest tests/ -v` on every push and PR; use `python-version: "3.10"`, cache pip deps, skip Playwright tests in CI (mark with `@pytest.mark.skip(reason="requires running server")`)
- [ ] Task 11: Plant photo gallery page — add `/photos` dashboard route + `photos.html` template that lists all captured plant photos (real or mock) from the `photos/` directory; show filename, plant name parsed from filename, timestamp, and a thumbnail `<img>` tag; link from nav; add route test in `tests/test_dashboard.py`
- [ ] Task 12: Manual agent trigger — add POST `/api/agent/run` endpoint in `routes.py` that fires `AgentLoop.run_once()` in the background and returns `{"status": "started"}`; add a "Run Claude now" button with HTMX to the overview page `index.html`; add test
- [ ] Task 13: Sensor history CSV export — add GET `/api/plants/{name}/export.csv` endpoint that returns the last 7 days of sensor readings as a CSV file (`Content-Disposition: attachment`); add a download link on the plant detail page `plant.html`; add test
- [ ] Task 14: Fix `set_light_schedule` stub — `src/flora/actuators/smartplug.py` `set_schedule()` currently always returns `True` without doing anything on Pi; implement using APScheduler to toggle the plug on/off at specified times (store schedule in SQLite); update tool description in `agent/tools.py` to accurately reflect what it does; add test

## Rules

- TDD: write failing test first, then implement
- One task per loop
- Commit after each task with conventional message: `Area: action taken`
- Do NOT use real API keys in tests — use env vars with `pytest.mark.skipif` markers
- `IS_PI = platform.machine() == "aarch64"` — all real hardware behind this guard
- Run `python3 -m pytest tests/ -v` after each task to confirm nothing broke
- Files stay under 300 LOC — split when needed
- No placeholder implementations — build it properly

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

## Completed (Phase 2)

- [x] Pillow fallback crash fixed — `_capture_mock` catches ImportError, writes placeholder
- [x] Garden canvas UX fix — sensor-offline plants render at 45% opacity, `has_reading` flag in JSON
- [x] `_render_plant` return type annotation fixed
- [x] `@pytest.mark.asyncio` added to async camera tests
- [x] miflora mock seed stabilised — removed hourly component
- [x] `get_running_loop()` replacing deprecated `get_event_loop()`
- [x] `replace_existing=True` on daily_summary scheduler job
- [x] Species-realistic mock data in garden visualisation
- [x] Unit tests: camera render, Pillow fallback, JPEG header, mock species helpers

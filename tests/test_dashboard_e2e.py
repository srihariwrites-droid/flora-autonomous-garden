"""Playwright end-to-end tests for the Flora dashboard.

These tests spin up a real uvicorn server in a background thread and use
playwright-pytest's `page` fixture to drive a headless Chromium browser.

Run with:
    python3 -m pytest tests/test_dashboard_e2e.py -v
"""
from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest
import uvicorn

from flora.config import load_config
from flora.dashboard.app import create_app
from flora.db import Database

_TOML = """
[app]
db_path = "test.db"
dashboard_port = 8000
sensor_poll_interval = 1800
agent_loop_interval = 7200

[anthropic]
api_key = "test"
model = "claude-haiku-4-5-20251001"

[telegram]
token = ""
chat_id = ""

[[plants]]
name = "basil-1"
species = "basil"
sensor_mac = "AA:BB:CC:DD:EE:FF"
pump_gpio = 17
moisture_target_min = 40
moisture_target_max = 70
"""

_E2E_PORT = 18765


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Start a real uvicorn instance for the duration of the test session."""
    tmp = tmp_path_factory.mktemp("e2e")
    toml = tmp / "flora.toml"
    toml.write_text(_TOML)
    config = load_config(str(toml))
    db_path = tmp / "test.db"

    # server/db refs shared across thread boundary
    server_ref: dict = {}

    def run_server() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _serve() -> None:
            db = Database(db_path)
            await db.connect()
            app = create_app(config, db)
            server = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=_E2E_PORT, log_level="error")
            )
            server_ref["server"] = server
            server_ref["db"] = db
            await server.serve()
            await db.close()

        loop.run_until_complete(_serve())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait until the server is actually accepting requests
    base = f"http://127.0.0.1:{_E2E_PORT}"
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base}/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)

    yield base

    if "server" in server_ref:
        server_ref["server"].should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_index_page_loads(live_server, page):
    """Index page returns 200 and shows Flora branding."""
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    assert "Flora" in page.title()
    assert page.locator("h1.page-title").count() == 1


def test_index_has_garden_visualization(live_server, page):
    """p5.js canvas container is present on the overview page."""
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    assert page.locator("#flora-art").count() == 1


def test_plant_card_link_navigates(live_server, page):
    """Clicking a plant name link navigates to the plant detail page."""
    page.goto(live_server)
    page.wait_for_load_state("networkidle")
    page.locator("a.plant-link").first.click()
    page.wait_for_load_state("networkidle")
    assert "/plants/" in page.url


def test_manual_water_htmx_response(live_server, page):
    """Water button posts via HTMX and injects a result fragment."""
    page.goto(f"{live_server}/plants/basil-1")
    page.wait_for_load_state("networkidle")
    page.locator("button.btn-primary").first.click()
    # HTMX swaps HTML into #water-result; wait for it
    page.wait_for_selector("#water-result .alert", timeout=5000)
    text = page.locator("#water-result .alert").inner_text()
    assert "Watered" in text or "watered" in text.lower()


def test_actions_page_renders(live_server, page):
    """Actions page loads with correct heading."""
    page.goto(f"{live_server}/actions")
    page.wait_for_load_state("networkidle")
    heading = page.locator("h1.page-title").inner_text()
    assert "Action" in heading


def test_journal_page_renders(live_server, page):
    """Journal/logs page loads with correct heading."""
    page.goto(f"{live_server}/logs")
    page.wait_for_load_state("networkidle")
    heading = page.locator("h1.page-title").inner_text()
    assert "Journal" in heading

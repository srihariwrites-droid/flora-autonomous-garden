# Flora Phase 2 — Pre-Hardware Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and verify all features that can be tested without physical hardware — API integration, Telegram, manual dashboard controls, photo pipeline, setup wizard, and GitHub push.

**Architecture:** All features use the existing mock sensor layer (`IS_PI = platform.machine() == "aarch64"`), so they run fully on a dev laptop. The Claude agent loop runs against real Anthropic API with mock sensor data. Telegram uses a real bot token. The photo pipeline uses a static test image in place of Pi Camera.

**Tech Stack:** Python 3.10+, FastAPI + HTMX, anthropic SDK, python-telegram-bot, aiosqlite, pytest + pytest-asyncio, PIL/Pillow for image handling.

---

## Prerequisites

```bash
cd /home/px0/flora-app
cp flora.example.toml flora.toml
# Edit flora.toml — fill in:
#   [anthropic] api_key = "your-real-key"
#   [telegram] token = "..." chat_id = "..."
```

Run tests before starting to confirm baseline:
```bash
python3 -m pytest tests/ -v
# Expected: 13 passed
```

---

### Task 1: End-to-End Agent Loop Test with Real API

Test that Claude reasons correctly over mock sensor data and calls tools.

**Files:**
- Create: `tests/test_agent_loop.py`

**Step 1: Write the failing test**

```python
# tests/test_agent_loop.py
import pytest
import os
from flora.config import load_config
from flora.db import Database
from flora.agent.loop import AgentLoop

SKIP_IF_NO_KEY = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)

@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()

@pytest.fixture
def config(tmp_path):
    toml = tmp_path / "flora.toml"
    toml.write_text("""
[app]
db_path = "test.db"
dashboard_port = 8000
sensor_poll_interval = 1800
agent_loop_interval = 7200

[anthropic]
api_key = "test-key"
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
""")
    return load_config(str(toml))

@SKIP_IF_NO_KEY
async def test_agent_loop_runs_without_error(config, db):
    """Agent loop completes one cycle with mock data and real Claude API."""
    loop = AgentLoop(config, db)
    # Should not raise — Claude may or may not call tools, both are valid
    await loop.run_once()

@SKIP_IF_NO_KEY
async def test_fallback_runs_when_api_key_invalid(tmp_path, db):
    """Fallback rule-based loop runs when API key is invalid."""
    toml = tmp_path / "flora.toml"
    toml.write_text("""
[app]
db_path = "test.db"
dashboard_port = 8000
sensor_poll_interval = 1800
agent_loop_interval = 7200

[anthropic]
api_key = "sk-ant-invalid"
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
""")
    config = load_config(str(toml))
    loop = AgentLoop(config, db)
    # Invalid key → fallback. Should not raise.
    await loop.run_once()
```

**Step 2: Run to verify it fails**

```bash
python3 -m pytest tests/test_agent_loop.py -v
```
Expected: FAIL — `ModuleNotFoundError` or `ImportError` if deps missing, or `SKIP` if no key set.

**Step 3: Set your real API key and run**

```bash
export ANTHROPIC_API_KEY="sk-ant-your-real-key"
python3 -m pytest tests/test_agent_loop.py -v -s
```
Expected: Both tests PASS (or SKIP if key not set).

**Step 4: Commit**

```bash
git add tests/test_agent_loop.py
git commit -m "test: add end-to-end agent loop test with real API"
```

---

### Task 2: Telegram Bot Integration Test

Verify Telegram sends messages. Requires a real bot token and chat ID.

**How to get a Telegram bot token:**
1. Open Telegram, search for `@BotFather`
2. Send `/newbot`, follow prompts → get token like `123456:ABCdef...`
3. Start a chat with your new bot, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   to find your `chat_id` (a number like `987654321`)

**Files:**
- Create: `tests/test_notifications.py`

**Step 1: Write the failing test**

```python
# tests/test_notifications.py
import pytest
import os
from flora.notifications import send_telegram, send_daily_summary

SKIP_IF_NO_TELEGRAM = pytest.mark.skipif(
    not (os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
    reason="TELEGRAM_TOKEN and TELEGRAM_CHAT_ID not set"
)

@SKIP_IF_NO_TELEGRAM
async def test_send_telegram_message():
    """Sends a real test message via Telegram."""
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    result = await send_telegram(token, chat_id, "Flora test message — integration test")
    assert result is True

async def test_send_telegram_skips_when_unconfigured():
    """Returns False gracefully when token is empty."""
    result = await send_telegram("", "", "should not send")
    assert result is False

@SKIP_IF_NO_TELEGRAM
async def test_send_daily_summary():
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    summaries = [
        {"name": "basil-1", "moisture": 55.0, "temperature": 22.1, "status": "healthy"},
        {"name": "mint-1", "moisture": 8.0, "temperature": 21.5, "status": "critical"},
    ]
    result = await send_daily_summary(token, chat_id, summaries)
    assert result is True
```

**Step 2: Run without env vars (should skip/pass)**

```bash
python3 -m pytest tests/test_notifications.py -v
```
Expected: 1 PASS (unconfigured test), 2 SKIP.

**Step 3: Run with real credentials**

```bash
export TELEGRAM_TOKEN="123456:ABCdef..."
export TELEGRAM_CHAT_ID="987654321"
python3 -m pytest tests/test_notifications.py -v -s
```
Expected: 3 PASS. Check your Telegram app — you should receive 2 messages.

**Step 4: Commit**

```bash
git add tests/test_notifications.py
git commit -m "test: add Telegram integration tests"
```

---

### Task 3: Manual Water Button in Dashboard

Add a POST endpoint and HTMX button so you can trigger a pump from the browser — essential for testing relay wiring when hardware arrives.

**Files:**
- Modify: `src/flora/dashboard/routes.py`
- Modify: `src/flora/dashboard/templates/plant.html`
- Create: `tests/test_dashboard.py`

**Step 1: Write the failing test**

```python
# tests/test_dashboard.py
import pytest
from httpx import AsyncClient, ASGITransport
from flora.config import load_config
from flora.db import Database
from flora.dashboard.app import create_app

@pytest.fixture
async def client(tmp_path):
    toml = tmp_path / "flora.toml"
    toml.write_text("""
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
""")
    config = load_config(str(toml))
    db = Database(tmp_path / "test.db")
    await db.connect()
    app = create_app(config, db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await db.close()

async def test_index_returns_200(client):
    resp = await client.get("/")
    assert resp.status_code == 200

async def test_plant_detail_returns_200(client):
    resp = await client.get("/plants/basil-1")
    assert resp.status_code == 200

async def test_plant_detail_404_unknown(client):
    resp = await client.get("/plants/does-not-exist")
    assert resp.status_code == 404

async def test_manual_water_endpoint(client):
    """POST /plants/basil-1/water triggers mock pump and returns 200."""
    resp = await client.post("/plants/basil-1/water", data={"duration": "5"})
    assert resp.status_code == 200
    assert "Watered" in resp.text

async def test_manual_water_unknown_plant(client):
    resp = await client.post("/plants/unknown/water", data={"duration": "5"})
    assert resp.status_code == 404
```

**Step 2: Run to verify it fails**

```bash
python3 -m pytest tests/test_dashboard.py -v
```
Expected: `test_manual_water_endpoint` FAIL — route doesn't exist yet.

**Step 3: Add the POST route to `src/flora/dashboard/routes.py`**

Add after the existing `plant_detail` route (around line 35):

```python
from fastapi import Form
from fastapi.responses import HTMLResponse

@router.post("/plants/{name}/water", response_class=HTMLResponse)
async def manual_water(name: str, duration: int = Form(default=10)) -> HTMLResponse:
    plant = config.plant_by_name(name)
    if plant is None:
        return HTMLResponse("<p>Plant not found</p>", status_code=404)
    duration = max(1, min(duration, 30))  # clamp 1-30s
    from flora.actuators.pump import water_plant as _pump
    from flora.db import ActionRecord
    from datetime import datetime
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
```

Also add `Form` to the imports at the top of `routes.py`:
```python
from fastapi import APIRouter, Form, Request
```

**Step 4: Add the button to `src/flora/dashboard/templates/plant.html`**

Find the section showing plant readings and add below it:

```html
<form hx-post="/plants/{{ plant.name }}/water"
      hx-target="#water-result"
      hx-swap="innerHTML"
      class="mt-4">
  <label>Duration (seconds):
    <input type="number" name="duration" value="10" min="1" max="30" class="input input-bordered w-20">
  </label>
  <button type="submit" class="btn btn-primary ml-2">
    💧 Water now
  </button>
</form>
<div id="water-result" class="mt-2"></div>
```

**Step 5: Run tests**

```bash
python3 -m pytest tests/test_dashboard.py -v
```
Expected: 5 PASS.

**Step 6: Manual smoke test**

```bash
flora flora.toml &
# Open http://localhost:8000/plants/basil-1
# Click "Water now" — check logs for "[MOCK] Pump GPIO 17: activating for 10s"
kill %1
```

**Step 7: Commit**

```bash
git add src/flora/dashboard/routes.py src/flora/dashboard/templates/plant.html tests/test_dashboard.py
git commit -m "feat: add manual water button to plant dashboard"
```

---

### Task 4: Photo Analysis Pipeline

Build the camera capture + Claude vision analysis path. Uses a static test image on non-Pi hardware.

**Files:**
- Create: `src/flora/sensors/camera.py`
- Create: `tests/test_camera.py`
- Modify: `src/flora/scheduler.py` (add daily photo job)

**Step 1: Write the failing test**

```python
# tests/test_camera.py
import pytest
from pathlib import Path
from flora.sensors.camera import capture_photo, PhotoResult

async def test_capture_returns_result_on_non_pi():
    """On non-Pi hardware, capture_photo returns a mock PhotoResult."""
    result = await capture_photo("basil-1", save_dir=Path("/tmp/flora-test-photos"))
    assert result is not None
    assert isinstance(result, PhotoResult)
    assert result.plant_name == "basil-1"
    assert result.path.exists()

async def test_capture_creates_directory(tmp_path):
    save_dir = tmp_path / "photos"
    assert not save_dir.exists()
    result = await capture_photo("mint-1", save_dir=save_dir)
    assert save_dir.exists()
    assert result is not None
```

**Step 2: Run to verify it fails**

```bash
python3 -m pytest tests/test_camera.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'flora.sensors.camera'`

**Step 3: Create `src/flora/sensors/camera.py`**

```python
"""Pi Camera capture with mock fallback for development."""
from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

IS_PI = platform.machine() == "aarch64"

# Static test image used on non-Pi hardware (1x1 white PNG, base64)
_MOCK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009001"
    "2e00000000c4944415478016360f8cfc00000000200016633e4a0000000049"
    "454e44ae426082"
)


@dataclass
class PhotoResult:
    plant_name: str
    timestamp: datetime
    path: Path


async def capture_photo(plant_name: str, save_dir: Path) -> PhotoResult | None:
    """Capture a photo of a plant. Returns None on failure."""
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow()
    filename = f"{plant_name}_{ts.strftime('%Y%m%d_%H%M%S')}.jpg"
    path = save_dir / filename

    if IS_PI:
        return await _capture_real(plant_name, path, ts)
    return _capture_mock(plant_name, path, ts)


async def _capture_real(plant_name: str, path: Path, ts: datetime) -> PhotoResult | None:
    try:
        from picamera2 import Picamera2  # type: ignore[import]
        cam = Picamera2()
        cam.configure(cam.create_still_configuration())
        cam.start()
        cam.capture_file(str(path))
        cam.stop()
        cam.close()
        logger.info("Photo captured: %s", path)
        return PhotoResult(plant_name=plant_name, timestamp=ts, path=path)
    except Exception as exc:
        logger.error("Camera capture failed: %s", exc)
        return None


def _capture_mock(plant_name: str, path: Path, ts: datetime) -> PhotoResult:
    path.write_bytes(_MOCK_PNG)
    logger.info("[MOCK] Photo saved: %s", path)
    return PhotoResult(plant_name=plant_name, timestamp=ts, path=path)
```

**Step 4: Run tests**

```bash
python3 -m pytest tests/test_camera.py -v
```
Expected: 2 PASS.

**Step 5: Add `picamera2` as optional dependency in `pyproject.toml`**

Add to `[project.optional-dependencies]`:
```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24.0", "mypy>=1.11.0"]
pi = ["picamera2"]
```

**Step 6: Wire photo capture into scheduler**

In `src/flora/scheduler.py`, find the `daily_summary` job and add a photo capture job. Add this function and register it:

```python
# Add this import at top of scheduler.py
from flora.sensors.camera import capture_photo
from pathlib import Path

# Add this job function alongside existing ones
async def _run_photo_capture(config: AppConfig, db: Database) -> None:
    photo_dir = Path("photos")
    for plant in config.plants:
        result = await capture_photo(plant.name, save_dir=photo_dir)
        if result:
            logger.info("Photo captured for %s: %s", plant.name, result.path)

# In create_scheduler(), add alongside existing jobs:
scheduler.add_job(
    lambda: asyncio.create_task(_run_photo_capture(config, db)),
    trigger="cron",
    hour=7,
    minute=0,
    id="daily_photo",
    name="Daily photo capture",
    replace_existing=True,
)
```

**Step 7: Commit**

```bash
git add src/flora/sensors/camera.py src/flora/scheduler.py tests/test_camera.py pyproject.toml
git commit -m "feat: add photo capture pipeline with Pi Camera + mock fallback"
```

---

### Task 5: Setup Wizard (`flora init`)

Interactive CLI to generate `flora.toml` from prompts — the zero-friction onboarding experience.

**Files:**
- Create: `src/flora/cli.py`
- Modify: `pyproject.toml` (add `flora-init` script entry point)
- Create: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/test_cli.py
from pathlib import Path
from flora.cli import generate_config

def test_generate_config_single_plant(tmp_path):
    """generate_config writes a valid TOML to the given path."""
    out = tmp_path / "flora.toml"
    generate_config(
        path=out,
        api_key="sk-ant-test",
        telegram_token="",
        telegram_chat_id="",
        plants=[{"name": "basil-1", "species": "basil", "mac": "AA:BB:CC:DD:EE:FF", "gpio": 17}],
        smart_plugs=[],
    )
    assert out.exists()
    content = out.read_text()
    assert "basil-1" in content
    assert "sk-ant-test" in content
    assert "AA:BB:CC:DD:EE:FF" in content

def test_generate_config_no_plants(tmp_path):
    out = tmp_path / "flora.toml"
    generate_config(
        path=out,
        api_key="sk-ant-test",
        telegram_token="",
        telegram_chat_id="",
        plants=[],
        smart_plugs=[],
    )
    assert out.exists()
    assert "[[plants]]" not in out.read_text()
```

**Step 2: Run to verify it fails**

```bash
python3 -m pytest tests/test_cli.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'flora.cli'`

**Step 3: Create `src/flora/cli.py`**

```python
"""Flora setup wizard — generates flora.toml interactively."""
from __future__ import annotations

import sys
from pathlib import Path


def generate_config(
    path: Path,
    api_key: str,
    telegram_token: str,
    telegram_chat_id: str,
    plants: list[dict[str, object]],
    smart_plugs: list[dict[str, object]],
) -> None:
    """Write a flora.toml to `path` from the given parameters."""
    lines = [
        "[app]",
        'db_path = "flora.db"',
        "dashboard_port = 8000",
        "sensor_poll_interval = 1800",
        "agent_loop_interval = 7200",
        "",
        "[anthropic]",
        f'api_key = "{api_key}"',
        'model = "claude-sonnet-4-6"',
        "",
        "[telegram]",
        f'token = "{telegram_token}"',
        f'chat_id = "{telegram_chat_id}"',
        "",
    ]
    for p in plants:
        lines += [
            "[[plants]]",
            f'name = "{p["name"]}"',
            f'species = "{p["species"]}"',
            f'sensor_mac = "{p["mac"]}"',
            f'pump_gpio = {p["gpio"]}',
            "moisture_target_min = 40",
            "moisture_target_max = 70",
            "",
        ]
    for plug in smart_plugs:
        lines += [
            "[[smart_plugs]]",
            f'alias = "{plug["alias"]}"',
            f'host = "{plug["host"]}"',
            f'role = "{plug["role"]}"',
            "",
        ]
    path.write_text("\n".join(lines))


def _prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or default


def wizard() -> None:
    """Interactive setup wizard — run via `flora-init`."""
    print("\nFlora Setup Wizard")
    print("=" * 40)

    out = Path(_prompt("Config file path", "flora.toml"))
    if out.exists():
        overwrite = _prompt(f"{out} already exists. Overwrite?", "n").lower()
        if overwrite != "y":
            print("Aborted.")
            sys.exit(0)

    api_key = _prompt("Anthropic API key (sk-ant-...)")
    tg_token = _prompt("Telegram bot token (leave blank to skip)", "")
    tg_chat = _prompt("Telegram chat ID (leave blank to skip)", "") if tg_token else ""

    plants = []
    print("\nAdd plants (press Enter with blank name to finish):")
    gpio_pin = 17
    while True:
        name = _prompt(f"  Plant name (e.g. basil-1)", "").strip()
        if not name:
            break
        species = _prompt(f"  Species for {name} (basil/parsley/mint/chives/coriander)", "basil")
        mac = _prompt(f"  BLE MAC address for {name} (e.g. C4:7C:8D:XX:XX:XX)")
        gpio = int(_prompt(f"  GPIO relay pin for {name} pump", str(gpio_pin)))
        plants.append({"name": name, "species": species, "mac": mac, "gpio": gpio})
        gpio_pin += 1

    plugs = []
    print("\nAdd smart plugs (press Enter with blank host to finish):")
    for role in ["grow_light", "humidifier", "fan"]:
        host = _prompt(f"  IP address for {role} plug (leave blank to skip)", "")
        if host:
            plugs.append({"alias": role, "host": host, "role": role})

    generate_config(out, api_key, tg_token, tg_chat, plants, plugs)
    print(f"\nConfig written to {out}")
    print("Run: flora flora.toml")
```

**Step 4: Add entry point in `pyproject.toml`**

```toml
[project.scripts]
flora = "flora.main:cli"
flora-init = "flora.cli:wizard"
```

**Step 5: Run tests**

```bash
python3 -m pytest tests/test_cli.py -v
```
Expected: 2 PASS.

**Step 6: Smoke test the wizard**

```bash
pip3 install -e . -q
flora-init
# Follow the prompts. Check the generated flora.toml.
```

**Step 7: Commit**

```bash
git add src/flora/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat: add flora-init setup wizard"
```

---

### Task 6: Push to GitHub

Get the project on GitHub for version control and future open-source release.

**Step 1: Install gh CLI if not installed**

```bash
which gh || (type -p curl >/dev/null || sudo apt install curl -y) \
  && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && sudo apt update && sudo apt install gh -y
```

**Step 2: Authenticate**

```bash
gh auth login
# Choose GitHub.com → HTTPS → Login with browser
```

**Step 3: Add a `.gitignore` entry for secrets**

```bash
echo "flora.toml" >> .gitignore
echo "flora.db" >> .gitignore
echo "photos/" >> .gitignore
git add .gitignore
git commit -m "chore: ignore local config, db, and photos"
```

**Step 4: Create and push the repo**

```bash
cd /home/px0/flora-app
gh repo create flora --public --description "Autonomous herb garden agent powered by Claude" --source=. --remote=origin --push
```

Expected output:
```
✓ Created repository <username>/flora on GitHub
✓ Added remote origin
✓ Pushed commits to github.com/<username>/flora
```

**Step 5: Verify**

```bash
gh repo view --web
```
Browser opens to your new GitHub repo.

---

## Run All Tests

After completing all tasks:

```bash
python3 -m pytest tests/ -v
```

Expected: All tests pass (agent/telegram tests skip unless env vars set).

---

## Summary of What Gets Built

| Feature | How to test |
|---------|-------------|
| Agent loop with real Claude | `ANTHROPIC_API_KEY=sk-ant-... pytest tests/test_agent_loop.py` |
| Telegram messages | `TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... pytest tests/test_notifications.py` |
| Manual water button | `flora flora.toml` → browser → `/plants/basil-1` → click Water now |
| Photo capture | `pytest tests/test_camera.py` — mock PNG created in `/tmp/flora-test-photos/` |
| Setup wizard | `flora-init` → follow prompts |
| GitHub repo | `gh repo view --web` |

# Flora

Autonomous herb garden agent powered by Claude AI. Runs on a Raspberry Pi — monitors soil moisture, temperature, and light via BLE/I2C sensors, waters plants automatically, and reasons about plant health using Claude's tool-use API. A local web dashboard shows live readings, sensor history charts, and the full Claude reasoning log.

---

## Hardware

| Component | Part |
|---|---|
| Compute | Raspberry Pi 4 (2 GB+) |
| Soil sensor | Xiaomi Mi Flora (BLE, one per plant) |
| Ambient | SHT31 (temp/humidity, I2C) + BH1750 (light, I2C) |
| Pump control | 5V relay module → 12V submersible pump |
| Grow light | TP-Link Kasa smart plug (local LAN) |

Flora runs fully on development hardware too — all sensors and actuators have mock fallbacks that activate automatically when not on a Pi (`platform.machine() != "aarch64"`).

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/srihariwrites-droid/flora-autonomous-garden.git
cd flora-autonomous-garden
pip install -e ".[dev]"
```

On Raspberry Pi, also install the Pi extras:

```bash
pip install -e ".[pi]"
```

### 2. Configure

```bash
cp flora.example.toml flora.toml
```

Edit `flora.toml` and fill in:
- `anthropic.api_key` — your Anthropic API key
- `telegram.token` + `telegram.chat_id` — for escalation alerts (optional)
- `plants[*].sensor_mac` — BLE MAC address of each Mi Flora sensor
- `plants[*].pump_gpio` — GPIO pin number for each pump relay
- `smart_plugs[*].host` — local IP of each TP-Link Kasa plug

Or run the interactive setup wizard:

```bash
flora-init
```

### 3. Run

```bash
flora flora.toml
```

Dashboard opens at **http://localhost:8000**

On Raspberry Pi, install as a systemd service so it runs on boot:

```bash
sudo cp flora.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flora
sudo journalctl -u flora -f   # follow logs
```

---

## How It Works

```
Every 30 min   → sensors polled (Mi Flora BLE + SHT31 + BH1750)
Every 2 hr     → Claude reasoning loop runs:
                   reads 7-day sensor history per plant
                   calls tools: water_plant, toggle_device,
                                update_plant_journal, escalate_to_human
Every day 7am  → daily Telegram summary + plant photo captured
```

All Claude decisions are logged to SQLite with the full reasoning text, visible in the dashboard under **Action History** and **Garden Journal**.

If the Claude API is unreachable, Flora falls back to rule-based watering: moisture below 30% triggers a 10-second pump pulse.

---

## Dashboard

| Page | URL |
|---|---|
| Overview (all plants) | `http://localhost:8000/` |
| Plant detail + chart | `http://localhost:8000/plants/<name>` |
| Action history | `http://localhost:8000/actions` |
| Garden journal | `http://localhost:8000/logs` |

The overview page includes a live p5.js generative art canvas — each herb is drawn as an animated procedural plant whose shape and colour reflects its current moisture and health status.

---

## Development

```bash
# Run tests
python3 -m pytest tests/ -v

# Run with mock sensors (any non-Pi machine)
flora flora.toml

# Playwright e2e tests (requires running server)
python3 -m pytest tests/test_dashboard_e2e.py -v
```

### Project structure

```
src/flora/
├── main.py              # entry point
├── config.py            # TOML config loader
├── db.py                # SQLite schema + queries
├── scheduler.py         # APScheduler: sensor poll + agent loop
├── notifications.py     # Telegram alerts
├── agent/
│   ├── loop.py          # Claude reasoning loop
│   ├── tools.py         # 6 Claude tool implementations
│   └── prompts.py       # system prompt + herb knowledge
├── sensors/
│   ├── miflora.py       # BLE Mi Flora (+ mock)
│   ├── sht31.py         # I2C temp/humidity (+ mock)
│   ├── bh1750.py        # I2C light (+ mock)
│   └── camera.py        # Pi Camera (+ procedural mock image)
├── actuators/
│   ├── pump.py          # GPIO relay (+ mock)
│   └── smartplug.py     # python-kasa TP-Link (+ mock)
└── dashboard/
    ├── app.py           # FastAPI app
    ├── routes.py        # all routes + API endpoints
    └── templates/       # Jinja2 + HTMX templates
```

---

## Configuration Reference

```toml
[app]
db_path = "flora.db"
dashboard_port = 8000
sensor_poll_interval = 1800   # seconds between sensor polls (default 30 min)
agent_loop_interval = 7200    # seconds between Claude cycles (default 2 hr)

[anthropic]
api_key = "sk-ant-..."
model = "claude-sonnet-4-6"

[telegram]
token = "..."
chat_id = "..."

[[plants]]
name = "basil-1"             # unique identifier (used in URLs)
species = "basil"            # used for herb-specific AI knowledge
sensor_mac = "C4:7C:8D:..."  # Mi Flora BLE MAC
pump_gpio = 17               # BCM GPIO pin for relay
moisture_target_min = 40     # % below this → Claude considers watering
moisture_target_max = 70     # % above this → Claude holds off

[[smart_plugs]]
alias = "grow-light"
host = "192.168.1.100"       # local LAN IP (no cloud required)
role = "grow_light"
```

---

## License

MIT

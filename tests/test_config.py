"""Tests for src/flora/config.py."""
import pytest
from pathlib import Path

from flora.config import AppConfig, PlantConfig, SmartPlugConfig, load_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_TOML = """
[anthropic]
api_key = "sk-fake-key"
"""

_FULL_TOML = """
[app]
db_path = "test.db"
dashboard_port = 9000
sensor_poll_interval = 600
agent_loop_interval = 3600

[anthropic]
api_key = "sk-fake-key"
model = "claude-test-model"

[telegram]
token = "fake-token"
chat_id = "12345"

[[plants]]
name = "basil"
species = "basil"
sensor_mac = "AA:BB:CC:DD:EE:01"
pump_gpio = 17

[[plants]]
name = "mint"
species = "mint"
sensor_mac = "AA:BB:CC:DD:EE:02"
pump_gpio = 27
moisture_target_min = 50
moisture_target_max = 80

[[smart_plugs]]
alias = "grow-light"
host = "192.168.1.10"
role = "grow_light"
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "flora.toml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# 1. Valid config with 2 plants and 1 smart plug
# ---------------------------------------------------------------------------

def test_load_full_config(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))

    assert isinstance(cfg, AppConfig)
    assert len(cfg.plants) == 2
    assert len(cfg.smart_plugs) == 1
    assert cfg.anthropic_api_key == "sk-fake-key"
    assert cfg.anthropic_model == "claude-test-model"
    assert cfg.telegram_token == "fake-token"
    assert cfg.telegram_chat_id == "12345"
    assert cfg.db_path == "test.db"


# ---------------------------------------------------------------------------
# 2. Default moisture values
# ---------------------------------------------------------------------------

def test_default_moisture_targets(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    basil = cfg.plant_by_name("basil")
    assert basil is not None
    assert basil.moisture_target_min == 40
    assert basil.moisture_target_max == 70


def test_custom_moisture_targets(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    mint = cfg.plant_by_name("mint")
    assert mint is not None
    assert mint.moisture_target_min == 50
    assert mint.moisture_target_max == 80


# ---------------------------------------------------------------------------
# 3. plant_by_name — found and not found
# ---------------------------------------------------------------------------

def test_plant_by_name_found(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    plant = cfg.plant_by_name("basil")
    assert isinstance(plant, PlantConfig)
    assert plant.name == "basil"
    assert plant.sensor_mac == "AA:BB:CC:DD:EE:01"
    assert plant.pump_gpio == 17


def test_plant_by_name_not_found(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    assert cfg.plant_by_name("thyme") is None


# ---------------------------------------------------------------------------
# 4. plug_by_role — found and not found
# ---------------------------------------------------------------------------

def test_plug_by_role_found(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    plug = cfg.plug_by_role("grow_light")
    assert isinstance(plug, SmartPlugConfig)
    assert plug.alias == "grow-light"
    assert plug.host == "192.168.1.10"


def test_plug_by_role_not_found(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    assert cfg.plug_by_role("humidifier") is None


# ---------------------------------------------------------------------------
# 5. Missing config file raises FileNotFoundError
# ---------------------------------------------------------------------------

def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.toml")


# ---------------------------------------------------------------------------
# 6. Config with 0 plants works
# ---------------------------------------------------------------------------

def test_zero_plants(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _MINIMAL_TOML))
    assert cfg.plants == []
    assert cfg.smart_plugs == []


# ---------------------------------------------------------------------------
# 7. Custom sensor_poll_interval and agent_loop_interval
# ---------------------------------------------------------------------------

def test_custom_intervals(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    assert cfg.sensor_poll_interval == 600
    assert cfg.agent_loop_interval == 3600


def test_default_intervals(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _MINIMAL_TOML))
    assert cfg.sensor_poll_interval == 1800
    assert cfg.agent_loop_interval == 7200


# ---------------------------------------------------------------------------
# 8. Correct dashboard_port loading
# ---------------------------------------------------------------------------

def test_custom_dashboard_port(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    assert cfg.dashboard_port == 9000


def test_default_dashboard_port(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _MINIMAL_TOML))
    assert cfg.dashboard_port == 8000


# ---------------------------------------------------------------------------
# 9. auto_water_min_interval_minutes loaded from TOML
# ---------------------------------------------------------------------------

_TOML_WITH_INTERVAL = """
[anthropic]
api_key = "sk-fake-key"

[[plants]]
name = "basil"
species = "basil"
sensor_mac = "AA:BB:CC:DD:EE:01"
pump_gpio = 17
auto_water_min_interval_minutes = 30
"""


def test_custom_auto_water_min_interval_minutes(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _TOML_WITH_INTERVAL))
    basil = cfg.plant_by_name("basil")
    assert basil is not None
    assert basil.auto_water_min_interval_minutes == 30


def test_default_auto_water_min_interval_minutes(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _FULL_TOML))
    basil = cfg.plant_by_name("basil")
    assert basil is not None
    assert basil.auto_water_min_interval_minutes == 15

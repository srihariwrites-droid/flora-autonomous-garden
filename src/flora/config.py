"""TOML configuration loader for Flora."""
from __future__ import annotations

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PlantConfig:
    name: str
    species: str          # basil | parsley | mint | chives | coriander
    sensor_mac: str       # BLE MAC address of Mi Flora sensor
    pump_gpio: int        # GPIO pin number for relay
    moisture_target_min: int = 40
    moisture_target_max: int = 70
    # Optional deterministic auto-water rule (no Claude API needed)
    auto_water_if_below: int | None = None   # moisture % threshold
    auto_water_duration_seconds: int = 8     # pump seconds (clamped 5-30)


@dataclass(frozen=True)
class SmartPlugConfig:
    alias: str
    host: str             # LAN IP address
    role: str             # grow_light | humidifier | fan


@dataclass(frozen=True)
class AppConfig:
    db_path: str
    dashboard_port: int
    sensor_poll_interval: int  # seconds
    agent_loop_interval: int   # seconds
    anthropic_api_key: str
    anthropic_model: str
    telegram_token: str
    telegram_chat_id: str
    plants: list[PlantConfig]
    smart_plugs: list[SmartPlugConfig]

    def plant_by_name(self, name: str) -> PlantConfig | None:
        return next((p for p in self.plants if p.name == name), None)

    def plug_by_role(self, role: str) -> SmartPlugConfig | None:
        return next((p for p in self.smart_plugs if p.role == role), None)


def load_config(path: str | Path = "flora.toml") -> AppConfig:
    """Load and validate flora.toml, returning a frozen AppConfig."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    app_section = raw.get("app", {})
    anthropic_section = raw.get("anthropic", {})
    telegram_section = raw.get("telegram", {})

    plants = [
        PlantConfig(
            name=p["name"],
            species=p["species"],
            sensor_mac=p["sensor_mac"],
            pump_gpio=p["pump_gpio"],
            moisture_target_min=p.get("moisture_target_min", 40),
            moisture_target_max=p.get("moisture_target_max", 70),
            auto_water_if_below=p.get("auto_water_if_below"),
            auto_water_duration_seconds=p.get("auto_water_duration_seconds", 8),
        )
        for p in raw.get("plants", [])
    ]

    smart_plugs = [
        SmartPlugConfig(
            alias=sp["alias"],
            host=sp["host"],
            role=sp["role"],
        )
        for sp in raw.get("smart_plugs", [])
    ]

    return AppConfig(
        db_path=app_section.get("db_path", "flora.db"),
        dashboard_port=app_section.get("dashboard_port", 8000),
        sensor_poll_interval=app_section.get("sensor_poll_interval", 1800),
        agent_loop_interval=app_section.get("agent_loop_interval", 7200),
        anthropic_api_key=anthropic_section["api_key"],
        anthropic_model=anthropic_section.get("model", "claude-sonnet-4-6"),
        telegram_token=telegram_section.get("token", ""),
        telegram_chat_id=telegram_section.get("chat_id", ""),
        plants=plants,
        smart_plugs=smart_plugs,
    )

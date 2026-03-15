"""TOML configuration loader for Flora."""
from __future__ import annotations

import re

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass, field
from pathlib import Path

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_KNOWN_SPECIES = {"basil", "parsley", "mint", "chives", "coriander"}


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
    auto_water_min_interval_minutes: int = 15  # minimum minutes between auto-water firings
    # Camera assignment (index into Picamera2 camera list; None = default 0)
    camera_index: int | None = None
    # Free-form notes about this plant (optional, e.g. placement, quirks)
    notes: str = ""


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


def validate_config(raw: dict) -> list[str]:
    """Validate raw TOML dict and return a list of human-readable error strings."""
    errors: list[str] = []

    app = raw.get("app", {})
    for field_name in ("sensor_poll_interval", "agent_loop_interval"):
        val = app.get(field_name)
        if val is not None and not isinstance(val, int):
            errors.append(f"[app] {field_name} must be an integer (got {val!r})")
        elif val is not None and not (val >= 1):
            errors.append(f"[app] {field_name} must be >= 1 (got {val!r})")

    port = app.get("dashboard_port")
    if port is not None and not isinstance(port, int):
        errors.append(f"[app] dashboard_port must be an integer (got {port!r})")
    elif port is not None and not (1 <= port <= 65535):
        errors.append(f"[app] dashboard_port must be 1-65535 (got {port!r})")

    db_path = app.get("db_path")
    if db_path is not None and not db_path:
        errors.append("[app] db_path must not be empty")

    telegram = raw.get("telegram", {})
    tg_token = telegram.get("token", "")
    tg_chat_id = telegram.get("chat_id", "")
    if bool(tg_token) != bool(tg_chat_id):
        errors.append(
            "[telegram] token and chat_id must both be set or both be empty"
        )

    anthropic = raw.get("anthropic", {})
    api_key = anthropic.get("api_key")
    if api_key is not None and not api_key:
        errors.append("[anthropic] api_key must not be empty")
    model = anthropic.get("model")
    if model is not None and not model:
        errors.append("[anthropic] model must not be empty")

    plants = raw.get("plants", [])

    seen_names: set[str] = set()
    seen_macs: set[str] = set()
    seen_gpios: set[int] = set()

    for i, p in enumerate(plants):
        label = f"Plant #{i + 1}"

        # Required fields
        for field_name in ("name", "species", "sensor_mac", "pump_gpio"):
            if field_name not in p:
                errors.append(f"{label}: missing required field '{field_name}'")

        name = p.get("name")
        if name is not None:
            if name in seen_names:
                errors.append(f"{label}: duplicate plant name '{name}'")
            seen_names.add(name)
            label = f"Plant '{name}'"

        mac = p.get("sensor_mac")
        if mac is not None:
            if not _MAC_RE.match(mac):
                errors.append(f"{label}: invalid sensor_mac '{mac}' (expected XX:XX:XX:XX:XX:XX)")
            elif mac.upper() in seen_macs:
                errors.append(f"{label}: duplicate sensor_mac '{mac}'")
            else:
                seen_macs.add(mac.upper())

        gpio = p.get("pump_gpio")
        if gpio is not None:
            if not isinstance(gpio, int) or not (0 <= gpio <= 27):
                errors.append(f"{label}: pump_gpio must be an integer 0-27 (got {gpio!r})")
            elif gpio in seen_gpios:
                errors.append(f"{label}: duplicate pump_gpio {gpio}")
            else:
                seen_gpios.add(gpio)

        mn = p.get("moisture_target_min")
        mx = p.get("moisture_target_max")
        if mn is not None and not isinstance(mn, int):
            errors.append(
                f"{label}: moisture_target_min must be an integer (got {mn!r})"
            )
        elif mn is not None and not (0 <= mn <= 100):
            errors.append(
                f"{label}: moisture_target_min must be 0-100 (got {mn!r})"
            )
        if mx is not None and not isinstance(mx, int):
            errors.append(
                f"{label}: moisture_target_max must be an integer (got {mx!r})"
            )
        elif mx is not None and not (0 <= mx <= 100):
            errors.append(
                f"{label}: moisture_target_max must be 0-100 (got {mx!r})"
            )
        if mn is not None and mx is not None and mn >= mx:
            errors.append(
                f"{label}: moisture_target_min ({mn}) must be less than moisture_target_max ({mx})"
            )

        duration = p.get("auto_water_duration_seconds")
        if duration is not None and not isinstance(duration, int):
            errors.append(
                f"{label}: auto_water_duration_seconds must be an integer (got {duration!r})"
            )
        elif duration is not None and not (1 <= duration <= 30):
            errors.append(
                f"{label}: auto_water_duration_seconds must be 1-30 (got {duration!r})"
            )

        interval = p.get("auto_water_min_interval_minutes")
        if interval is not None and not isinstance(interval, int):
            errors.append(
                f"{label}: auto_water_min_interval_minutes must be an integer (got {interval!r})"
            )
        elif interval is not None and not (interval >= 1):
            errors.append(
                f"{label}: auto_water_min_interval_minutes must be >= 1 (got {interval!r})"
            )

        threshold = p.get("auto_water_if_below")
        if threshold is not None and not (0 <= threshold <= 100):
            errors.append(
                f"{label}: auto_water_if_below must be 0-100 (got {threshold!r})"
            )

        species = p.get("species")
        if species is not None and species not in _KNOWN_SPECIES:
            errors.append(
                f"{label}: species must be one of {', '.join(sorted(_KNOWN_SPECIES))} (got {species!r})"
            )

        camera_index = p.get("camera_index")
        if camera_index is not None and camera_index < 0:
            errors.append(
                f"{label}: camera_index must be >= 0 (got {camera_index!r})"
            )

        notes = p.get("notes")
        if notes is not None and len(notes) > 500:
            errors.append(
                f"{label}: notes must be <= 500 characters (got {len(notes)})"
            )

    seen_plug_aliases: set[str] = set()
    seen_plug_hosts: set[str] = set()

    for i, sp in enumerate(raw.get("smart_plugs", [])):
        label = f"Smart plug #{i + 1}"
        for field_name in ("alias", "host", "role"):
            if field_name not in sp:
                errors.append(f"{label}: missing required field '{field_name}'")

        alias = sp.get("alias")
        if alias is not None:
            if alias in seen_plug_aliases:
                errors.append(f"{label}: duplicate alias '{alias}'")
            else:
                seen_plug_aliases.add(alias)

        host = sp.get("host")
        if host is not None and not host:
            errors.append(f"{label}: host must not be empty")
        elif host is not None:
            if host in seen_plug_hosts:
                errors.append(f"{label}: duplicate host '{host}'")
            else:
                seen_plug_hosts.add(host)

        role = sp.get("role")
        if role is not None and role not in ("grow_light", "humidifier", "fan"):
            errors.append(
                f"{label}: role must be one of grow_light, humidifier, fan (got {role!r})"
            )

    return errors


def append_plant_to_toml(path: str | Path, plant: dict) -> None:
    """Append a new [[plants]] entry to flora.toml, preserving all existing content."""
    config_path = Path(path)
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""

    lines = ["\n[[plants]]"]
    for key, value in plant.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        elif value is not None:
            lines.append(f"{key} = {value}")

    with open(config_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def load_config(path: str | Path = "flora.toml") -> AppConfig:
    """Load and validate flora.toml, returning a frozen AppConfig."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    errors = validate_config(raw)
    if errors:
        raise ValueError("flora.toml validation failed:\n" + "\n".join(errors))

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
            auto_water_min_interval_minutes=p.get("auto_water_min_interval_minutes", 15),
            camera_index=p.get("camera_index"),
            notes=p.get("notes", ""),
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

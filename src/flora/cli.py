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
        name = _prompt("  Plant name (e.g. basil-1)", "").strip()
        if not name:
            break
        species = _prompt(f"  Species for {name} (basil/parsley/mint/chives/coriander)", "basil")
        mac = _prompt(f"  BLE MAC address for {name} (e.g. C4:7C:8D:XX:XX:XX)")
        gpio = int(_prompt(f"  GPIO relay pin for {name} pump", str(gpio_pin)))
        plants.append({"name": name, "species": species, "mac": mac, "gpio": gpio})
        gpio_pin += 1

    plugs: list[dict[str, object]] = []
    print("\nAdd smart plugs (press Enter with blank host to finish):")
    for role in ["grow_light", "humidifier", "fan"]:
        host = _prompt(f"  IP address for {role} plug (leave blank to skip)", "")
        if host:
            plugs.append({"alias": role, "host": host, "role": role})

    generate_config(out, api_key, tg_token, tg_chat, plants, plugs)
    print(f"\nConfig written to {out}")
    print("Run: flora flora.toml")

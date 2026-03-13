"""Tests for the flora-init setup wizard config generator."""
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

"""Tests for flora.toml config validation (issue #31)."""
from __future__ import annotations

import pytest

from flora.config import validate_config


def _base_plant(**overrides) -> dict:
    p = {
        "name": "basil",
        "species": "basil",
        "sensor_mac": "AA:BB:CC:DD:EE:01",
        "pump_gpio": 17,
        "moisture_target_min": 40,
        "moisture_target_max": 70,
    }
    p.update(overrides)
    return p


def test_valid_config_returns_no_errors():
    raw = {
        "app": {"db_path": "flora.db"},
        "plants": [_base_plant()],
    }
    assert validate_config(raw) == []


def test_valid_config_multiple_plants_returns_no_errors():
    raw = {
        "plants": [
            _base_plant(name="basil", sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17),
            _base_plant(name="mint",  sensor_mac="AA:BB:CC:DD:EE:02", pump_gpio=18),
        ]
    }
    assert validate_config(raw) == []


def test_duplicate_mac_detected():
    raw = {
        "plants": [
            _base_plant(name="basil", sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17),
            _base_plant(name="mint",  sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=18),
        ]
    }
    errors = validate_config(raw)
    assert any("duplicate sensor_mac" in e for e in errors)


def test_duplicate_gpio_detected():
    raw = {
        "plants": [
            _base_plant(name="basil", sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17),
            _base_plant(name="mint",  sensor_mac="AA:BB:CC:DD:EE:02", pump_gpio=17),
        ]
    }
    errors = validate_config(raw)
    assert any("duplicate pump_gpio" in e for e in errors)


def test_duplicate_name_detected():
    raw = {
        "plants": [
            _base_plant(name="basil", sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17),
            _base_plant(name="basil", sensor_mac="AA:BB:CC:DD:EE:02", pump_gpio=18),
        ]
    }
    errors = validate_config(raw)
    assert any("duplicate plant name" in e for e in errors)


def test_invalid_mac_format_detected():
    raw = {"plants": [_base_plant(sensor_mac="ZZZZ")]}
    errors = validate_config(raw)
    assert any("invalid sensor_mac" in e for e in errors)


def test_mac_case_insensitive_dedup():
    """AA:BB:CC:DD:EE:01 and aa:bb:cc:dd:ee:01 are the same MAC."""
    raw = {
        "plants": [
            _base_plant(name="basil", sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=17),
            _base_plant(name="mint",  sensor_mac="aa:bb:cc:dd:ee:01", pump_gpio=18),
        ]
    }
    errors = validate_config(raw)
    assert any("duplicate sensor_mac" in e for e in errors)


def test_moisture_min_gte_max_detected():
    raw = {"plants": [_base_plant(moisture_target_min=70, moisture_target_max=40)]}
    errors = validate_config(raw)
    assert any("moisture_target_min" in e for e in errors)


def test_moisture_min_equal_max_detected():
    raw = {"plants": [_base_plant(moisture_target_min=50, moisture_target_max=50)]}
    errors = validate_config(raw)
    assert any("moisture_target_min" in e for e in errors)


def test_missing_required_field_detected():
    raw = {"plants": [{"species": "basil", "sensor_mac": "AA:BB:CC:DD:EE:01", "pump_gpio": 17}]}
    errors = validate_config(raw)
    assert any("missing required field 'name'" in e for e in errors)


def test_all_errors_returned_at_once():
    """Multiple problems should all appear in the errors list simultaneously."""
    raw = {
        "plants": [
            # missing name, invalid mac, gpio out of range
            {"species": "basil", "sensor_mac": "BADMAC", "pump_gpio": 99},
        ]
    }
    errors = validate_config(raw)
    assert len(errors) >= 3


def test_gpio_out_of_range_detected():
    raw = {"plants": [_base_plant(pump_gpio=99)]}
    errors = validate_config(raw)
    assert any("pump_gpio" in e for e in errors)


def test_empty_plants_list_is_valid():
    raw = {"plants": []}
    assert validate_config(raw) == []


def test_load_config_raises_on_invalid(tmp_path):
    """load_config raises ValueError with all errors when validation fails."""
    from flora.config import load_config

    toml = tmp_path / "flora.toml"
    toml.write_text(
        '[app]\ndb_path = "flora.db"\n'
        '[anthropic]\napi_key = "sk-test"\n'
        '[telegram]\ntoken = ""\nchat_id = ""\n'
        '[[plants]]\nname = "basil"\nspecies = "basil"\n'
        'sensor_mac = "BADMAC"\npump_gpio = 17\n'
    )
    with pytest.raises(ValueError, match="flora.toml validation failed"):
        load_config(toml)

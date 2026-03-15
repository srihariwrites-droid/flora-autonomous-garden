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


def test_auto_water_duration_too_low_detected():
    raw = {"plants": [_base_plant(auto_water_duration_seconds=0)]}
    errors = validate_config(raw)
    assert any("auto_water_duration_seconds" in e for e in errors)


def test_auto_water_duration_too_high_detected():
    raw = {"plants": [_base_plant(auto_water_duration_seconds=31)]}
    errors = validate_config(raw)
    assert any("auto_water_duration_seconds" in e for e in errors)


def test_auto_water_duration_valid_range_passes():
    for val in (1, 15, 30):
        raw = {"plants": [_base_plant(auto_water_duration_seconds=val)]}
        assert validate_config(raw) == [], f"Expected no errors for duration={val}"


def test_moisture_target_min_below_zero_detected():
    raw = {"plants": [_base_plant(moisture_target_min=-1, moisture_target_max=70)]}
    errors = validate_config(raw)
    assert any("moisture_target_min" in e for e in errors)


def test_moisture_target_max_above_100_detected():
    raw = {"plants": [_base_plant(moisture_target_min=40, moisture_target_max=101)]}
    errors = validate_config(raw)
    assert any("moisture_target_max" in e for e in errors)


def test_moisture_target_min_above_100_detected():
    raw = {"plants": [_base_plant(moisture_target_min=110, moisture_target_max=120)]}
    errors = validate_config(raw)
    assert any("moisture_target_min" in e for e in errors)


def test_moisture_target_valid_boundaries_pass():
    for mn, mx in ((0, 1), (0, 100), (50, 100)):
        raw = {"plants": [_base_plant(moisture_target_min=mn, moisture_target_max=mx)]}
        assert validate_config(raw) == [], f"Expected no errors for min={mn}, max={mx}"


def test_auto_water_min_interval_zero_detected():
    raw = {"plants": [_base_plant(auto_water_min_interval_minutes=0)]}
    errors = validate_config(raw)
    assert any("auto_water_min_interval_minutes" in e for e in errors)


def test_auto_water_min_interval_negative_detected():
    raw = {"plants": [_base_plant(auto_water_min_interval_minutes=-5)]}
    errors = validate_config(raw)
    assert any("auto_water_min_interval_minutes" in e for e in errors)


def test_auto_water_min_interval_one_passes():
    raw = {"plants": [_base_plant(auto_water_min_interval_minutes=1)]}
    assert validate_config(raw) == []


def test_sensor_poll_interval_zero_detected():
    raw = {"app": {"sensor_poll_interval": 0}, "plants": []}
    errors = validate_config(raw)
    assert any("sensor_poll_interval" in e for e in errors)


def test_sensor_poll_interval_negative_detected():
    raw = {"app": {"sensor_poll_interval": -60}, "plants": []}
    errors = validate_config(raw)
    assert any("sensor_poll_interval" in e for e in errors)


def test_sensor_poll_interval_one_passes():
    raw = {"app": {"sensor_poll_interval": 1}, "plants": []}
    assert validate_config(raw) == []


def test_agent_loop_interval_zero_detected():
    raw = {"app": {"agent_loop_interval": 0}, "plants": []}
    errors = validate_config(raw)
    assert any("agent_loop_interval" in e for e in errors)


def test_agent_loop_interval_negative_detected():
    raw = {"app": {"agent_loop_interval": -1}, "plants": []}
    errors = validate_config(raw)
    assert any("agent_loop_interval" in e for e in errors)


def test_agent_loop_interval_one_passes():
    raw = {"app": {"agent_loop_interval": 1}, "plants": []}
    assert validate_config(raw) == []


def test_dashboard_port_zero_detected():
    raw = {"app": {"dashboard_port": 0}, "plants": []}
    errors = validate_config(raw)
    assert any("dashboard_port" in e for e in errors)


def test_dashboard_port_negative_detected():
    raw = {"app": {"dashboard_port": -1}, "plants": []}
    errors = validate_config(raw)
    assert any("dashboard_port" in e for e in errors)


def test_dashboard_port_above_max_detected():
    raw = {"app": {"dashboard_port": 65536}, "plants": []}
    errors = validate_config(raw)
    assert any("dashboard_port" in e for e in errors)


def test_dashboard_port_valid_boundaries_pass():
    for port in (1, 8000, 65535):
        raw = {"app": {"dashboard_port": port}, "plants": []}
        assert validate_config(raw) == [], f"Expected no errors for port={port}"


def _base_plug(**overrides) -> dict:
    sp = {"alias": "grow-light", "host": "192.168.1.10", "role": "grow_light"}
    sp.update(overrides)
    return sp


def test_smart_plug_missing_host_detected():
    raw = {"plants": [], "smart_plugs": [{"alias": "grow-light", "role": "grow_light"}]}
    errors = validate_config(raw)
    assert any("missing required field 'host'" in e for e in errors)


def test_smart_plug_missing_alias_detected():
    raw = {"plants": [], "smart_plugs": [{"host": "192.168.1.10", "role": "grow_light"}]}
    errors = validate_config(raw)
    assert any("missing required field 'alias'" in e for e in errors)


def test_smart_plug_missing_role_detected():
    raw = {"plants": [], "smart_plugs": [{"alias": "grow-light", "host": "192.168.1.10"}]}
    errors = validate_config(raw)
    assert any("missing required field 'role'" in e for e in errors)


def test_smart_plug_empty_host_detected():
    raw = {"plants": [], "smart_plugs": [_base_plug(host="")]}
    errors = validate_config(raw)
    assert any("host must not be empty" in e for e in errors)


def test_smart_plug_valid_config_passes():
    raw = {"plants": [], "smart_plugs": [_base_plug()]}
    assert validate_config(raw) == []

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
        '[anthropic]\napi_key = "sk-ant-xxxxxxxxxxxxxxxxxxxx"\n'
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


@pytest.mark.parametrize("value,should_error", [
    (0, True),
    (-60, True),
    (1, False),
])
def test_sensor_poll_interval_low_boundary(value, should_error):
    raw = {"app": {"sensor_poll_interval": value}, "plants": []}
    errors = validate_config(raw)
    if should_error:
        assert any("sensor_poll_interval" in e for e in errors)
    else:
        assert not any("sensor_poll_interval" in e for e in errors)


@pytest.mark.parametrize("value,should_error", [
    (0, True),
    (-1, True),
    (1, False),
])
def test_agent_loop_interval_low_boundary(value, should_error):
    raw = {"app": {"agent_loop_interval": value}, "plants": []}
    errors = validate_config(raw)
    if should_error:
        assert any("agent_loop_interval" in e for e in errors)
    else:
        assert not any("agent_loop_interval" in e for e in errors)


@pytest.mark.parametrize("port,should_error", [
    (0, True),
    (-1, True),
    (65536, True),
    (1, False),
    (8000, False),
    (65535, False),
])
def test_dashboard_port_boundary(port, should_error):
    raw = {"app": {"dashboard_port": port}, "plants": []}
    errors = validate_config(raw)
    if should_error:
        assert any("dashboard_port" in e for e in errors)
    else:
        assert not any("dashboard_port" in e for e in errors)


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


def test_smart_plug_unknown_role_detected():
    raw = {"plants": [], "smart_plugs": [_base_plug(role="heater")]}
    errors = validate_config(raw)
    assert any("role must be one of" in e for e in errors)


def test_smart_plug_all_valid_roles_pass():
    for role in ("grow_light", "humidifier", "fan"):
        raw = {"plants": [], "smart_plugs": [_base_plug(role=role)]}
        assert validate_config(raw) == [], f"Expected no errors for role={role!r}"


def test_auto_water_if_below_negative_detected():
    raw = {"plants": [_base_plant(auto_water_if_below=-1)]}
    errors = validate_config(raw)
    assert any("auto_water_if_below" in e for e in errors)


def test_auto_water_if_below_above_100_detected():
    raw = {"plants": [_base_plant(auto_water_if_below=101)]}
    errors = validate_config(raw)
    assert any("auto_water_if_below" in e for e in errors)


def test_auto_water_if_below_valid_boundaries_pass():
    for val in (0, 50, 100):
        p = _base_plant(auto_water_if_below=val)
        del p["moisture_target_min"]  # isolate range check from cross-field check
        raw = {"plants": [p]}
        assert validate_config(raw) == [], f"Expected no errors for auto_water_if_below={val}"


def test_auto_water_if_below_absent_passes():
    raw = {"plants": [_base_plant()]}
    assert validate_config(raw) == []


# --- species validation (issue #71) ---

def test_species_unknown_value_detected():
    raw = {"plants": [_base_plant(species="tomato")]}
    errors = validate_config(raw)
    assert any("species" in e for e in errors)


def test_species_all_known_values_pass():
    for species in ("basil", "parsley", "mint", "chives", "coriander"):
        raw = {"plants": [_base_plant(species=species)]}
        assert validate_config(raw) == [], f"Expected no errors for species={species!r}"


def test_camera_index_negative_detected():
    raw = {"plants": [_base_plant(camera_index=-1)]}
    errors = validate_config(raw)
    assert any("camera_index" in e for e in errors)


def test_camera_index_zero_passes():
    raw = {"plants": [_base_plant(camera_index=0)]}
    assert validate_config(raw) == []


def test_camera_index_positive_passes():
    raw = {"plants": [_base_plant(camera_index=2)]}
    assert validate_config(raw) == []


def test_camera_index_absent_passes():
    raw = {"plants": [_base_plant()]}
    assert validate_config(raw) == []


# --- db_path validation (issue #75) ---

def test_db_path_empty_string_detected():
    raw = {"app": {"db_path": ""}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("db_path" in e for e in errors)


def test_db_path_non_empty_passes():
    raw = {"app": {"db_path": "flora.db"}, "plants": [_base_plant()]}
    assert validate_config(raw) == []


def test_db_path_absent_passes():
    raw = {"plants": [_base_plant()]}
    assert validate_config(raw) == []


def test_db_path_null_byte_detected():
    raw = {"app": {"db_path": "flora\x00.db"}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("db_path" in e for e in errors)


def test_db_path_control_char_detected():
    raw = {"app": {"db_path": "flora\x01.db"}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("db_path" in e for e in errors)


def test_notes_too_long_detected():
    raw = {"plants": [_base_plant(notes="x" * 501)]}
    errors = validate_config(raw)
    assert any("notes" in e for e in errors)


def test_notes_at_limit_passes():
    raw = {"plants": [_base_plant(notes="x" * 500)]}
    assert validate_config(raw) == []


def test_notes_empty_passes():
    raw = {"plants": [_base_plant(notes="")]}
    assert validate_config(raw) == []


def test_notes_absent_passes():
    raw = {"plants": [_base_plant()]}
    assert validate_config(raw) == []


def test_telegram_token_without_chat_id_detected():
    raw = {"plants": [], "telegram": {"token": "abc123", "chat_id": ""}}
    errors = validate_config(raw)
    assert any("telegram" in e for e in errors)


def test_telegram_chat_id_without_token_detected():
    raw = {"plants": [], "telegram": {"token": "", "chat_id": "99999"}}
    errors = validate_config(raw)
    assert any("telegram" in e for e in errors)


def test_telegram_both_set_passes():
    raw = {"plants": [], "telegram": {"token": "123456789:ABCdef", "chat_id": "99999"}}
    assert validate_config(raw) == []


def test_telegram_both_empty_passes():
    raw = {"plants": [], "telegram": {"token": "", "chat_id": ""}}
    assert validate_config(raw) == []


def test_telegram_section_absent_passes():
    raw = {"plants": []}
    assert validate_config(raw) == []


def test_anthropic_api_key_empty_detected():
    raw = {"plants": [], "anthropic": {"api_key": ""}}
    errors = validate_config(raw)
    assert any("api_key" in e for e in errors)


def test_anthropic_api_key_non_empty_passes():
    raw = {"plants": [_base_plant()], "anthropic": {"api_key": "sk-ant-" + "x" * 20}}
    assert validate_config(raw) == []


def test_anthropic_section_absent_passes():
    raw = {"plants": []}
    assert validate_config(raw) == []


def test_pump_gpio_float_detected():
    raw = {"plants": [_base_plant(pump_gpio=17.0)]}
    errors = validate_config(raw)
    assert any("pump_gpio" in e for e in errors)


def test_smart_plug_duplicate_alias_detected():
    raw = {
        "plants": [],
        "smart_plugs": [
            _base_plug(alias="grow-light", host="192.168.1.10"),
            _base_plug(alias="grow-light", host="192.168.1.11"),
        ],
    }
    errors = validate_config(raw)
    assert any("duplicate alias" in e for e in errors)


def test_smart_plug_unique_aliases_pass():
    raw = {
        "plants": [],
        "smart_plugs": [
            _base_plug(alias="grow-light", host="192.168.1.10"),
            _base_plug(alias="humidifier", host="192.168.1.11", role="humidifier"),
        ],
    }
    assert validate_config(raw) == []


def test_smart_plug_duplicate_host_detected():
    raw = {
        "plants": [],
        "smart_plugs": [
            _base_plug(alias="grow-light", host="192.168.1.10"),
            _base_plug(alias="humidifier", host="192.168.1.10", role="humidifier"),
        ],
    }
    errors = validate_config(raw)
    assert any("duplicate host" in e for e in errors)


def test_smart_plug_unique_hosts_pass():
    raw = {
        "plants": [],
        "smart_plugs": [
            _base_plug(alias="grow-light", host="192.168.1.10"),
            _base_plug(alias="humidifier", host="192.168.1.11", role="humidifier"),
        ],
    }
    assert validate_config(raw) == []


def test_moisture_target_min_float_detected():
    raw = {"plants": [_base_plant(moisture_target_min=40.5, moisture_target_max=70)]}
    errors = validate_config(raw)
    assert any("moisture_target_min" in e for e in errors)


def test_moisture_target_max_float_detected():
    raw = {"plants": [_base_plant(moisture_target_min=40, moisture_target_max=70.5)]}
    errors = validate_config(raw)
    assert any("moisture_target_max" in e for e in errors)


def test_moisture_target_integer_values_pass():
    raw = {"plants": [_base_plant(moisture_target_min=40, moisture_target_max=70)]}
    assert validate_config(raw) == []


def test_anthropic_model_empty_detected():
    raw = {"plants": [_base_plant()], "anthropic": {"api_key": "sk-ant-" + "x" * 20, "model": ""}}
    errors = validate_config(raw)
    assert any("model" in e for e in errors)


def test_anthropic_model_non_empty_passes():
    raw = {"plants": [_base_plant()], "anthropic": {"api_key": "sk-ant-" + "x" * 20, "model": "claude-sonnet-4-6"}}
    assert validate_config(raw) == []


def test_anthropic_model_absent_passes():
    raw = {"plants": [_base_plant()], "anthropic": {"api_key": "sk-ant-" + "x" * 20}}
    assert validate_config(raw) == []


def test_sensor_poll_interval_float_detected():
    raw = {"app": {"sensor_poll_interval": 1800.5}, "plants": []}
    errors = validate_config(raw)
    assert any("sensor_poll_interval" in e for e in errors)


def test_agent_loop_interval_float_detected():
    raw = {"app": {"agent_loop_interval": 3600.0}, "plants": []}
    errors = validate_config(raw)
    assert any("agent_loop_interval" in e for e in errors)


def test_interval_integer_values_pass():
    raw = {"app": {"sensor_poll_interval": 1800, "agent_loop_interval": 7200}, "plants": []}
    assert validate_config(raw) == []


def test_dashboard_port_float_detected():
    raw = {"app": {"dashboard_port": 8000.0}, "plants": []}
    errors = validate_config(raw)
    assert any("dashboard_port" in e for e in errors)


def test_dashboard_port_integer_passes():
    raw = {"app": {"dashboard_port": 8000}, "plants": []}
    assert validate_config(raw) == []


def test_auto_water_duration_float_detected():
    raw = {"plants": [_base_plant(auto_water_duration_seconds=8.5)]}
    errors = validate_config(raw)
    assert any("auto_water_duration_seconds" in e for e in errors)


def test_auto_water_duration_integer_passes():
    raw = {"plants": [_base_plant(auto_water_duration_seconds=8)]}
    assert validate_config(raw) == []


def test_auto_water_min_interval_float_detected():
    raw = {"plants": [_base_plant(auto_water_min_interval_minutes=15.5)]}
    errors = validate_config(raw)
    assert any("auto_water_min_interval_minutes" in e for e in errors)


def test_auto_water_min_interval_integer_passes():
    raw = {"plants": [_base_plant(auto_water_min_interval_minutes=15)]}
    assert validate_config(raw) == []


def test_auto_water_if_below_float_detected():
    raw = {"plants": [_base_plant(auto_water_if_below=45.5)]}
    errors = validate_config(raw)
    assert any("auto_water_if_below" in e for e in errors)


def test_auto_water_if_below_integer_passes():
    p = _base_plant(auto_water_if_below=45)
    del p["moisture_target_min"]  # isolate type check from cross-field check
    raw = {"plants": [p]}
    assert validate_config(raw) == []


def test_plug_host_valid_ipv4_passes():
    for host in ("192.168.1.10", "10.0.0.1", "255.255.255.255", "0.0.0.0"):
        raw = {"plants": [], "smart_plugs": [_base_plug(host=host)]}
        assert validate_config(raw) == [], f"Expected no errors for host={host!r}"


def test_plug_host_valid_hostname_passes():
    for host in ("myplug", "my-plug", "plug.local", "smart-plug-01.lan"):
        raw = {"plants": [], "smart_plugs": [_base_plug(host=host)]}
        assert validate_config(raw) == [], f"Expected no errors for host={host!r}"


def test_plug_host_invalid_format_detected():
    for host in ("192.168.1 .10", "my plug", "host@local", "plug!", "192.168.1."):
        raw = {"plants": [], "smart_plugs": [_base_plug(host=host)]}
        errors = validate_config(raw)
        assert any("host" in e for e in errors), f"Expected error for host={host!r}"


def test_plant_name_valid_chars_pass():
    for name in ("basil", "my-herb", "herb_1", "Mint", "coriander-2"):
        raw = {"plants": [_base_plant(name=name)]}
        assert validate_config(raw) == [], f"Expected no errors for name={name!r}"


def test_plant_name_with_space_detected():
    raw = {"plants": [_base_plant(name="my basil")]}
    errors = validate_config(raw)
    assert any("name" in e for e in errors)


def test_plant_name_with_special_char_detected():
    for name in ("basil!", "herb@home", "mint/1"):
        raw = {"plants": [_base_plant(name=name)]}
        errors = validate_config(raw)
        assert any("name" in e for e in errors), f"Expected error for name={name!r}"


def test_plant_name_empty_detected():
    raw = {"plants": [_base_plant(name="")]}
    errors = validate_config(raw)
    assert any("name" in e for e in errors)


def test_plug_alias_valid_chars_pass():
    for alias in ("grow-light", "humidifier_1", "fan", "MyFan"):
        raw = {"plants": [], "smart_plugs": [_base_plug(alias=alias)]}
        assert validate_config(raw) == [], f"Expected no errors for alias={alias!r}"


def test_plug_alias_with_space_detected():
    raw = {"plants": [], "smart_plugs": [_base_plug(alias="grow light")]}
    errors = validate_config(raw)
    assert any("alias" in e for e in errors)


def test_plug_alias_with_special_char_detected():
    for alias in ("fan!", "plug@home", "light/1"):
        raw = {"plants": [], "smart_plugs": [_base_plug(alias=alias)]}
        errors = validate_config(raw)
        assert any("alias" in e for e in errors), f"Expected error for alias={alias!r}"


def test_plug_alias_empty_detected():
    raw = {"plants": [], "smart_plugs": [_base_plug(alias="")]}
    errors = validate_config(raw)
    assert any("alias" in e for e in errors)


def test_model_valid_passes():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20, "model": "claude-sonnet-4-6"}, "plants": [_base_plant()]}
    assert validate_config(raw) == []


def test_model_too_long_detected():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20, "model": "x" * 101}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("model" in e for e in errors)


def test_model_with_space_detected():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20, "model": "claude sonnet"}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("model" in e for e in errors)


def test_model_with_newline_detected():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20, "model": "claude\nsonnet"}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("model" in e for e in errors)


def test_model_exactly_100_chars_passes():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20, "model": "a" * 100}, "plants": [_base_plant()]}
    assert validate_config(raw) == []


def test_auto_water_if_below_less_than_min_passes():
    raw = {"plants": [_base_plant(auto_water_if_below=30, moisture_target_min=40)]}
    assert validate_config(raw) == []


def test_auto_water_if_below_equal_to_min_detected():
    raw = {"plants": [_base_plant(auto_water_if_below=40, moisture_target_min=40)]}
    errors = validate_config(raw)
    assert any("auto_water_if_below" in e for e in errors)


def test_auto_water_if_below_greater_than_min_detected():
    raw = {"plants": [_base_plant(auto_water_if_below=50, moisture_target_min=40)]}
    errors = validate_config(raw)
    assert any("auto_water_if_below" in e for e in errors)


def test_auto_water_if_below_absent_no_cross_error():
    raw = {"plants": [_base_plant(moisture_target_min=40)]}
    assert validate_config(raw) == []


def test_moisture_target_min_absent_no_cross_error():
    raw = {"plants": [_base_plant(auto_water_if_below=30)]}
    assert validate_config(raw) == []


def test_telegram_valid_token_and_chat_id_pass():
    raw = {"telegram": {"token": "123456789:ABCdef-ghiJKL_mnoPQR", "chat_id": "987654321"}}
    assert validate_config(raw) == []


def test_telegram_group_chat_id_passes():
    raw = {"telegram": {"token": "123456789:ABCdef", "chat_id": "-100123456789"}}
    assert validate_config(raw) == []


def test_telegram_token_missing_colon_detected():
    raw = {"telegram": {"token": "123456789ABCdef", "chat_id": "123"}}
    errors = validate_config(raw)
    assert any("token" in e for e in errors)


def test_telegram_token_non_numeric_id_detected():
    raw = {"telegram": {"token": "abc:ABCdef", "chat_id": "123"}}
    errors = validate_config(raw)
    assert any("token" in e for e in errors)


def test_telegram_chat_id_non_numeric_detected():
    raw = {"telegram": {"token": "123456789:ABCdef", "chat_id": "my_group"}}
    errors = validate_config(raw)
    assert any("chat_id" in e for e in errors)


@pytest.mark.parametrize("value,should_error", [
    (86400, False),
    (86401, True),
])
def test_sensor_poll_interval_high_boundary(value, should_error):
    raw = {"app": {"sensor_poll_interval": value}}
    errors = validate_config(raw)
    if should_error:
        assert any("sensor_poll_interval" in e for e in errors)
    else:
        assert not any("sensor_poll_interval" in e for e in errors)


@pytest.mark.parametrize("value,should_error", [
    (86400, False),
    (86401, True),
])
def test_agent_loop_interval_high_boundary(value, should_error):
    raw = {"app": {"agent_loop_interval": value}}
    errors = validate_config(raw)
    if should_error:
        assert any("agent_loop_interval" in e for e in errors)
    else:
        assert not any("agent_loop_interval" in e for e in errors)


def test_api_key_set_with_plants_passes():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20}, "plants": [_base_plant()]}
    assert validate_config(raw) == []


def test_api_key_set_with_no_plants_detected():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20}, "plants": []}
    errors = validate_config(raw)
    assert any("plants" in e for e in errors)


def test_api_key_absent_with_no_plants_passes():
    raw = {"plants": []}
    assert validate_config(raw) == []


def test_pump_gpio_reserved_pins_detected():
    for pin in (0, 1, 14, 15):
        p = _base_plant(pump_gpio=pin)
        raw = {"plants": [p]}
        errors = validate_config(raw)
        assert any("reserved" in e for e in errors), f"Expected reserved error for pin {pin}"


def test_pump_gpio_non_reserved_passes():
    for pin in (17, 27, 2, 3, 4):
        p = _base_plant(pump_gpio=pin)
        raw = {"plants": [p]}
        assert validate_config(raw) == [], f"Expected no errors for pin {pin}"


def test_api_key_valid_passes():
    raw = {"anthropic": {"api_key": "sk-ant-" + "x" * 20}, "plants": [_base_plant()]}
    assert validate_config(raw) == []


def test_api_key_too_short_detected():
    raw = {"anthropic": {"api_key": "sk-short"}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("api_key" in e for e in errors)


def test_api_key_with_space_detected():
    raw = {"anthropic": {"api_key": "sk-ant-valid key with space"}, "plants": [_base_plant()]}
    errors = validate_config(raw)
    assert any("api_key" in e for e in errors)


def test_camera_index_valid_passes():
    for idx in (0, 1, 9):
        raw = {"plants": [_base_plant(camera_index=idx)]}
        assert validate_config(raw) == [], f"Expected no errors for camera_index={idx}"


def test_camera_index_above_max_detected():
    raw = {"plants": [_base_plant(camera_index=10)]}
    errors = validate_config(raw)
    assert any("camera_index" in e for e in errors)


def test_notes_normal_text_passes():
    raw = {"plants": [_base_plant(notes="Kitchen windowsill\nWatered daily.")]}
    assert validate_config(raw) == []


def test_notes_null_byte_detected():
    raw = {"plants": [_base_plant(notes="good notes\x00bad")]}
    errors = validate_config(raw)
    assert any("notes" in e and "control" in e for e in errors)


def test_notes_control_char_detected():
    raw = {"plants": [_base_plant(notes="bad\x01char")]}
    errors = validate_config(raw)
    assert any("notes" in e and "control" in e for e in errors)


def test_moisture_float_min_no_false_cross_field_error():
    """A float moisture_target_min should produce a type error but NOT a cross-field error."""
    raw = {"plants": [_base_plant(moisture_target_min=20.5, moisture_target_max=70)]}
    errors = validate_config(raw)
    assert any("moisture_target_min" in e and "integer" in e for e in errors)
    assert not any("must be less than" in e for e in errors)

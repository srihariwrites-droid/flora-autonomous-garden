"""Tests for analytics helpers (issue #40)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from flora.analytics import estimate_hours_to_threshold
from flora.db import SensorReading


def _r(moisture: float, hours_ago: float) -> SensorReading:
    return SensorReading(
        plant_name="basil",
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        moisture=moisture,
        temperature=22.0,
        light=None,
        fertility=None,
        battery=None,
    )


def test_returns_none_when_no_readings():
    assert estimate_hours_to_threshold([], target_min=40) is None


def test_returns_none_when_single_reading():
    assert estimate_hours_to_threshold([_r(60.0, 1.0)], target_min=40) is None


def test_returns_none_when_moisture_increasing():
    # Moisture went up: oldest=50, newest=60 — rate is negative, skip
    readings = [_r(50.0, 2.0), _r(60.0, 0.0)]
    assert estimate_hours_to_threshold(readings, target_min=40) is None


def test_returns_none_when_decline_too_slow():
    # 0.1%/h decline — below 0.5%/h threshold
    readings = [_r(55.0, 10.0), _r(54.0, 0.0)]
    assert estimate_hours_to_threshold(readings, target_min=40) is None


def test_estimates_hours_for_fast_decline():
    # 60% → 50% over 2h = 5%/h decline; 50 - 40 = 10% remaining → 2h
    readings = [_r(60.0, 2.0), _r(50.0, 0.0)]
    result = estimate_hours_to_threshold(readings, target_min=40)
    assert result == pytest.approx(2.0, abs=0.1)


def test_estimates_hours_for_moderate_decline():
    # 70% → 64% over 3h = 2%/h decline; 64 - 40 = 24% remaining → 12h
    readings = [_r(70.0, 3.0), _r(64.0, 0.0)]
    result = estimate_hours_to_threshold(readings, target_min=40)
    assert result == pytest.approx(12.0, abs=0.1)


def test_returns_none_when_already_below_threshold():
    # Current moisture already below target_min
    readings = [_r(50.0, 2.0), _r(35.0, 0.0)]
    assert estimate_hours_to_threshold(readings, target_min=40) is None


def test_handles_many_readings_uses_oldest_and_newest():
    # oldest=80% at 4h ago, newest=72% now → 2%/h; 72-40=32% → 16h
    readings = [
        _r(80.0, 4.0),
        _r(77.0, 3.0),
        _r(74.5, 1.5),
        _r(72.0, 0.0),
    ]
    result = estimate_hours_to_threshold(readings, target_min=40)
    assert result == pytest.approx(16.0, abs=0.5)

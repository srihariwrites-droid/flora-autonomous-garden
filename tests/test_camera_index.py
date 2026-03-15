"""Tests for per-plant camera_index config (issue #26)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flora.config import PlantConfig


def test_camera_index_defaults_to_none():
    p = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
    )
    assert p.camera_index is None


def test_camera_index_set():
    p = PlantConfig(
        name="mint", species="mint",
        sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=18,
        camera_index=1,
    )
    assert p.camera_index == 1


async def test_capture_photo_passes_camera_index(tmp_path):
    """capture_photo forwards camera_index to _capture_real on Pi, mock on dev."""
    from flora.sensors.camera import capture_photo

    # On non-Pi, mock path is taken — just verify the file is created
    result = await capture_photo("basil", save_dir=tmp_path, camera_index=1)
    assert result is not None
    assert result.plant_name == "basil"
    assert result.path.exists()


async def test_run_photo_capture_passes_plant_camera_index(tmp_path):
    """_run_photo_capture passes plant.camera_index (or 0) to capture_photo."""
    from flora.scheduler import _run_photo_capture

    plant = PlantConfig(
        name="mint", species="mint",
        sensor_mac="AA:BB:CC:DD:EE:01", pump_gpio=18,
        camera_index=2,
    )
    config = MagicMock()
    config.plants = [plant]
    db = MagicMock()

    captured_calls = []

    async def mock_capture(plant_name, save_dir, camera_index=0):
        captured_calls.append({"plant_name": plant_name, "camera_index": camera_index})
        r = MagicMock()
        r.path = tmp_path / f"{plant_name}.jpg"
        return r

    with patch("flora.scheduler.capture_photo", side_effect=mock_capture):
        await _run_photo_capture(config, db)

    assert captured_calls == [{"plant_name": "mint", "camera_index": 2}]


async def test_run_photo_capture_defaults_to_0_when_camera_index_none(tmp_path):
    """When camera_index is None, capture_photo is called with camera_index=0."""
    from flora.scheduler import _run_photo_capture

    plant = PlantConfig(
        name="basil", species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF", pump_gpio=17,
        camera_index=None,
    )
    config = MagicMock()
    config.plants = [plant]
    db = MagicMock()

    captured_calls = []

    async def mock_capture(plant_name, save_dir, camera_index=0):
        captured_calls.append(camera_index)
        r = MagicMock()
        r.path = tmp_path / f"{plant_name}.jpg"
        return r

    with patch("flora.scheduler.capture_photo", side_effect=mock_capture):
        await _run_photo_capture(config, db)

    assert captured_calls == [0]

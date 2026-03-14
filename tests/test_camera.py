"""Camera capture tests — mock fallback only (no Pi hardware required)."""
from pathlib import Path
import pytest
from flora.sensors.camera import capture_photo, PhotoResult


@pytest.mark.asyncio
async def test_capture_returns_result_on_non_pi():
    """On non-Pi hardware, capture_photo returns a mock PhotoResult."""
    result = await capture_photo("basil-1", save_dir=Path("/tmp/flora-test-photos"))
    assert result is not None
    assert isinstance(result, PhotoResult)
    assert result.plant_name == "basil-1"
    assert result.path.exists()


@pytest.mark.asyncio
async def test_capture_creates_directory(tmp_path):
    save_dir = tmp_path / "photos"
    assert not save_dir.exists()
    result = await capture_photo("mint-1", save_dir=save_dir)
    assert save_dir.exists()
    assert result is not None

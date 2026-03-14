"""Camera capture tests — mock fallback only (no Pi hardware required)."""
from pathlib import Path
from unittest.mock import patch
import pytest
from flora.sensors.camera import capture_photo, PhotoResult, _render_plant, _capture_mock
from datetime import datetime


@pytest.mark.asyncio
async def test_capture_returns_result_on_non_pi():
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


def test_render_plant_returns_pillow_image(tmp_path):
    """_render_plant produces a valid PIL Image."""
    from PIL import Image
    img = _render_plant("basil", seed=42)
    assert img is not None
    assert isinstance(img, Image.Image)
    assert img.size == (640, 480)
    assert img.mode == "RGB"


def test_render_plant_is_seeded_deterministic():
    """Same seed → identical pixel at a fixed coordinate."""
    img1 = _render_plant("basil", seed=1234)
    img2 = _render_plant("basil", seed=1234)
    assert img1.getpixel((320, 240)) == img2.getpixel((320, 240))


def test_render_plant_differs_by_seed():
    """Different seeds produce different plant images (branch angles vary)."""
    img_a = _render_plant("basil", seed=1)
    img_b = _render_plant("basil", seed=9999)
    # Compare a broad sample of pixels in the plant body area
    pixels_differ = any(
        img_a.getpixel((x, y)) != img_b.getpixel((x, y))
        for x in range(200, 440, 20)
        for y in range(40, 160, 20)
    )
    assert pixels_differ


def test_capture_mock_falls_back_when_pillow_missing(tmp_path):
    """If Pillow is not available, _capture_mock writes a placeholder file instead of crashing."""
    path = tmp_path / "plant_mock.jpg"
    ts = datetime.utcnow()

    with patch("flora.sensors.camera._render_plant", side_effect=ImportError("no PIL")):
        result = _capture_mock("basil", path, ts)

    assert result is not None
    assert result.plant_name == "basil"
    assert path.exists()
    assert path.read_bytes() == b"MOCK_IMAGE"


def test_capture_mock_saves_jpeg(tmp_path):
    """On a normal system with Pillow, _capture_mock saves a real JPEG."""
    path = tmp_path / "plant.jpg"
    ts = datetime.utcnow()
    result = _capture_mock("coriander", path, ts)
    assert result.path.exists()
    # JPEG files start with FF D8
    header = path.read_bytes()[:2]
    assert header == b"\xff\xd8", f"Expected JPEG header, got {header!r}"

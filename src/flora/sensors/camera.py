"""Pi Camera capture with mock fallback for development."""
from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

IS_PI = platform.machine() == "aarch64"

# Minimal placeholder image bytes written for mock captures
_MOCK_PNG = b"MOCK_IMAGE"


@dataclass
class PhotoResult:
    plant_name: str
    timestamp: datetime
    path: Path


async def capture_photo(plant_name: str, save_dir: Path) -> PhotoResult | None:
    """Capture a photo of a plant. Returns None on failure."""
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow()
    filename = f"{plant_name}_{ts.strftime('%Y%m%d_%H%M%S')}.jpg"
    path = save_dir / filename

    if IS_PI:
        return await _capture_real(plant_name, path, ts)
    return _capture_mock(plant_name, path, ts)


async def _capture_real(plant_name: str, path: Path, ts: datetime) -> PhotoResult | None:
    try:
        from picamera2 import Picamera2  # type: ignore[import]
        cam = Picamera2()
        cam.configure(cam.create_still_configuration())
        cam.start()
        cam.capture_file(str(path))
        cam.stop()
        cam.close()
        logger.info("Photo captured: %s", path)
        return PhotoResult(plant_name=plant_name, timestamp=ts, path=path)
    except Exception as exc:
        logger.error("Camera capture failed: %s", exc)
        return None


def _capture_mock(plant_name: str, path: Path, ts: datetime) -> PhotoResult:
    path.write_bytes(_MOCK_PNG)
    logger.info("[MOCK] Photo saved: %s", path)
    return PhotoResult(plant_name=plant_name, timestamp=ts, path=path)

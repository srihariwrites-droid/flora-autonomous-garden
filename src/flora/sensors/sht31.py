"""SHT31 I2C ambient temperature and humidity sensor."""
from __future__ import annotations

import logging
import platform
import random
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

IS_PI = platform.machine() in ("aarch64", "armv7l")


@dataclass
class SHT31Reading:
    temperature: float   # Celsius
    humidity: float      # 0-100 %


async def read_sht31() -> SHT31Reading | None:
    """Read ambient temperature and humidity. Returns None on error."""
    if IS_PI:
        return _read_real()
    return _read_mock()


def _read_real() -> SHT31Reading | None:
    try:
        import board  # type: ignore[import]
        import adafruit_sht31d  # type: ignore[import]

        i2c = board.I2C()
        sensor = adafruit_sht31d.SHT31D(i2c)
        return SHT31Reading(
            temperature=float(sensor.temperature),
            humidity=float(sensor.relative_humidity),
        )
    except Exception as exc:
        logger.warning("SHT31 read failed: %s", exc)
        return None


def _read_mock() -> SHT31Reading:
    rng = random.Random(int(datetime.utcnow().hour))
    return SHT31Reading(
        temperature=rng.uniform(19, 24),
        humidity=rng.uniform(45, 65),
    )

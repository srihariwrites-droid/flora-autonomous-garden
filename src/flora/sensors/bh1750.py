"""BH1750 I2C ambient light sensor."""
from __future__ import annotations

import logging
import platform
import random
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

IS_PI = platform.machine() == "aarch64"


@dataclass
class BH1750Reading:
    light_lux: float   # lux


async def read_bh1750() -> BH1750Reading | None:
    """Read ambient light level in lux. Returns None on error."""
    if IS_PI:
        return _read_real()
    return _read_mock()


def _read_real() -> BH1750Reading | None:
    try:
        import board  # type: ignore[import]
        import adafruit_bh1750  # type: ignore[import]

        i2c = board.I2C()
        sensor = adafruit_bh1750.BH1750(i2c)
        return BH1750Reading(light_lux=float(sensor.lux))
    except Exception as exc:
        logger.warning("BH1750 read failed: %s", exc)
        return None


def _read_mock() -> BH1750Reading:
    rng = random.Random(int(datetime.utcnow().hour))
    hour = datetime.utcnow().hour
    # simulate day/night cycle
    if 6 <= hour <= 20:
        lux = rng.uniform(1000, 5000)
    else:
        lux = rng.uniform(0, 50)
    return BH1750Reading(light_lux=lux)

"""Mi Flora BLE soil sensor driver."""
from __future__ import annotations

import logging
import platform
import random
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

IS_PI = platform.machine() == "aarch64"


@dataclass
class MiFloraReading:
    moisture: float       # 0-100 %
    temperature: float    # Celsius
    light: int            # lux
    fertility: int        # µS/cm
    battery: int          # 0-100 %


async def read_miflora(mac: str) -> MiFloraReading | None:
    """Poll a Mi Flora sensor by MAC address. Returns None if unreachable."""
    if IS_PI:
        return await _read_real(mac)
    return _read_mock(mac)


async def _read_real(mac: str) -> MiFloraReading | None:
    try:
        from miflora.miflora_poller import MiFloraPoller  # type: ignore[import]
        from btlewrap.bluepy import BluepyBackend  # type: ignore[import]

        poller = MiFloraPoller(mac, BluepyBackend)
        return MiFloraReading(
            moisture=float(poller.parameter_value("moisture")),
            temperature=float(poller.parameter_value("temperature")),
            light=int(poller.parameter_value("light")),
            fertility=int(poller.parameter_value("conductivity")),
            battery=int(poller.parameter_value("battery")),
        )
    except Exception as exc:
        logger.warning("Mi Flora read failed for %s: %s", mac, exc)
        return None


def _read_mock(mac: str) -> MiFloraReading:
    """Return plausible mock sensor data seeded by MAC for repeatability."""
    seed = hash(mac) % 10000
    rng = random.Random(seed + int(datetime.utcnow().hour))
    return MiFloraReading(
        moisture=rng.uniform(35, 65),
        temperature=rng.uniform(18, 26),
        light=rng.randint(500, 8000),
        fertility=rng.randint(100, 400),
        battery=rng.randint(60, 100),
    )

"""GPIO relay pump control for water delivery."""
from __future__ import annotations

import asyncio
import logging
import platform
from datetime import datetime

logger = logging.getLogger(__name__)

IS_PI = platform.machine() == "aarch64"

# Max safe pump duration to prevent flooding
MAX_DURATION_SECONDS = 30


async def water_plant(gpio_pin: int, duration_seconds: int) -> bool:
    """
    Activate pump relay on gpio_pin for duration_seconds.
    Clamps duration to MAX_DURATION_SECONDS.
    Returns True on success, False on error.
    """
    duration = min(duration_seconds, MAX_DURATION_SECONDS)
    if duration <= 0:
        logger.warning("Ignoring water request with duration <= 0")
        return False

    logger.info("Watering: GPIO %d for %ds", gpio_pin, duration)

    if IS_PI:
        return await _activate_relay(gpio_pin, duration)
    return await _mock_activate(gpio_pin, duration)


async def _activate_relay(gpio_pin: int, duration: int) -> bool:
    try:
        from gpiozero import OutputDevice  # type: ignore[import]

        relay = OutputDevice(gpio_pin, active_high=False)
        relay.on()
        await asyncio.sleep(duration)
        relay.off()
        relay.close()
        return True
    except Exception as exc:
        logger.error("Pump relay GPIO %d failed: %s", gpio_pin, exc)
        return False


async def _mock_activate(gpio_pin: int, duration: int) -> bool:
    logger.info("[MOCK] Pump GPIO %d: activating for %ds", gpio_pin, duration)
    await asyncio.sleep(0.1)  # don't actually wait in dev
    logger.info("[MOCK] Pump GPIO %d: done", gpio_pin)
    return True

"""TP-Link Kasa smart plug control for lights, humidifier, fan."""
from __future__ import annotations

import logging
import platform
from datetime import time as dtime

logger = logging.getLogger(__name__)

IS_PI = platform.machine() == "aarch64"


async def toggle_plug(host: str, alias: str, on: bool) -> bool:
    """Turn a smart plug on or off by IP address."""
    logger.info("SmartPlug %s (%s): %s", alias, host, "ON" if on else "OFF")
    if IS_PI:
        return await _kasa_toggle(host, on)
    logger.info("[MOCK] SmartPlug %s: %s", alias, "ON" if on else "OFF")
    return True


async def set_schedule(
    host: str,
    alias: str,
    on_time: dtime,
    off_time: dtime,
) -> bool:
    """
    Set a daily on/off schedule on a Kasa plug.
    Clears existing schedules and sets new ones.
    """
    logger.info(
        "SmartPlug %s (%s): schedule ON=%s OFF=%s",
        alias, host, on_time, off_time,
    )
    if IS_PI:
        return await _kasa_set_schedule(host, on_time, off_time)
    logger.info("[MOCK] SmartPlug %s: schedule set", alias)
    return True


async def _kasa_toggle(host: str, on: bool) -> bool:
    try:
        from kasa import SmartPlug  # type: ignore[import]

        plug = SmartPlug(host)
        await plug.update()
        if on:
            await plug.turn_on()
        else:
            await plug.turn_off()
        return True
    except Exception as exc:
        logger.error("Kasa toggle failed for %s: %s", host, exc)
        return False


async def _kasa_set_schedule(host: str, on_time: dtime, off_time: dtime) -> bool:
    try:
        from kasa import SmartPlug  # type: ignore[import]
        from kasa.modules import Schedule  # type: ignore[import]

        plug = SmartPlug(host)
        await plug.update()
        schedule: Schedule = plug.modules["schedule"]

        # Remove existing rules
        existing = await schedule.get_rules()
        for rule in existing.rules:
            await schedule.delete_rule(rule)

        # Add ON rule
        await schedule.add_rule(
            on=True,
            start=on_time.hour * 60 + on_time.minute,
            repeat=True,
        )
        # Add OFF rule
        await schedule.add_rule(
            on=False,
            start=off_time.hour * 60 + off_time.minute,
            repeat=True,
        )
        await plug.update()
        return True
    except Exception as exc:
        logger.error("Kasa schedule failed for %s: %s", host, exc)
        return False

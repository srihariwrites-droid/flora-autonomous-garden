"""Telegram notification support for Flora."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Send a Telegram message. Returns True on success."""
    if not token or not chat_id:
        logger.warning("Telegram not configured — skipping notification")
        return False
    try:
        from telegram import Bot  # type: ignore[import]
        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode=None)
        logger.info("Telegram sent: %s", message[:60])
        return True
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


async def send_daily_summary(
    token: str,
    chat_id: str,
    plant_summaries: list[dict[str, object]],
    photo_paths: dict[str, Path] | None = None,
) -> bool:
    """Send a daily summary of all plant statuses.

    If photo_paths is provided, sends one photo per plant (with a caption)
    before the aggregate text summary. Gracefully falls back to text-only
    if a photo send fails.
    """
    if not plant_summaries:
        return False

    if photo_paths:
        await _send_plant_photos(token, chat_id, plant_summaries, photo_paths)

    lines = ["Flora Daily Summary\n"]
    for plant in plant_summaries:
        name = plant.get("name", "?")
        moisture = plant.get("moisture")
        temp = plant.get("temperature")
        status = plant.get("status", "unknown")
        m_str = f"{moisture:.0f}%" if isinstance(moisture, (int, float)) else "N/A"
        t_str = f"{temp:.1f}°C" if isinstance(temp, (int, float)) else "N/A"
        lines.append(f"• {name}: moisture={m_str}, temp={t_str} [{status}]")

    message = "\n".join(lines)
    return await send_telegram(token, chat_id, message)


async def _send_plant_photos(
    token: str,
    chat_id: str,
    plant_summaries: list[dict[str, object]],
    photo_paths: dict[str, Path],
) -> None:
    """Send one photo per plant that has a path in photo_paths."""
    if not token or not chat_id:
        return
    try:
        from telegram import Bot  # type: ignore[import]
        bot = Bot(token=token)
        for plant in plant_summaries:
            name = str(plant.get("name", ""))
            photo = photo_paths.get(name)
            if photo is None or not photo.exists():
                continue
            status = plant.get("status", "unknown")
            moisture = plant.get("moisture")
            m_str = f"{moisture:.0f}%" if isinstance(moisture, (int, float)) else "N/A"
            caption = f"{name} — {status}, moisture {m_str}"
            try:
                with photo.open("rb") as fh:
                    await bot.send_photo(chat_id=chat_id, photo=fh, caption=caption)
                logger.info("Sent photo for %s", name)
            except Exception as exc:
                logger.warning("Could not send photo for %s: %s", name, exc)
    except Exception as exc:
        logger.warning("Photo send setup failed: %s", exc)

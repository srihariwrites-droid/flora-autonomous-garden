"""Telegram notification support for Flora."""
from __future__ import annotations

import logging

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
) -> bool:
    """Send a daily summary of all plant statuses."""
    if not plant_summaries:
        return False

    lines = ["🌿 Flora Daily Summary\n"]
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

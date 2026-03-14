"""Telegram notification integration tests — skipped if env vars not set."""
import asyncio
import os
import threading
import pytest
from flora.notifications import send_telegram, send_daily_summary

SKIP_IF_NO_TELEGRAM = pytest.mark.skipif(
    not (os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
    reason="TELEGRAM_TOKEN and TELEGRAM_CHAT_ID not set",
)


@SKIP_IF_NO_TELEGRAM
async def test_send_telegram_message():
    """Sends a real test message via Telegram."""
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    result = await send_telegram(token, chat_id, "Flora test message — integration test")
    assert result is True


def test_send_telegram_skips_when_unconfigured():
    """Returns False gracefully when token is empty.

    Run in a dedicated thread so its event loop is isolated from any
    session-level loop left open by pytest-playwright fixtures.
    """
    results: list[bool] = []

    def _run() -> None:
        loop = asyncio.new_event_loop()
        try:
            results.append(loop.run_until_complete(send_telegram("", "", "should not send")))
        finally:
            loop.close()

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    assert results[0] is False


@SKIP_IF_NO_TELEGRAM
async def test_send_daily_summary():
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    summaries = [
        {"name": "basil-1", "moisture": 55.0, "temperature": 22.1, "status": "healthy"},
        {"name": "mint-1", "moisture": 8.0, "temperature": 21.5, "status": "critical"},
    ]
    result = await send_daily_summary(token, chat_id, summaries)
    assert result is True

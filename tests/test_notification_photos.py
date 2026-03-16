"""Tests for send_daily_summary photo attachment (issue #17)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

SUMMARIES = [
    {"name": "basil", "moisture": 55.0, "temperature": 22.1, "status": "healthy"},
    {"name": "mint", "moisture": 8.0, "temperature": 21.5, "status": "critical"},
]


async def test_send_daily_summary_text_only_when_no_photos():
    """When photo_paths is None, only send_telegram is called."""
    from flora.notifications import send_daily_summary

    with patch("flora.notifications.send_telegram", new=AsyncMock(return_value=True)) as mock_tg:
        result = await send_daily_summary("tok", "123", SUMMARIES, photo_paths=None)

    assert result is True
    mock_tg.assert_awaited_once()
    msg = mock_tg.call_args[0][2]
    assert "basil" in msg
    assert "mint" in msg


async def test_send_daily_summary_sends_photo_for_each_plant(tmp_path):
    """One sendPhoto call per plant that has a photo, then text summary."""
    from flora.notifications import send_daily_summary

    basil_photo = tmp_path / "basil_20260315.jpg"
    basil_photo.write_bytes(b"\xff\xd8fake")

    photo_paths = {"basil": basil_photo}  # mint has no photo

    mock_bot = MagicMock()
    mock_bot.send_photo = AsyncMock()
    mock_bot.send_message = AsyncMock()

    with patch("flora.notifications.send_telegram", new=AsyncMock(return_value=True)) as mock_tg, \
         patch("telegram.Bot", return_value=mock_bot):
        result = await send_daily_summary("tok", "123", SUMMARIES, photo_paths=photo_paths)

    # One photo sent (only basil has one)
    mock_bot.send_photo.assert_awaited_once()
    call_kwargs = mock_bot.send_photo.call_args[1]
    assert call_kwargs["chat_id"] == "123"
    assert "basil" in call_kwargs["caption"]

    # Text summary still sent
    assert result is True
    mock_tg.assert_awaited_once()


async def test_send_daily_summary_falls_back_to_text_on_photo_error(tmp_path):
    """If send_photo raises, text summary is still sent."""
    from flora.notifications import send_daily_summary

    basil_photo = tmp_path / "basil_20260315.jpg"
    basil_photo.write_bytes(b"\xff\xd8fake")

    mock_bot = MagicMock()
    mock_bot.send_photo = AsyncMock(side_effect=Exception("network error"))
    mock_bot.send_message = AsyncMock()

    with patch("flora.notifications.send_telegram", new=AsyncMock(return_value=True)) as mock_tg, \
         patch("telegram.Bot", return_value=mock_bot):
        result = await send_daily_summary("tok", "123", SUMMARIES, photo_paths={"basil": basil_photo})

    # Text summary still sent despite photo failure
    assert result is True
    mock_tg.assert_awaited_once()


async def test_send_daily_summary_skips_missing_photo_file(tmp_path):
    """If path listed but file doesn't exist, photo is skipped silently."""
    from flora.notifications import send_daily_summary

    nonexistent = tmp_path / "basil_missing.jpg"

    mock_bot = MagicMock()
    mock_bot.send_photo = AsyncMock()

    with patch("flora.notifications.send_telegram", new=AsyncMock(return_value=True)), \
         patch("telegram.Bot", return_value=mock_bot):
        result = await send_daily_summary("tok", "123", SUMMARIES, photo_paths={"basil": nonexistent})

    mock_bot.send_photo.assert_not_awaited()
    assert result is True


async def test_send_daily_summary_returns_false_for_empty_summaries():
    from flora.notifications import send_daily_summary

    with patch("flora.notifications.send_telegram", new=AsyncMock()) as mock_tg:
        result = await send_daily_summary("tok", "123", [])

    assert result is False
    mock_tg.assert_not_awaited()


async def test_photo_file_handle_closed_after_send(tmp_path):
    """File handle opened for send_photo must be closed after the call returns."""
    from flora.notifications import send_daily_summary

    basil_photo = tmp_path / "basil_20260315.jpg"
    basil_photo.write_bytes(b"\xff\xd8fake")

    sent_handles: list = []

    mock_bot = MagicMock()

    async def capture_photo(**kwargs):
        sent_handles.append(kwargs.get("photo"))

    mock_bot.send_photo = AsyncMock(side_effect=capture_photo)

    with patch("flora.notifications.send_telegram", new=AsyncMock(return_value=True)), \
         patch("telegram.Bot", return_value=mock_bot):
        await send_daily_summary("tok", "123", SUMMARIES, photo_paths={"basil": basil_photo})

    assert sent_handles, "send_photo was not called"
    assert sent_handles[0].closed, "file handle was not closed after send_photo"

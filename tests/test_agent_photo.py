"""Tests for agent loop photo attachment (issue #15)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flora.agent.loop import _latest_photo


# ---------------------------------------------------------------------------
# _latest_photo helper
# ---------------------------------------------------------------------------

def test_latest_photo_returns_none_when_dir_missing(tmp_path):
    missing = tmp_path / "no_such_dir"
    assert _latest_photo(missing, "basil") is None


def test_latest_photo_returns_none_when_no_files(tmp_path):
    assert _latest_photo(tmp_path, "basil") is None


def test_latest_photo_returns_most_recent(tmp_path):
    old = tmp_path / "basil_20260101_070000.jpg"
    new = tmp_path / "basil_20260315_070000.jpg"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    import time; time.sleep(0.01)
    new.touch()  # ensure newer mtime
    result = _latest_photo(tmp_path, "basil")
    assert result == new


def test_latest_photo_ignores_other_plants(tmp_path):
    (tmp_path / "mint_20260315_070000.jpg").write_bytes(b"mint")
    assert _latest_photo(tmp_path, "basil") is None


def test_latest_photo_ignores_non_jpg(tmp_path):
    (tmp_path / "basil_20260315_070000.png").write_bytes(b"png")
    assert _latest_photo(tmp_path, "basil") is None


# ---------------------------------------------------------------------------
# AgentLoop._run_claude_loop photo attachment
# ---------------------------------------------------------------------------

async def test_photo_block_included_in_message(tmp_path):
    """When a photo exists, an image content block must appear in the user message."""
    import base64

    # Write a small fake JPEG
    photo = tmp_path / "basil_20260315_070000.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0fake_jpeg_bytes")

    from flora.agent.loop import AgentLoop
    from flora.config import AppConfig, PlantConfig

    plant = PlantConfig(
        name="basil",
        species="basil",
        sensor_mac="AA:BB:CC:DD:EE:FF",
        pump_gpio=17,
        moisture_target_min=40,
        moisture_target_max=70,
    )
    config = MagicMock(spec=AppConfig)
    config.plants = [plant]
    config.anthropic_api_key = "test"
    config.anthropic_model = "claude-3-5-haiku-20241022"

    db = MagicMock()
    db.get_latest_ambient = AsyncMock(return_value=None)
    db.get_sensor_history = AsyncMock(return_value=[])
    db.get_journal = AsyncMock(return_value=[])

    # Fake Claude response — stop immediately (no tool use)
    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    fake_response.content = []

    captured_messages = []

    async def fake_create(**kwargs):
        captured_messages.extend(kwargs["messages"])
        return fake_response

    with patch("flora.agent.loop.Path", side_effect=lambda p: tmp_path if p == "photos" else Path(p)):
        loop = AgentLoop(config, db)
        loop._client = MagicMock()
        loop._client.messages = MagicMock()
        loop._client.messages.create = fake_create

        await loop._run_claude_loop()

    assert captured_messages, "No messages were sent"
    user_content = captured_messages[0]["content"]
    assert isinstance(user_content, list), "Content should be a list of blocks"

    image_blocks = [b for b in user_content if b.get("type") == "image"]
    assert len(image_blocks) == 1, f"Expected 1 image block, got {len(image_blocks)}"
    assert image_blocks[0]["source"]["media_type"] == "image/jpeg"
    expected_b64 = base64.standard_b64encode(photo.read_bytes()).decode()
    assert image_blocks[0]["source"]["data"] == expected_b64


async def test_no_photo_block_when_no_photo(tmp_path):
    """When no photo exists, content should have only text blocks."""
    from flora.agent.loop import AgentLoop
    from flora.config import AppConfig, PlantConfig

    plant = PlantConfig(
        name="mint",
        species="mint",
        sensor_mac="AA:BB:CC:DD:EE:01",
        pump_gpio=18,
        moisture_target_min=50,
        moisture_target_max=80,
    )
    config = MagicMock(spec=AppConfig)
    config.plants = [plant]
    config.anthropic_api_key = "test"
    config.anthropic_model = "claude-3-5-haiku-20241022"

    db = MagicMock()
    db.get_latest_ambient = AsyncMock(return_value=None)
    db.get_sensor_history = AsyncMock(return_value=[])
    db.get_journal = AsyncMock(return_value=[])

    fake_response = MagicMock()
    fake_response.stop_reason = "end_turn"
    fake_response.content = []

    captured_messages = []

    async def fake_create(**kwargs):
        captured_messages.extend(kwargs["messages"])
        return fake_response

    with patch("flora.agent.loop.Path", side_effect=lambda p: tmp_path if p == "photos" else Path(p)):
        loop = AgentLoop(config, db)
        loop._client = MagicMock()
        loop._client.messages = MagicMock()
        loop._client.messages.create = fake_create

        await loop._run_claude_loop()

    user_content = captured_messages[0]["content"]
    image_blocks = [b for b in user_content if b.get("type") == "image"]
    assert image_blocks == [], "No image blocks expected when no photo present"

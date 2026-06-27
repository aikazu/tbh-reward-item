"""Shared fixtures for dev_tools.scrape_pipeline tests."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def fake_image_bytes() -> bytes:
    """Return PNG bytes for a 512x512 image (decodeable by Pillow)."""
    img = Image.new("RGB", (512, 512), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def fake_corrupt_bytes() -> bytes:
    """Return bytes that are NOT a valid image."""
    return b"this is not an image, just text"


@pytest.fixture
def sample_json_tree(tmp_path: Path) -> Path:
    """Create a tmp dir with 3 gear + 2 material + 1 box JSON files.

    Returns the tmp_path root. Files reference image URLs with item IDs
    300001-300003 (gear), 100001-100002 (material), 200001 (box).
    """
    # gear
    gear_dir = tmp_path / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    (gear_dir / "legendary.json").write_text(json.dumps([
        {"id": 300001, "name": "Long Sword", "image": "https://x/sword1.png"},
        {"id": 300002, "name": "Short Sword", "image": "https://x/sword2.png"},
        {"id": 300003, "name": "Great Sword", "image": "https://x/sword3.png"},
    ]))
    # material
    item_dir = tmp_path / "item" / "CRAFTING"
    item_dir.mkdir(parents=True)
    (item_dir / "RARE.json").write_text(json.dumps([
        {"id": 100001, "name": "Bronze Ingot", "image": "https://x/ingot1.png"},
        {"id": 100002, "name": "Iron Ingot", "image": "https://x/ingot2.png"},
    ]))
    # box
    box_dir = tmp_path / "box_loot_cache"
    box_dir.mkdir(parents=True)
    (box_dir / "42.json").write_text(json.dumps([
        {"id": 200001, "name": "Mystery Box", "image": "https://x/box42.png", "box_id": 42},
    ]))
    return tmp_path

"""Tests for dev_tools.scrape_pipeline.image_stage."""
from __future__ import annotations

from pathlib import Path

from dev_tools.scrape_pipeline.image_stage import collect_images


def test_collect_walks_all_json_dirs(sample_json_tree: Path):
    """Should discover all items across gear/item/box JSON caches."""
    result = collect_images(sample_json_tree)
    ids = sorted(result.keys())
    assert ids == [100001, 100002, 200001, 300001, 300002, 300003]


def test_collect_returns_url_per_id(sample_json_tree: Path):
    """Each id maps to its first-seen image URL."""
    result = collect_images(sample_json_tree)
    assert result[300001] == "https://x/sword1.png"
    assert result[100001] == "https://x/ingot1.png"
    assert result[200001] == "https://x/box42.png"


def test_collect_dedups_by_id(sample_json_tree: Path):
    """If the same id appears in multiple files, first URL wins."""
    # Add a duplicate id in a new file
    dup = sample_json_tree / "gear" / "sword" / "common.json"
    dup.write_text(__import__("json").dumps([
        {"id": 300001, "name": "Dup", "image": "https://x/different.png"},
    ]))
    result = collect_images(sample_json_tree)
    # First-seen (legendary.json) wins
    assert result[300001] == "https://x/sword1.png"


def test_collect_skips_items_without_image(sample_json_tree: Path):
    """Items missing 'image' field are silently dropped."""
    import json
    p = sample_json_tree / "gear" / "sword" / "mythic.json"
    p.write_text(json.dumps([
        {"id": 300099, "name": "No Image"},  # no image field
        {"id": 300100, "name": "Has Image", "image": "https://x/has.png"},
    ]))
    result = collect_images(sample_json_tree)
    assert 300099 not in result
    assert result[300100] == "https://x/has.png"


def test_collect_empty_tree_returns_empty(tmp_path: Path):
    """No JSON files = empty dict, no raise."""
    assert collect_images(tmp_path) == {}

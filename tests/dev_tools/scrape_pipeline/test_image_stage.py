"""Tests for dev_tools.scrape_pipeline.image_stage."""
from __future__ import annotations

from pathlib import Path

from dev_tools.scrape_pipeline.image_stage import collect_images  # pyright: ignore[reportMissingImports]


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

from unittest.mock import MagicMock, patch

from dev_tools.scrape_pipeline.errors import ImageMissingError
from dev_tools.scrape_pipeline.image_stage import _process_one_image


def test_process_one_image_success(tmp_path: Path, fake_image_bytes: bytes):
    """Successful download + convert writes a WebP file at expected path."""
    dest = tmp_path / "out.webp"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        result = _process_one_image(300001, "https://x/sword.png", dest)
    assert result == "downloaded"
    assert dest.exists()
    assert dest.stat().st_size > 0


def test_process_one_image_skips_existing(tmp_path: Path):
    """If dest already exists, skip without re-downloading."""
    dest = tmp_path / "exists.webp"
    dest.write_bytes(b"already here")
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = b""  # would fail decode; should not be called
        result = _process_one_image(300001, "https://x/sword.png", dest)
    assert result == "skipped"
    assert dest.read_bytes() == b"already here"  # unchanged


def test_process_one_image_http_404_raises_image_missing(tmp_path: Path):
    """HTTP 404 must raise ImageMissingError so caller logs + skips."""
    dest = tmp_path / "out.webp"
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.raise_for_status.side_effect = Exception("404")
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.side_effect = ImageMissingError("404 not found")
        try:
            _process_one_image(300001, "https://x/missing.png", dest)
        except ImageMissingError:
            pass
        else:
            raise AssertionError("expected ImageMissingError")
    assert not dest.exists()


def test_process_one_image_network_error_raises_image_error(tmp_path: Path):
    """Network failures raise ImageError so caller logs + skips."""
    from dev_tools.scrape_pipeline.errors import ImageError
    dest = tmp_path / "out.webp"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.side_effect = ImageError("connection refused")
        try:
            _process_one_image(300001, "https://x/down.png", dest)
        except ImageError:
            pass
        else:
            raise AssertionError("expected ImageError")
    assert not dest.exists()


def test_process_one_image_corrupt_bytes_raises(tmp_path: Path, fake_corrupt_bytes: bytes):
    """Non-image bytes raise (caller logs + skips)."""
    from dev_tools.scrape_pipeline.errors import ImageError
    dest = tmp_path / "out.webp"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_corrupt_bytes
        try:
            _process_one_image(300001, "https://x/bad.png", dest)
        except ImageError:
            pass
        else:
            raise AssertionError("expected ImageError on corrupt bytes")
    assert not dest.exists()


from dev_tools.scrape_pipeline.image_stage import run_bundle


def test_run_bundle_processes_all_items(sample_json_tree: Path, tmp_path: Path, fake_image_bytes: bytes):
    """run_bundle collects from JSON tree, downloads each, writes WebP."""
    out_root = tmp_path / "out"
    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        stats = run_bundle(sample_json_tree, out_root, workers=2)
    # 6 items in fixture
    assert stats["images_total"] == 6
    assert stats["downloaded"] == 6
    assert stats["failed"] == 0
    # files on disk
    for iid in (300001, 300002, 300003, 100001, 100002, 200001):
        assert (out_root / "images" / f"{iid}.webp").exists()


def test_run_bundle_records_failures_without_aborting(sample_json_tree: Path, tmp_path: Path, fake_image_bytes: bytes):
    """Per-item failure must be recorded + counted, not abort the run."""
    from dev_tools.scrape_pipeline.errors import ImageMissingError
    out_root = tmp_path / "out"
    call_count = {"n": 0}

    def flaky(url):
        call_count["n"] += 1
        if "sword1" in url:
            raise ImageMissingError("404")
        return fake_image_bytes

    with patch("dev_tools.scrape_pipeline.image_stage._download", side_effect=flaky):
        stats = run_bundle(sample_json_tree, out_root, workers=1)
    assert stats["images_total"] == 6
    assert stats["downloaded"] == 5
    assert stats["failed"] == 1
    # missing one not on disk
    assert not (out_root / "images" / "300001.webp").exists()
    assert (out_root / "images" / "300002.webp").exists()


def test_run_bundle_skips_existing(tmp_path: Path, fake_image_bytes: bytes):
    """Existing WebP files must be skipped (resume behavior)."""
    # Build a minimal JSON tree with 2 items
    json_root = tmp_path / "cache"
    gear_dir = json_root / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    import json as _json
    (gear_dir / "common.json").write_text(_json.dumps([
        {"id": 300010, "image": "https://x/a.png"},
        {"id": 300011, "image": "https://x/b.png"},
    ]))
    out_root = tmp_path / "out"
    img_dir = out_root / "images"
    img_dir.mkdir(parents=True)
    # Pre-create one WebP
    (img_dir / "300010.webp").write_bytes(b"already here")

    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        stats = run_bundle(json_root, out_root, workers=1)
    assert stats["images_total"] == 2
    assert stats["downloaded"] == 1
    assert stats["skipped"] == 1

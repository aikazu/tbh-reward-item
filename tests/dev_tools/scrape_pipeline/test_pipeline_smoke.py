"""End-to-end pipeline smoke test (marked slow, excluded by default)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dev_tools.scrape_pipeline.image_stage import run_bundle
from dev_tools.scrape_pipeline.manifest import read_manifest, write_manifest


@pytest.mark.integration
def test_pipeline_smoke_real_pillow(tmp_path: Path, fake_image_bytes: bytes):
    """Real Pillow decode + WebP encode on fixture bytes, with mocked HTTP."""
    # Build minimal JSON cache: 3 items
    cache = tmp_path / "cache"
    gear_dir = cache / "gear" / "sword"
    gear_dir.mkdir(parents=True)
    (gear_dir / "common.json").write_text(json.dumps([
        {"id": 300010, "image": "https://x/a.png"},
        {"id": 300011, "image": "https://x/b.png"},
        {"id": 300012, "image": "https://x/c.png"},
    ]))
    out_root = tmp_path / "out"

    with patch("dev_tools.scrape_pipeline.image_stage._download") as dl:
        dl.return_value = fake_image_bytes
        stats = run_bundle(cache, out_root, workers=2)

    assert stats["images_total"] == 3
    assert stats["downloaded"] == 3
    assert stats["failed"] == 0

    # Verify WebP files actually decodeable + correct size
    from PIL import Image
    for iid in (300010, 300011, 300012):
        path = out_root / "images" / f"{iid}.webp"
        assert path.exists()
        with Image.open(path) as img:
            assert img.size == (256, 256)
            assert img.format == "WEBP"

    # Manifest round-trip
    manifest_path = out_root / "manifest.json"
    write_manifest({"scrape": {}, "images": stats}, manifest_path)
    loaded = read_manifest(manifest_path)
    assert loaded["images"] == stats

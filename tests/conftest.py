"""Shared test fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_config_dict() -> dict:
    return {
        "listen_port": 8877,
        "only_post": True,
        "require_boxes_marker": True,
        "url_contains": ["/backend-function/base/v1"],
        "specific_queue_rules": [
            {
                "enabled": True,
                "name": "White box",
                "item_id": 910801,
                "replacement_reward_item_ids": [406171],
            }
        ],
        "range_replacement": {
            "enabled": True,
            "name": "Range replacement",
            "match_min_item_id": 500000,
            "match_max_item_id": 950000,
            "replacement_reward_item_ids": [605041, 615041],
        },
    }


@pytest.fixture
def config_file(tmp_path: Path, sample_config_dict: dict) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config_dict, indent=4), encoding="utf-8")
    return p
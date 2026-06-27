"""Tests for dev_tools.scrape_pipeline.errors."""
from __future__ import annotations

import json

import lxml.etree
import pytest
import requests

from dev_tools.scrape_pipeline.errors import (
    ImageError,
    ImageMissingError,
    NetworkError,
    RateLimitError,
    SchemaError,
    ScrapeError,
    categorize,
)


def test_categorize_connection_error_is_network():
    exc = requests.exceptions.ConnectionError("refused")
    assert isinstance(categorize(exc), NetworkError)


def test_categorize_timeout_is_network():
    exc = requests.exceptions.Timeout("slow")
    assert isinstance(categorize(exc), NetworkError)


def test_categorize_http_500_is_network():
    resp = requests.Response()
    resp.status_code = 503
    exc = requests.exceptions.HTTPError("503", response=resp)
    assert isinstance(categorize(exc), NetworkError)


def test_categorize_http_429_is_rate_limit():
    resp = requests.Response()
    resp.status_code = 429
    exc = requests.exceptions.HTTPError("429", response=resp)
    assert isinstance(categorize(exc), RateLimitError)


def test_categorize_http_404_is_image_missing():
    resp = requests.Response()
    resp.status_code = 404
    exc = requests.exceptions.HTTPError("404", response=resp)
    assert isinstance(categorize(exc), ImageMissingError)
    assert isinstance(categorize(exc), ImageError)


def test_categorize_json_decode_is_schema():
    exc = json.JSONDecodeError("bad", "doc", 0)
    assert isinstance(categorize(exc), SchemaError)


def test_categorize_xml_syntax_is_schema():
    try:
        lxml.etree.fromstring("<broken")
    except lxml.etree.XMLSyntaxError as exc:
        assert isinstance(categorize(exc), SchemaError)
    else:
        pytest.fail("expected XMLSyntaxError")


def test_categorize_unknown_is_base_scrape_error():
    exc = ValueError("weird")
    result = categorize(exc)
    assert isinstance(result, ScrapeError)
    assert not isinstance(result, (NetworkError, SchemaError, RateLimitError, ImageError))


def test_all_categories_inherit_from_scrape_error():
    """Every category must be catchable as ScrapeError."""
    assert issubclass(NetworkError, ScrapeError)
    assert issubclass(SchemaError, ScrapeError)
    assert issubclass(RateLimitError, ScrapeError)
    assert issubclass(ImageError, ScrapeError)
    assert issubclass(ImageMissingError, ImageError)

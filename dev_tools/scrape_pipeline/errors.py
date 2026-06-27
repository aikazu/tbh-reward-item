"""Error hierarchy + categorization for the scrape pipeline."""
from __future__ import annotations

import json

import lxml.etree
import requests


class ScrapeError(Exception):
    """Base class for all pipeline errors."""


class NetworkError(ScrapeError):
    """Transient network failure — should retry."""


class SchemaError(ScrapeError):
    """Wiki/game data shape changed — fail fast, scraper needs update."""


class RateLimitError(ScrapeError):
    """Server throttled us — long backoff, then retry once."""


class ImageError(ScrapeError):
    """Image acquisition failure."""


class ImageMissingError(ImageError):
    """Image URL returned 404 — skip, don't retry."""


def categorize(exc: BaseException) -> ScrapeError:
    """Map a raw exception to its ScrapeError category.

    Returns the closest ScrapeError subclass wrapping ``exc``. Always returns
    a ScrapeError — unknown exception types become plain ScrapeError.
    """
    if isinstance(exc, ScrapeError):
        return exc
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return NetworkError(str(exc))
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, "status_code", None)
        if status == 429:
            return RateLimitError(str(exc))
        if status == 404:
            return ImageMissingError(str(exc))
        if status is not None and 500 <= status < 600:
            return NetworkError(str(exc))
    if isinstance(exc, json.JSONDecodeError):
        return SchemaError(f"JSON decode failed: {exc}")
    if isinstance(exc, lxml.etree.XMLSyntaxError):
        return SchemaError(f"XML syntax error: {exc}")
    return ScrapeError(str(exc))

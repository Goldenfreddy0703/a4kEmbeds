# -*- coding: utf-8 -*-
"""Client for https://anikotoapi.site (see site docs / playground)."""

from __future__ import annotations

from providerModules.a4kEmbeds import request as http
from providerModules.a4kEmbeds.core import tools

_BASE_URL = "https://anikotoapi.site"
_PER_PAGE = 100
_MAX_SCAN_PAGES = 15

_mal_series_cache = {}


def _get_json(path, params=None):
    response = http.get(_BASE_URL + path, params=params or {})
    if response is None:
        return None
    status = getattr(response, "status_code", 500)
    if status >= 400:
        tools.log(f"anikoto api {path}: HTTP {status}", "info")
        return None
    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError):
        return None
    if not payload.get("ok"):
        tools.log(f"anikoto api {path}: ok=false", "info")
        return None
    return payload


def find_series_id(mal_id):
    """Map MAL id to Anikoto catalog id by scanning paginated recent-anime."""
    key = str(mal_id)
    if key in _mal_series_cache:
        return _mal_series_cache[key]

    for page in range(1, _MAX_SCAN_PAGES + 1):
        payload = _get_json("/recent-anime", {"page": page, "per_page": _PER_PAGE})
        if not payload:
            break
        for row in payload.get("data") or []:
            if str(row.get("mal_id")) == key:
                series_id = row.get("id")
                if series_id is not None:
                    _mal_series_cache[key] = series_id
                    return series_id
        pagination = payload.get("pagination") or {}
        total_pages = pagination.get("total_pages") or page
        if page >= total_pages:
            break

    return None


def get_series(series_id):
    payload = _get_json(f"/series/{series_id}")
    if not payload:
        return None
    return payload.get("data") or {}

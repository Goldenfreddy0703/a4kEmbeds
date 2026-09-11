# -*- coding: utf-8 -*-
"""
HTTP helper for a4kEmbeds.

Uses script.module.curl_cffi when installed (Chrome TLS impersonation for
Cloudflare). Falls back to cloudscraper (a4kScrapers bundled), then requests.

Install separately in Kodi: script.module.curl_cffi
Do not vendor curl_cffi inside a4kEmbeds (platform-specific native binaries).
"""

from __future__ import annotations

import os
import sys

import requests

from providerModules.a4kEmbeds.core import tools

_DEFAULT_TIMEOUT = 20
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_curl_cffi_available = False
_curl_cffi_requests = None

try:
    import curl_cffi.requests as _curl_cffi_requests
    _curl_cffi_available = True
except ImportError:
    try:
        import xbmcaddon

        _lib = os.path.join(xbmcaddon.Addon("script.module.curl_cffi").getAddonInfo("path"), "lib")
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        import curl_cffi.requests as _curl_cffi_requests
        _curl_cffi_available = True
    except Exception:
        pass


class _CurlCffiSession:
    IMPERSONATE = "chrome120"
    name = "curl_cffi"

    def __init__(self):
        self._session = _curl_cffi_requests.Session()

    def get(self, url, headers=None, params=None, timeout=_DEFAULT_TIMEOUT, allow_redirects=True, **kwargs):
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)
        return self._session.get(
            url,
            headers=merged,
            params=params,
            timeout=timeout,
            allow_redirects=allow_redirects,
            impersonate=self.IMPERSONATE,
            **kwargs,
        )


class _CloudscraperSession:
    name = "cloudscraper"

    def __init__(self, session):
        self._session = session

    def get(self, url, headers=None, params=None, timeout=_DEFAULT_TIMEOUT, allow_redirects=True, **kwargs):
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)
        return self._session.get(
            url,
            headers=merged,
            params=params,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )


class _RequestsSession:
    name = "requests"

    def __init__(self):
        self._session = requests.Session()

    def get(self, url, headers=None, params=None, timeout=_DEFAULT_TIMEOUT, allow_redirects=True, **kwargs):
        merged = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)
        return self._session.get(
            url,
            headers=merged,
            params=params,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )


_session = None
_logged_backend = False


def _backend():
    global _session, _logged_backend
    if _session is not None:
        return _session
    if _curl_cffi_available:
        _session = _CurlCffiSession()
        if not _logged_backend:
            tools.log("request backend: curl_cffi (chrome120)", "info")
            _logged_backend = True
        return _session
    try:
        from providerModules.a4kScrapers.third_party.cloudscraper import cloudscraper

        _session = _CloudscraperSession(cloudscraper.create_scraper(interpreter="native"))
        if not _logged_backend:
            tools.log("request backend: cloudscraper", "info")
            _logged_backend = True
        return _session
    except Exception:
        pass
    _session = _RequestsSession()
    if not _logged_backend:
        tools.log(
            "request backend: requests (install script.module.curl_cffi for Cloudflare sites)",
            "warning",
        )
        _logged_backend = True
    return _session


def curl_cffi_available():
    return _curl_cffi_available


def get(url, headers=None, params=None, timeout=_DEFAULT_TIMEOUT, allow_redirects=True):
    backend = _backend()
    return backend.get(
        url,
        headers=headers,
        params=params,
        timeout=timeout,
        allow_redirects=allow_redirects,
    )


def post(url, data=None, headers=None, timeout=_DEFAULT_TIMEOUT, allow_redirects=True):
    backend = _backend()
    session = getattr(backend, "_session", backend)
    merged = dict(_DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    return session.post(
        url,
        data=data,
        headers=merged,
        timeout=timeout,
        allow_redirects=allow_redirects,
    )


def get_text(url, headers=None, params=None, timeout=_DEFAULT_TIMEOUT):
    response = get(url, headers=headers, params=params, timeout=timeout)
    if response is None:
        return ""
    if getattr(response, "status_code", 0) >= 400:
        return ""
    return getattr(response, "text", "") or ""


def post_text(url, data=None, headers=None, timeout=_DEFAULT_TIMEOUT):
    response = post(url, data=data, headers=headers, timeout=timeout)
    if response is None:
        return ""
    if getattr(response, "status_code", 0) >= 400:
        return ""
    return getattr(response, "text", "") or ""


def get_final_url(url, headers=None, timeout=_DEFAULT_TIMEOUT):
    response = get(url, headers=headers, timeout=timeout, allow_redirects=True)
    if response is None:
        return ""
    return getattr(response, "url", url) or url

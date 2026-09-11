# -*- coding: utf-8 -*-
"""WCO HTTP client with WatchNixtoons2-style Cloudflare TLS fallback."""

from __future__ import annotations

import ssl
import time
import urllib.parse

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

WCO_HTTP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

_session = requests.Session()
_last_request_by_host = {}
_tls_adapters = None


class _TLS11HttpAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_version=ssl.PROTOCOL_TLSv1_1,
        )


class _TLS12HttpAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_version=ssl.PROTOCOL_TLSv1_2,
        )


def _get_tls_adapters():
    global _tls_adapters
    if _tls_adapters is None:
        _tls_adapters = [_TLS12HttpAdapter(), _TLS11HttpAdapter()]
    return _tls_adapters


def request(method, url, data=None, headers=None, timeout=20):
    """Make a WCO request using WNT2 TLS retry on Cloudflare 403."""
    merged = {
        "User-Agent": WCO_HTTP_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "no-cache",
    }
    if headers:
        merged.update(headers)

    parsed = urllib.parse.urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    host = parsed.netloc or ""

    elapsed = time.time() - _last_request_by_host.get(host, 0.0)
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)

    response = None
    status = 0
    for attempt in range(2):
        if method.upper() == "POST":
            response = _session.post(
                url,
                data=data,
                headers=merged,
                verify=False,
                timeout=timeout,
            )
        else:
            response = _session.get(
                url,
                headers=merged,
                verify=False,
                timeout=timeout,
            )

        status = getattr(response, "status_code", 0) or 0
        if status in (200, 204):
            break

        server = (getattr(response, "headers", {}) or {}).get("server", "")
        if status == 403 and str(server).lower() == "cloudflare" and attempt == 0:
            _session.mount(domain, _get_tls_adapters()[attempt])
            continue
        break

    if host:
        _last_request_by_host[host] = time.time()
    return response


def solve_media_redirect(url, headers=None, timeout=20):
    """Follow getvid/CDN redirects and return the final media URL."""
    merged = {
        "User-Agent": WCO_HTTP_UA,
        "Accept": "video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5",
    }
    if headers:
        merged.update(headers)

    current = url
    for _ in range(8):
        try:
            response = _session.get(
                current,
                headers=merged,
                stream=True,
                allow_redirects=False,
                verify=False,
                timeout=timeout,
            )
        except Exception:
            return None

        location = (getattr(response, "headers", {}) or {}).get("Location")
        if location:
            current = urllib.parse.urljoin(current, location)
            continue

        if getattr(response, "status_code", 0) in (200, 206):
            return current
        return None
    return None

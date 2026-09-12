# -*- coding: utf-8 -*-
"""Client for Cinejoy / api.shegu.st (TMDB-based HLS streams)."""

from __future__ import annotations

import json
import re
import urllib.parse

from providerModules.a4kEmbeds import request as http
from providerModules.a4kEmbeds.core import tools
from providerModules.a4kEmbeds.crypto import aes_gcm_decrypt
from providerModules.a4kEmbeds.wasm.crush_seal import seal_request

_API_BASE = "https://api.shegu.st"
_SUBS_BASE = "https://subtitles.shegu.st"
_REFERER = "https://cinejoy.to/"
_ORIGIN = "https://cinejoy.to"

_PREFIX = b"lumen-gate-v2"
_HEADER_LEN = 98
_IV_LEN = 12

_servers_cache = None


def _build_aad(key_id, ephemeral_public):
    aad = bytearray(len(_PREFIX) + 3 + len(ephemeral_public))
    aad[0:len(_PREFIX)] = _PREFIX
    aad[len(_PREFIX) : len(_PREFIX) + 3] = bytes([0, 2, key_id])
    aad[len(_PREFIX) + 3 :] = ephemeral_public
    return bytes(aad)


def _decrypt_response(raw, ctx):
    if len(raw) < _IV_LEN + 16:
        raise RuntimeError("cinejoy: encrypted response too short")
    iv = raw[:_IV_LEN]
    ciphertext = raw[_IV_LEN:]
    aad = _build_aad(ctx["key_id"], ctx["ephemeral_public"])
    plain = aes_gcm_decrypt(ctx["response_key"], iv, ciphertext, aad)
    return json.loads(plain.decode("utf-8"))


def _post_encrypted(path, payload):
    body = json.dumps({"path": path, "payload": payload}, separators=(",", ":"))
    sealed = seal_request(body.encode("utf-8"))
    response = http.post(
        _API_BASE + "/g",
        data=sealed["body"],
        headers={
            "Content-Type": "text/plain;charset=UTF-8",
            "Referer": _REFERER,
            "Origin": _ORIGIN,
        },
    )
    if response is None or getattr(response, "status_code", 500) >= 400:
        status = getattr(response, "status_code", "no response")
        raise RuntimeError(f"cinejoy: POST /g failed ({status})")
    return _decrypt_response(response.content, sealed)


def get_servers():
    global _servers_cache
    if _servers_cache is not None:
        return _servers_cache

    response = http.get(
        _API_BASE + "/servers",
        headers={"Referer": _REFERER, "Origin": _ORIGIN},
    )
    if response is None or getattr(response, "status_code", 500) >= 400:
        return []
    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError):
        return []
    servers = payload.get("servers") or []
    _servers_cache = [row.get("name") for row in servers if row.get("name")]
    return _servers_cache


def _default_server():
    servers = get_servers()
    return servers[0] if servers else "Lisbon"


def _unwrap_stream(payload):
    if not payload:
        return None
    data = payload.get("data") or {}
    if payload.get("status") not in (None, 200) and not data:
        return None
    streams = data.get("stream") or []
    if not streams:
        return None
    first = streams[0]
    playlist = first.get("playlist") or first.get("url")
    if not playlist:
        return None
    return {
        "url": playlist,
        "type": first.get("type") or "hls",
        "captions": first.get("captions") or [],
    }


def _resolve_on_server(path, payload, server, tmdb_id, label):
    try:
        result = _post_encrypted(f"/{server}{path}", payload)
    except Exception as exc:
        tools.log(f"cinejoy: {server} failed for {label} ({exc})", "info")
        return None

    stream = _unwrap_stream(result)
    if not stream:
        tools.log(f"cinejoy: {server} no stream for {label}", "info")
        return None

    stream["server"] = server
    return stream


def _collect_streams(path, payload, tmdb_id, label, servers=None):
    servers = servers or get_servers() or [_default_server()]
    seen_urls = set()
    streams = []
    for server in servers:
        stream = _resolve_on_server(path, payload, server, tmdb_id, label)
        if not stream:
            continue
        url = stream.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        streams.append(stream)
    if streams:
        names = ", ".join(row.get("server", "?") for row in streams)
        tools.log(f"cinejoy: {len(streams)} stream(s) for {label} [{names}]", "info")
    return streams


def resolve_movie(tmdb_id, title=None, year=None, server=None):
    if server:
        payload = {"tmdb": str(tmdb_id)}
        if title:
            payload["title"] = title
        if year:
            payload["year"] = str(year)
        stream = _resolve_on_server("/movie", payload, server, tmdb_id, f"tmdb={tmdb_id}")
        return stream

    streams = resolve_movie_all(tmdb_id, title=title, year=year)
    return streams[0] if streams else None


def resolve_movie_all(tmdb_id, title=None, year=None, servers=None):
    payload = {"tmdb": str(tmdb_id)}
    if title:
        payload["title"] = title
    if year:
        payload["year"] = str(year)
    return _collect_streams("/movie", payload, tmdb_id, f"tmdb={tmdb_id}", servers=servers)


def resolve_episode(tmdb_id, season, episode, title=None, year=None, server=None):
    payload = {
        "tmdb": str(tmdb_id),
        "season": str(season),
        "episode": str(episode),
    }
    if title:
        payload["title"] = title
    if year:
        payload["year"] = str(year)
    label = f"tmdb={tmdb_id} S{season}E{episode}"

    if server:
        return _resolve_on_server("/series", payload, server, tmdb_id, label)

    streams = resolve_episode_all(tmdb_id, season, episode, title=title, year=year)
    return streams[0] if streams else None


def resolve_episode_all(tmdb_id, season, episode, title=None, year=None, servers=None):
    payload = {
        "tmdb": str(tmdb_id),
        "season": str(season),
        "episode": str(episode),
    }
    if title:
        payload["title"] = title
    if year:
        payload["year"] = str(year)
    label = f"tmdb={tmdb_id} S{season}E{episode}"
    return _collect_streams("/series", payload, tmdb_id, label, servers=servers)


def fetch_subtitles(media_type, tmdb_id, season=None, episode=None):
    params = {"type": media_type, "tmdb": str(tmdb_id)}
    if media_type == "tv":
        params["season"] = str(season)
        params["episode"] = str(episode)

    response = http.get(
        _SUBS_BASE + "/subtitles",
        params=params,
        headers={"Referer": _REFERER, "Origin": _ORIGIN},
    )
    if response is None or getattr(response, "status_code", 500) >= 400:
        return []
    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError):
        return []
    return payload.get("subtitles") or []


def playback_headers():
    return {
        "User-Agent": http._DEFAULT_HEADERS["User-Agent"],
        "Referer": _REFERER,
        "Origin": _ORIGIN,
    }


def is_hls_stream(url):
    lower = (url or "").lower()
    if ".m3u8" in lower:
        return True
    if "movieboxnoob.cc" in lower and "/content" in lower:
        return True
    if "bright67.online" in lower and "/hls/" in lower:
        return True
    return False


def _pick_variant_m3u8(master_text, base_url):
    lines = master_text.replace("\r\n", "\n").split("\n")
    best_url = None
    best_bw = -1
    origin = "{uri.scheme}://{uri.netloc}".format(uri=urllib.parse.urlparse(base_url))
    for index, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        match = re.search(r"BANDWIDTH=(\d+)", line)
        bandwidth = int(match.group(1)) if match else 0
        if index + 1 >= len(lines):
            continue
        candidate = lines[index + 1].strip()
        if not candidate or candidate.startswith("#"):
            continue
        resolved = urllib.parse.urljoin(origin + "/", candidate.lstrip("/"))
        if bandwidth >= best_bw:
            best_bw = bandwidth
            best_url = resolved
    return best_url


def _resolve_lol_content_url(url):
    headers = playback_headers()
    response = http.get(url, headers=headers)
    if response is None or getattr(response, "status_code", 500) >= 400:
        raise RuntimeError(f"cinejoy: Solara manifest fetch failed ({getattr(response, 'status_code', 'no response')})")

    master_text = getattr(response, "text", "") or ""
    if not master_text.lstrip().startswith("#EXTM3U"):
        raise RuntimeError("cinejoy: Solara manifest is not HLS")

    variant = _pick_variant_m3u8(master_text, url)
    if variant:
        return variant

    if ".m3u8" in url.lower():
        return url
    raise RuntimeError("cinejoy: Solara manifest had no playable variants")


def prepare_playback_url(url, server=None):
    """Normalize tokenized Solara URLs to a direct .m3u8 for Inputstream Adaptive."""
    if not url:
        return url
    if ".m3u8" in url.lower():
        return url
    server_name = (server or "").lower()
    if server_name == "solara" or ("movieboxnoob.cc" in url.lower() and "/content" in url.lower()):
        return _resolve_lol_content_url(url)
    if is_hls_stream(url):
        return url
    return url

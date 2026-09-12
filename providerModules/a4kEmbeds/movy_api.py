# -*- coding: utf-8 -*-
"""Client for Movy / api.wecollege.net (TMDB-based streams)."""

from __future__ import annotations

import json
import time

from providerModules.a4kEmbeds import request as http
from providerModules.a4kEmbeds.core import tools
from providerModules.a4kEmbeds.movy_crypto import decrypt_sources

_API_BASE = "https://api.wecollege.net"
_REFERER = "https://www.movy.sx/"
_ORIGIN = "https://www.movy.sx"

_SERVERS = (
    "miami",
    "boise",
    "seattle",
    "denver",
    "atlanta",
    "phoenix",
    "portland",
    "austin",
    "cancun",
    "dallas",
    "delhi",
    "orlando",
    "paris",
    "tampa",
)

_seed_cache = {}


def _api_headers():
    return {
        "Referer": _REFERER,
        "Origin": _ORIGIN,
    }


def _get_seed(media_id: str) -> str:
    cache_key = f"{_API_BASE}|{media_id}"
    now_ms = int(time.time() * 1000)
    cached = _seed_cache.get(cache_key)
    if cached and cached["expires_at"] - 5000 > now_ms:
        return cached["seed"]

    response = http.get(
        f"{_API_BASE}/seed",
        params={"mediaId": media_id},
        headers=_api_headers(),
    )
    if response is None or getattr(response, "status_code", 500) >= 400:
        raise RuntimeError(f"movy: seed request failed ({getattr(response, 'status_code', 'no response')})")

    payload = response.json()
    seed = payload.get("seed")
    if not seed:
        raise RuntimeError("movy: seed response missing seed")
    ttl_ms = int(payload.get("ttlMs") or 30000)
    _seed_cache[cache_key] = {"seed": seed, "expires_at": now_ms + ttl_ms}
    return seed


def _build_params(
    title,
    media_type,
    tmdb_id,
    year=None,
    season=None,
    episode=None,
    imdb_id=None,
    server=None,
):
    params = {
        "title": title or "",
        "mediaType": "movie" if media_type == "movie" else "tv",
        "episodeId": str(episode or 1),
        "seasonId": str(season or 1),
        "tmdbId": str(tmdb_id),
        "imdbId": imdb_id or "",
        "enc": "2",
    }
    if year not in (None, ""):
        params["year"] = str(year)
    if server == "munich":
        params["language"] = "german"
    return params


def _filter_sources(server: str, sources: list[dict]) -> list[dict]:
    rows = list(sources or [])
    if server == "austin":
        english = [row for row in rows if (row.get("quality") or "") == "English"]
        if english:
            return english
    if server == "denver":
        dash = [
            row
            for row in rows
            if (row.get("type") or "").lower() == "dash"
            or ".mpd" in (row.get("url") or "").lower()
        ]
        if dash:
            return dash
    return rows


def _pick_hls_sources(sources: list[dict]) -> list[dict]:
    picked = []
    for row in sources or []:
        url = row.get("url") or ""
        lower = url.lower()
        if ".m3u8" in lower:
            picked.append(row)
    return picked


def _fetch_server_sources(server, params, media_id: str):
    seed = _get_seed(media_id)
    query = dict(params)
    query["seed"] = seed
    response = http.get(
        f"{_API_BASE}/{server}/sources",
        params=query,
        headers=_api_headers(),
    )
    if response is None or getattr(response, "status_code", 500) >= 400:
        status = getattr(response, "status_code", "no response")
        raise RuntimeError(f"movy: {server} failed ({status})")

    encrypted = getattr(response, "text", "") or ""
    if not encrypted:
        raise RuntimeError(f"movy: {server} returned empty payload")

    plain = decrypt_sources(encrypted, seed, int(media_id))
    payload = json.loads(plain)
    sources = _filter_sources(server, payload.get("sources") or [])
    sources = _pick_hls_sources(sources)
    subtitles = payload.get("subtitles") or []
    return sources, subtitles


def _normalize_quality(label: str) -> str:
    text = (label or "").strip().lower()
    if text.endswith("p") and text[:-1].isdigit():
        return label
    if text in ("1080", "720", "480", "360"):
        return f"{text}p"
    return label or "auto"


def _collect_streams(params, media_id: str, label: str, servers=None):
    servers = servers or _SERVERS
    seen_urls = set()
    streams = []
    for server in servers:
        try:
            sources, _subtitles = _fetch_server_sources(server, params, media_id)
        except Exception as exc:
            tools.log(f"movy: {server} failed for {label} ({exc})", "info")
            continue
        for row in sources:
            url = row.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            quality = _normalize_quality(row.get("quality") or "auto")
            streams.append(
                {
                    "url": url,
                    "quality": quality,
                    "server": server.title(),
                    "type": "hls",
                }
            )
    if streams:
        names = ", ".join(row.get("server", "?") for row in streams[:6])
        if len(streams) > 6:
            names += ", ..."
        tools.log(f"movy: {len(streams)} stream(s) for {label} [{names}]", "info")
    return streams


def resolve_movie_all(tmdb_id, title=None, year=None, imdb_id=None, servers=None):
    params = _build_params(title, "movie", tmdb_id, year=year, imdb_id=imdb_id)
    return _collect_streams(params, str(tmdb_id), f"tmdb={tmdb_id}", servers=servers)


def resolve_episode_all(
    tmdb_id,
    season,
    episode,
    title=None,
    year=None,
    imdb_id=None,
    servers=None,
):
    params = _build_params(
        title,
        "tv",
        tmdb_id,
        year=year,
        season=season,
        episode=episode,
        imdb_id=imdb_id,
    )
    label = f"tmdb={tmdb_id} S{season}E{episode}"
    return _collect_streams(params, str(tmdb_id), label, servers=servers)


def playback_headers():
    return {
        "User-Agent": http._DEFAULT_HEADERS["User-Agent"],
        "Referer": _REFERER,
        "Origin": _ORIGIN,
    }

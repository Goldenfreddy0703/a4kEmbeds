# -*- coding: utf-8 -*-
"""Movy adaptive provider (api.wecollege.net / TMDB IDs)."""

from __future__ import annotations

from providerModules.a4kEmbeds import movy_api
from providerModules.a4kEmbeds.core import tools
from providerModules.a4kEmbeds.listitem import build_hls_listitem


def _tmdb_id(simple_info, all_info=None):
    for source in (simple_info or {}, (all_info or {}).get("info") or {}):
        value = source.get("tmdb_id")
        if value not in (None, "", 0):
            return str(value)
    return None


def _imdb_id(simple_info, all_info=None):
    for source in (simple_info or {}, (all_info or {}).get("info") or {}):
        for key in ("imdb_id", "imdb", "imdbnumber"):
            value = source.get(key)
            if value not in (None, ""):
                text = str(value).strip()
                return text if text.startswith("tt") else f"tt{text}"
    return None


def _build_sources(title_label, streams, extra=None):
    sources = []
    extra = extra or {}
    for stream in streams:
        url = stream.get("url")
        if not url:
            continue
        server = stream.get("server") or "Movy"
        quality = stream.get("quality") or "auto"
        entry = {
            "release_title": f"{title_label} [Movy {server} {quality}]",
            "quality": quality if quality.endswith("p") else "1080p",
            "url": url,
            "referer": movy_api._REFERER,
            "info": {"MOVY", server.upper(), quality.upper()},
            "movy": True,
            "movy_server": server,
        }
        entry.update(extra)
        sources.append(entry)
    return sources


def _season_episode(simple_info):
    season = None
    episode = None
    for s_key in ("tvdb_season_number", "season_number", "alternative_season"):
        value = simple_info.get(s_key)
        if value not in (None, ""):
            try:
                season = int(value)
                break
            except (TypeError, ValueError):
                continue
    for e_key in (
        "tvdb_episode_number",
        "episode_number",
        "alternative_episode",
        "simkl_episode_number",
        "absolute_number",
    ):
        value = simple_info.get(e_key)
        if value not in (None, ""):
            try:
                episode = int(value)
                break
            except (TypeError, ValueError):
                continue
    return season or 1, episode or 1


class sources:
    def episode(self, simple_info, all_info, **kwargs):
        tmdb_id = _tmdb_id(simple_info, all_info)
        if not tmdb_id:
            tools.log("movy: missing tmdb_id", "info")
            return []

        season, episode = _season_episode(simple_info)
        title = (
            simple_info.get("show_title")
            or (all_info or {}).get("info", {}).get("tvshowtitle")
            or "Unknown"
        )
        year = simple_info.get("year")
        imdb_id = _imdb_id(simple_info, all_info)

        try:
            streams = movy_api.resolve_episode_all(
                tmdb_id,
                season,
                episode,
                title=title,
                year=year,
                imdb_id=imdb_id,
            )
        except Exception as exc:
            tools.log(f"movy: resolve failed ({exc})", "info")
            return []

        return _build_sources(
            f"{title} - S{season}E{episode}",
            streams,
            extra={"tmdb_id": tmdb_id, "season": season, "episode": episode},
        )

    def movie(self, title, year, imdb_id=None, **kwargs):
        simple_info = kwargs.get("simple_info") or {}
        all_info = kwargs.get("info") or {}
        tmdb_id = _tmdb_id(simple_info, all_info)
        if not tmdb_id:
            tools.log("movy: missing tmdb_id for movie", "info")
            return []

        movie_title = title or simple_info.get("title") or "Unknown"
        movie_year = year or simple_info.get("year")
        movie_imdb = imdb_id or _imdb_id(simple_info, all_info)
        try:
            streams = movy_api.resolve_movie_all(
                tmdb_id,
                title=movie_title,
                year=movie_year,
                imdb_id=movie_imdb,
            )
        except Exception as exc:
            tools.log(f"movy: movie resolve failed ({exc})", "info")
            return []

        year_label = f" ({movie_year})" if movie_year else ""
        return _build_sources(
            f"{movie_title}{year_label}".strip(),
            streams,
            extra={"tmdb_id": tmdb_id},
        )


def get_listitem(source):
    play_url = source.get("url")
    if not play_url:
        raise Exception("movy: empty stream url")
    headers = movy_api.playback_headers()
    return build_hls_listitem(play_url, headers)

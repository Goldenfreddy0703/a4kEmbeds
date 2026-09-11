# -*- coding: utf-8 -*-
"""WatchNixtoons2 adaptive provider (wcostream.tv)."""

from __future__ import annotations

from providerModules.a4kEmbeds import wco_api
from providerModules.a4kEmbeds.core import tools
from providerModules.a4kEmbeds.listitem import build_playable_listitem


def _int_field(simple_info, key):
    value = (simple_info or {}).get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_anime_scrape(simple_info):
    if simple_info.get("isanime"):
        return True
    if simple_info.get("mal_id") or simple_info.get("anidb_id"):
        return True
    return bool(simple_info.get("simkl_episode_number"))


def _scrape_coordinates(simple_info):
    """Return (season, episode) for WCO's Season X Episode Y titles."""
    if _is_anime_scrape(simple_info):
        episode_keys = (
            "alternative_episode",
            "simkl_episode_number",
            "absolute_number",
            "episode_number",
            "tvdb_episode_number",
        )
    else:
        tvdb_season = _int_field(simple_info, "tvdb_season_number")
        tvdb_episode = _int_field(simple_info, "tvdb_episode_number")
        if tvdb_season is not None and tvdb_episode is not None:
            return tvdb_season, tvdb_episode

        episode_keys = (
            "tvdb_episode_number",
            "episode_number",
            "alternative_episode",
            "simkl_episode_number",
        )

    season_keys = ("tvdb_season_number", "season_number", "alternative_season")

    season = None
    for key in season_keys:
        season = _int_field(simple_info, key)
        if season is not None:
            break

    episode = None
    for key in episode_keys:
        episode = _int_field(simple_info, key)
        if episode is not None:
            break

    if episode is None and not _is_anime_scrape(simple_info):
        episode = _int_field(simple_info, "absolute_number")

    return season, episode or 1


def _build_source(show_title, episode, episode_url, *, season=None, lang=None, is_anime=False, quality="1080p"):
    if is_anime:
        tag = "DUB" if lang == "dub" else "SUB"
        release_title = f"{show_title} - Ep {episode} [WCO {tag}]"
        info = {"WCO", tag}
    else:
        season_part = f"S{season}" if season is not None else ""
        release_title = f"{show_title} - {season_part}E{episode} [WCO]"
        info = {"WCO"}

    return {
        "release_title": release_title,
        "quality": quality,
        "url": episode_url,
        "referer": wco_api.BASE_URL,
        "info": info,
        "wco": True,
    }


class sources:
    def episode(self, simple_info, all_info, **kwargs):
        season, episode = _scrape_coordinates(simple_info)
        is_anime = _is_anime_scrape(simple_info)
        show_title = (
            simple_info.get("show_title")
            or (all_info or {}).get("info", {}).get("tvshowtitle")
            or "Unknown"
        )

        search_titles = wco_api.build_search_titles(simple_info, all_info)
        if not search_titles:
            tools.log("watchnixtoons2: no search titles", "info")
            return []

        matches = wco_api.find_episodes_for_show(
            search_titles,
            season,
            episode,
            split_langs=is_anime,
        )
        if not matches:
            tools.log(
                f"watchnixtoons2: no episodes for '{show_title}' S{season}E{episode}",
                "info",
            )
            return []

        results = []
        for match in matches:
            lang = wco_api.episode_lang(match) if is_anime else None
            source = _build_source(
                show_title,
                episode,
                match["url"],
                season=season,
                lang=lang,
                is_anime=is_anime,
            )
            if source:
                results.append(source)

        tools.log(f"watchnixtoons2: {len(results)} source(s) for ep {episode}", "info")
        return results

    def movie(self, title, year, imdb_id=None, **kwargs):
        return []


def get_listitem(source):
    episode_url = source.get("url")
    if not episode_url:
        raise Exception("watchnixtoons2: empty episode url")

    resolved = wco_api.resolve_episode_page(episode_url)
    if not resolved or not resolved.get("url"):
        raise Exception(f"watchnixtoons2: failed to resolve {episode_url}")

    play_url = resolved["url"]
    referer = resolved.get("referer") or wco_api.BASE_URL
    headers = {
        "User-Agent": wco_api.WCO_UA,
        "Referer": referer,
        "Accept": "video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5",
    }
    return build_playable_listitem(play_url, headers)

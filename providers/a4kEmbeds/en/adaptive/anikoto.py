# -*- coding: utf-8 -*-
"""Anikoto adaptive provider (anikotoapi.site + MegaPlay embeds)."""

from __future__ import annotations

import urllib.parse

from providerModules.a4kEmbeds import anikoto_api
from providerModules.a4kEmbeds.core import tools
from providerModules.a4kEmbeds.embed_extractor import resolve_embed, resolve_megaplay_embed
from providerModules.a4kEmbeds.listitem import (
    build_playable_listitem,
    download_megaplay_subtitles,
    split_stream_url,
)

_REFERER = "https://anikototv.to/"
_MEGAPLAY_MAL = "https://megaplay.buzz/stream/mal/{mal_id}/{episode}/{lang}?s=tcdn"


def _episode_number(simple_info):
    for key in ("alternative_episode", "simkl_episode_number", "absolute_number", "episode_number"):
        value = simple_info.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 1


def _build_source(title, episode, lang, embed_url):
    if not embed_url:
        return None
    label = "DUB" if lang == "dub" else "SUB"
    referer = embed_url if "megaplay.buzz" in embed_url else _REFERER
    return {
        "release_title": f"{title} - Ep {episode} [Anikoto {label}]",
        "quality": "1080p",
        "url": embed_url,
        "embed": True,
        "referer": referer,
        "info": {"ANIKOTO", label},
    }


def _embed_urls_from_api(mal_id, episode):
    series_id = anikoto_api.find_series_id(mal_id)
    if not series_id:
        return []
    payload = anikoto_api.get_series(series_id)
    if not payload:
        return []
    urls = []
    for row in payload.get("episodes") or []:
        try:
            ep_num = int(row.get("number"))
        except (TypeError, ValueError):
            continue
        if ep_num != episode:
            continue
        embeds = row.get("embed_url") or {}
        if embeds.get("sub"):
            urls.append(("sub", embeds["sub"]))
        if embeds.get("dub"):
            urls.append(("dub", embeds["dub"]))
        break
    return urls


def _embed_urls_from_megaplay(mal_id, episode):
    urls = []
    for lang in ("sub", "dub"):
        urls.append((lang, _MEGAPLAY_MAL.format(mal_id=mal_id, episode=episode, lang=lang)))
    return urls


class sources:
    def episode(self, simple_info, all_info, **kwargs):
        mal_id = simple_info.get("mal_id")
        if not mal_id:
            tools.log("anikoto: missing mal_id", "info")
            return []

        episode = _episode_number(simple_info)
        title = (
            simple_info.get("show_title")
            or (all_info or {}).get("info", {}).get("tvshowtitle")
            or f"Anime {mal_id}"
        )

        embed_pairs = _embed_urls_from_api(mal_id, episode)
        if embed_pairs:
            tools.log(f"anikoto: {len(embed_pairs)} embed(s) from API for mal={mal_id} ep={episode}", "info")
        else:
            embed_pairs = _embed_urls_from_megaplay(mal_id, episode)
            tools.log(f"anikoto: using MegaPlay MAL URLs for mal={mal_id} ep={episode}", "info")

        results = []
        for lang, embed_url in embed_pairs:
            source = _build_source(title, episode, lang, embed_url)
            if source:
                results.append(source)

        tools.log(f"anikoto: {len(results)} source(s) for ep {episode}", "info")
        return results

    def movie(self, title, year, imdb_id=None, **kwargs):
        return []


def get_listitem(source):
    url = source.get("url")
    referer = source.get("referer") or _REFERER
    subtitle_paths = []
    if source.get("embed"):
        if "megaplay.buzz" in (url or ""):
            resolved_data = resolve_megaplay_embed(url, referer=referer)
            if not resolved_data:
                raise Exception(f"anikoto: failed to resolve embed {url}")
            url = resolved_data["stream"]
            referer_root = urllib.parse.urljoin(resolved_data.get("embed_url") or url, "/")
            subtitle_paths = download_megaplay_subtitles(resolved_data.get("tracks") or [], referer_root)
        else:
            resolved = resolve_embed(url, referer=referer)
            if not resolved:
                raise Exception(f"anikoto: failed to resolve embed {url}")
            url = resolved
    play_url, headers = split_stream_url(url)
    if not headers and source.get("headers"):
        headers = source.get("headers")
    if not play_url:
        raise Exception("anikoto: empty stream url")
    return build_playable_listitem(play_url, headers, subtitle_paths=subtitle_paths)

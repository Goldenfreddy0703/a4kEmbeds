# -*- coding: utf-8 -*-
"""Resolve embed host pages to playable stream URLs (Otaku-style)."""

from __future__ import annotations

import json
import re
import time
import urllib.parse

from providerModules.a4kEmbeds import jsunpack
from providerModules.a4kEmbeds import request as http
from providerModules.a4kEmbeds.core import tools

_EDGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.62"
)
_FF_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"

_EXTRACTORS = []


def _register(prefixes, parser):
    _EXTRACTORS.append((prefixes, parser))


def _append_headers(headers):
    return "|%s" % "&".join(
        ["%s=%s" % (key, urllib.parse.quote_plus(headers[key])) for key in headers]
    )


def _packed_data(html):
    packed = ""
    for match in re.finditer(r"(eval\s*\(function\(p,a,c,k,e,.*?)</script>", html, re.DOTALL | re.I):
        chunk = match.group(1)
        parts = re.findall(r"(eval\s*\(function\(p,a,c,k,e,)", chunk, re.DOTALL | re.IGNORECASE)
        if len(parts) == 1:
            if jsunpack.detect(chunk):
                packed += jsunpack.unpack(chunk)
        else:
            for piece in ["eval" + x for x in chunk.split("eval") if x]:
                if jsunpack.detect(piece):
                    packed += jsunpack.unpack(piece)
    return packed


def _fetch_page(url, referer=None, headers=None):
    merged = {}
    if referer:
        merged["Referer"] = referer
    if headers:
        merged.update(headers)
    response = http.get(url, headers=merged)
    if response is None or getattr(response, "status_code", 500) >= 400:
        return None, None
    text = getattr(response, "text", "") or ""
    final_url = getattr(response, "url", url) or url
    return final_url, text


def resolve_embed(url, referer=None):
    for prefixes, parser in _EXTRACTORS:
        if any(url.startswith(prefix) for prefix in prefixes):
            try:
                final_url, html = _fetch_page(url, referer=referer)
                if html is None:
                    return None
                return parser(final_url, html, referer=referer or url)
            except Exception as exc:
                tools.log(f"embed_extractor failed for {url}: {exc}", "warning")
                return None
    tools.log(f"embed_extractor: no handler for {url}", "info")
    return None


def _extract_kwik(url, page_content, referer=None):
    page_content += _packed_data(page_content)
    match = re.search(r"const\s*source\s*=\s*'([^']+)", page_content)
    if not match:
        return None
    ref = urllib.parse.urljoin(url, "/")
    headers = {"User-Agent": _EDGE_UA, "Referer": ref, "Origin": ref[:-1]}
    return match.group(1) + _append_headers(headers)


def _extract_mixdrop(url, page_content, referer=None):
    match = re.search(r'(?:vsr|wurl|surl)[^=]*=\s*"([^"]+)', _packed_data(page_content))
    if not match:
        return None
    surl = match.group(1)
    if surl.startswith("//"):
        surl = "https:" + surl
    return surl + _append_headers({"User-Agent": _EDGE_UA, "Referer": url})


def _extract_streamtape(url, page_content, referer=None):
    src = re.findall(r'''ById\('.+?=\s*(["']//[^;<]+)''', page_content)
    if not src:
        return None
    src_url = ""
    for part in src[-1].replace("'", '"').split("+"):
        piece = re.findall(r'"([^"]*)', part)
        if not piece:
            continue
        p1 = piece[0]
        p2 = 0
        if "substring" in part:
            p2 = sum(int(x) for x in re.findall(r"substring\((\d+)", part))
        src_url += p1[p2:]
    src_url += "&stream=1"
    return src_url + _append_headers({"User-Agent": _EDGE_UA, "Referer": url})


def _extract_filemoon(url, page_content, referer=None):
    match = re.search(r'sources:\s*\[{\s*file:\s*"([^"]+)', _packed_data(page_content))
    if not match:
        return None
    surl = match.group(1)
    if surl.startswith("//"):
        surl = "https:" + surl
    return surl + _append_headers({"User-Agent": _EDGE_UA, "Referer": url})


def _extract_mp4upload(url, page_content, referer=None):
    page_content += _packed_data(page_content)
    match = re.search(r'src\("([^"]+)', page_content) or re.search(r'src:\s*"([^"]+)', page_content)
    if not match:
        return None
    headers = {"User-Agent": _EDGE_UA, "Referer": url, "verifypeer": "false"}
    return match.group(1) + _append_headers(headers)


def _megaplay_player_id(page_content):
    match = re.search(r'id="megaplay-player"[^>]*data-id="(\d+)"', page_content, re.I)
    if not match:
        match = re.search(r'data-id="(\d+)"[^>]*data-realid=', page_content, re.I)
    return match.group(1) if match else None


def _megaplay_api_data(url, page_content, referer=None):
    referer = referer or url
    player_id = _megaplay_player_id(page_content)
    if not player_id:
        return None
    api_url = f"https://megaplay.buzz/stream/getSourcesNew?id={player_id}"
    headers = {
        "User-Agent": _FF_UA,
        "Referer": url,
        "X-Requested-With": "XMLHttpRequest",
    }
    response = http.get(api_url, headers=headers)
    if response is None or getattr(response, "status_code", 500) >= 400:
        return None
    try:
        return response.json()
    except (ValueError, TypeError, AttributeError):
        return None


def _megaplay_stream_url(url, data):
    sources = data.get("sources")
    file_url = None
    if isinstance(sources, dict):
        file_url = sources.get("file")
    elif isinstance(sources, list) and sources:
        file_url = sources[0].get("file")
    if not file_url:
        return None
    netloc = urllib.parse.urljoin(url, "/")
    return file_url + _append_headers(
        {"User-Agent": "iPad", "Referer": netloc, "Origin": netloc.rstrip("/")}
    )


def _megaplay_caption_tracks(data):
    tracks = []
    for track in data.get("tracks") or []:
        if track.get("kind") == "captions" and track.get("file"):
            tracks.append(track)
    return tracks


def resolve_megaplay_embed(url, referer=None):
    """Resolve MegaPlay embed to stream URL plus caption tracks."""
    final_url, html = _fetch_page(url, referer=referer)
    if html is None:
        return None
    data = _megaplay_api_data(final_url, html, referer=referer or final_url)
    if not data:
        return None
    stream = _megaplay_stream_url(final_url, data)
    if not stream:
        return None
    return {
        "stream": stream,
        "tracks": _megaplay_caption_tracks(data),
        "embed_url": final_url,
    }


def _extract_megaplay(url, page_content, referer=None):
    data = _megaplay_api_data(url, page_content, referer=referer or url)
    if not data:
        return None
    return _megaplay_stream_url(url, data)


def _extract_dood(url, page_content, referer=None):
    import random
    import string

    def dood_decode(pdata):
        alphabet = string.ascii_letters + string.digits
        return pdata + "".join(random.choice(alphabet) for _ in range(10))

    match = re.search(
        r'''dsplayer\.hotkeys[^']+'([^']+).+?function\s*makePlay.+?return[^?]+([^"]+)''',
        page_content,
        re.DOTALL,
    )
    if not match:
        return None
    token = match.group(2)
    host_match = re.search(
        r"(?://|\.)((?:do*ds?(?:tream|ter)?|ds2(?:play|video))\.(?:com?|watch|to|s[ho]|cx|l[ai]|w[sf]|pm|re|yt|stream|pro))/(?:d|e)/([0-9a-zA-Z]+)",
        url,
    )
    if not host_match:
        return None
    host = host_match.group(1)
    nurl = "https://{0}{1}".format(host, match.group(1))
    html = http.get_text(nurl, headers={"Referer": url, "User-Agent": _EDGE_UA})
    if not html:
        return None
    return dood_decode(html) + token + str(int(time.time() * 1000)) + _append_headers(
        {"User-Agent": _EDGE_UA, "Referer": url}
    )


_register(["https://kwik.cx/", "https://kwik.si/"], _extract_kwik)
_register(["https://megaplay.buzz/"], _extract_megaplay)
_register(
    [
        "https://mixdrop.co/",
        "https://mixdrop.to/",
        "https://mixdrop.sx/",
        "https://mixdrop.bz/",
        "https://mixdrp.to/",
    ],
    _extract_mixdrop,
)
_register(["https://streamtape.com/e/"], _extract_streamtape)
_register(
    [
        "https://filemoon.sx/e/",
        "https://kerapoxy.cc/e/",
        "https://1azayf9w.xyz/e/",
    ],
    _extract_filemoon,
)
_register(["https://www.mp4upload.com/", "https://mp4upload.com/"], _extract_mp4upload)
_register(
    [
        "https://dood.wf/",
        "https://doodstream.com/",
        "https://ds2play.com/",
        "https://doods.pro/",
    ],
    _extract_dood,
)

# -*- coding: utf-8 -*-
"""Build Kodi ListItems for embed/HLS playback."""

from __future__ import annotations

import os
import re
import urllib.parse

import xbmcgui
import xbmcvfs

from providerModules.a4kEmbeds import request as http


def split_stream_url(url_with_headers):
    """Split Otaku-style ``url|Referer=...&User-Agent=...`` strings."""
    if not url_with_headers or "|" not in url_with_headers:
        return url_with_headers, {}
    url, query = url_with_headers.split("|", 1)
    headers = {}
    for part in query.split("&"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        headers[key] = urllib.parse.unquote_plus(value)
    return url, headers


_SUB_LABEL_CODES = {
    "english": "eng",
    "arabic": "ara",
    "french": "fre",
    "german": "ger",
    "italian": "ita",
    "portuguese": "por",
    "russian": "rus",
    "spanish": "spa",
    "japanese": "jpn",
}

_VTT_TIME_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?\.\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?\.\d{3})"
)


def _normalize_vtt_timestamp(timestamp):
    parts = (timestamp or "").strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return f"00:{minutes.zfill(2)}:{seconds}"
    return timestamp.strip()


def _vtt_timestamp_to_srt(timestamp):
    normalized = _normalize_vtt_timestamp(timestamp)
    if "." not in normalized:
        return f"{normalized},000"
    main, fraction = normalized.rsplit(".", 1)
    return f"{main},{fraction[:3].ljust(3, '0')}"


def _strip_subtitle_markup(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return text.replace("&nbsp;", " ").strip()


def vtt_to_srt(content):
    """Convert MegaPlay WebVTT cues to SRT (Kodi renders SRT more reliably)."""
    text = re.sub(r"\r\n?", "\n", content or "")
    cues = []

    for match in _VTT_TIME_RE.finditer(text):
        start = _vtt_timestamp_to_srt(match.group("start"))
        end = _vtt_timestamp_to_srt(match.group("end"))
        body_start = match.end()
        next_match = _VTT_TIME_RE.search(text, body_start)
        body_end = next_match.start() if next_match else len(text)
        body = text[body_start:body_end].strip("\n")

        lines = []
        for line in body.split("\n"):
            stripped = line.strip()
            if not stripped:
                if lines:
                    break
                continue
            if stripped.startswith("NOTE") or stripped.startswith("STYLE"):
                continue
            lines.append(_strip_subtitle_markup(stripped))

        cue_text = "\n".join(line for line in lines if line).strip()
        if cue_text:
            cues.append((start, end, cue_text))

    if not cues:
        return ""

    blocks = []
    for index, (start, end, cue_text) in enumerate(cues, 1):
        blocks.extend([str(index), f"{start} --> {end}", cue_text, ""])
    return "\n".join(blocks).strip() + "\n"


def _subtitle_language(track):
    sub_url = track.get("file") or ""
    match = re.search(r"/([a-z]{3})-\d+\.vtt", sub_url, re.I)
    if match:
        return match.group(1).lower()
    label = (track.get("label") or "").strip().lower()
    for keyword, code in _SUB_LABEL_CODES.items():
        if keyword in label:
            return code
    return "und"


def clear_temporary_subtitles():
    _, files = xbmcvfs.listdir("special://temp/")
    for fname in files:
        if fname.startswith("TemporarySubs"):
            xbmcvfs.delete(f"special://temp/{fname}")


def download_megaplay_subtitles(tracks, referer_root):
    """Download MegaPlay VTT tracks to special://temp and return Kodi subtitle paths."""
    if not tracks:
        return []

    tracks = sorted(
        tracks,
        key=lambda track: (not bool(track.get("default")), (track.get("label") or "").lower()),
    )

    clear_temporary_subtitles()
    headers = {
        "User-Agent": "iPad",
        "Referer": referer_root,
        "Origin": referer_root.rstrip("/"),
    }
    temp_dir = xbmcvfs.translatePath("special://temp/")
    subtitle_paths = []

    for idx, track in enumerate(tracks):
        sub_url = track.get("file")
        if not sub_url:
            continue
        response = http.get(sub_url, headers=headers)
        if response is None or getattr(response, "status_code", 500) >= 400:
            continue
        content = getattr(response, "text", "") or ""
        if not content.strip():
            continue

        srt_content = vtt_to_srt(content)
        if not srt_content.strip():
            continue

        lang = _subtitle_language(track)
        fname = f"TemporarySubs.{idx}.{lang}.srt"
        fname = fname.encode(encoding="ascii", errors="ignore").decode(encoding="ascii")
        fpath = os.path.join(temp_dir, fname)
        with open(fpath, "w", encoding="utf-8") as handle:
            handle.write(srt_content)
        subtitle_paths.append(f"special://temp/{fname}")

    return subtitle_paths


def build_playable_listitem(url, headers=None, subtitle_paths=None):
    lower = (url or "").lower()
    if ".m3u8" in lower:
        return build_hls_listitem(url, headers, subtitle_paths=subtitle_paths)

    play_path = url
    if headers and "|" not in (url or ""):
        header_text = _format_headers_isa(headers)
        if header_text:
            play_path = f"{url}|{header_text}"

    item = xbmcgui.ListItem(path=play_path, offscreen=True)
    item.setContentLookup(False)
    item.setProperty("isFolder", "false")
    item.setProperty("isPlayable", "true")
    if subtitle_paths:
        item.setSubtitles(subtitle_paths)

    return item


def build_hls_listitem(url, headers=None, subtitle_paths=None):
    """Return a ListItem configured for Inputstream Adaptive HLS."""
    item = xbmcgui.ListItem(path=url, offscreen=True)
    item.setContentLookup(False)
    item.setProperty("isFolder", "false")
    item.setProperty("isPlayable", "true")
    item.setMimeType("application/x-mpegURL")

    item.setProperty("inputstream", "inputstream.adaptive")
    item.setProperty("inputstream.adaptive.manifest_type", "hls")

    header_text = _format_headers_isa(headers)
    if header_text:
        item.setProperty("inputstream.adaptive.stream_headers", header_text)
        item.setProperty("inputstream.adaptive.manifest_headers", header_text)
        item.setProperty("inputstream.adaptive.stream_params", header_text)

    if subtitle_paths:
        item.setSubtitles(subtitle_paths)

    return item


def _format_headers_isa(headers):
    """Format headers for inputstream.adaptive (Otaku-style key=value&...)."""
    if not headers:
        return ""
    if isinstance(headers, str):
        text = headers.strip()
        if "\r\n" in text or (": " in text and "=" not in text.split("&", 1)[0]):
            parsed = {}
            for line in text.replace("\r\n", "\n").split("\n"):
                if ": " in line:
                    key, value = line.split(": ", 1)
                    parsed[key.strip()] = value.strip()
            return urllib.parse.urlencode(parsed)
        return text
    if isinstance(headers, dict):
        return urllib.parse.urlencode(
            {key: value for key, value in headers.items() if value is not None}
        )
    return ""

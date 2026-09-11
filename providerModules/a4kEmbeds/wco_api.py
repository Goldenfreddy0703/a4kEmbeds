# -*- coding: utf-8 -*-
"""WatchNixtoons2 / WCOStream scraper (ported from Otaku + WNT2 addon)."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
from difflib import SequenceMatcher

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from providerModules.a4kEmbeds import wco_http
from providerModules.a4kEmbeds.core import tools

BASE_URL = "https://www.wcostream.tv/"
WCO_UA = wco_http.WCO_HTTP_UA
_series_episodes_cache = {}


def _default_headers():
    return {
        "User-Agent": WCO_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "no-cache",
    }


def _request(method, url, data=None, headers=None, use_cache=True):
    request_headers = dict(headers or {})

    status = 0
    text = ""
    response = wco_http.request(
        method,
        url,
        data=data,
        headers=request_headers,
        timeout=20,
    )

    if response is not None:
        status = getattr(response, "status_code", 0) or 0
        if status < 400:
            text = getattr(response, "text", "") or ""

    return text or None


def _clean_title(title):
    if not title:
        return ""
    cleaned = re.sub(r"\s*\([^)]*\)", "", title)
    cleaned = re.sub(r"\s*\[[^\]]*\]", "", cleaned)
    cleaned = re.sub(r"\s*:\s*[^:]*$", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _truncate_search_title(title, max_length=40):
    if len(urllib.parse.quote_plus(title)) <= max_length:
        return title
    words = title.split()
    while len(words) > 1:
        words = words[1:]
        test_title = " ".join(words)
        if len(urllib.parse.quote_plus(test_title)) <= max_length:
            return test_title
    if words:
        return words[0][:max_length]
    return title[:max_length]


def search_series(title):
    search_title = _truncate_search_title((title or "").strip())
    if not search_title:
        return []

    data = {"catara": search_title, "konuara": "series"}
    response = _request(
        "POST",
        f"{BASE_URL}search",
        data=data,
        headers={"Referer": BASE_URL},
    )
    if not response:
        return []

    results = []
    if "aramamotoru" in response:
        start_pos = response.find("aramamotoru")
        end_pos = response.find("cizgiyazisi", start_pos)
        if start_pos != -1 and end_pos != -1:
            section = response[start_pos:end_pos]
            pattern = r'<a href="(?P<link>[^"]+)[^>]*>(?P<name>[^<]+)</a>'
            for index, match in enumerate(re.finditer(pattern, section)):
                href = match.group("link").lstrip("/")
                if not href:
                    continue
                results.append(
                    {
                        "index": index,
                        "title": match.group("name").strip(),
                        "href": href,
                        "url": urllib.parse.urljoin(BASE_URL, href),
                    }
                )

    if not results and BeautifulSoup is not None:
        soup = BeautifulSoup(response, "html.parser")
        for index, container in enumerate(soup.find_all("div", class_="cerceve")):
            title_div = container.find("div", class_="aramadabaslik")
            if not title_div:
                continue
            link = title_div.find("a")
            if not link:
                continue
            href = (link.get("href") or "").lstrip("/")
            if not href:
                continue
            results.append(
                {
                    "index": index,
                    "title": (link.get("title") or link.text or "").strip(),
                    "href": href,
                    "url": urllib.parse.urljoin(BASE_URL, href),
                }
            )

    return results[:10]


def get_episodes_from_series(series_url):
    cached = _series_episodes_cache.get(series_url)
    if cached is not None:
        return [dict(row) for row in cached]

    response = _request("GET", series_url)
    if not response:
        return []

    show_type = None
    lang_match = re.search(r"lang=(dub|sub|cartoon)", series_url, re.IGNORECASE)
    if lang_match:
        show_type = lang_match.group(1).lower()

    start_pos = response.find('name="pid"')
    if start_pos == -1:
        return []
    end_pos = response.find("<!--CAT PAGE", start_pos)
    section = response[start_pos:end_pos] if end_pos != -1 else response[start_pos:]

    pattern = re.compile(
        r'<a href="(?P<link>[^"]+).*?(?:data-lang="(?P<type>[^"]+)")?>(?:<span>)?(?P<name>[^<]+)',
        re.DOTALL,
    )
    episodes = []
    for match in pattern.finditer(section):
        episode_type = (match.group("type") or "").lower()
        if show_type in ("sub", "dub") and episode_type in ("sub", "dub") and episode_type != show_type:
            continue

        href = match.group("link")
        title_text = html.unescape((match.group("name") or "").strip())
        if not href or not title_text:
            continue
        episodes.append(
            {
                "title": title_text,
                "href": href,
                "url": href if href.startswith("http") else urllib.parse.urljoin(BASE_URL, href),
                "episode_type": episode_type,
            }
        )
    _series_episodes_cache[series_url] = [dict(row) for row in episodes]
    return episodes


def _normalize_series_base_title(title):
    base = (title or "").strip()
    for suffix in (
        " english subbed",
        " english dubbed",
        " english dub",
        " subbed",
        " dubbed",
    ):
        if base.lower().endswith(suffix):
            base = base[:-len(suffix)].strip()
    return base


def _titles_match(search_title, series_title):
    common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}

    def clean_for_matching(value):
        cleaned = re.sub(r"[^\w\s]", " ", value.lower())
        words = [word for word in cleaned.split() if word not in common_words]
        return " ".join(words)

    clean_search = clean_for_matching(search_title)
    clean_series = clean_for_matching(series_title)
    if clean_search in clean_series or clean_series in clean_search:
        return True
    search_words = set(clean_search.split())
    series_words = set(clean_series.split())
    if not search_words or not series_words:
        return False
    overlap = len(search_words.intersection(series_words))
    total = len(search_words.union(series_words))
    return (overlap / total) >= 0.6 if total else False


def _get_series_variants(series_results):
    if not series_results:
        return []
    anchor_base = _normalize_series_base_title(series_results[0]["title"]).lower()
    variants = []
    seen_urls = set()
    for series in series_results:
        series_base = _normalize_series_base_title(series["title"]).lower()
        same_show = series_base == anchor_base or _titles_match(series_results[0]["title"], series["title"])
        if not same_show or series["url"] in seen_urls:
            continue
        seen_urls.add(series["url"])
        variants.append(series)
    return variants or [series_results[0]]


def _fuzzy_title_match(search_title, candidates):
    if not search_title or not candidates:
        return list(range(len(candidates)))

    search_lower = search_title.lower()
    matches = []
    for index, candidate in enumerate(candidates):
        candidate_lower = (candidate or "").lower()
        if search_lower in candidate_lower or candidate_lower in search_lower:
            matches.append(index)
            continue
        if SequenceMatcher(None, search_lower, candidate_lower).ratio() >= 0.55:
            matches.append(index)
    return matches


def find_episode_match(episodes, target_season, target_episode, search_title=None):
    matches = []
    for episode in episodes:
        title_text = episode["title"]
        if target_season is not None:
            season_episode_pattern = re.compile(
                rf"season\s+{target_season}\s+episode\s+{target_episode}(?!\d)",
                re.IGNORECASE,
            )
            if season_episode_pattern.search(title_text):
                episode["match_type"] = "season_episode"
                episode["priority"] = 1
                matches.append(episode)
                continue

        episode_only_pattern = re.compile(rf"episode\s+{target_episode}(?!\d)", re.IGNORECASE)
        if episode_only_pattern.search(title_text) and not re.search(
            r"season\s+\d+", title_text, re.IGNORECASE
        ):
            episode["match_type"] = "episode_only"
            episode["priority"] = 2
            matches.append(episode)
            continue

        episode_number_pattern = re.compile(rf"\b{target_episode}\b(?!\d)", re.IGNORECASE)
        if episode_number_pattern.search(title_text):
            episode["match_type"] = "episode_number"
            episode["priority"] = 3
            matches.append(episode)

    matches.sort(key=lambda row: row.get("priority", 99))
    if search_title and matches:
        fuzzy_targets = [
            f"{row.get('series_title', '')} {row.get('title', '')}".strip() or row.get("title", "")
            for row in matches
        ]
        indices = _fuzzy_title_match(search_title, fuzzy_targets)
        if not indices:
            indices = _fuzzy_title_match(
                search_title,
                [row.get("series_title", "") or row.get("title", "") for row in matches],
            )
        if indices:
            filtered = []
            for rank, index in enumerate(indices):
                row = matches[index]
                row["title_rank"] = rank
                filtered.append(row)
            return filtered
        return matches
    return matches


def _is_dub_episode(episode_data):
    episode_title = episode_data.get("title", "").lower()
    series_title = episode_data.get("series_title", "").lower()
    combined = f"{episode_title} {series_title}"
    sub_markers = ("english subbed", "english sub", " subbed")
    dub_markers = ("english dubbed", "english dub", " dubbed")
    if any(marker in combined for marker in sub_markers):
        return False
    if any(marker in combined for marker in dub_markers):
        return True
    return bool(re.search(r"\bdub(?:bed)?\b", combined) and not re.search(r"\bsub(?:bed)?\b", combined))


def episode_lang(episode_data):
    return "dub" if _is_dub_episode(episode_data) else "sub"


def _pick_sub_and_dub_episodes(episode_matches):
    picked = {}
    for match in episode_matches:
        lang = episode_lang(match)
        existing = picked.get(lang)
        if not existing or match.get("priority", 99) < existing.get("priority", 99):
            picked[lang] = match
    return list(picked.values())


def _pick_best_episode(episode_matches):
    if not episode_matches:
        return []
    best = min(
        episode_matches,
        key=lambda row: (row.get("priority", 99), row.get("title_rank", 99)),
    )
    return [best]


def _is_better_episode(candidate, existing):
    if not existing:
        return True
    candidate_priority = candidate.get("priority", 99)
    existing_priority = existing.get("priority", 99)
    if candidate_priority != existing_priority:
        return candidate_priority < existing_priority
    return candidate.get("title_rank", 99) < existing.get("title_rank", 99)


def find_episodes_for_show(search_titles, season, episode, split_langs=True):
    found = {}
    for search_title in search_titles:
        if not search_title:
            continue
        series_results = search_series(search_title)
        if not series_results:
            continue

        variants = _get_series_variants(series_results)

        all_episodes = []
        for series in variants:
            for row in get_episodes_from_series(series["url"]):
                row["series_title"] = series["title"]
                row["series_url"] = series["url"]
                all_episodes.append(row)

        episode_matches = find_episode_match(all_episodes, season, episode, search_title)
        if split_langs:
            picked_matches = _pick_sub_and_dub_episodes(episode_matches)
        else:
            picked_matches = _pick_best_episode(episode_matches)

        for match in picked_matches:
            if split_langs:
                lang = episode_lang(match)
                existing = found.get(lang)
                if _is_better_episode(match, existing):
                    found[lang] = match
            else:
                existing = found.get("stream")
                if _is_better_episode(match, existing):
                    found["stream"] = match

        if split_langs and "sub" in found and "dub" in found:
            break
        if not split_langs and found:
            break

    return list(found.values())


def _unescape_html_url(url):
    return html.unescape(url or "")


def _ensure_full_url(base_url, url):
    url = _unescape_html_url(url)
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return "https:" + url
    return urllib.parse.urljoin(base_url, url)


def _embed_api_origin(embed_url):
    parsed = urllib.parse.urlparse(embed_url)
    if parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return "https://embed.wcostream.com/"


def _find_embed_url(page_content, episode_url):
    if '"vjs_iframe"' in page_content:
        match = re.search(
            r'<iframe id="(?:[a-zA-Z0-9-]+)" class="vjs_iframe" rel="nofollow" src="([^"]+)"',
            page_content,
            re.DOTALL,
        )
        if match:
            return _ensure_full_url(episode_url, match.group(1)), True

    if 'uploads0" src=' in page_content:
        match = re.search(
            r'<iframe\s*id="(?:[a-zA-Z]+)uploads(?:[0-9]+)"\s*src="([^"]+)"',
            page_content,
            re.DOTALL,
        )
        if match:
            return _ensure_full_url(episode_url, match.group(1)), False

    if '-js-0" src=' in page_content:
        match = re.search(
            r'<iframe\s*(?:rel="nofollow")?\s*id="(?:[a-zA-Z]+)\-js\-(?:[0-9]+)"\s*src="([^"]+)"',
            page_content,
            re.DOTALL,
        )
        if match:
            return _ensure_full_url(episode_url, match.group(1)), False

    embed_match = re.search(
        r'<iframe[^>]+src="((?:https?:)?//embed\.wcostream\.com/inc/embed/[^"]+)"',
        page_content,
        re.IGNORECASE,
    )
    if embed_match:
        return _ensure_full_url(episode_url, embed_match.group(1)), False

    embed_url_index = page_content.find('onclick="myFunction')
    if embed_url_index <= 0:
        embed_url_index = page_content.find('class="episode-descp"')
    if embed_url_index > 0:
        match = re.search(r'src="([^"]+)', page_content[embed_url_index:])
        if match:
            return _ensure_full_url(episode_url, match.group(1)), False

    skip_hosts = ("ads", "analytics", "disqus", "facebook", "twitter", "check-login")
    for iframe_url in re.findall(r'<iframe[^>]+src="([^"]+)"', page_content, re.IGNORECASE):
        if any(skip in iframe_url.lower() for skip in skip_hosts):
            continue
        return _ensure_full_url(episode_url, iframe_url), False

    return None, False


def _normalize_embed_player_url(embed_url):
    embed_url = _unescape_html_url(embed_url)
    parsed = urllib.parse.urlparse(embed_url)
    host = (parsed.netloc or "").lower()
    if host.endswith("vhs.wcostream.com") and "/video-js/" not in (parsed.path or ""):
        query = f"?{parsed.query}" if parsed.query else ""
        return f"https://vhs.wcostream.com/video-js/{query}"
    if "inc/embed/index.php" in embed_url:
        embed_url = embed_url.replace("inc/embed/index.php", "inc/embed/video-js-new.php")
    elif "inc/embed/video-js.php" in embed_url:
        embed_url = embed_url.replace("inc/embed/video-js.php", "inc/embed/video-js-new.php")
    return embed_url


def _resolve_api_url(player_html, embed_url):
    api_origin = _embed_api_origin(embed_url)
    if "getRedirectedUrl(videoUrl)" in player_html or 'getRedirectedUrl("' in player_html:
        match = re.search(r'\$\.getJSON\("([^"]+)"', player_html, re.DOTALL)
        if match:
            path = match.group(1)
            source_url = path if path.startswith("http") else urllib.parse.urljoin(api_origin, path.lstrip("/"))
            if "json" not in source_url:
                source_url += "&json" if "?" in source_url else "?json"
            return source_url

    match = re.search(r'"(/inc/embed/getvidlink[^"]+)', player_html, re.DOTALL)
    if match:
        return urllib.parse.urljoin(api_origin, match.group(1).lstrip("/"))
    return None


def _quality_from_label(label):
    label = (label or "").lower()
    if "1080" in label or "fhd" in label:
        return "1080p", 3
    if "720" in label or label == "hd":
        return "720p", 2
    return "SD", 1


def _stream_candidates_from_player(player_html, embed_url, is_m3u8_player=False):
    if "high volume of requests" in player_html:
        return []

    candidates = []

    if "getvid?evid" in player_html or 'getRedirectedUrl("' in player_html:
        source_url = _resolve_api_url(player_html, embed_url)
        if source_url:
            api_headers = {
                "Accept": "*/*",
                "Referer": embed_url,
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": WCO_UA,
            }
            server_resp = _request("GET", source_url, headers=api_headers, use_cache=False)
            if server_resp:
                try:
                    json_data = json.loads(server_resp)
                except (ValueError, TypeError):
                    json_data = {}
                server_base = (json_data.get("server") or "").rstrip("/")
                for label, key in (("FHD", "fhd"), ("HD", "hd"), ("SD", "enc")):
                    token = json_data.get(key)
                    if server_base and token:
                        quality, rank = _quality_from_label(label)
                        candidates.append(
                            {
                                "url": f"{server_base}/getvid?evid={token}",
                                "quality": quality,
                                "rank": rank,
                                "referer": embed_url,
                            }
                        )
                cdn_backup = json_data.get("cdn")
                token = json_data.get("fhd") or json_data.get("hd") or json_data.get("enc")
                if cdn_backup and token:
                    candidates.append(
                        {
                            "url": f"{cdn_backup.rstrip('/')}/getvid?evid={token}",
                            "quality": "720p",
                            "rank": 2,
                            "referer": embed_url,
                        }
                    )

    if not candidates:
        source_match = re.search(r'<source\s*src="([^"]+)"', player_html, re.DOTALL)
        if source_match:
            candidates.append(
                {
                    "url": source_match.group(1),
                    "quality": "1080p",
                    "rank": 3,
                    "referer": embed_url,
                }
            )
        else:
            redirect_match = re.search(r'getRedirectedUrl\("([^"]+)', player_html, re.DOTALL)
            if redirect_match:
                candidates.append(
                    {
                        "url": redirect_match.group(1),
                        "quality": "1080p",
                        "rank": 3,
                        "referer": embed_url,
                    }
                )

    if not candidates:
        sources_block = re.search(r"sources:\s*?\[(.*?)\]", player_html, re.DOTALL)
        if sources_block:
            stream_pattern = re.compile(r'\{\s*?file:\s*?"(.*?)"(?:,\s*?label:\s*?"(.*?)")?')
            for source_match in stream_pattern.finditer(sources_block.group(1)):
                label = source_match.group(2) or "Stream"
                quality, rank = _quality_from_label(label)
                candidates.append(
                    {
                        "url": source_match.group(1),
                        "quality": quality,
                        "rank": rank,
                        "referer": embed_url,
                    }
                )

    if is_m3u8_player and not candidates:
        tools.log("wco: m3u8 player detected but no stream candidates found", "info")

    candidates.sort(key=lambda row: row.get("rank", 0), reverse=True)
    return candidates


def _premium_workaround_check(page_content, episode_url):
    playlist_matches = re.findall(r'href="([^"]*playlist-cat-jw[^"]*)"', page_content)
    for playlist_path in playlist_matches:
        playlist_url = (
            playlist_path
            if playlist_path.startswith("http")
            else urllib.parse.urljoin(episode_url, playlist_path)
        )
        playlist_resp = _request("GET", playlist_url)
        if not playlist_resp:
            continue
        rss_url_match = re.search(r"<link[^>]*>([^<]+)</link>", playlist_resp)
        if rss_url_match:
            video_url = rss_url_match.group(1).strip()
            if video_url.startswith("http"):
                return {
                    "url": video_url,
                    "quality": "1080p",
                    "rank": 3,
                    "referer": episode_url,
                }
    return None


def resolve_episode_page(episode_url):
    """Resolve a WCO episode page to the best playable stream URL + headers."""
    page_content = _request("GET", episode_url, use_cache=False)
    if not page_content:
        return None

    premium = _premium_workaround_check(page_content, episode_url)
    if premium:
        return premium

    embed_url, is_m3u8_player = _find_embed_url(page_content, episode_url)
    if not embed_url:
        tools.log(f"wco: no embed url on {episode_url}", "info")
        return None

    player_url = _normalize_embed_player_url(embed_url)
    player_html = _request(
        "GET",
        player_url,
        headers={"Referer": episode_url},
        use_cache=False,
    )
    if not player_html:
        return None

    candidates = _stream_candidates_from_player(player_html, player_url, is_m3u8_player)
    if not candidates:
        tools.log(f"wco: no stream candidates for {episode_url}", "info")
        return None

    best = candidates[0]
    play_url = best["url"]
    if "getvid" in play_url and ".m3u8" not in (play_url or "").lower():
        redirected = wco_http.solve_media_redirect(
            play_url,
            headers={
                "User-Agent": WCO_UA,
                "Referer": BASE_URL,
            },
        )
        if redirected:
            play_url = redirected

    return {
        "url": play_url,
        "quality": best.get("quality", "1080p"),
        "referer": best.get("referer") or player_url,
    }


def build_search_titles(simple_info, all_info=None):
    titles = []
    seen = set()

    def add(value):
        value = (value or "").strip()
        if not value:
            return
        key = value.lower()
        if key in seen:
            return
        seen.add(key)
        titles.append(value)

    info = (all_info or {}).get("info", {})
    add(simple_info.get("show_title"))
    add(info.get("tvshowtitle"))
    for alias in simple_info.get("show_aliases") or []:
        add(alias)
    cleaned = _clean_title(simple_info.get("show_title") or info.get("tvshowtitle"))
    add(cleaned)
    return titles

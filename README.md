# a4kEmbeds

Embed / adaptive provider pack for **[Prism](https://github.com/Goldenfreddy0703/Prism)** only.

Companion to [a4kScrapers](https://github.com/Goldenfreddy0703/a4kScrapers). That pack returns torrents; this one resolves host embeds to playable streams (HLS / direct).

**Current version:** `0.4.0`

## Install

In Prism, set the a4kEmbeds provider URL to:

```
https://api.github.com/repos/Goldenfreddy0703/a4kEmbeds/zipball
```

No GitHub Pages or build step required — pushing to `main` is the release.

## Providers

### Adaptive / embeds

`AniKoto`, `Watchnixtoons2`

| Provider | What it covers |
| --- | --- |
| **AniKoto** | Anime episodes via anikoto + MegaPlay embeds (SUB / DUB, MAL id) |
| **Watchnixtoons2** | Cartoons and anime from WCOStream (SUB / DUB when split) |

## Updating

When you change providers:

1. Edit files in `providers/` or `providerModules/`
2. Bump `version` in `meta.json`
3. Commit and push to `main`

Prism checks `remote_meta` for the new version and pulls updates automatically.

## Repo structure

```
providers/          # Individual provider modules (one file per site)
providerModules/    # Shared framework (core, request, embed extractors)
meta.json           # Version and update URLs
```

## Credits

- Provider pack format based on [a4k-openproject/a4kScrapers](https://github.com/a4k-openproject/a4kScrapers)
- Maintained by [Goldenfreddy0703](https://github.com/Goldenfreddy0703) for [Prism](https://github.com/Goldenfreddy0703/Prism)

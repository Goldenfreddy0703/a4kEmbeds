* [v0.4.2]:
  * Fixed Anikoto / MegaPlay playback after API changes (encrypted `enc` responses)
  * MegaPlay resolver decrypts stream URLs, passes `s=tcdn`, and builds tokenized HLS variant URLs
  * Anikoto referer set to anikototv.to (primary mirror); MAL fallback embeds include `s=tcdn`

* [v0.4.1]:
  * Added Cinejoy adaptive provider (TMDB movies / TV, multi-server HLS)
  * Added Movy adaptive provider (TMDB movies / TV, encrypted API)
  * Cinejoy seal: pure-Python crypto (no WASM runtime in the pack)

* [v0.4.0]:
  * Added adaptive scrapers (Anikoto, Watchnixtoons2)

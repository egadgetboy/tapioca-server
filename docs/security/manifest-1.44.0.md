# Security manifest, tapiOca 1.44.0

The six questions every release answers (DL287), for its readiness record.

1. **New or changed routes or parameters?** No new route. `PUT /api/notify`
   and `PUT /api/arr` take `homeOk` and answer 409 for a new address on the
   home network until the Admin agrees. Both are in the route matrix
   (`tests/security/authz_matrix.py`), Admin only.
2. **New outbound request?** None. All six of tapiOca's own ways out (Plex,
   a player's file from Plex, Sonarr and Radarr, alerts, the away-address
   check, the update check) now go through `app/safefetch.py`, and so does
   every name lookup. The census follows imports and aliases (httpx's
   helpers, urllib, http.client, sockets and lookups), and fails on a way
   out outside safefetch, a proxy or mounts that could route around it, or a
   redirect followed. FFmpeg and ffprobe aren't requests of tapiOca's own:
   they read the media folder's files and Plex's stream addresses, which
   `PlexClient.stream_url` builds on the typed Plex address only.
3. **New file write or upload?** None. The census lists all 51.
4. **New use of FFmpeg or another program?** None. The census lists all 18.
5. **New stored field returned to a client?** None. `homeOk` is never
   stored.
6. **New dependency?** None.

**What this release's suite doesn't cover** (the residual risk): the
security suite's slices 2 and 3 (the HLS boundary in depth, injection
breadth, uploads and FFmpeg, timing, linked servers, cryptography, races,
fault injection, rate limits, data at rest, dependency and image scans,
smuggling, logging, property and differential tests, fuzzing), and checks
for what isn't built yet. Also left for slice 2 (the media pipeline): a
`-protocol_whitelist` on FFmpeg's inputs from the media folder (only
uploads have one today), so a playlist file there can't make FFmpeg fetch
over the network; and CHAIN-01 covers what an outsider or a User can reach,
not the Admin-only routes this release changed, which test_ssrf.py and the
alert and Sonarr tests cover instead. No external pen test yet.

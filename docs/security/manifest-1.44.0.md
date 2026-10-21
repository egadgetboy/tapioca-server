# Security manifest, tapiOca 1.44.0

The six questions every release answers (DL287), for its readiness record.

1. **New or changed routes or parameters?** No new route. `PUT /api/notify`
   and `PUT /api/arr` take `homeOk` and answer 409 for a new address on the
   home network until the Admin agrees. Both are in the route matrix
   (`tests/security/authz_matrix.py`), Admin only.
2. **New outbound request?** None. All six ways out (Plex, a player's file
   from Plex, Sonarr and Radarr, alerts, the away-address check, the
   update check) now go through `app/safefetch.py`, and the census fails on
   one outside it.
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
for what isn't built yet. No external pen test yet.

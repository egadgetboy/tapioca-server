# Security report, tapiOca 1.44.3

Run 2026-10-29.
A local run, at commit 1b942adda0622edf35727b3d9803b46469885eda.
Python 3.13.17, pytest 9.1.1.

| Area | Severity | Passed | Failed |
| --- | --- | --- | --- |
| The census: every way out, program and write declared (A.1, DEP-03, DEP-04) | High | 19 | 0 |
| Every route from every vantage point (AZ-01 to AZ-03, AUTH-01, AUTH-02) | Critical | 229 | 0 |
| Sign-in tokens: ended at once, never in an address or a log, kinds kept apart (AUTH-06, 06b, 07) | Critical | 9 | 0 |
| Outbound requests by provenance (SSRF-01 to SSRF-08) | Critical | 67 | 0 |
| Paths on every route with a parameter (INJ-01) | Critical | 37 | 0 |
| The four scripted chains (CHAIN-01 to CHAIN-04) | Critical | 12 | 0 |
| Only Sign out reads the device sign-ins' record, in code and as it runs (1.44.3) | High | 3 | 0 |
| The live harness (attack_check) | Critical | 825 | 0 |

Checks in all: 1201 (the corpus last recorded 1201).

Tracked exceptions (Medium):
- MED-FFMPEG-01 (Medium, tracked for The security suite: breadth and depth, slice 2's media pipeline): FFmpeg and ffprobe read Media with no protocol or format whitelist (uploads have one). A file in the media folder that holds a playlist or a DASH manifest under a video's name can make them fetch an address from this machine or the home network, and they follow a redirect from Plex's address. tapiOca's own requests (safefetch) aren't affected. Found by the security audit of 1.44.0.



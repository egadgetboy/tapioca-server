# Security manifest, tapiOca 1.44.4

The six questions every release answers, for its readiness record.

1. **New or changed routes or parameters?** None. The Broken files tab's
   Needs you list changes on the page alone: it reads `/api/broken` and
   `/api/reports` as before.
2. **New outbound request?** None new. The update check's one request, to
   GitHub's public API for tapiOca's latest release, now names the
   repository by its current number (1437500119, not 1414995565 from before
   1.44.2's fresh start). It's still asked only when an Admin turned the
   check on, still through `app/safefetch.py`, with the same 10-second wait,
   no redirects followed, and nothing sent but the request itself.
3. **New file write or upload?** None.
4. **New use of FFmpeg or another program?** None. (The gates' new step,
   which compares that number with the repository's own, runs in CI only,
   and never ships.)
5. **New stored field returned to a client?** None.
6. **New dependency?** None.

**What this release's suite doesn't cover** (the residual risk): as
1.44.0's manifest says (slices 2 and 3 of the suite; MED-FFMPEG-01, still a
tracked Medium exception). No external pen test yet.

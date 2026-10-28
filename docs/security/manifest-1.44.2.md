# Security manifest, tapiOca 1.44.2

The six questions every release answers, for its readiness record.

1. **New or changed routes or parameters?** None.
2. **New outbound request?** None.
3. **New file write or upload?** None.
4. **New use of FFmpeg or another program?** None.
5. **New stored field returned to a client?** None.
6. **New dependency?** None. One changed: certifi, the list of trusted
   certificate authorities, from 2026.7.22 to 2026.10.18, which drops root
   certificates whose intermediate keys were compromised
   (GHSA-6q48-6c7w-9gw2, Critical). It's what tapiOca checks every HTTPS
   address it reaches against.

**Also in it, never shipped in the image:** the release gate and the checks
CI runs on every push (the release manifest, the size ratchet on
`app/main.py`, copied code, ruff on changed lines, vulture, strict types on
new modules, the dependency scan with a bill of materials, coverage of
changed lines, and new and changed tests run 20 times).

**What this release's suite doesn't cover** (the residual risk): as
1.44.0's manifest says (slices 2 and 3 of the suite; MED-FFMPEG-01, still a
tracked Medium exception). No external pen test yet.

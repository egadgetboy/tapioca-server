# Security manifest, tapiOca 1.44.3

The six questions every release answers, for its readiness record.

1. **New or changed routes or parameters?** One route changed, none new:
   `POST /api/internal/picker/remove` joins the Gate's open routes. The
   device's key says which device, and the handler decides: a sign-in still
   good, or the person's newest on that device after it ended (or the one a
   changed password renewed it from), taking only that person off that
   device's list. Bearer only (a browser's cookie no longer works there); an
   API token gets the Gate's own answer, kept for the handler. Its class in
   the suite's matrix changes from watcher to a new class, device, with its
   own checks, and the Gate's open list is pinned.
2. **New outbound request?** None.
3. **New file write or upload?** None but the database: a new table,
   `device_sign_ins` (hashes only, as `sessions` keeps them), emptied in
   every backup 1.44.3 makes and forgotten when one is restored, kept in the
   before-update copy.
4. **New use of FFmpeg or another program?** None.
5. **New stored field returned to a client?** None: only the remove reads
   the table, and it answers `{"ok": true}` or the refusals it answered
   before.
6. **New dependency?** None.

**The threat model:** `docs/threat-models/signout-ends.md` (every path, the
races, the update and going back), audited three times before any code.

**What this release's suite doesn't cover** (the residual risk): as
1.44.0's manifest says (slices 2 and 3 of the suite; MED-FFMPEG-01, still a
tracked Medium exception). No external pen test yet.

---
paths:
  - "app/folderart.py"
  - "app/applibrary.py"
  - "app/library.py"
  - "app/folders.py"
  - "app/folderscan.py"
  - "app/ondemand.py"
  - "app/web/**"
  - "tests/test_picture_*.py"
  - "tests/test_whose_pictures.py"
  - "tools/picture_load.py"
---
# Browsing speed (standing rules, loaded with the work)

## Tests
- **No release may make browsing slower** (the restore-fast-pictures
  handoff's part 8d, after the owner's report of October 20; the plan's
  release gate and DL282).
  - Hard gates, with no margin: a folder page under picture load never
    answers 503; the counts never go up (Plex details lookups per picture,
    FFmpeg starts per Plex picture, picture requests in the roll for
    pictures already kept).
  - Timings: p95 may be at most 20% worse than the recorded baseline, and
    never past the budget.
  - Any change to pictures, browsing, the shell's grids or caching runs the
    handoff's 8a to 8c before its candidate: the server's
    `tests/test_picture_speed.py` (8a); `tools/picture_load.py` on the
    plan's low-end server (8b, the owner's to run: that hardware is outside
    the repos); the apps' shared cases, picture tests and timed roll (8c).
  - A new baseline is recorded only with the owner's OK.
  - **One exception, by the owner (October 21, DL283):** the picture
    revert ships on 8a, the shared cases and the apps' picture tests, the
    owner checking real devices after it's out, with 8c's timed roll built
    right after it as its own release; every release after it runs the
    whole rule.

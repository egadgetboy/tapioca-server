# CLAUDE.md, old to new (server)

Every rule of the old `CLAUDE.md` (256 lines, 26032 bytes), in order, with the one file it lives in now. Rules move word for word; the only change of words is the reference marked. `python3 tools/claude_rules.py` checks each rule is in its file, once, by a hash of its words.

| Old line | Old section | Rule starts | Now in |
| --- | --- | --- | --- |
| 3 |  | tapiOca (called StationPlay until 1.34.0) is a self-hosted TV and media … | `CLAUDE.md` |
| 9 | The product | "Station," never "channel," in anything people read (Plex's own feature … | `CLAUDE.md` |
| 11 | The product | "Media," never "Library," for the on-demand titles, in anything people r… | `CLAUDE.md` |
| 13 | The product | Legal care (the owner, October 11; the plan's "Legal care" has it all): … | `CLAUDE.md` |
| 31 | The product | Clear American English. Friendly, short and plain on the page; concise i… | `CLAUDE.md` |
| 34 | The product | No outside services beyond those the plan names (the plan's Principles l… | `CLAUDE.md` |
| 36 | The product | A look unlike Plex or Emby. Original work only.… | `CLAUDE.md` |
| 37 | The product | Opt-in features, a lean server: no new dependencies; what an app can do … | `CLAUDE.md` |
| 39 | The product | No real file names or paths in anything the apps receive.… | `CLAUDE.md` |
| 40 | The product | tapiOca is labeled beta (the owner, October 12; alpha before) until the … | `CLAUDE.md` |
| 42 | The product | The page is a full web client for Admins only (the owner, October 17, D1… | `CLAUDE.md` |
| 52 | The product | Admins see viewing by default (the owner, October 17, D09, replacing the… | `CLAUDE.md` |
| 58 | The product | 1.0 is feature-complete (the owner, October 18, 2:46 PM; the plan's feat… | `CLAUDE.md` |
| 63 | The product | Features lead, APIs follow (the same day): the tuner (HDHomeRun, M3U, XM… | `CLAUDE.md` |
| 70 | The product | Every tapiOca app needs a signed-in person (the owner, October 18): some… | `CLAUDE.md` |
| 78 | The product | The plan is the one specification (the owner, October 18): the apps repo… | `CLAUDE.md` |
| 85 | The product | Only the server owner acknowledges (the owner, October 18; the plan's Le… | `CLAUDE.md` |
| 91 | The product | Personal use, on hardware you own (the owner, October 12): the README an… | `CLAUDE.md` |
| 98 | The product | Parental claims say "in tapiOca's apps," and the docs say what limits do… | `CLAUDE.md` |
| 100 | The product | Together, server and apps (the owner, October 13: "I'm OK with certain f… | `CLAUDE.md` |
| 106 | The product | No licensing in the server (the owner's final plan, October 10): it stay… | `CLAUDE.md` (reference updated) |
| 113 | Resuming work | Every time work resumes, and as each release starts, tell the owner in o… | `CLAUDE.md` |
| 122 | How work runs | The lead developer decides every engineering question: risk classes, tes… | `CLAUDE.md` |
| 123 | How work runs | The order is frozen at the top (the owner, October 27): the next five re… | `CLAUDE.md` |
| 124 | How work runs | The look alongside S4 (the owner, October 31, DL407): the server release… | `CLAUDE.md` |
| 125 | How work runs | The apps' look first: server halves and behavior that changes no app scr… | `CLAUDE.md` |
| 126 | How work runs | Every feature through intake: a new feature gets its place in the plan's… | `CLAUDE.md` |
| 127 | How work runs | Gates come from the class, checked by CI: from the release that builds t… | `CLAUDE.md` |
| 128 | How work runs | Modular, checkably: new feature code goes in its own module, never into … | `CLAUDE.md` |
| 129 | How work runs | One status source: the plan's release order is the status; the resume no… | `CLAUDE.md` |
| 130 | How work runs | Decisions batched: new ideas arrive as proposals and are folded into the… | `CLAUDE.md` |
| 131 | How work runs | Until the launch (apps 1.0, server 2.0.0) (the owner, October 27): every… | `CLAUDE.md` |
| 132 | How work runs | No slop (the owner, October 27): every release leaves the modules it tou… | `CLAUDE.md` |
| 133 | How work runs | Never build on what's going away (the owner, November 1, DL425): no work… | `CLAUDE.md` |
| 134 | How work runs | Quality gates (the owner, October 27; the release gate's table has each;… | `.claude/rules/releases.md` |
| 135 | How work runs | Flaky tests are defects: never rerun to green or loosened; a new or chan… | `.claude/rules/releases.md` |
| 136 | How work runs | Changed core lines are covered, and the key modules get mutation tests o… | `.claude/rules/releases.md` |
| 137 | How work runs | Warnings fail the build; strict type checking (mypy, strict) on new code… | `.claude/rules/releases.md` |
| 138 | How work runs | Changed screens are compared with what the owner approved; a difference … | `.claude/rules/releases.md` |
| 139 | How work runs | CPU, memory and startup never get worse without the owner's OK.… | `.claude/rules/releases.md` |
| 140 | How work runs | Accessibility audits run on changed screens.… | `.claude/rules/releases.md` |
| 141 | How work runs | Beside Jellyfin (the owner, October 28, DL375): monthly and at each feat… | `.claude/rules/releases.md` |
| 142 | How work runs | Halt and report (the owner, October 28: "halt and report if testing show… | `.claude/rules/releases.md` |
| 143 | How work runs | Dependencies are pinned and scanned, with a license check and a bill of … | `.claude/rules/releases.md` |
| 144 | How work runs | A soak before a Class D release publishes, on a CI server with real FFmp… | `.claude/rules/releases.md` |
| 145 | How work runs | A session ends clean: CI green, no work on a branch that isn't written d… | `CLAUDE.md` |
| 146 | How work runs | Heavy checks at the release candidate, not on every push.… | `.claude/rules/releases.md` |
| 147 | How work runs | After 1.0, only: Samsung and LG TVs and Fire TV (both for review of supp… | `CLAUDE.md` |
| 148 | How work runs | Stop only the affected work, and ask the owner, when two controlling req… | `CLAUDE.md` |
| 149 | How work runs | Four states: Exploratory; Implemented, pending release; Integrated, rele… | `CLAUDE.md` |
| 150 | How work runs | Classes, by what a change can reach: A (words and looks), B (routine beh… | `CLAUDE.md` |
| 151 | How work runs | Modular code: one authoritative decision for each rule, called from ever… | `CLAUDE.md` |
| 152 | How work runs | The stack is locked (the owner, November 2, DL430; DL408): Python stays … | `CLAUDE.md` |
| 155 | Tests | Every bug gets a failing test first, then a root-cause fix. The test sta… | `CLAUDE.md` |
| 157 | Tests | Never weaken a test: Don’t loosen a tolerance, change an expected result… | `CLAUDE.md` |
| 158 | Tests | While working, run the changed area's tests (and D's negative, race and … | `CLAUDE.md` |
| 159 | Tests | Don't edit `tests/fakeplex.py`.… | `CLAUDE.md` |
| 160 | Tests | No release may make browsing slower (the restore-fast-pictures handoff's… | `.claude/rules/browsing-speed.md` |
| 163 | Tests | Hard gates, with no margin: a folder page under picture load never answe… | `.claude/rules/browsing-speed.md` |
| 167 | Tests | Timings: p95 may be at most 20% worse than the recorded baseline, and ne… | `.claude/rules/browsing-speed.md` |
| 169 | Tests | Any change to pictures, browsing, the shell's grids or caching runs the … | `.claude/rules/browsing-speed.md` |
| 174 | Tests | A new baseline is recorded only with the owner's OK.… | `.claude/rules/browsing-speed.md` |
| 175 | Tests | One exception, by the owner (October 21, DL283): the picture revert ship… | `.claude/rules/browsing-speed.md` |
| 180 | Tests | The wording scan passes (from 1.33.0).… | `CLAUDE.md` |
| 183 | Releases | The manual (the owner, November 1, DL422; the plan's The manuals): `manu… | `.claude/rules/releases.md` |
| 184 | Releases | Remaining Development (the owner, November 1, DL426): the two PDF handof… | `.claude/rules/releases.md` |
| 185 | Releases | Releases are bundles: compatible A to C work ships together when it belo… | `.claude/rules/releases.md` |
| 189 | Releases | Each release candidate, by class (the plan's release gate has the table)… | `.claude/rules/releases.md` |
| 190 | Releases | The security suite, at every release candidate (the owner, October 21: "… | `.claude/rules/releases.md` |
| 208 | Releases | Playback observability grows with every release (DL289): a release that … | `.claude/rules/releases.md` |
| 213 | Releases | Any database change on upgrade is preceded by an automatic backup (`data… | `CLAUDE.md` |
| 216 | Releases | Notes (`docs/releases/v<version>.md`, line 2 `commit: <full ID>` of the … | `.claude/rules/releases.md` |
| 220 | Releases | The image is published (the owner, October 12, later the same day: D4 is… | `.claude/rules/releases.md` |
| 228 | Releases | Report to the owner, 5 lines, for each published release: version and su… | `.claude/rules/releases.md` |
| 229 | Releases | Every 3 releases, stop and tell the owner, who runs an independent audit… | `.claude/rules/releases.md` |
| 235 | High-risk areas | Always built by the main session, never handed to `routine-builder`: the… | `CLAUDE.md` |
| 241 | Delegation | Hand `routine-builder` whole tasks, such as a full screen or a set of wo… | `CLAUDE.md` |
| 244 | Delegation | Every handoff is complete: the task, the files involved, the relevant de… | `CLAUDE.md` |
| 246 | Delegation | Review everything `routine-builder` returns before it goes into a releas… | `CLAUDE.md` |
| 248 | Delegation | Send work to `cold-auditor` by class: every D change before integration … | `CLAUDE.md` |
| 249 | Delegation | Never set the `CLAUDE_CODE_EFFORT_LEVEL` environment variable: it overri… | `CLAUDE.md` |
| 253 | Git and the machine | Explicit paths, never `git add -A`; never `git reset --hard` with uncomm… | `CLAUDE.md` |
| 255 | Git and the machine | Stop processes by their PID only (never `pkill -f` or `pgrep -f`).… | `CLAUDE.md` |
| 256 | Git and the machine | GitHub Actions minutes count: run what a change needs, nothing more.… | `CLAUDE.md` |

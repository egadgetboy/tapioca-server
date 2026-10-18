# tapiOca: standing rules

tapiOca (called StationPlay until 1.34.0) is a self-hosted TV and media server, free and open source under
the AGPL (version 3), copyright egadgetboy. Its paid apps live in a private repo
(egadgetboy/tapioca-apps). These are the owner's standing decisions:
follow them in every change.

## The product
- **"Station," never "channel,"** in anything people read (Plex's own
  feature names excepted).
- **"Media," never "Library,"** for the on-demand titles, in anything people
  read (the owner, October 11).
- **Legal care** (the owner, October 11; the plan's "Legal care" has it
  all): anything people read speaks of "your own movies and shows," never
  free TV, real network or show names, or cutting the cord. The tuner,
  playlist and guide addresses stay home-network only and "work with Plex
  and Jellyfin," never "IPTV". No built-in logo resembles a real network's
  name, symbol, colors or layout. Sonarr and Radarr are an optional
  integration the docs describe plainly, never marketed. Details come from
  Plex, the files, an Admin's keyed services and the open sources built in
  (Wikidata; TVmaze's data, credited, never its images); only the server
  contacts them, and their credits show under About. Each release carries
  the open-source notices its parts require (FFmpeg's, in the image). The name
  (the owner, October 12): **tapiOca**, always a lowercase t and a capital O,
  even at the start of a sentence (never "Tapioca", "TAPIOCA" or "TapiOca");
  the full name is **"tapiOca: Stations & Media"**; lowercase **tapioca** for
  new identifiers. Names other programs match (the StationPlay-API header, cookies, the database, the container name, Plex's
  tuner and guide IDs and more) keep their old names: see
  docs/notes/names-kept.md. The brand kit is in the apps repo, at
  brand/tapioca-brand-kit.
- **Clear American English.** Friendly, short and plain on the page;
  concise in the logs. Short sentences, one idea each, no jargon. Say
  **PIN**, never "passcode" (the owner's choice, from 1.31.0).
- **No outside services** beyond those the plan names (the plan's Principles
  list them all), and no AI features. Nothing outside the home is required.
- **A look unlike Plex or Emby.** Original work only.
- **Opt-in features, a lean server:** no new dependencies; what an app can
  do itself lives in the app.
- **No real file names or paths** in anything the apps receive.
- tapiOca is labeled **beta** (the owner, October 12; alpha before) until the
  apps launch. No DVR.
- **The page is a full web client for Admins only** (the owner, October 17,
  D10, replacing "no web client for watching" and the browse-only web
  companion): one page for running the server and for everything the paid
  apps do, Stations and Media playback included, free, and only with an
  Admin's sign-in (Full or Light, as on the page today). At most **one
  active browser sign-in per server**, across all Admins and browsers,
  enforced by the server (tabs of the same sign-in are fine); it never
  limits the apps, other clients or how many watch a Station. It never
  changes the apps' purchase for anyone else, and no playback address it
  uses works without that sign-in.
- **Admins see viewing by default** (the owner, October 17, D09, replacing
  the opt-in "Share what you watch with your Admin"): each person's history
  and stats, for fixing problems and choosing what to add. A person may ask
  to stop; an Admin decides, and the request shows Pending, Approved or
  Denied. The privacy notice and each person's first sign-in say this
  plainly, and never claim it overrides rights the law gives.
- **1.0 is feature-complete** (the owner, October 18, 2:46 PM; the plan's
  feature register): every retained feature ships before 1.0, on every
  platform it applies to, with Plex and without it. A server with no Plex,
  Plex Pass, Sonarr or Radarr is first-class.
- **Features lead, APIs follow** (the same day): the tuner (HDHomeRun, M3U,
  XMLTV, HLS) stays as it is; tapiOca's apps use their own signed-in routes;
  `/api/v1`, API tokens and the companion API are retired in two releases
  ("The apps' own routes", then "Retire the public API"). Never add to
  `/api/v1`. The web client's playback and app features answer only at home
  or through an authenticated VPN into home, by one server-side policy;
  the management page stays reachable away from home.
- **Every tapiOca app needs a signed-in person** (the owner, October 18):
  someone an Admin added, with no anonymous or guest viewing, and nothing
  kept for a made-up person. A server with signing in off keeps serving
  Plex, Jellyfin and other apps on the tuner exactly as before; tapiOca's
  apps ask the Admin to turn signing in on first. **The server decides**
  every limit, lock, pause, viewing time and break, on every way of
  watching, and a stream already going stops when a rule says so; the apps
  never hold those rules themselves (the plan's Profiles).
- **The plan is the one specification** (the owner, October 18): the
  apps repo's `plan.md` (its `plan-update` branch until it's merged), with
  every decision of the owner's written into the section it changes, and
  its decision log dated. The owner's handoffs in its `reference/` are the
  sources it was built from; where one differs from the plan, the plan is
  current. New decisions change the plan's own text, never a banner or an
  addendum.
- **Only the server owner acknowledges** (the owner, October 18; the
  plan's Legal care): the Media & Access Responsibilities notice, once, at
  first setup, after counsel's review. No app, viewer or other Admin is
  ever asked to accept terms, and nothing limits the AGPL's rights.
  Accounts, User Groups and invitations are access controls, never rights
  to anyone's Media.
- **Personal use, on hardware you own** (the owner, October 12): the README
  and first-run setup's Plex step say tapiOca works with your own Plex
  Media Server, and that Plex's terms license it for personal use, on
  hardware and storage you own. They state it as Plex's terms, never as a
  limit tapiOca sets. The privacy notice (PRIVACY.md, served at
  /privacy) and the copyright notice in the source stay, as Plex's terms
  ask of software that calls Plex.
- **Parental claims** say "in tapiOca's apps," and the docs say what
  limits don't cover (Plex, Jellyfin and anything else on the tuner).
- **Together, server and apps** (the owner, October 13: "I'm OK with
  certain features only working if tapiOca Server and Client are working
  together. This is a selling point."): a feature may work only between
  tapiOca's server and its apps, and that's said as a strength. The docs
  and release notes still say plainly what other apps, Plex's own among
  them, don't get.
- **No licensing in the server** (the owner's final plan, October 10): it
  stays fully open source and unlimited and never locks anything. The apps
  are unlocked in their own stores, one purchase per platform, with a free
  tier until then (the apps repo's CLAUDE.md has the details). Never limit
  Plex, Jellyfin or other clients.

## Resuming work
- **Every time work resumes, and as each release starts,** tell the owner
  in one short paragraph (the owner, October 18): what was finished last;
  what's being built now, and about how long it should take (work apart
  from CI waits); the next 2 or 3 after it; the quality proof it gets; any
  owner input needed (usually none); and which effort level he should be
  on (Medium, High, Extra high or Max). It's FYI: don't wait for a reply.
  Keep it current in the plan's `next.md`, "Where we are".

## How work runs (the owner, October 18, 12:42 PM; the plan's "How work runs until the beta" has it all)
- **The lead developer decides every engineering question**: risk classes, tests, reviews, CI, module seams, the release order and what each release bundles. Report them as FYI; never ask the owner to approve them. The owner decides a feature's behavior, the look, launch scope and anything legal or commercial, only where the plan doesn't already say.
- **By development need, never by how recent a decision is:** what's in progress, then what other work is built on, then the apps' new shell before any new app screen, then features. Follow the plan's release order.
- **Stop only the affected work, and ask the owner,** when two controlling requirements contradict; a change would depart from the plan's product, security or compatibility contracts; an engineering conclusion contradicts an earlier decision without evidence that settles it; scope or behavior drifts; an ambiguity has materially different user-facing or security outcomes; or a step is outside the repos (the owner's TrueNAS server, router or Plex: the owner installs releases), needs a production secret, or can't be undone. Say: the blocked item, the exact conflict and its sections, the consequences, at most three options with a recommendation, and the safe work that goes on.
- **Four states:** Exploratory; Implemented, pending release; Integrated, release candidate; Released. Built means Released.
- **Classes,** by what a change can reach: A (words and looks), B (routine behavior and data), C (workflows and stored settings), D (sign-in, rosters, limits, what plays, stopping streams, casting, privacy, schema and migrations, critical concurrency). A change takes the highest class it can reach.
- **Modular code:** one authoritative decision for each rule, called from every place that enforces it; seams are extracted in the release that needs them (characterization tests, a pure move, then the new behavior, then delete the copies). No rewrites, no splitting for size, no new frameworks or dependencies.

## Tests
- **Every bug gets a failing test first,** then a root-cause fix. The test
  stays.
- **Never weaken a test:** don't loosen a tolerance, change an expected
  result to make it pass, skip it or delete it. If a test looks wrong, stop
  and explain why.
- While working, run the changed area's tests (and D's negative, race and restart cases), in a local environment matched to the image's pins where possible. The full suite (35 to 45 minutes) is proved by image.yml's Test step, in the exact image, on amd64 and arm64, once per release candidate; run it locally only to chase a failure.
- Don't edit `tests/fakeplex.py`.
- The wording scan passes (from 1.33.0).

## Releases
- **Releases are bundles:** compatible A to C work ships together when it belongs together, with one candidate and one gate; D work ships in a small candidate of its own. Tiny wording or style fixes wait for the next release. Minor version for features, patch for fixes. The version is in `app/__init__.py` and
  `pyproject.toml`. (From 1.34.0, the TrueNAS file and `docker-compose.yml`
  ask for the published image at `:latest`. The TrueNAS file is
  `tapioca-server.yaml` from 1.35.0, `stationplay.yaml` before.)
- **Each release candidate,** by class (the plan's release gate has the table): a threat model and every-path matrix before D code; reviews by class (A and B a written self-review; C a focused independent review; D a `cold-auditor` audit before integration and of the final diff, with later rounds re-checking the fixed items unless the design changed); the area's tests while building; then, always: CI's full suite in the exact image on both architectures, `python tools/upgrade_check.py --from <previous release's commit>`, `python -m tools.attack_check`, `python tools/image_check.py` and the release's own tests (`tests/test_info_station.py`, whose what's-new must be this version's, and `tests/test_release_workflow.py`) before the push to main (about 3 minutes), real FFmpeg streaming for affected playback, Playwright at 390, 768 and 1440 wide, light and dark, for page changes; then notes and a report.
- Any database change on upgrade is preceded by an automatic backup
  (`data/backups/before-<version>-<date>.db`), and the notes give tested
  rollback steps.
- **Notes** (`docs/releases/v<version>.md`, line 2 `commit: <full ID>` of
  the tested commit on `main`): one screen. A summary sentence, short New
  and Fixed bullets, Updating, Rolling back. Published by
  `.github/workflows/release.yml`.
- **The image is published** (the owner, October 12, later the same day:
  D4 is No, U1): `ghcr.io/egadgetboy/tapioca-server`, amd64 and arm64, with
  `:<version>`, `:<major.minor>` and `:latest` moved only after the image's
  tests pass; always the exact image tested, by digest, never rebuilt (C7);
  with the GPL and LGPL packages' source attached to each release (C6), and
  each release zip signed. The YAML and compose files use `:latest` and start without the
  internet (`pull_policy: missing`; each install's update steps pull: the
  lead developer, October 12, for the owner to confirm, as U2 had `always`). Building from source stays an advanced choice.
- **Report** to the owner, 5 lines, for each published release: version and summary; tests; choices; known limits; one improvement made to the development process (FYI). Then: which work went to `routine-builder`, and what `cold-auditor` found and what was done about each item.
- **Every 3 releases, stop** and tell the owner, who runs an independent
  audit before work continues. (Suspended by the owner on October 12 until
  the apps reach their beta: keep going, decide as the lead developer, and
  don't stop for anything aesthetic. He audits at the beta.)

## High-risk areas
Always built by the main session, never handed to `routine-builder`: the
streaming engine, sign-in and security, user access and content limits,
database changes and upgrades, multi-server, Watch Group sync, audio
passthrough, and anything that could expose data or stop playback.

## Delegation
- Hand `routine-builder` whole tasks, such as a full screen or a set of
  wording changes, not one-line fixes. Each helper starts fresh and has to
  re-read files, so tiny handoffs cost more than they save.
- Every handoff is complete: the task, the files involved, the relevant
  decisions, and what "done" means. Helpers don't see the conversation.
- Review everything `routine-builder` returns before it goes into a
  release.
- Send work to `cold-auditor` by class: every D change before integration and its final diff; C's affected flows when warranted. Fix everything it finds, or explain in the report why an item isn't a problem. Each fix gets a test that would have caught it.
- Never set the `CLAUDE_CODE_EFFORT_LEVEL` environment variable: it
  overrides the helpers' effort levels.

## Git and the machine
- Explicit paths, never `git add -A`; never `git reset --hard` with
  uncommitted work. Only the main session pushes.
- Stop processes by their PID only (never `pkill -f` or `pgrep -f`).
- GitHub Actions minutes count: run what a change needs, nothing more.

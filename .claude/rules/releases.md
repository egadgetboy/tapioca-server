---
paths:
  - "docs/releases/**"
  - "docs/security/**"
  - "manual/**"
  - "tools/manual/**"
  - "tools/release_gate.py"
  - "tools/security_suite.py"
  - "tools/attack_check.py"
  - "tools/upgrade_check.py"
  - "tools/image_check.py"
  - "tests/test_info_station.py"
  - "tests/test_release_workflow.py"
  - ".github/workflows/**"
  - "app/__init__.py"
  - "pyproject.toml"
  - "docker-compose.yml"
  - "tapioca-server.yaml"
  - "Dockerfile"
---
# Releases and quality gates (standing rules, loaded with the work)

## How work runs (the owner, October 18, 12:42 PM; the plan's "How work runs until the beta" has it all)
- **Quality gates** (the owner, October 27; the release gate's table has each; built into CI by the two Gates releases, followed by hand until then):
  - **Flaky tests are defects:** never rerun to green or loosened; a new or changed test runs about 20 times in CI before it merges; a quarantined test has an open defect with a deadline in `next.md`.
  - **Changed core lines are covered,** and the key modules get mutation tests on a schedule.
  - **Warnings fail the build;** strict type checking (mypy, strict) on new code, with a baseline for the rest.
  - **Changed screens are compared** with what the owner approved; a difference past the threshold fails until a person fixes it or the owner approves the new look.
  - **CPU, memory and startup never get worse** without the owner's OK.
  - **Accessibility audits** run on changed screens.
  - **Beside Jellyfin** (the owner, October 28, DL375): monthly and at each feature release candidate, tapiOca is measured the same way as Jellyfin's newest open-source apps and server (the comparison runs in the apps repository); the manifest names the run, and where tapiOca is heavier is captured in `next.md` and triaged.
  - **Halt and report** (the owner, October 28: "halt and report if testing shows results that are not acceptable tolerance"): when a measurement is past its tolerance (a hard limit worse than its baseline by more than its `worse_by`, or a measure more than 20% heavier than Jellyfin's), stop that release's work and tell the owner at once: what, by how much, the run, and at most three options with a recommendation. Never loosen a tolerance, rerun to green or carry on without his OK; other work on the release waits.
  - **Dependencies are pinned and scanned,** with a license check and a bill of materials; a known Critical or High fails the build.
  - **A soak before a Class D release publishes,** on a CI server with real FFmpeg and headless clients. Never pause for a real device before 1.0: a step only a real device can show is "NOT RUN, real device, at 1.0", never passed.
  - **Heavy checks at the release candidate,** not on every push.

## Releases
- **The manual** (the owner, November 1, DL422; the plan's The manuals): `manual/tapioca-server-manual.pdf`, linked from README.md, is the one manual, and covers only what's released: every feature, setting, choice and default, with steps, tips and a glossary, in clear, polished American English. Each release changes its chapters with the change, sets the cover's release and date, rebuilds the PDF (`python3 tools/manual/build.py manual`) and passes `python3 tools/manual/check.py` before its notes are pushed. Never an older edition kept or attached; screenshots stay placeholders until the owner asks for them.
- **Remaining Development** (the owner, November 1, DL426): the two PDF handoffs of what's planned and not yet built live in the apps repo (`remaining/server/`, `remaining/apps/`), private with the plan. Each server release, in the same session, takes what it shipped out of both, writes in the decisions made since, sets both covers' Server version and date, rebuilds both PDFs there and passes the apps repo's `python3 tools/manual/check.py` before its notes are pushed.
- **Releases are bundles:** compatible A to C work ships together when it belongs together, with one candidate and one gate; D work ships in a small candidate of its own. Tiny wording or style fixes wait for the next release. Minor version for features, patch for fixes. The version is in `app/__init__.py` and
  `pyproject.toml`. (From 1.34.0, the TrueNAS file and `docker-compose.yml`
  ask for the published image at `:latest`. The TrueNAS file is
  `tapioca-server.yaml` from 1.35.0, `stationplay.yaml` before.)
- **Each release candidate,** by class (the plan's release gate has the table): a threat model and every-path matrix before D code; reviews by class (A and B a written self-review; C a focused independent review; D a `cold-auditor` audit before integration and of the final diff, with later rounds re-checking the fixed items unless the design changed); the area's tests while building; then, always: CI's full suite in the exact image on both architectures, `python tools/upgrade_check.py --from <previous release's commit>`, the security suite (`python -m tools.security_suite`, below), `python tools/image_check.py` and the release's own tests (`tests/test_info_station.py`, whose what's-new must be this version's, and `tests/test_release_workflow.py`) before the push to main (about 3 minutes), real FFmpeg streaming for affected playback, Playwright at 390, 768 and 1440 wide, light and dark, for page changes; then notes and a report.
- **The security suite, at every release candidate** (the owner, October
  21: "Update security battery for every future tapioca release"; DL287;
  the plan's release gate): `python -m tools.security_suite` passes with no
  open Critical or High, in every class, on both sides. It runs
  `tests/security` (also on every push, with the other tests) and the live
  harness, `tools/attack_check.py` (`python -m tools.attack_check` still
  runs it alone), and writes `docs/security/report-<version>.md`. A Medium
  needs a tracked exception in `tools/security_exceptions.json`, which the
  report lists. Its corpus only grows: a drop in its count fails the run
  unless `tools/security_corpus.json` logs a merge of duplicates. Each
  release writes `docs/security/manifest-<version>.md`, answering the six
  questions (new routes or parameters, outbound requests, file writes,
  programs started, stored fields sent to a client, dependencies; "none"
  is fine), and adds what it answers yes to the suite's matrices. A new
  route, outbound request, program or write that isn't declared fails the
  suite's census. Every outbound request goes through `app/safefetch.py`:
  a typed address may be at home; any other must be public (DL287's
  provenance).
- **Playback observability grows with every release** (DL289): a release
  that touches playback, conversion, HDR or sound handling, or a new way
  of playing asks whether the diagnostic view and the log capture the new
  behavior, its reason and its health signal. New playback behavior ships
  with its telemetry.
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
- **Report** to the owner, 5 lines, for each published release: version and summary; tests; choices; known limits; one improvement made to the development process (FYI). Then a security line (for example, "Security: 1,138 checks, all passing; no exceptions"). Then: which work went to `routine-builder`, and what `cold-auditor` found and what was done about each item.
- **Every 3 releases, stop** and tell the owner, who runs an independent
  audit before work continues. (Suspended by the owner on October 12 until
  the apps reach their beta: keep going, decide as the lead developer, and
  don't stop for anything aesthetic. He audits at the beta.)

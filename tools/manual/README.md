# tapiOca's manual kit

One manual per repo, at `manual/<file>.pdf`, linked from README.md, and replaced by each release (the plan's The manuals; DL422). Old editions are never kept in the repo; git history has them.

- **Write:** `manual/src/NN-name.md`, one chapter each, in order, each starting with one `# ` heading; `##` and `###` inside. The cover is `manual/manual.json`: `file`, `title`, `subtitle`, `releases` (`[["Server", "1.44.3"]]`, or one pair for each app), `date` ("November 1, 2026") and `label`.
- **Conventions:**
  - Callouts: a quote whose first words are `**Tip:**`, `**Note:**` or `**Important:**`.
  - A screenshot still to come: `[[screenshot: what it will show]]` on its own line (a labeled placeholder box).
  - A setting: a table, `| Setting | What it does | Choices | Default |`, its name in bold exactly as on screen.
  - The glossary: `Term`, then `: what it means` on the next line.
  - A line quoting another product's own feature name ends with `<!-- wording-ok -->`.
- **Build:** `python3 -m pip install -r tools/manual/requirements.txt` (a dev tool only, never in the image or an app), then `python3 tools/manual/build.py manual`. It writes the PDF, `manual/manual.lock` (the PDF's hash, tied to the chapters and cover it was built from; committed with it) and an `.html` beside it (not committed).
- **Check:** `python3 tools/manual/check.py`, at every release candidate, before the notes go up. It checks every document (`manual/`, and `remaining/*/` where they exist), and fails on a stale or second copy, a cover that doesn't name the release being published, a missing README link, or the wording rules.
- **Remaining Development** (DL426, the apps repo only): `remaining/server/` and `remaining/apps/` are documents of the same shape, with `"kind": "remaining"` in `manual.json` (their covers name the server's and each app's newest release) and an optional `"edition"` line for the contents page. Build each with `python3 tools/manual/build.py remaining/server` (or `remaining/apps`); `check.py` with no argument checks every document.
- **Fonts:** Outfit, from the brand kit, under the SIL Open Font License (`fonts/OFL.txt`).

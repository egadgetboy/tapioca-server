"""The development safeguards DS-2 and DS-3 (DL430), checked on every push.

DS-2: committing, pushing and `gh` are the main session's alone. Each helper's
agent file (`.claude/agents/*.md`) names its tools and carries HOOK, and the
project settings carry it too, for every Bash call: a call whose hook input
names an `agent_id` (a helper's) and whose command runs `gh`, or names `git`
with `commit` or `push`, is refused (exit 2); a hook that fails refuses too.
The main session's calls go through.

DS-3: secret-shaped files are never read: the project settings deny reading
each of DENY's patterns, and no such file is tracked but the ones TRACKED
names, each with why.

    python3 tools/helpers_check.py          # check (the Gates workflow)
    python3 tools/helpers_check.py write    # write HOOK and DENY into the files
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HOOK = (
    "python3 -c \"import json,re,sys;d=json.load(sys.stdin);c=str((d.get('tool_input') or {}).get('command',''));"
    "b=bool(d.get('agent_id')) and bool(re.search(r'(?<![\\w.-])gh(?![\\w.-])',c) or (re.search(r'(?<![\\w.-])git(?![\\w.-])',c) "
    "and re.search(r'(?<![\\w-])(?:commit|push)(?![\\w-])',c)));"
    "b and sys.stderr.write('Refused for a helper: git commit, git push and gh are the main session alone (DS-2, DL430). Leave it for the main session.\\n');"
    "sys.exit(2 if b else 0)\" || exit 2"
)
DENY = [
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/*.key)",
    "Read(**/*.pem)",
    "Read(**/*.jks)",
    "Read(**/*.keystore)",
    "Read(**/*.p12)",
    "Read(**/credentials*.json)",
]
# (Each again from the filesystem's root: `**/` is read from where the session starts, so a file outside it, a
# download in the scratchpad say, needs its own. Observed November 3: a `.key` there was read until these.)
DENY += [rule.replace("Read(**/", "Read(//**/") for rule in DENY]
SECRET_SHAPED = re.compile(r"(?:^|/)\.env(?:\.[^/]*)?$|\.(?:key|pem|jks|keystore|p12)$|(?:^|/)credentials[^/]*\.json$")
# The secret-shaped files tracked on purpose, each with why.
TRACKED = {
    "android/keys/testing.keystore": "signs test builds only, never a store build; its password is in the build file (android/keys/README.md)",
}


def settings(hook: str = HOOK) -> dict:
    return {
        "permissions": {"deny": DENY},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": hook}]}]},
    }


def agent_hooks(hook: str = HOOK) -> str:
    """The `hooks:` block an agent file's front matter carries."""
    return f'hooks:\n  PreToolUse:\n    - matcher: "Bash"\n      hooks:\n        - type: command\n          command: {json.dumps(hook)}\n'


def front_matter(text: str) -> str:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return ""
    return text[4 : 4 + text[4:].index("\n---\n") + 1]


def problems(root: Path, tracked: list[str]) -> list[str]:
    out = []
    path = root / ".claude/settings.json"
    try:
        given = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        given = None
    if given != settings():
        out.append(".claude/settings.json: not the safeguards' settings (python3 tools/helpers_check.py write)")
    agents = sorted((root / ".claude/agents").glob("*.md"))
    if not agents:
        out.append(".claude/agents: no agent files")
    for agent in agents:
        head = front_matter(agent.read_text(encoding="utf-8"))
        rel = agent.relative_to(root)
        if not re.search(r"(?m)^tools:\s*\S", head):
            out.append(f"{rel}: no tools list (DS-2)")
        if agent_hooks() not in head:
            out.append(f"{rel}: not the safeguards' hook (python3 tools/helpers_check.py write)")
    for name in tracked:
        if SECRET_SHAPED.search(name) and name not in TRACKED:
            out.append(f"{name}: a secret-shaped file is tracked (DS-3)")
    return out


def write(root: Path) -> None:
    (root / ".claude/settings.json").write_text(json.dumps(settings(), indent=2) + "\n", encoding="utf-8")
    for agent in sorted((root / ".claude/agents").glob("*.md")):
        text = agent.read_text(encoding="utf-8")
        head = front_matter(text)
        kept = re.sub(r"(?ms)^hooks:\n(?:[ ]+.*\n)*", "", head)
        agent.write_text("---\n" + kept + agent_hooks() + text[4 + len(head) :], encoding="utf-8")


def main() -> int:
    if sys.argv[1:] == ["write"]:
        write(ROOT)
        return 0
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    found = problems(ROOT, tracked)
    for p in found:
        print(f"::error::{p}")
    print(f"helpers_check: {'nothing found' if not found else f'{len(found)} found'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

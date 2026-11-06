"""Fail-closed GitHub Gates evidence for an exact release commit."""
from __future__ import annotations

import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

WORKFLOW = ".github/workflows/gates.yml"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def evaluate_runs(runs: list[dict], sha: str) -> str | None:
    if not SHA_RE.fullmatch(sha):
        return "Gates refused: release commit is not a full SHA."
    matching = [r for r in runs if isinstance(r, dict)
                and r.get("head_sha") == sha and r.get("path") == WORKFLOW]
    if any(r.get("status") != "completed" for r in matching):
        return "Gates refused: a run for the release commit is not completed."
    if not matching:
        return "Gates refused: no completed Gates run exists for the release commit."
    newest = max(matching, key=lambda r: int(r.get("id", 0)))
    if newest.get("conclusion") != "success":
        return "Gates refused: the newest completed Gates run did not succeed."
    return None


def fetch_runs(repository: str, sha: str) -> list[dict]:
    if repository not in ("egadgetboy/tapioca-apps", "egadgetboy/tapioca-server"):
        raise ValueError("unexpected repository")
    if not SHA_RE.fullmatch(sha):
        raise ValueError("release commit must be a full SHA")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GitHub API token missing")
    url = (f"https://api.github.com/repos/{repository}/actions/workflows/"
           f"gates.yml/runs?head_sha={sha}&per_page=100&page=")
    runs: list[dict] = []
    for page in range(1, 11):
        request = Request(url + str(page),
                          headers={"Authorization": f"Bearer {token}",
                                   "Accept": "application/vnd.github+json",
                                   "X-GitHub-Api-Version": "2022-11-28"})
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        batch = payload.get("workflow_runs")
        if not isinstance(batch, list):
            raise ValueError("malformed GitHub workflow response")
        runs.extend(batch)
        if len(batch) < 100:
            return runs
    raise ValueError("Gates history exceeds the supported query window")


def require_success(repository: str, sha: str) -> str | None:
    try:
        return evaluate_runs(fetch_runs(repository, sha), sha)
    except (OSError, ValueError, TypeError, KeyError, TimeoutError):
        return "Gates refused: GitHub evidence is unavailable or invalid."

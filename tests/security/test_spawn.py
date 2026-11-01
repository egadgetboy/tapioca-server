"""Every program tapiOca starts goes through one function, app/spawn.py's start (MED-FFMPEG-01, the security suite's
slice 2): FFmpeg is started with no proxy in its environment, so no proxy ever sees what it reads (Plex's address,
its token in it, among them), and the census knows each place that starts one."""

from __future__ import annotations

import asyncio
import json
import sys

from app import spawn

from . import inventory

PROXIES = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


def test_a_program_started_has_no_proxy_in_its_environment(monkeypatch):
    for name in PROXIES:
        monkeypatch.setenv(name, "http://proxy.example:3128")
    monkeypatch.setenv("TAPIOCA_KEPT", "yes")

    async def environment() -> dict[str, str]:
        proc = await spawn.start(
            sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))",
            stdout=asyncio.subprocess.PIPE,
        )  # fmt: skip
        out, _ = await proc.communicate()
        return json.loads(out)

    seen = asyncio.run(environment())
    assert not [name for name in seen if name in PROXIES]
    assert seen["TAPIOCA_KEPT"] == "yes" and seen["PATH"], "the rest of its environment kept"


def test_only_spawn_starts_a_program_itself():
    starting = {str(site) for site in inventory.spawn_sites() if site.call != "spawn.start"}
    assert starting == {
        "app/spawn.py:start asyncio.create_subprocess_exec",
        "app/cleanup.py:_idle_disk subprocess.run",
    }, starting

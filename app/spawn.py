"""Every program tapiOca starts (FFmpeg and ffprobe), through one function (MED-FFMPEG-01, the security suite's
slice 2): started with no proxy in its environment, so no proxy ever sees what FFmpeg reads (Plex's address, with
its token, among them). The security suite's census knows each place that calls it."""

from __future__ import annotations

import asyncio
import os
from typing import Any

# (FFmpeg's http reads http_proxy; the rest are the other names a proxy goes by.)
_PROXIES = frozenset({"http_proxy", "https_proxy", "all_proxy", "ftp_proxy"})


def _environment() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name.lower() not in _PROXIES}


def unwhitelisted(args: tuple[str, ...]) -> str | None:
    """The first input FFmpeg is handed without whitelists of its own, if any: each `-i` but a lavfi graph needs a
    protocol whitelist, and a format whitelist unless its format is given (`-f`), among its own options."""
    after = 0
    for at, arg in enumerate(args):
        if arg != "-i":
            continue
        own = args[after:at]
        forced = own[own.index("-f") + 1] if "-f" in own[:-1] else ""
        if forced != "lavfi" and not (
            "-protocol_whitelist" in own and ("-format_whitelist" in own or forced)
        ):
            return args[at + 1] if at + 1 < len(args) else "(none)"
        after = at + 2
    return None


async def start(*args: str, **options: Any) -> asyncio.subprocess.Process:
    """asyncio.create_subprocess_exec, with the environment less any proxy; enforced, never with an input
    without its whitelists (MED-FFMPEG-01)."""
    # (mediainput starts FFmpeg through here: imported at the call, not the top.)
    from . import mediainput

    if mediainput.ENFORCED and (bare := unwhitelisted(args)):
        raise ValueError(f"An FFmpeg input without its whitelists: {bare}")
    return await asyncio.create_subprocess_exec(*args, env=_environment(), **options)

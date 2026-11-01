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


async def start(*args: str, **options: Any) -> asyncio.subprocess.Process:
    """asyncio.create_subprocess_exec, with the environment less any proxy."""
    return await asyncio.create_subprocess_exec(*args, env=_environment(), **options)

"""What the FFmpeg tapiOca runs can do, checked once as it starts: tone mapping HDR, drawing subtitles, and what a
Media read may open (mediainput). Each switches its own feature off, with a warning, when FFmpeg can't do it."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import mediainput, subtitles
from .config import Settings
from .ffmpeg import subtitles_problem, tone_mapping_problem

log = logging.getLogger(__name__)


async def check(ctx: Any, settings: Settings) -> None:
    """Sets ctx.tone_mapping and ctx.subtitling, and checks a Media read's allow-list (report-only)."""
    problem = await tone_mapping_problem(settings)
    ctx.tone_mapping = problem is None
    if problem:
        log.warning(
            "This ffmpeg can't tone-map HDR to SDR, so HDR programs will look washed out (%s)",
            problem,
        )
    await asyncio.to_thread(subtitles.tidy, settings.data_dir)
    problem = await subtitles_problem(settings, settings.data_dir / subtitles.FOLDER)
    ctx.subtitling = problem is None
    if problem:
        log.warning(
            "tapiOca can't draw subtitles, so programs will play without them (%s)",
            problem,
        )
    await mediainput.check_at_start(settings.ffmpeg_path)

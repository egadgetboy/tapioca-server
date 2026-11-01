"""What FFmpeg can do, checked once as tapiOca starts (app/ffmpegstart.py): tone mapping, subtitles and what a Media
read may open. Each switches its own feature off with a warning when FFmpeg can't do it; moved unchanged out of
app/main.py's lifespan, which may only shrink."""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app import ffmpegstart
from app.config import Settings

SMALL = Settings(plex_url="", plex_token="", video_width=640, video_height=360)
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no FFmpeg here")


@needs_ffmpeg
def test_a_working_ffmpeg_turns_tone_mapping_and_subtitles_on(tmp_path):
    ctx = SimpleNamespace(tone_mapping=None, subtitling=None)
    asyncio.run(ffmpegstart.check(ctx, replace(SMALL, data_dir=tmp_path)))
    assert ctx.tone_mapping is True and ctx.subtitling is True


def test_an_ffmpeg_that_cant_turns_them_off_and_says_why(tmp_path, caplog):
    ctx = SimpleNamespace(tone_mapping=None, subtitling=None)
    broken = replace(SMALL, data_dir=tmp_path, ffmpeg_path=str(tmp_path / "no-ffmpeg"))
    with caplog.at_level(logging.WARNING):
        asyncio.run(ffmpegstart.check(ctx, broken))
    assert ctx.tone_mapping is False and ctx.subtitling is False
    said = caplog.text
    assert "HDR programs will look washed out" in said
    assert "tapiOca can't draw subtitles" in said
    assert "Media" in said

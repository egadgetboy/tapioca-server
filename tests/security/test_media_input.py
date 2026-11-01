"""A Media read opens only a video container, by its own name only (MED-FFMPEG-01, the security suite's slice 2:
the apps repository's docs/threat-models/security-suite-2.md). An ffconcat list named movie.mkv plays a file
beside it, another title's, a way around a person's limits; an HLS or DASH list, a picture reader or a device
input opens what it names. So a Media read takes an allow-list of video containers, failing closed, its
protocols by its address, mov's references off (by default, pinned), its memory bounded and, over http, no
redirect. Report-only until the release's soak: a read whose container isn't on the list is logged, once, and
read all the same."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from app import ffmpeg as ff
from app import folderscan, mediainput
from app.config import Settings

SMALL = Settings(plex_url="", plex_token="", video_width=640, video_height=360)
needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="no FFmpeg here"
)


def _video(path: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x90:r=10:d=1",
            "-c:v",
            "mpeg4",
            str(path),
        ],
        check=True,
    )
    return path


def _concat(folder: Path, beside: Path) -> Path:
    """An ffconcat list, named as a movie, naming the file beside it."""
    listed = folder / "movie.mkv"
    listed.write_text(f"ffconcat version 1.0\nfile '{beside.name}'\n")
    return listed


@pytest.mark.parametrize("name", sorted(mediainput.NEVER))
def test_a_demuxer_that_opens_what_it_names_is_never_allowed(name):
    assert name not in mediainput.ALLOWED
    assert not mediainput.allowed(name)


def test_every_video_container_on_the_list_is_read():
    for name in (
        "matroska,webm",
        "mov,mp4,m4a,3gp,3g2,mj2",
        "avi",
        "mpegts",
        "mpeg",
        "asf",
        "flv",
        "ogg",
        "m4v",
    ):
        assert mediainput.allowed(name), name


def test_a_container_partly_off_the_list_isnt_read():
    assert not mediainput.allowed("matroska,concat")
    assert not mediainput.allowed("")


@pytest.mark.parametrize(
    "source, protocols",
    [
        ("/media/Movies/A/a.mkv", "file"),
        ("http://192.168.1.20:32400/library/parts/1/file.mkv?X-Plex-Token=t", "http,tcp"),
        ("https://plex.example.net:32400/library/parts/1/file.mkv?X-Plex-Token=t", "https,tls,tcp"),
    ],
)
def test_a_media_reads_options(source, protocols):
    options = mediainput.options(source)
    said = dict(zip(options[::2], options[1::2], strict=True))
    assert said["-format_whitelist"] == ",".join(mediainput.ALLOWED)
    assert said["-protocol_whitelist"] == protocols
    assert "-enable_drefs" not in said, "mov's alone: see test_movs_references_are_off_by_default"
    assert said["-max_pixels"] == str(mediainput.MAX_PIXELS)
    assert said["-max_alloc"] == str(mediainput.MAX_ALLOC)
    if source.startswith("http"):
        assert said["-max_redirects"] == "0"
    else:
        assert "-max_redirects" not in said


@needs_ffmpeg
def test_with_its_options_an_ffconcat_list_named_as_a_movie_isnt_read(tmp_path):
    other = _video(tmp_path / "other.mp4")
    listed = _concat(tmp_path, other)
    opened = subprocess.run(["ffprobe", "-v", "error", str(listed)], capture_output=True, text=True)
    assert opened.returncode == 0, "today's read opens the file it names"
    refused = subprocess.run(
        ["ffprobe", "-v", "error", *mediainput.options(str(listed)), str(listed)],
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert mediainput.refused(refused.stderr), refused.stderr


@needs_ffmpeg
def test_with_its_options_a_real_video_is_read(tmp_path):
    for name in ("film.mkv", "film.mp4", "film.avi", "film.ts"):
        video = _video(tmp_path / name)
        read = subprocess.run(
            ["ffprobe", "-v", "error", *mediainput.options(str(video)), str(video)],
            capture_output=True,
            text=True,
        )
        assert read.returncode == 0, (name, read.stderr)


@needs_ffmpeg
def test_with_its_options_ffmpeg_plays_a_real_video(tmp_path):
    # (FFmpeg itself, not only ffprobe, refuses a demuxer's option the file's demuxer doesn't have.)
    for name in ("film.mkv", "film.mp4", "film.avi", "film.ts"):
        video = _video(tmp_path / name)
        played = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                *mediainput.options(str(video)),
                "-i",
                str(video),
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        assert played.returncode == 0, (name, played.stderr)


@needs_ffmpeg
def test_movs_references_are_off_by_default():
    # (Pinned here rather than given: the option is mov's alone, and FFmpeg refuses it for any other file.)
    said = subprocess.run(
        ["ffmpeg", "-hide_banner", "-h", "demuxer=mov"], capture_output=True, text=True
    ).stdout
    line = next(line for line in said.splitlines() if line.strip().startswith("-enable_drefs"))
    assert "(default false)" in line, line


@needs_ffmpeg
def test_report_only_a_probe_of_an_ffconcat_list_is_logged_once_and_read(
    tmp_path, caplog, monkeypatch
):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    listed = _concat(tmp_path, _video(tmp_path / "other.mp4"))
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        first = asyncio.run(ff.probe(SMALL, str(listed)))
        asyncio.run(ff.probe(SMALL, str(listed)))
    assert first.ok, "report-only: read as before"
    said = [r.getMessage() for r in caplog.records if "concat" in r.getMessage()]
    assert len(said) == 1, said
    assert listed.name in said[0], "the soak's report names the file"


def test_a_plex_address_is_logged_without_its_token(caplog, monkeypatch):
    monkeypatch.setattr(mediainput, "_said", set())
    source = "http://192.168.1.20:32400/library/parts/1/file.mkv?X-Plex-Token=secret"
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        mediainput.note(ff.redact(source), "concat")
    assert "concat" in caplog.text
    assert "secret" not in caplog.text


@needs_ffmpeg
def test_report_only_a_probe_of_a_real_video_says_nothing(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        assert asyncio.run(ff.probe(SMALL, str(_video(tmp_path / "film.mkv")))).ok
    assert not [r for r in caplog.records if r.name == "app.mediainput"]


@needs_ffmpeg
def test_an_uploads_probe_keeps_its_own_options(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        asyncio.run(
            ff.probe(SMALL, str(_video(tmp_path / "bumper.mp4")), options=ff.UPLOADED_VIDEO)
        )
    assert not [r for r in caplog.records if r.name == "app.mediainput"]


@needs_ffmpeg
def test_report_only_a_folder_scan_of_an_ffconcat_list_is_logged_once_and_read(
    tmp_path, caplog, monkeypatch
):
    # (A folder's Media is read by the folder scan's own ffprobe, not by probe.)
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    listed = _concat(tmp_path, _video(tmp_path / "other.mp4"))
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        first = asyncio.run(folderscan.read_file("ffprobe", str(listed)))
        asyncio.run(folderscan.read_file("ffprobe", str(listed)))
    assert first["ok"], "report-only: read as before"
    said = [r.getMessage() for r in caplog.records if "concat" in r.getMessage()]
    assert len(said) == 1, said

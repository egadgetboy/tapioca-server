"""What FFmpeg writes lands only in tapiOca's own places, named by tapiOca, whatever a Media file is called (MED-02,
the security suite's slice 2: the apps repository's docs/threat-models/security-suite-2.md). Each place that has
FFmpeg read a file and write something is run, with real FFmpeg, on a file whose folder and name hold a quote, a
semicolon, a command, a newline and a filter's own punctuation; then nothing new is anywhere but the data folder,
and nothing there carries any part of the name. (Enforced and report-only alike: a name is a name either way.)"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app import ffmpeg as ff
from app import folderart, mediainput, subtitles
from app.config import Settings

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="no FFmpeg here"
)

SMALL = Settings(plex_url="", plex_token="", video_width=320, video_height=180)
FOLDER = "Movies'; touch PWNED; '"
NAME = "Film $(touch PWNED) [x],movie=evil;\n'1999'.mkv"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def _hostile_film(media: Path) -> Path:
    """A film with a text subtitle track and a cover inside, and a subtitle file beside it, all named as above."""
    folder = media / FOLDER
    folder.mkdir(parents=True)
    plain, cover, cues = media / "plain.mkv", media / "cover.png", media / "cues.srt"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=160x90:r=10:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-c:v", "mpeg4", "-c:a", "aac", str(plain))  # fmt: skip
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", str(cover))
    cues.write_text("1\n00:00:00,500 --> 00:00:01,500\nWWWW\n", encoding="utf-8")
    film = folder / NAME
    _ffmpeg("-i", str(plain), "-i", str(cues), "-i", str(cover), "-map", "0", "-map", "1", "-map", "2",
            "-c", "copy", "-c:s", "srt", "-metadata:s:s:0", "language=eng", "-disposition:v:1", "attached_pic",
            str(film))  # fmt: skip
    shutil.copy(cues, folder / (Path(NAME).stem + ".fr.srt"))
    for made in (plain, cover, cues):
        made.unlink()
    return film


def _everything(*roots: Path) -> set[Path]:
    return {p for root in roots for p in root.rglob("*")}


@pytest.mark.parametrize("enforced", [False, True])
def test_what_ffmpeg_writes_lands_only_in_tapiocas_own_places(tmp_path, monkeypatch, enforced):
    monkeypatch.setattr(mediainput, "ENFORCED", enforced)
    monkeypatch.setattr(mediainput, "FFMPEG_PROBLEM", None)
    data, media, elsewhere = tmp_path / "data", tmp_path / "media", tmp_path / "cwd"
    data.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    film = _hostile_film(media)
    temp = Path(tempfile.gettempdir())
    before, temp_before = _everything(tmp_path), set(temp.iterdir())

    async def each_place() -> None:
        probe = await ff.probe(SMALL, str(film))
        assert probe.ok, probe.error
        for wanted, beside in (
            ("eng", False),
            ("fra", True),
        ):  # (the track inside, then the file beside it)
            choice = await asyncio.to_thread(
                subtitles.for_program, data, "always", wanted, str(film), probe
            )
            assert isinstance(choice, subtitles.Extraction) and choice.sidecar == beside
            assert await subtitles.extract(SMALL, choice)
        picture, _ = await folderart.cover("ffmpeg", data, str(film), 3, "png", 64)
        assert picture.startswith(b"\x89PNG")
        args = ff.program_command(SMALL, str(film), 0.0, 1.0, 0.0, 5.0, 0, "Night Owl")
        played = await asyncio.to_thread(subprocess.run, args, capture_output=True, timeout=60)
        assert played.returncode == 0 and played.stdout, played.stderr[-400:]

    asyncio.run(each_place())
    new = _everything(tmp_path) - before
    assert all(data in p.parents for p in new), sorted(str(p) for p in new if data not in p.parents)
    assert len([p for p in new if p.suffix == ".ass"]) == 2 and [
        p for p in new if p.suffix == ".png"
    ]
    fragments = ("PWNED", "evil", "movie=", "1999", "Film", "'", ";", "$", "\n", "[")
    named = [p for p in new if any(f in p.name for f in fragments)]
    assert not named, named
    assert not [p for p in set(temp.iterdir()) - temp_before if any(f in p.name for f in fragments)]
    assert not list(Path("/").glob("PWNED")) and not os.path.exists(elsewhere / "PWNED")

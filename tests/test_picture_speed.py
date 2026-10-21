"""Fast pictures again (1.43.0; the owner, October 20, 9:15 PM: "We need to
rip all of this out and go back to the way this was handled so well
before"; the plan's DL282, the restore-fast-pictures handoff, part 8a).

1.42's "Pictures that load fast" made each cold picture with tapiOca's own
FFmpeg from Plex's full-size original, up to 8 at once, carried on after
the app had scrolled past, and looked each title's details up on the same 6
library turns a folder's own fetches wait for. Under a fast roll, a folder
then took longer than its 8 seconds and the apps said "Couldn't load this
folder". These hold the line it's back on: Plex resizes, tapiOca keeps
pictures in memory, a picture of a listed title asks Plex nothing but the
picture, nothing is made for a request that's gone, and 1.42's disk cache
is removed once.

Plex here is the stand-in with latency added in front of it (never in
tests/fakeplex.py): a title's details 150 ms, a picture 40 ms, 500 titles of
a folder 250 ms; the full-size original is a real 2000 by 3000 picture.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import plex as plex_module
from app.config import Settings
from app.main import create_app
from app.plex import PlexClient

from .test_media_solid import OddPlex, shared

MINUTE = 60_000
TITLES = 2_000


def original() -> bytes:
    """A real full-size poster, about 1 MB (as Plex keeps one)."""
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc2=s=2000x3000", "-frames:v", "1", "-q:v", "2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip


def big_folder() -> OddPlex:
    fp = OddPlex()
    fp.add_section("2", "Movies", "movie")
    full = original()
    for n in range(TITLES):
        key = str(10_000 + n)
        fp.add_movie(key, f"Movie {n}", f"/m/{n}.mkv", 90 * MINUTE, section="2", genres=["Drama"])
        fp.odd[f"/library/metadata/{key}/thumb"] = httpx.Response(
            200, content=full, headers={"content-type": "image/jpeg"}
        )
        fp.odd[f"/library/metadata/{key}/art"] = httpx.Response(
            200, content=full, headers={"content-type": "image/jpeg"}
        )
    return fp


def slowed(fp: OddPlex) -> httpx.MockTransport:
    async def answer(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/photo/:/transcode" or path.endswith(("/thumb", "/art")) or "/thumb/" in path:
            await asyncio.sleep(0.04)
        elif path.startswith("/library/metadata/") and path.count("/") == 3:
            await asyncio.sleep(0.15)  # (a title's details)
        elif path.startswith("/library/sections/"):
            await asyncio.sleep(0.25)  # (a page of a folder)
        return await fp.answer(request)

    return httpx.MockTransport(answer)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    fp = big_folder()
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data")
    app = create_app(settings, PlexClient("http://plex.test", "token", transport=slowed(fp)))
    app.state.ctx.play_transport = slowed(fp)
    with TestClient(app) as home:
        shared(home)
        assert home.get("/api/internal/libraries/2?size=200").status_code == 200  # (browsed once)
        home.plex = fp
        yield home


def picture(home: TestClient, key: str, n: int) -> httpx.Response:
    """As 0.12.0 asks: WebP, a poster 240 wide, every tenth a backdrop 1920 wide."""
    if n % 10 == 0:
        return home.get(f"/api/internal/art/{key}?kind=backdrop&w=1920&format=webp")
    return home.get(f"/api/internal/art/{key}?kind=poster&w=240&format=webp")


def roll(home: TestClient, keys: list[str]) -> tuple[list[int], httpx.Response, float]:
    """The pictures of a fast roll all at once, and 50 ms in, the folder's
    first page with its kept list forgotten: (the pictures' statuses, the
    folder's answer, its seconds)."""
    home.app.state.ctx.catalog._wholes.clear()  # (its kept list forgotten)
    with concurrent.futures.ThreadPoolExecutor(64) as pool:
        asked = [pool.submit(picture, home, k, n) for n, k in enumerate(keys)]
        time.sleep(0.05)
        began = time.monotonic()
        page = home.get("/api/internal/libraries/2?start=0&size=50")
        took = time.monotonic() - began
        return [f.result().status_code for f in asked], page, took


def test_a_folder_opens_while_a_fast_rolls_pictures_are_made(folder):
    for run in range(5):
        keys = [str(10_000 + run * 300 + i) for i in range(300)]
        statuses, page, took = roll(folder, keys)
        assert page.status_code == 200, (run, page.text)
        assert took < 2.0, (run, took)
        assert 503 not in statuses, (run, sorted(set(statuses)))


def details_of(requests: list[str], key: str) -> list[str]:
    return [p for p in requests if p == f"/library/metadata/{key}"]


def test_no_picture_asks_plex_for_details_when_its_list_said_enough(folder):
    keys = [str(10_000 + i) for i in range(200)]
    asked = len(folder.plex.requests)
    for k in keys:
        assert folder.get(f"/api/internal/art/{k}?kind=poster&w=320").status_code == 200
    since = folder.plex.requests[asked:]
    assert all(details_of(since, k) == [] for k in keys), [p for p in since if p.count("/") == 3]


def test_a_picture_from_plex_never_starts_ffmpeg(folder, monkeypatch):
    started: list[tuple] = []
    real = asyncio.create_subprocess_exec

    async def counted(*args, **kw):
        started.append(args)
        return await real(*args, **kw)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", counted)
    for i in range(100):
        got = folder.get(f"/api/internal/art/{10_000 + i}?kind=poster&w=480&format=webp")
        assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert started == []


def test_nothing_is_made_for_pictures_after_their_requests_end(folder, monkeypatch):
    """A fast roll's requests, given up 200 ms in (the app scrolled past):
    in the 3 seconds after, no picture is asked of Plex and no FFmpeg runs."""
    started: list[tuple] = []
    real = asyncio.create_subprocess_exec

    async def counted(*args, **kw):
        started.append(args)
        return await real(*args, **kw)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", counted)
    app = folder.app

    async def given_up() -> None:
        transport = httpx.ASGITransport(app=app, client=("192.168.1.50", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            asks = [
                asyncio.ensure_future(
                    c.get(f"/api/internal/art/{10_000 + i}?kind=poster&w=240&format=webp")
                )
                for i in range(300)
            ]
            await asyncio.sleep(0.2)
            for a in asks:
                a.cancel()
            await asyncio.gather(*asks, return_exceptions=True)

    folder.portal.call(given_up)
    asked, began = len(folder.plex.requests), len(started)
    time.sleep(3)
    pictures = [
        p for p in folder.plex.requests[asked:]
        if p == "/photo/:/transcode" or p.endswith(("/thumb", "/art"))
    ]  # fmt: skip
    assert pictures == [] and started[began:] == []


def test_an_app_asking_for_webp_gets_jpeg_and_says_so(folder):
    got = folder.get("/api/internal/art/10001?kind=poster&w=320&format=webp")
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert got.content[:3] == b"\xff\xd8\xff" or got.content.startswith(b"poster")


def test_a_width_between_is_made_at_the_next_of_six(folder):
    asked = len(folder.plex.requests)
    assert folder.get("/api/internal/art/10002?kind=poster&w=240").status_code == 200
    assert folder.get("/api/internal/art/10002?kind=poster&w=320").status_code == 200
    resized = [p for p in folder.plex.requests[asked:] if p == "/photo/:/transcode"]
    assert len(resized) == 1  # (240 is made at 320: one picture, kept once)


# 1.42's disk cache, removed once ------------------------------------------------------------


def old_cache(data: Path) -> Path:
    pictures = data / "cache" / "pictures"
    (pictures / "ab").mkdir(parents=True)
    (pictures / "FORMAT").write_text("2\n")
    (pictures / "index.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    (pictures / "ab" / "abcdef.webp").write_bytes(b"x" * 4096)
    (data / "cache" / ".pictures-gone-x").mkdir()
    (data / "cache" / ".pictures-gone-x" / "f").write_bytes(b"y")
    return pictures


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_1_42s_picture_cache_is_removed_once_and_nothing_else(tmp_path, monkeypatch):
    from app import cleanup

    data = tmp_path / "data"
    (data / "logos").mkdir(parents=True)
    (data / "logos" / "5.png").write_bytes(b"logo")
    (data / "backups").mkdir()
    (data / "backups" / "before-1.42.0-2026-10-19.db").write_bytes(b"backup")
    old_cache(data)
    kept = {"logos": snapshot(data / "logos"), "backups": snapshot(data / "backups")}
    monkeypatch.setattr(cleanup, "DELAY_S", 0)
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=data)
    app = create_app(
        settings, PlexClient("http://plex.test", "token", transport=OddPlex().transport())
    )
    with TestClient(app):
        db = data / "stationplay.db"
        end = time.monotonic() + 10
        while (data / "cache").exists() and time.monotonic() < end:
            time.sleep(0.05)
        assert not (data / "cache").exists()
        assert kept == {"logos": snapshot(data / "logos"), "backups": snapshot(data / "backups")}
        assert db.exists()


def test_the_clean_up_never_follows_a_link_and_does_nothing_with_nothing_there(tmp_path):
    from app import cleanup

    data = tmp_path / "data"
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "ab").mkdir(parents=True)
    (elsewhere / "ab" / "keep.webp").write_bytes(b"theirs")
    (data / "cache").mkdir(parents=True)
    (data / "cache" / "pictures").symlink_to(elsewhere, target_is_directory=True)
    cleanup.old_picture_cache(data)
    assert not (data / "cache" / "pictures").exists() and not os.path.islink(
        data / "cache" / "pictures"
    )
    assert (elsewhere / "ab" / "keep.webp").read_bytes() == b"theirs"
    # (A link inside the folder: removed as a link, its target untouched.)
    pictures = old_cache(data)
    (pictures / "link").symlink_to(elsewhere, target_is_directory=True)
    cleanup.old_picture_cache(data)
    assert (elsewhere / "ab" / "keep.webp").read_bytes() == b"theirs"
    assert not (data / "cache").exists()
    # (Nothing there: nothing done, nothing made.)
    cleanup.old_picture_cache(data)
    assert not (data / "cache").exists() and sorted(p.name for p in data.iterdir()) == []


def test_a_cache_that_cant_be_moved_is_emptied_in_place(tmp_path, monkeypatch, caplog):
    from app import cleanup

    caplog.set_level(logging.INFO)
    data = tmp_path / "data"
    pictures = old_cache(data)
    real = os.rename

    def own_mount(src, dst, *a, **kw):
        if Path(src) == pictures:
            raise OSError(18, "Invalid cross-device link")
        return real(src, dst, *a, **kw)

    monkeypatch.setattr(cleanup.os, "rename", own_mount)
    cleanup.old_picture_cache(data)
    assert pictures.is_dir() and list(pictures.iterdir()) == []
    assert "removed" in caplog.text and "abcdef" not in caplog.text

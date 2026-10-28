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
import contextlib
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
        fp.episodes[key]["art"] = f"/library/metadata/{key}/art/1"  # (a backdrop too, made at 1920)
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
        # (The audit: no 503 alone would pass a server shedding the load with 404s.)
        assert set(statuses) == {200}, (run, sorted(set(statuses)))


def details_of(requests: list[str], key: str) -> list[str]:
    return [p for p in requests if p == f"/library/metadata/{key}"]


def test_the_top_of_a_folder_over_the_where_table_still_asks_no_details(tmp_path, monkeypatch):
    # (The audit's P1: facts were kept for 40,000 titles but where each is for
    # 5,000, so in a 6,000-title folder the top of the list, where a roll
    # starts, had been forgotten and each poster looked its title up.)
    from app import ondemand

    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    fp = OddPlex()
    fp.add_section("2", "Movies", "movie")
    many = ondemand.WHERE_KEPT + 1_000
    for n in range(many):
        fp.add_movie(str(10_000 + n), f"Movie {n:05}", f"/m/{n}.mkv", 90 * MINUTE, section="2")
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data")
    with TestClient(
        create_app(settings, PlexClient("http://plex.test", "token", transport=fp.transport()))
    ) as home:
        shared(home)
        first = home.get("/api/internal/libraries/2?start=0&size=50")
        assert first.status_code == 200
        keys = [i["key"] for i in first.json()["items"]]
        assert len(keys) == 50
        asked = len(fp.requests)
        fp.odd["/photo/:/transcode"] = httpx.Response(
            200, content=b"\xff\xd8poster", headers={"content-type": "image/jpeg"}
        )
        for k in keys:
            # (The re-check's audit: 404 was let pass, so a wrong library refused them all unseen.)
            assert home.get(f"/api/internal/art/{k}?kind=poster&w=320").status_code == 200, k
        since = fp.requests[asked:]
        assert all(details_of(since, k) == [] for k in keys), [
            p for p in since if p.count("/") == 3
        ][:5]


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
    # (The audit: "couldn't all be removed" contains "removed" too.)
    assert (
        "was removed" in caplog.text
        and "couldn't" not in caplog.text
        and "abcdef" not in caplog.text
    )


def test_a_linked_data_cache_is_cleaned_through_its_link_and_says_so_truly(tmp_path, caplog):
    # (The audit's P1: with data/cache a link, the folder was renamed aside in
    # the link's target, never deleted, and the log said it was freed.)
    from app import cleanup

    caplog.set_level(logging.INFO)
    data = tmp_path / "data"
    target = tmp_path / "fast-disk" / "tapioca-cache"
    old_cache(target.parent / "staged")
    (target.parent).mkdir(exist_ok=True)
    os.rename(target.parent / "staged" / "cache", target)
    (target / "theirs.txt").write_text("keep")
    data.mkdir()
    (data / "cache").symlink_to(target, target_is_directory=True)
    cleanup.old_picture_cache(data)
    assert sorted(p.name for p in target.iterdir()) == ["theirs.txt"], (
        "nothing of 1.42's left, nothing else touched"
    )
    assert os.path.islink(data / "cache"), "the link stays"
    assert "was removed" in caplog.text and "couldn't" not in caplog.text


def test_a_pictures_folder_that_isnt_1_42s_and_the_database_are_never_touched(tmp_path, caplog):
    from app import cleanup

    caplog.set_level(logging.INFO)
    data = tmp_path / "data"
    (data / "cache" / "pictures" / "family").mkdir(parents=True)
    (data / "cache" / "pictures" / "family" / "beach.jpg").write_bytes(b"theirs")
    (data / "stationplay.db").write_bytes(b"SQLite format 3\x00" + bytes(range(256)))
    before = snapshot(data)
    cleanup.old_picture_cache(data)
    assert snapshot(data) == before, (
        "no FORMAT and no index.db: not 1.42's; and the database byte for byte"
    )
    assert "isn't 1.42's" in caplog.text and "beach" not in caplog.text


def test_a_delete_that_fails_says_where_to_delete(tmp_path, monkeypatch, caplog):
    from app import cleanup

    caplog.set_level(logging.INFO)
    data = tmp_path / "data"
    old_cache(data)
    real = cleanup.shutil.rmtree

    def refused(path, *a, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(cleanup.shutil, "rmtree", refused)
    cleanup.old_picture_cache(data)
    monkeypatch.setattr(cleanup.shutil, "rmtree", real)
    # (The re-check: never "delete data/cache", which may be a link to a disk holding the person's own files.)
    assert (
        "couldn't all be removed: delete data/cache/pictures and any data/cache/.pictures-gone-* folders"
        in caplog.text
    )
    assert "was removed" not in caplog.text


def test_two_starts_at_once_end_clean_and_say_nothing_failed(tmp_path, caplog):
    import threading

    from app import cleanup

    caplog.set_level(logging.INFO)
    for n in range(10):
        data = tmp_path / f"data{n}"
        pictures = old_cache(data)
        for i in range(200):
            (pictures / "ab" / f"{i}.webp").write_bytes(b"x")
        both = [threading.Thread(target=cleanup.old_picture_cache, args=(data,)) for _ in range(2)]
        for t in both:
            t.start()
        for t in both:
            t.join()
        assert not (data / "cache").exists(), n
    assert "couldn't" not in caplog.text


def test_the_clean_up_runs_at_idle_disk_and_lowest_cpu_priority(tmp_path, monkeypatch):
    import threading

    from app import cleanup

    asked: list[list[str]] = []
    niced: list[tuple] = []
    monkeypatch.setattr(cleanup, "DELAY_S", 0)
    monkeypatch.setattr(cleanup.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cleanup.subprocess, "run", lambda args, **kw: asked.append(args))
    monkeypatch.setattr(cleanup.os, "setpriority", lambda *a: niced.append(a))
    where: list[str] = []
    monkeypatch.setattr(
        cleanup, "old_picture_cache", lambda d: where.append(threading.current_thread().name)
    )
    asyncio.run(cleanup.later(tmp_path / "data"))
    assert where == ["old-picture-cache"], "off the event loop, in its own thread"
    assert len(asked) == 1 and asked[0][:4] == ["/usr/bin/ionice", "-c", "3", "-p"], asked
    assert niced and niced[0][2] == 19
    assert asked[0][4] == str(niced[0][1]), "the clean-up's own thread"


def test_the_load_tool_measures_kept_and_cold_apart_and_from_when_each_is_sent(folder):
    # (The audit's P1: it warmed the kept pictures at 320 and measured them at
    # 480, so they were cold; cold and kept keys overlapped; and the time a
    # request waited for one of the 64 connections was counted as the server's.)
    import tools.picture_load as load

    seen: list[str] = []
    flying = {"now": 0, "most": 0}

    class Watched(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.inner = httpx.ASGITransport(app=folder.app)

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if "/art/" in request.url.path:
                seen.append(f"{request.url.path}?{request.url.query.decode()}")
                flying["now"] += 1
                flying["most"] = max(flying["most"], flying["now"])
            try:
                return await self.inner.handle_async_request(request)
            finally:
                if "/art/" in request.url.path:
                    flying["now"] -= 1

    async def go() -> None:
        await load.run("http://testserver", "", "2", 400, 0, transport=Watched())

    asyncio.run(go())
    widths = {q.split("w=")[1] for q in seen}
    assert widths == {str(load.WIDTH)}, widths
    # (The re-check's audit: half the roll is given up on, so the split is by the warm-up's own count.)
    kept = 400 // 4
    warm = [q.split("?")[0] for q in seen[:kept]]
    rolled = [q.split("?")[0] for q in seen[kept:]]
    assert len(set(warm)) == kept and len(set(rolled)) == len(rolled), "each asked once in the roll"
    cold = [k for k in rolled if k not in set(warm)]
    assert cold and len(cold) < len(rolled), "kept and cold, apart"
    assert len(rolled) > 100, len(rolled)
    assert flying["most"] <= load.AT_ONCE


def ondemand_turns() -> int:
    from app import ondemand

    return ondemand.PICTURES_AT_ONCE


def test_a_picture_given_up_on_is_never_asked_of_plex_under_a_real_server(tmp_path, monkeypatch):
    # (The audit: httpx's ASGITransport cancels a handler when its client goes;
    # uvicorn doesn't, so under it every scrolled-past poster still took a
    # picture turn and asked Plex.)
    import socket
    import threading

    import uvicorn

    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    fp = big_folder()
    made: list[str] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/photo/:/transcode":
            made.append(request.url.params.get("url", ""))
            await asyncio.sleep(1.0)  # (a slow resize: every app has gone before the next turn)
        return await fp.answer(request)

    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data")
    app = create_app(
        settings, PlexClient("http://plex.test", "token", transport=httpx.MockTransport(answer))
    )
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    running = threading.Thread(target=server.run, daemon=True)
    running.start()
    try:
        end = time.monotonic() + 10
        while not server.started and time.monotonic() < end:
            time.sleep(0.05)
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base, headers={"X-Tapioca-Page": "1"}) as home:
            shared(home)
            assert home.get("/api/internal/libraries/2?size=200").status_code == 200

        def given_up(n: int) -> None:
            with (
                contextlib.suppress(httpx.HTTPError),
                httpx.Client(base_url=base, timeout=0.2) as c,
            ):
                c.get(f"/api/internal/art/{10_000 + n}?kind=poster&w=320")

        with concurrent.futures.ThreadPoolExecutor(40) as pool:
            list(pool.map(given_up, range(40)))
        time.sleep(6)
        # (Only those that had a turn before their app went: one round of the turns, and a few to spare.)
        assert len(made) <= ondemand_turns() + 4, len(made)
    finally:
        server.should_exit = True
        running.join(10)


def test_leftovers_are_swept_even_beside_a_pictures_folder_that_isnt_1_42s(tmp_path, caplog):
    # (The re-check: the early return for someone else's folder skipped the sweep.)
    from app import cleanup

    caplog.set_level(logging.INFO)
    data = tmp_path / "data"
    (data / "cache" / "pictures").mkdir(parents=True)
    (data / "cache" / "pictures" / "theirs.jpg").write_bytes(b"theirs")  # (someone else's, not empty)
    (data / "cache" / ".pictures-gone-1-2" / "ab").mkdir(parents=True)
    (data / "cache" / ".pictures-gone-1-2" / "ab" / "x.webp").write_bytes(b"x")
    cleanup.old_picture_cache(data)
    assert sorted(p.name for p in (data / "cache").iterdir()) == ["pictures"]
    assert "isn't 1.42's" in caplog.text


def test_a_pictures_link_says_its_target_was_left(tmp_path, caplog):
    # (The re-check: removing only the link logged "removed (0 MB freed)" while 1.42's files stayed.)
    from app import cleanup

    caplog.set_level(logging.INFO)
    data = tmp_path / "data"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (data / "cache").mkdir(parents=True)
    (data / "cache" / "pictures").symlink_to(elsewhere, target_is_directory=True)
    cleanup.old_picture_cache(data)
    assert "was a link" in caplog.text and "MB freed" not in caplog.text


def test_an_emptied_mount_is_quiet_after_and_the_marks_go_last(tmp_path, monkeypatch, caplog):
    # (The final audit: an emptied mount warned "isn't 1.42's" at every later start; a delete cut
    # short after the marks went was never tried again; and someone else's folder was named for deleting.)
    from app import cleanup

    caplog.set_level(logging.INFO)
    data = tmp_path / "data"
    pictures = old_cache(data)
    (pictures / "cd").mkdir()
    (pictures / "cd" / "x.webp").write_bytes(b"x")
    real_unlink = Path.unlink
    gone: list[str] = []

    def watched(self, *a, **kw):
        gone.append(self.name)
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(
        cleanup.os, "rename", lambda *a, **kw: (_ for _ in ()).throw(OSError(18, "EXDEV"))
    )
    monkeypatch.setattr(Path, "unlink", watched)
    cleanup.old_picture_cache(data)
    files = [n for n in gone if n in ("FORMAT", "index.db")]
    assert files and gone[-len(files) :] == files, gone
    caplog.clear()
    cleanup.old_picture_cache(data)
    assert "isn't 1.42's" not in caplog.text, "an emptied mount is done, said nothing"
    (pictures / "family").mkdir()
    (data / "cache" / ".pictures-gone-9").mkdir()
    monkeypatch.setattr(cleanup, "_delete_tree", lambda path: False)
    caplog.clear()
    cleanup.old_picture_cache(data)
    assert "delete any data/cache/.pictures-gone-* folders" in caplog.text
    assert "delete data/cache/pictures" not in caplog.text

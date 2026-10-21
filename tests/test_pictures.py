"""Pictures that load fast (the plan's "Pictures that load fast"; app/pictures.py):
the disk cache behind the memory cache, made once, WebP when an app asks,
widths per kind, quality at a measured floor, and changed art never kept."""

from __future__ import annotations

import asyncio
import json
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from app import pictures
from app import plex as plex_module
from app.config import Settings
from app.main import create_app
from app.plex import PlexClient

from .test_media_solid import library, limited, refused, shared



def asked_for_pictures(requests: list[str]) -> list[str]:
    return [p for p in requests if p == "/photo/:/transcode" or "/thumb" in p or "/art/" in p or p.endswith("/art")]


def details_of(key: str, requests: list[str]) -> list[str]:
    return [p for p in requests if p == f"/library/metadata/{key}"]


def server(plex, data_dir):
    """tapiOca on `data_dir`, as it starts again after a restart or an update."""
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=data_dir)
    app = create_app(settings, PlexClient("http://plex.test", "token", transport=plex.transport()))
    app.state.ctx.play_transport = plex.transport()
    return app


def test_after_a_restart_a_picture_comes_from_disk_without_asking_plex(tmp_path, monkeypatch):
    # (Before, pictures were kept in memory only: after every restart or update, each one was
    # fetched from Plex and made again, and its title looked up first.)
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    data = tmp_path / "data"
    with TestClient(server(plex, data)) as home:
        shared(home)
        first = home.get("/api/internal/art/300?kind=poster&w=320")
        assert first.status_code == 200
    asked = len(plex.requests)
    with TestClient(server(plex, data)) as home:  # (started again: nothing in memory)
        again = home.get("/api/internal/art/300?kind=poster&w=320")
        assert again.status_code == 200
        assert again.content == first.content and again.headers["etag"] == first.headers["etag"]
        since = plex.requests[asked:]
        assert asked_for_pictures(since) == [], since
        assert details_of("300", since) == [], "no details asked either, for a viewer without limits"


def test_a_title_someone_may_not_see_is_refused_even_with_its_picture_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    data = tmp_path / "data"
    app = server(plex, data)
    admin, kit, lee = limited(app, plex)
    try:
        assert admin.get("/api/internal/art/301").status_code == 200  # (kept, on disk)
        assert admin.get("/api/internal/art/300").status_code == 200
    finally:
        admin.__exit__(None, None, None)
    again = server(plex, data)
    with TestClient(again) as phone:
        refused(phone.get("/api/internal/art/301", headers=kit), 404)  # (Kid doesn't allow it)
        refused(phone.get("/api/internal/art/300", headers=lee), 404)  # (TV only)


# Made as an app asks: WebP, JPEG, made once ----------------------------------------------------


def real_picture(width: int, height: int, seed: int = 1) -> bytes:
    """A picture with gradients and grain, as a poster or backdrop has (PNG)."""
    made = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", f"gradients=s={width}x{height}:c0=0x203060:c1=0xd08040:c2=0x40a070:n=3:seed={seed}",
         "-vf", "noise=alls=6:allf=u,drawbox=x=iw/4:y=ih/3:w=iw/2:h=ih/6:color=white@0.8:t=fill",
         "-frames:v", "1", "-f", "image2", "-c:v", "png", "pipe:1"],
        capture_output=True, check=True,
    )  # fmt: skip
    return made.stdout


def probe(data: bytes) -> dict:
    """What FFmpeg reads in a picture: its codec, width and height."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "json", "-"],
        input=data, capture_output=True, check=True,
    )  # fmt: skip
    return json.loads(out.stdout)["streams"][0]


def kept_by_plex(plex, key: str, data: bytes) -> None:
    """Plex keeps `data` as `key`'s poster (its resize stays the stand-in's)."""
    plex.odd[f"/library/metadata/{key}/thumb"] = httpx.Response(200, content=data, headers={"content-type": "image/png"})


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    with TestClient(server(plex, tmp_path / "data")) as client:
        shared(client)
        client.plex = plex
        yield client


def test_webp_when_an_app_asks_made_from_the_picture_as_plex_keeps_it(home):
    kept_by_plex(home.plex, "300", real_picture(600, 900))
    got = home.get("/api/internal/art/300?kind=poster&w=300&format=webp")
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/webp"
    seen = probe(got.content)
    assert seen["codec_name"] == "webp" and seen["width"] == 320 and seen["height"] == 480, seen
    # (Plex's resize was asked for WebP first; it made JPEG, so it isn't asked again for WebP.)
    asked = len(home.plex.requests)
    assert home.get("/api/internal/art/300?kind=poster&w=480&format=webp").headers["content-type"] == "image/webp"
    assert "/photo/:/transcode" not in home.plex.requests[asked:]


def test_no_format_is_jpeg_as_older_apps_expect(home):
    got = home.get("/api/internal/art/300?kind=poster&w=320")
    assert got.headers["content-type"] == "image/jpeg" and got.content == b"poster 300"  # (Plex's own resize)
    for wrong in ("format=avif", "format=png", "format="):
        refused(home.get(f"/api/internal/art/300?{wrong}"), 400)


def test_with_no_webp_encoder_the_answer_is_jpeg_and_says_so(home, monkeypatch):
    monkeypatch.setattr(home.app.state.ctx.settings, "ffmpeg_path", "/no/such/ffmpeg")
    kept_by_plex(home.plex, "300", real_picture(600, 900))
    got = home.get("/api/internal/art/300?kind=poster&w=320&format=webp")
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert got.content == b"poster 300"


def test_ten_asks_for_the_same_new_picture_make_it_once(home):
    from concurrent.futures import ThreadPoolExecutor

    home.plex.slow_at, home.plex.pause = {"/photo/:/transcode"}, 0.3
    home.get("/api/internal/items/300")
    asked = len(home.plex.requests)
    with ThreadPoolExecutor(10) as pool:
        got = list(pool.map(lambda _: home.get("/api/internal/art/300?kind=poster&w=320"), range(10)))
    assert {g.status_code for g in got} == {200} and {g.content for g in got} == {b"poster 300"}
    assert home.plex.requests[asked:].count("/photo/:/transcode") == 1


def test_the_image_can_make_webp():
    # (The image's FFmpeg lists libwebp; CI runs this in the image itself, so it fails if it's gone.)
    assert asyncio.run(pictures.makes_webp("ffmpeg"))


# The disk cache --------------------------------------------------------------------------------


def test_the_cache_never_passes_its_cap(tmp_path):
    cache = pictures.DiskCache(tmp_path / "pictures", most_bytes=10_000)
    cache.open()
    for n in range(40):
        assert cache.put(f"{n:040x}", pictures.Kept(bytes([n % 256]) * 1_000, "image/jpeg", '"t"'))
        assert cache.bytes_kept <= 10_000
    on_disk = sum(f.stat().st_size for f in (tmp_path / "pictures").rglob("*") if f.is_file() and len(f.name) == 40)
    assert on_disk <= 10_000
    assert cache.get(f"{0:040x}") is None and cache.get(f"{39:040x}") is not None  # (the oldest went first)
    cache.close()


def test_a_full_disk_or_a_failed_write_still_answers(home, monkeypatch):
    from collections import namedtuple

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(pictures.shutil, "disk_usage", lambda _: usage(10 << 30, 10 << 30, 1 << 20))
    assert home.get("/api/internal/art/300?w=320").status_code == 200
    assert home.app.state.ctx.picture_disk.bytes_kept == 0  # (not kept: the disk was nearly full)
    monkeypatch.undo()
    monkeypatch.setattr(pictures.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("read-only")))
    assert home.get("/api/internal/art/301?w=320").status_code == 200


def test_no_title_or_file_name_is_in_the_cache(home):
    for key in ("300", "301", "201"):
        assert home.get(f"/api/internal/art/{key}?w=320").status_code in (200, 404)
    folder = home.app.state.ctx.settings.data_dir / pictures.FOLDER
    names = [p.name for p in folder.rglob("*")]
    assert names, "something was kept"
    said = b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())
    for title in ("The Movie", "Another Movie", "Bonanza", "Episode 1", "movie.mkv", "/films", "/tv/"):
        assert all(title.casefold() not in n.casefold() for n in names), title
        assert title.encode() not in said, title


def test_a_new_encoder_version_makes_new_files(home, monkeypatch):
    assert home.get("/api/internal/art/300?w=320").status_code == 200
    first = pictures.name(f"plex {home.app.state.ctx.settings.plex_url}", "300", "poster", 320, "jpeg")
    monkeypatch.setattr(pictures, "ENCODER", "2")
    assert pictures.name(f"plex {home.app.state.ctx.settings.plex_url}", "300", "poster", 320, "jpeg") != first


def test_a_cache_with_another_format_stamp_is_emptied_never_read(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    data = tmp_path / "data"
    with TestClient(server(plex, data)) as home:
        shared(home)
        assert home.get("/api/internal/art/300?w=320").status_code == 200
    folder = data / pictures.FOLDER
    (folder / "FORMAT").write_text("tapioca-pictures 0\n")  # (as another version of tapiOca left it)
    asked = len(plex.requests)
    with TestClient(server(plex, data)) as home:
        assert home.get("/api/internal/art/300?w=320").status_code == 200
        assert "/photo/:/transcode" in plex.requests[asked:], "made again, never read from the old cache"
    assert (folder / "FORMAT").read_text().strip() == pictures.STAMP


# Changed art never sticks ------------------------------------------------------------------------


def test_a_changed_plex_picture_shows_after_the_next_browse_with_no_ask_just_to_check(home):
    assert home.get("/api/internal/items/300").status_code == 200  # (Plex says its poster's version)
    first = home.get("/api/internal/art/300?w=320")
    asked = len(home.plex.requests)
    again = home.get("/api/internal/art/300?w=320")
    assert again.content == first.content and home.plex.requests[asked:] == [], "nothing asked just to check"
    home.plex.episodes["300"]["thumb"] = "/library/metadata/300/thumb/1700000099"  # (a new poster in Plex)
    home.plex.odd["/photo/:/transcode"] = httpx.Response(200, content=b"new poster 300", headers={"content-type": "image/jpeg"})
    assert home.get("/api/internal/art/300?w=320").content == first.content  # (not heard of yet: kept)
    assert home.get("/api/internal/libraries/2").status_code == 200  # (the next browse hears of it)
    assert home.get("/api/internal/art/300?w=320").content == b"new poster 300"

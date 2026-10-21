"""Pictures that load fast (the plan's "Pictures that load fast"; app/pictures.py):
the disk cache behind the memory cache, made once, WebP when an app asks,
widths per kind, quality at a measured floor, and changed art never kept."""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path

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


def test_a_replaced_poster_file_shows_after_the_next_rescan_never_reading_the_disk_just_to_check(tmp_path):
    from .folderlib import Clips, radarr_movies
    from .test_folder_media import add_library, keys_by_title

    clips = Clips(tmp_path / "clips")
    root = tmp_path / "media"
    radarr_movies(root / "Movies", clips)
    poster = root / "Movies" / "The Glass Garden (1999)" / "poster.jpg"
    settings = Settings(data_dir=tmp_path / "data", media_dir=str(root))
    with TestClient(create_app(settings, PlexClient("", ""))) as home:
        lib = add_library(home, "Movies", "movie", str(root / "Movies"))
        key = keys_by_title(home, lib)["The Glass Garden"]
        first = home.get(f"/api/internal/art/{key}?w=320")
        assert first.status_code == 200
        poster.write_bytes(clips.wide.read_bytes())  # (replaced, beside the movie)
        assert home.get(f"/api/internal/art/{key}?w=320").content == first.content  # (no scan yet: kept)
        scanned = home.get("/api/folder-libraries").json()["libraries"][0]["scannedMs"]
        assert home.post(f"/api/folder-libraries/{lib}/scan").status_code == 202
        for _ in range(300):
            if home.get("/api/folder-libraries").json()["libraries"][0]["scannedMs"] != scanned:
                break
            time.sleep(0.05)
        again = home.get(f"/api/internal/art/{key}?w=320")
        assert again.status_code == 200 and again.content != first.content


# Station logos -------------------------------------------------------------------------------------


def test_a_logo_an_app_asks_a_width_of_is_made_that_wide_kept_a_year_and_stays_png(home):
    from app.logos import LogoLibrary

    made = home.post("/api/channels", json={"number": 42, "logo": "halloween",
                                            "sources": [{"type": "show", "ratingKey": "100"}]})  # fmt: skip
    assert made.status_code == 201, made.text
    plain = home.get("/channel-icon/42.png")  # (as Plex and the tuner have always had it)
    assert plain.status_code == 200 and plain.headers["cache-control"] == "max-age=86400"
    assert plain.content == LogoLibrary().path("halloween").read_bytes(), "unchanged without w"
    # (The address the apps are given, with its version: the test once made one up.)
    logo = next(s["logo"] for s in home.get("/api/v1/stations").json()["stations"] if s["number"] == 42)
    sized = home.get(f"{logo}&w=100")
    assert sized.status_code == 200 and sized.headers["content-type"] == "image/png"
    assert sized.headers["cache-control"] == "private, max-age=31536000"
    seen = probe(sized.content)
    assert seen["codec_name"] == "png" and seen["width"] == 120, seen  # (rounded up)
    assert len(sized.content) < len(plain.content)
    again = home.get(f"{logo}&w=110", headers={"If-None-Match": sized.headers["etag"]})
    assert again.status_code == 304
    for wrong in ("w=0", "w=wide", "w=10001"):
        refused(home.get(f"/channel-icon/42.png?{wrong}"), 400)
    assert home.post("/api/channels", json={"number": 46, "sources": [{"type": "show", "ratingKey": "100"}]}).status_code == 201
    badge = home.get("/channel-icon/46.png?w=160")  # (no logo: its number, drawn)
    assert badge.status_code == 200 and probe(badge.content)["width"] == 160


def test_a_logo_away_from_home_comes_at_its_width_too(home):
    assert home.post("/api/channels", json={"number": 45, "logo": "halloween",
                                            "sources": [{"type": "show", "ratingKey": "100"}]}).status_code == 201  # fmt: skip
    signed = home.post("/api/access/users", json={"name": "Ada", "password": "correct horse"})
    assert signed.status_code in (200, 201), signed.text
    token = TestClient(home.app).post("/api/internal/sign-in", json={"name": "Ada", "password": "correct horse"}).json()["token"]
    stations = home.get("/api/v1/stations", headers={"Authorization": f"Bearer {token}"}).json()["stations"]
    logo = next(s["logo"] for s in stations if s["number"] == 45)
    assert logo.startswith("/hls/k/"), logo
    got = home.get(f"{logo}&w=100")
    assert got.status_code == 200 and probe(got.content)["width"] == 120
    assert got.headers["cache-control"] == "private, max-age=31536000"


# Quality, at a measured floor -----------------------------------------------------------------------


def film_like(width: int, height: int, busy: bool) -> bytes:
    """A poster or backdrop as Plex keeps one: a high-quality JPEG with film grain (soft, in the
    brightness), smooth gradients where banding would show, and sharp edges; or a busy one."""
    base = f"testsrc2=s={width}x{height}" if busy else (
        f"gradients=s={width}x{height}:c0=0x203060:c1=0xd08040:c2=0x40a070:n=3:seed=7")
    look = ("format=yuv444p,noise=c0s=12:c0f=u,gblur=sigma=0.8:planes=1,"
            "drawbox=x=iw/4:y=ih/3:w=iw/2:h=ih/6:color=white@0.8:t=fill,format=yuvj420p")
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", base, "-vf", look,
         "-frames:v", "1", "-q:v", "2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip


def planes_ssim(made: bytes, lossless: bytes, pix: str) -> tuple[float, ...]:
    import re
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        a, b = f"{folder}/made", f"{folder}/lossless.y4m"
        Path(a).write_bytes(made)
        Path(b).write_bytes(lossless)
        said = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", a, "-i", b, "-lavfi",
             f"[0:v]format={pix}[x];[1:v]format={pix}[y];[x][y]ssim", "-f", "null", "-"],
            capture_output=True, check=True,
        ).stderr.decode()  # fmt: skip
    return tuple(float(x) for x in re.search(r"SSIM Y:([\d.]+).*U:([\d.]+).*V:([\d.]+)", said).groups())


def test_every_width_and_format_keeps_every_color_plane_at_the_floor():
    # (Against a lossless resize at the same width: the encoder's own loss, on brightness and both
    # colors, so banding in a gradient shows. The settings are the smallest that keep it.)
    worst = {}
    for kind, size in (("poster", (2000, 3000)), ("backdrop", (3840, 2160))):
        sources = [film_like(*size, busy=False), film_like(*size, busy=True)]
        for width in pictures.widths(kind):
            height = pictures.height_for(kind, width)
            for fmt, pix in (("jpeg", "yuvj420p"), ("webp", "yuv420p")):
                for n, source in enumerate(sources):
                    lossless = subprocess.run(
                        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-frames:v", "1", "-vf",
                         f"scale='min({width},iw)':'min({height},ih)':force_original_aspect_ratio=decrease,format={pix}",
                         "-f", "yuv4mpegpipe", "-strict", "-1", "pipe:1"],
                        input=source, capture_output=True, check=True,
                    ).stdout  # fmt: skip
                    made = subprocess.run(
                        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "yuv4mpegpipe", "-i", "pipe:0",
                         "-frames:v", "1", *pictures.encoder_args(kind, width, fmt), "pipe:1"],
                        input=lossless, capture_output=True, check=True,
                    ).stdout  # fmt: skip
                    worst[(kind, width, fmt, n)] = min(planes_ssim(made, lossless, pix))
    under = {k: round(v, 4) for k, v in worst.items() if v < pictures.QUALITY_FLOOR}
    assert not under, under


# Drawn ahead, never in playback's way -----------------------------------------------------------------


def test_drawing_ahead_pauses_while_anyone_watches_then_draws_what_a_screen_asks_from_disk(home, monkeypatch):
    from app import applibrary

    monkeypatch.setattr(applibrary, "AHEAD_WAIT_S", 0.05)
    ctx = home.app.state.ctx
    played = home.post("/api/internal/progress", json={"key": "300", "positionMs": 9 * 60_000})
    assert played.status_code in (200, 204), played.text
    watching = [True]
    monkeypatch.setattr(ctx.folders, "watching", lambda: watching[0])
    asked = len(home.plex.requests)

    async def draw() -> int:
        return await ctx.draw_ahead()

    going = home.portal.start_task_soon(draw)  # (on the server's own loop)
    time.sleep(0.4)
    assert "/photo/:/transcode" not in home.plex.requests[asked:], "nothing drawn while someone watches"
    watching[0] = False
    assert going.result(timeout=10) >= 1
    since = len(home.plex.requests)
    got = home.get("/api/internal/art/300?kind=poster&w=320")
    assert got.status_code == 200 and "/photo/:/transcode" not in home.plex.requests[since:]


def test_a_screens_request_goes_ahead_of_drawing_ahead():
    async def run() -> list[str]:
        maker, order = pictures.Maker(), []

        async def screen() -> None:
            async with maker.screen():
                await asyncio.sleep(0.2)
                order.append("screen")

        async def ahead() -> None:
            await asyncio.sleep(0.05)  # (asked once the screen's is being made)
            await maker.ahead_turn()
            order.append("ahead")

        await asyncio.gather(screen(), ahead())
        return order

    assert asyncio.run(run()) == ["screen", "ahead"]


def test_an_admin_sets_the_space_for_pictures_and_it_lasts(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    data = tmp_path / "data"
    with TestClient(server(plex, data)) as page:
        shared(page)
        assert page.get("/api/app-pictures").json()["gb"] == 2.0
        assert page.get("/api/internal/art/300?w=320").status_code == 200
        assert page.get("/api/app-pictures").json()["keptBytes"] > 0
        assert page.put("/api/app-pictures", json={"gb": 0}).json() == {"gb": 0, "keptBytes": 0, "most": 1000}
        assert page.get("/api/internal/art/300?w=320").status_code == 200  # (still answered, kept in memory only)
        assert page.app.state.ctx.picture_disk.bytes_kept == 0
        for wrong in (-1, 1001, "lots"):
            assert page.put("/api/app-pictures", json={"gb": wrong}).status_code == 422
        assert page.put("/api/app-pictures", json={"gb": 1.5}).json()["gb"] == 1.5
    with TestClient(server(plex, data)) as page:  # (started again: the Admin's choice stays)
        assert page.get("/api/app-pictures").json()["gb"] == 1.5


# The cold audit (October 19): each failing first ----------------------------------------------------


def test_letting_go_of_many_pictures_never_holds_up_other_disk_work(tmp_path):
    # (Each row was its own synced commit under the cache's one lock, on the shared threads that also
    # read a Station's pieces: lowering the space with 20,000 kept held a 1 MB read up for seconds.)
    import concurrent.futures
    import os as os_module

    cache = pictures.DiskCache(tmp_path / "pictures", most_bytes=10 << 30)
    cache.open()
    for n in range(20_000):
        cache.put(f"{n:040x}", pictures.Kept(b"x" * 1000, "image/jpeg", '"t"'))
    piece = tmp_path / "piece.ts"
    piece.write_bytes(os_module.urandom(1 << 20))

    async def run() -> tuple[float, float]:
        asyncio.get_running_loop().set_default_executor(concurrent.futures.ThreadPoolExecutor(8))
        began = time.perf_counter()
        letting_go = asyncio.create_task(cache.run(cache.set_most, 1 << 20))  # (as the page's Save calls it)
        await asyncio.sleep(0.05)
        asks = [asyncio.create_task(cache.run(cache.get, f"{19_999 - i:040x}")) for i in range(12)]  # (a screen's)
        await asyncio.sleep(0.01)
        read = time.perf_counter()
        await asyncio.to_thread(piece.read_bytes)  # (a Station's piece, as hls.py reads it)
        waited = time.perf_counter() - read
        await letting_go
        await asyncio.gather(*asks)
        return waited, time.perf_counter() - began

    waited, took = asyncio.run(run())
    assert waited < 0.2, f"a Station's read waited {waited:.2f} s"
    assert took < 5, f"letting go took {took:.1f} s"
    assert cache.bytes_kept <= 1 << 20
    cache.close()


def test_a_picture_made_for_a_request_that_gave_up_is_still_kept(tmp_path, monkeypatch):
    from app import ondemand

    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    monkeypatch.setattr(ondemand, "LIBRARY_WAIT_S", 0.6)
    plex = library()
    with TestClient(server(plex, tmp_path / "data")) as home:
        shared(home)
        assert home.get("/api/internal/items/300").status_code == 200
        plex.slow_at, plex.pause = {"/photo/:/transcode"}, 1.0
        start = len(plex.requests)
        assert home.get("/api/internal/art/300?kind=poster&w=320").status_code == 503  # (gave up waiting)
        time.sleep(1.5)  # (its making goes on, and ends)
        again = home.get("/api/internal/art/300?kind=poster&w=320")
        assert again.status_code == 200 and again.content == b"poster 300"
        assert plex.requests[start:].count("/photo/:/transcode") == 1, "made once, and kept"


def test_a_resize_that_failed_never_keeps_the_full_size_picture_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    big = real_picture(1000, 1500)
    plex.odd["/library/metadata/300/thumb"] = httpx.Response(200, content=big, headers={"content-type": "image/jpeg"})
    plex.odd["/photo/:/transcode"] = httpx.Response(503)  # (Plex's resizer busy, once)
    with TestClient(server(plex, tmp_path / "data")) as home:
        shared(home)
        assert home.get("/api/internal/art/300?kind=poster&w=160").status_code == 200  # (as before: the original)
        assert home.app.state.ctx.picture_disk.bytes_kept == 0, "but never kept on disk"


def test_a_poster_removed_since_is_no_longer_served(home):
    assert home.get("/api/internal/items/300").status_code == 200
    assert home.get("/api/internal/art/300?w=320").status_code == 200
    home.plex.episodes["300"].pop("thumb", None)  # (the poster removed in Plex)
    home.plex.no_poster.add("300")
    assert home.get("/api/internal/libraries/2").status_code == 200  # (the next browse hears of it)
    refused(home.get("/api/internal/art/300?w=320"), 404, "There's no such picture")


def test_a_changed_picture_that_cant_be_made_now_keeps_the_one_kept(home):
    assert home.get("/api/internal/items/300").status_code == 200
    first = home.get("/api/internal/art/300?w=320")
    home.plex.episodes["300"]["thumb"] = "/library/metadata/300/thumb/1700000099"
    assert home.get("/api/internal/libraries/2").status_code == 200
    home.plex.odd["/photo/:/transcode"] = httpx.Response(500)
    home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(500)
    home.plex.slow_at = {"/photo/:/transcode"}
    home.plex.down = True  # (Plex away just then)
    got = home.get("/api/internal/art/300?w=320")
    home.plex.down = False
    assert got.status_code == 200 and got.content == first.content


def test_a_torn_file_is_made_again_never_served_empty(tmp_path):
    cache = pictures.DiskCache(tmp_path / "pictures", most_bytes=1 << 30)
    cache.open()
    name = "ab" + "0" * 38
    assert cache.put(name, pictures.Kept(b"x" * 5000, "image/jpeg", '"t"'))
    (tmp_path / "pictures" / name[:2] / name).write_bytes(b"x" * 10)  # (torn by a power cut)
    assert cache.get(name) is None
    assert cache.bytes_kept == 0


def test_a_broken_or_missing_index_empties_the_cache_and_keeps_going(tmp_path):
    folder = tmp_path / "pictures"
    cache = pictures.DiskCache(folder, most_bytes=1 << 30)
    cache.open()
    for n in range(20):
        cache.put(f"{n:040x}", pictures.Kept(b"x" * 5000, "image/jpeg", '"t"'))
    cache.close()
    (folder / ".leftover.1.2").write_bytes(b"part")  # (a write cut short)
    for extra in ("index.db-wal", "index.db-shm"):
        (folder / extra).unlink(missing_ok=True)
    (folder / "index.db").write_bytes(b"not a database" * 100)
    again = pictures.DiskCache(folder, most_bytes=1 << 30)
    again.open()
    assert [p for p in folder.rglob("*") if p.is_file() and (len(p.name) == 40 or p.name.startswith("."))] == []
    assert again.put("cd" + "0" * 38, pictures.Kept(b"y" * 100, "image/jpeg", '"u"'))
    assert again.get("cd" + "0" * 38) is not None
    again.close()
    (folder / "index.db").unlink()  # (deleted by hand: the files it named are let go too)
    third = pictures.DiskCache(folder, most_bytes=1 << 30)
    third.open()
    assert [p for p in folder.rglob("*") if p.is_file() and len(p.name) == 40] == []
    third.close()


def test_a_viewer_without_limits_never_gets_a_picture_kept_from_a_media_folder_unshared_since(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    data = tmp_path / "data"
    with TestClient(server(plex, data)) as home:
        shared(home)
        assert home.get("/api/internal/art/300?w=320").status_code == 200
    with TestClient(server(plex, data)) as home:
        assert home.put("/api/app-libraries", json={"libraries": ["1"]}).status_code == 200
        refused(home.get("/api/internal/art/300?w=320"), 404)


def test_drawing_ahead_waits_for_a_screens_request(home):
    ctx = home.app.state.ctx
    assert home.post("/api/internal/progress", json={"key": "300", "positionMs": 60_000}).status_code in (200, 204)
    asked = len(home.plex.requests)

    async def draw_while_a_screen_is_made() -> tuple[int, int]:
        async with ctx.picture_maker.screen():
            going = asyncio.create_task(ctx.draw_ahead())
            await asyncio.sleep(0.3)
            during = home.plex.requests[asked:].count("/photo/:/transcode")
        return during, await going

    during, made = home.portal.call(draw_while_a_screen_is_made)
    assert during == 0 and made >= 1


def test_a_new_encoder_version_makes_the_picture_again_never_reading_the_old(home, monkeypatch):
    assert home.get("/api/internal/art/300?w=320").status_code == 200
    home.app.state.ctx.app_pictures.clear()
    asked = len(home.plex.requests)
    monkeypatch.setattr(pictures, "ENCODER", "2")
    assert home.get("/api/internal/art/300?w=320").status_code == 200
    assert home.plex.requests[asked:].count("/photo/:/transcode") == 1


def test_a_logo_that_couldnt_be_sized_is_never_kept_a_year(home, monkeypatch):
    assert home.post("/api/channels", json={"number": 43, "logo": "halloween",
                                            "sources": [{"type": "show", "ratingKey": "100"}]}).status_code == 201  # fmt: skip
    plain = home.get("/channel-icon/43.png")

    async def cant(*_):
        return None

    monkeypatch.setattr(pictures, "logo", cant)
    sized = home.get("/channel-icon/43.png?v=1-halloween&w=100")
    assert sized.status_code == 200 and sized.content == plain.content
    assert sized.headers["cache-control"] == "max-age=86400", "as it is, for a day"
    monkeypatch.undo()
    again = home.get("/channel-icon/43.png?v=1-halloween&w=100")
    assert probe(again.content)["width"] == 120, "sized once it can be"


def test_a_logo_address_without_its_version_is_never_kept_a_year(home):
    assert home.post("/api/channels", json={"number": 44, "logo": "halloween",
                                            "sources": [{"type": "show", "ratingKey": "100"}]}).status_code == 201  # fmt: skip
    current = home.get("/api/v1/stations").json()["stations"]
    logo = next(s["logo"] for s in current if s["number"] == 44)
    assert home.get(f"{logo}&w=100").headers["cache-control"] == "private, max-age=31536000"
    for old in ("/channel-icon/44.png?w=100", "/channel-icon/44.png?v=0-old&w=100"):
        assert home.get(old).headers["cache-control"] == "private, max-age=86400", old
    tag = home.get(f"{logo}&w=100").headers["etag"]
    assert home.get(f"{logo}&w=100", headers={"If-None-Match": "*"}).status_code == 304
    assert home.get(f"{logo}&w=100", headers={"If-None-Match": f'"x{tag[1:]}'}).status_code == 200

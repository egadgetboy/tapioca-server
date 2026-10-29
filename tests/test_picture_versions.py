"""Changed art still shows, in memory (1.43.0; the restore-fast-pictures
handoff, part 2): what 1.42's "Pictures that load fast" got right is kept
with pictures as 1.41.0 made them. A picture is kept in memory with the
version of the art it was made from, as the library last said it (Plex's
thumb and art timestamps from its lists; a Media folder's picture files from
its scan), so changed art is made again with no request just to check,
art removed since isn't served, and a changed picture that can't be made
now sends the one kept. Moved from 1.42's tests/test_pictures.py, each with
its name and expected result (the setup from the memory cache where it was
the disk cache)."""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import plex as plex_module
from app.config import Settings
from app.main import create_app
from app.plex import PlexClient

from .test_media_solid import library, limited, refused, shared
from .timing import within


def server(plex, data_dir):
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=data_dir)
    app = create_app(settings, PlexClient("http://plex.test", "token", transport=plex.transport()))
    app.state.ctx.play_transport = plex.transport()
    return app


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    with TestClient(server(plex, tmp_path / "data")) as client:
        shared(client)
        client.plex = plex
        yield client


def test_a_changed_plex_picture_shows_after_the_next_browse_with_no_ask_just_to_check(home):
    assert (
        home.get("/api/internal/items/300").status_code == 200
    )  # (Plex says its poster's version)
    first = home.get("/api/internal/art/300?w=320")
    asked = len(home.plex.requests)
    again = home.get("/api/internal/art/300?w=320")
    assert again.content == first.content and home.plex.requests[asked:] == [], (
        "nothing asked just to check"
    )
    home.plex.episodes["300"]["thumb"] = (
        "/library/metadata/300/thumb/1700000099"  # (a new poster in Plex)
    )
    home.plex.odd["/photo/:/transcode"] = httpx.Response(
        200, content=b"new poster 300", headers={"content-type": "image/jpeg"}
    )
    assert (
        home.get("/api/internal/art/300?w=320").content == first.content
    )  # (not heard of yet: kept)
    assert home.get("/api/internal/libraries/2").status_code == 200  # (the next browse hears of it)
    assert home.get("/api/internal/art/300?w=320").content == b"new poster 300"


def test_a_replaced_poster_file_shows_after_the_next_rescan_never_reading_the_disk_just_to_check(
    tmp_path,
):
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
        assert (
            home.get(f"/api/internal/art/{key}?w=320").content == first.content
        )  # (no scan yet: kept)
        scanned = home.get("/api/folder-libraries").json()["libraries"][0]["scannedMs"]
        assert home.post(f"/api/folder-libraries/{lib}/scan").status_code == 202
        for _ in range(300):
            if home.get("/api/folder-libraries").json()["libraries"][0]["scannedMs"] != scanned:
                break
            time.sleep(0.05)
        again = home.get(f"/api/internal/art/{key}?w=320")
        assert again.status_code == 200 and again.content != first.content


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
    for unwell in (503, 502, 500):
        home.plex.odd["/photo/:/transcode"] = httpx.Response(unwell)  # (Plex restarting, say)
        home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(unwell)
        began = time.monotonic()
        got = home.get("/api/internal/art/300?w=320")
        assert got.status_code == 200 and got.content == first.content, unwell
        within(time.monotonic() - began, 2)
    assert home.app.state.ctx.app_pictures.get(("300", "poster", 320)) is not None, "still kept"
    home.plex.odd = {}
    home.plex.odd["/photo/:/transcode"] = httpx.Response(
        200, content=b"new poster 300", headers={"content-type": "image/jpeg"}
    )
    assert home.get("/api/internal/art/300?w=320").content == b"new poster 300"


def test_no_format_is_jpeg_as_older_apps_expect(home):
    got = home.get("/api/internal/art/300?kind=poster&w=320")
    assert (
        got.headers["content-type"] == "image/jpeg" and got.content == b"poster 300"
    )  # (Plex's own resize)
    # (1.43.0: any format is ignored, as 1.41.0 never read one; 1.42 refused these with 400.)
    for ignored in ("format=avif", "format=png", "format=", "format=webp"):
        again = home.get(f"/api/internal/art/300?w=320&{ignored}")
        assert again.status_code == 200 and again.headers["content-type"] == "image/jpeg", ignored


def test_a_title_someone_may_not_see_is_refused_even_with_its_picture_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(plex_module, "RETRY_S", 0.01)
    plex = library()
    app = server(plex, tmp_path / "data")
    admin, kit, lee = limited(app, plex)
    try:
        assert admin.get("/api/internal/art/301").status_code == 200  # (kept, in memory)
        assert admin.get("/api/internal/art/300").status_code == 200
        refused(admin.get("/api/internal/art/301", headers=kit), 404)  # (Kid doesn't allow it)
        refused(admin.get("/api/internal/art/300", headers=lee), 404)  # (TV only)
    finally:
        admin.__exit__(None, None, None)


def test_a_viewer_without_limits_never_gets_a_picture_kept_from_a_media_folder_unshared_since(
    home,
):
    assert home.get("/api/internal/art/300?w=320").status_code == 200  # (kept)
    assert home.put("/api/app-libraries", json={"libraries": ["1"]}).status_code == 200
    refused(home.get("/api/internal/art/300?w=320"), 404)


def changed(home):
    """Poster 300 kept, then changed in Plex and heard of: (the kept bytes)."""
    assert home.get("/api/internal/items/300").status_code == 200
    first = home.get("/api/internal/art/300?w=320")
    assert first.status_code == 200
    home.plex.episodes["300"]["thumb"] = "/library/metadata/300/thumb/1700000099"
    assert home.get("/api/internal/libraries/2").status_code == 200
    return first.content


def test_a_changed_picture_plex_refuses_for_now_keeps_the_one_kept(home):
    # (The audit: 401, 403 and 429 counted as removed, dropping the kept copy.)
    first = changed(home)
    for refusing in (401, 403, 429):
        home.plex.odd["/photo/:/transcode"] = httpx.Response(refusing)
        home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(refusing)
        got = home.get("/api/internal/art/300?w=320")
        assert got.status_code == 200 and got.content == first, refusing
    assert home.app.state.ctx.app_pictures.get(("300", "poster", 320)) is not None


def test_a_changed_picture_now_gone_is_dropped(home):
    changed(home)
    for gone in (404, 410):
        home.plex.odd["/photo/:/transcode"] = httpx.Response(gone)
        home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(gone)
        refused(home.get("/api/internal/art/300?w=320"), 404, "There's no such picture")
        assert home.app.state.ctx.app_pictures.get(("300", "poster", 320)) is None


def test_a_missing_media_folder_picture_drops_the_kept_one_and_says_so(home, monkeypatch):
    # (The audit: NoPicture became "isn't in a Media folder shared" before the route saw it.)
    from app.library import NoPicture

    changed(home)
    ctx = home.app.state.ctx

    async def none(*a, **kw):
        raise NoPicture("poster")

    monkeypatch.setattr(ctx.library, "picture", none)
    refused(home.get("/api/internal/art/300?w=320"), 404, "There's no such picture")
    assert ctx.app_pictures.get(("300", "poster", 320)) is None


def test_a_changed_picture_that_doesnt_come_keeps_the_one_kept(home, monkeypatch):
    first = changed(home)
    ctx = home.app.state.ctx
    for trouble in (httpx.ConnectError("down"), httpx.ReadTimeout("slow")):

        async def failing(*a, _t=trouble, **kw):
            raise _t

        monkeypatch.setattr(ctx.library, "picture", failing)
        got = home.get("/api/internal/art/300?w=320")
        assert got.status_code == 200 and got.content == first, type(trouble).__name__


def test_with_nothing_kept_plex_trouble_is_a_503_never_gone(home, monkeypatch):
    # (The owner, October 21, DL283: a Plex hiccup isn't a missing picture. A 404
    # made the apps forget their saved copy and ask for the bigger wide art.
    # Plex's 5xx, 401 and 429 with nothing kept answer 503; only its 404, 410 or
    # a non-picture answer 404.)
    ctx = home.app.state.ctx
    assert home.get("/api/internal/items/300").status_code == 200
    for trouble in (500, 502, 503, 401, 429):
        home.plex.odd["/photo/:/transcode"] = httpx.Response(trouble)
        home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(trouble)
        refused(home.get("/api/internal/art/300?w=320"), 503)
    home.plex.odd = {}

    async def failing(*a, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(ctx.library, "picture", failing)
    assert home.get("/api/internal/art/300?w=480").status_code == 503


def test_1_42s_picture_route_is_gone(home):
    assert home.get("/api/app-pictures").status_code == 404
    assert home.put("/api/app-pictures", json={"gb": 1}).status_code == 404


def test_before_the_first_scan_a_cover_keeps_one_version(tmp_path):
    # (The audit: before the first scan after a start, reading a video's size
    # for its embedded cover wrote "0-<size>" into the stamps, so the cover's
    # version changed on the next request and it was made again, and again at
    # the scan: up to three FFmpeg runs per cover. And that read was the
    # database's, on the loop.)
    from .folderlib import Clips, radarr_movies
    from .test_folder_media import add_library, keys_by_title

    clips = Clips(tmp_path / "clips")
    root = tmp_path / "media"
    radarr_movies(root / "Movies", clips)
    (
        root / "Movies" / "The Glass Garden (1999)" / "poster.jpg"
    ).unlink()  # (its cover is inside the file)
    settings = Settings(data_dir=tmp_path / "data", media_dir=str(root))
    with TestClient(create_app(settings, PlexClient("", ""))) as home:
        lib = add_library(home, "Movies", "movie", str(root / "Movies"))
        key = keys_by_title(home, lib)["The Glass Garden"]
        library = home.app.state.ctx.library
        library._folder_source()._picture_stamps.clear()  # (as before the first scan after a start)
        before = library.picture_version(key, "poster")
        assert home.get(f"/api/internal/art/{key}?w=320").status_code == 200
        assert library.picture_version(key, "poster") == before, "the same version: made once"


def test_a_changed_show_poster_reaches_its_episodes_after_the_shows_are_browsed(home):
    # (The audit: an episode's poster took its version from the episode's own
    # list, so a new show poster reached episode cards only once that show's
    # episodes were fetched again.)
    assert home.get("/api/internal/items/100/episodes").status_code == 200
    first = home.get("/api/internal/art/201?kind=poster&w=320")
    assert first.status_code == 200
    home.plex.shows["100"]["thumb"] = (
        "/library/metadata/100/thumb/1700000099"  # (a new show poster)
    )
    home.plex.odd["/photo/:/transcode"] = httpx.Response(
        200, content=b"new show poster", headers={"content-type": "image/jpeg"}
    )
    assert home.get("/api/internal/libraries/1").status_code == 200  # (the shows, browsed)
    assert home.get("/api/internal/art/201?kind=poster&w=320").content == b"new show poster"


def test_plex_refusing_tapiocas_sign_in_for_a_picture_tells_the_admin_once(home):
    # (The owner, October 21, DL283: a 401 from Plex usually means tapiOca's
    # sign-in to Plex has stopped working: one Admin alert, not only retries.)
    alerts = home.app.state.ctx.alerts
    assert home.get("/api/internal/items/300").status_code == 200
    home.plex.odd["/photo/:/transcode"] = httpx.Response(401)
    home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(401)
    for width in (160, 320, 480):
        refused(home.get(f"/api/internal/art/300?w={width}"), 503)
    said = [a for a in alerts.now() if a.kind == "plex-pictures"]
    assert len(said) == 1 and "sign-in to Plex needs attention" in said[0].sentence, [
        a.sentence for a in alerts.now()
    ]
    # (The apps' re-check: fixed by the very next picture, mixed answers would start and fix it
    # over and over, each a notification. Fixed only after five in a row.)
    started = len([a for a in alerts.listed() if a.kind == "plex-pictures"])
    for width in (160, 320, 480, 720):
        home.app.state.ctx.app_pictures.clear()
        home.plex.odd = {}
        assert home.get(f"/api/internal/art/300?w={width}").status_code == 200
        home.plex.odd["/photo/:/transcode"] = httpx.Response(401)
        home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(401)
        home.app.state.ctx.app_pictures.clear()
        refused(home.get(f"/api/internal/art/300?w={width}"), 503)
    assert len([a for a in alerts.now() if a.kind == "plex-pictures"]) == 1, "still the one alert"
    assert len([a for a in alerts.listed() if a.kind == "plex-pictures"]) == started, (
        "never started again"
    )
    home.plex.odd = {}
    for width in (160, 320, 480, 720, 1280):
        home.app.state.ctx.app_pictures.clear()
        assert home.get(f"/api/internal/art/300?w={width}").status_code == 200
    assert [a for a in alerts.now() if a.kind == "plex-pictures"] == [], "fixed"


def test_the_pictures_alert_never_flaps_on_pictures_already_coming(home, monkeypatch):
    # (The final audit: five pictures asked before the 401 that finish after it
    # fixed the alert at once, and the next 401 started it again: counted only
    # pictures asked after the latest 401 now, and by what was sent, not what's up.)
    ctx = home.app.state.ctx
    sent: list[tuple[str, str]] = []
    real = ctx.notify.send
    monkeypatch.setattr(
        ctx.notify,
        "send",
        lambda sentence, kind, state, **kw: (
            sent.append((kind, state)),
            real(sentence, kind, state, **kw),
        ),
    )
    assert home.get("/api/internal/items/300").status_code == 200
    began = ctx.alerts.pictures_asked()  # (as a picture's turn starts, before the 401)
    home.plex.odd["/photo/:/transcode"] = httpx.Response(401)
    home.plex.odd["/library/metadata/300/thumb"] = httpx.Response(401)
    refused(home.get("/api/internal/art/300?w=320"), 503)
    for _ in range(6):
        ctx.alerts.plex_made_a_picture(began)  # (those already coming, finishing after it)
    assert [k for k, _ in sent if k == "plex-pictures"] == ["plex-pictures"], sent


def test_an_older_version_skips_the_pictures_alert_so_a_rollback_never_keeps_it(tmp_path):
    # (The final audit: as kind plex, 1.42.1 restored it as going and nothing in it
    # ever fixed it. A kind of its own is skipped by any version that doesn't know it.)
    from app import alerts as alerts_module

    assert alerts_module.PLEX_PICTURES not in (
        "plex",
        "data-full",
        "data-write",
        "station",
        "backups",
        "clock",
        "outside",
        "files",
        "clips",
        "access",
    )  # fmt: skip  (1.42.1's kinds)
    assert alerts_module.PLEX_PICTURES in alerts_module.KINDS


def test_a_changed_picture_that_plex_answers_with_a_non_picture_drops_the_kept_one(home):
    # (The final audit: untested. An answer that isn't a picture is as good as none.)
    changed(home)
    page = httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    home.plex.odd["/photo/:/transcode"] = page
    home.plex.odd["/library/metadata/300/thumb"] = page
    refused(home.get("/api/internal/art/300?w=320"), 404, "There's no such picture")
    assert home.app.state.ctx.app_pictures.get(("300", "poster", 320)) is None


def test_a_media_folder_picture_never_touches_the_plex_alert(tmp_path, monkeypatch):
    # (The final audit: untested.)
    from .folderlib import Clips, radarr_movies
    from .test_folder_media import add_library, keys_by_title

    clips = Clips(tmp_path / "clips")
    root = tmp_path / "media"
    radarr_movies(root / "Movies", clips)
    settings = Settings(data_dir=tmp_path / "data", media_dir=str(root))
    with TestClient(create_app(settings, PlexClient("", ""))) as home:
        lib = add_library(home, "Movies", "movie", str(root / "Movies"))
        key = keys_by_title(home, lib)["The Glass Garden"]
        touched: list[int] = []
        monkeypatch.setattr(
            home.app.state.ctx.alerts, "plex_made_a_picture", lambda asked: touched.append(asked)
        )
        assert home.get(f"/api/internal/art/{key}?w=320").status_code == 200
        assert touched == []

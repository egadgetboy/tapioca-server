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
        assert time.monotonic() - began < 2
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

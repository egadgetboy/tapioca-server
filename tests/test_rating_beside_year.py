"""The content rating beside the year (VR10, W066; the owner, October 18:
"if we can display the year on a movie or TV show, we can also display the
MPAA rating"). Every Media card tapiOca's apps get carries `contentRating`
beside its `year`: a show's or movie's own, and an episode's as limits judge
it (its show's, or its own if that's stricter). Only for what the person may
see, as every card already is."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import ratings
from app.applibrary import card
from app.catalog import EPISODE, MOVIE, SHOW, Entry
from app.config import Settings
from app.main import create_app
from app.plex import PlexClient

from .fakeplex_library import LibraryPlex
from .test_who_sees_what import KIT, kid_level, sign_in_app


def test_a_rating_is_shown_as_people_know_it():
    assert ratings.shown("PG-13") == "PG-13"
    assert ratings.shown("  TV-14 ") == "TV-14"
    assert ratings.shown("us/TV-MA") == "TV-MA"  # (Plex's country mark left off)
    assert ratings.shown("gb/15") == "15"
    for none in (None, "", "  ", "NR", "Not Rated", "unrated", "us/"):
        assert ratings.shown(none) is None, none


def entry(key: str, kind: str, rating: str = "", show_key: str | None = None) -> Entry:
    return Entry(key=key, kind=kind, title=f"Title {key}", year=2024, content_rating=rating,
                 show_key=show_key)  # fmt: skip


def test_a_card_carries_the_rating_beside_its_year():
    assert card(entry("1", MOVIE, "PG"), {})["contentRating"] == "PG"
    assert card(entry("2", SHOW, "TV-PG"), {}, 3)["contentRating"] == "TV-PG"
    assert card(entry("3", MOVIE), {})["contentRating"] is None
    show = entry("10", SHOW, "TV-PG")
    # An episode: its show's, or its own when that's stricter, as limits judge it.
    assert card(entry("11", EPISODE, "", "10"), {}, show=show)["contentRating"] == "TV-PG"
    assert card(entry("12", EPISODE, "TV-14", "10"), {}, show=show)["contentRating"] == "TV-14"
    assert card(entry("13", EPISODE, "TV-Y", "10"), {}, show=show)["contentRating"] == "TV-PG"
    assert card(entry("14", EPISODE, "TV-14", "10"), {})["contentRating"] == "TV-14"
    assert card(entry("15", EPISODE, "", "10"), {}, show=entry("10", SHOW))["contentRating"] is None


@pytest.fixture
def plex():
    fp = LibraryPlex()
    fp.add_show("100", "Puppet Town", year=2021, contentRating=["TV-Y7"])
    for n in range(1, 4):
        fp.add_episode(f"20{n}", "100", 1, n, f"Puppets {n}", f"/tv/p/{n}.mkv", 22 * 60_000)
    fp.episodes["203"]["contentRating"] = "TV-PG"  # (stricter than its show's)
    fp.add_section("2", "Movies", "movie")
    fp.add_movie("300", "Picnic", "/m/picnic.mkv", 90 * 60_000, section="2",
                 contentRating=["PG"])  # fmt: skip
    fp.add_movie("301", "Heist", "/m/heist.mkv", 100 * 60_000, section="2",
                 contentRating=["R"])  # fmt: skip
    for key in ("201", "202", "203", "300", "301"):
        fp.describe(key)
    return fp


@pytest.fixture
def app(plex, tmp_path):
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data")
    app = create_app(settings, PlexClient("http://plex.test", "token", transport=plex.transport()))
    app.state.ctx.play_transport = plex.transport()
    return app


def test_every_media_card_carries_its_rating_and_only_what_the_person_sees(app):
    with TestClient(app) as admin:
        assert admin.put("/api/app-libraries", json={"libraries": ["1", "2"]}).status_code == 200
        admin.post("/api/access/users", json={"name": "Ada", "password": "correct horse"})
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        kid = kid_level(admin)
        assert (
            admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": kid}).status_code
            == 200
        )
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)

        def got(path: str) -> dict:
            answer = phone.get(path, headers=as_kit)
            assert answer.status_code == 200, answer.text
            return answer.json()

        # A Media folder's list: each card's rating beside its year; the R
        # movie Kid may not see isn't there, so neither is its rating.
        movies = {c["key"]: c for c in got("/api/internal/libraries/2")["items"]}
        assert set(movies) == {"300"}
        assert movies["300"]["contentRating"] == "PG"
        shows = {c["key"]: c for c in got("/api/internal/libraries/1")["items"]}
        assert shows["100"]["contentRating"] == "TV-Y7"
        # A show's page, and the episode Up next names.
        page = got("/api/internal/items/100")
        assert page["contentRating"] == "TV-Y7"
        assert page["next"]["key"] == "201" and page["next"]["contentRating"] == "TV-Y7"
        # An episode's own page: the stricter of its own and its show's.
        assert got("/api/internal/items/203")["contentRating"] == "TV-PG"
        assert got("/api/internal/items/202")["contentRating"] == "TV-Y7"
        # Search's cards too.
        found = got("/api/internal/search?q=picnic")["items"]
        assert [c["contentRating"] for c in found if c["key"] == "300"] == ["PG"]

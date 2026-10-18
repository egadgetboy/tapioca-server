"""The one program check (1.40.0; the owner, October 18, Q-2 and Q-7: "one
shared program-level access-control mechanism", enforced the same on every
playback path). Every way of watching asks viewing.Viewer.sees: a Station's
pieces as they air (1.39.0), Media as it starts, and now Media while it
plays. Two of its rules wait for their features: episodes hidden for
someone (the hiding release) and Viewing Levels that need Clean audio
(Clean audio's release C), which never takes "not known" for ready (D04).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import ondemand
from app.titles import Judged
from app.viewing import UNRESTRICTED, Level, Viewer

from . import test_who_sees_what as who
from .test_who_sees_what import ADA, KIT, TV, kid_level, set_up, sign_in_app

# (Who sees what's library and app, as its tests have them.)
plex = who.plex
app = who.app

OPEN = Level(1, "Unrestricted", None, None, True, None, UNRESTRICTED)


def episode(key: str, show: str = "110", clean: bool | None = None) -> Judged:
    return Judged(True, 18, "1", True, show, None, own_key=key, clean=clean)


def test_an_episode_hidden_for_someone_is_refused_and_its_show_isnt():
    kit = Viewer(OPEN, everything=False, hidden=frozenset({"212"}))
    assert not kit.sees(episode("212"))
    assert kit.sees(episode("211"))
    # (The show itself, and so every Station that plays it, stays: Q-2.)
    assert kit.sees(Judged(True, 18, "1", True, "110", None, own_key="110"))


def test_a_level_that_needs_clean_audio_never_takes_unknown_for_ready():
    kit = Viewer(OPEN, everything=False, needs_clean=True)
    assert not kit.sees(episode("211", clean=None))  # (not known: D04, fails closed)
    assert not kit.sees(episode("211", clean=False))
    assert kit.sees(episode("211", clean=True))


def test_an_admins_exception_for_a_show_never_brings_back_a_hidden_episode():
    from app.viewing import Person

    kit = Viewer(
        Level(2, "Kid", 7, 7, False, None, "kid"), everything=False,
        own=Person(allowed=(("110", "Night Shift"),)), hidden=frozenset({"212"}),
    )  # fmt: skip
    assert kit.sees(episode("211"))
    assert not kit.sees(episode("212"))


def test_someone_with_neither_watches_as_before(app):
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        viewing = app.state.ctx.viewing
        viewer = viewing.viewer(app.state.ctx.db.user(kit["id"]))
        assert viewer.everything and viewer.hidden == frozenset() and not viewer.needs_clean


def file_of(phone: TestClient, played: dict, headers: dict):
    return phone.get(played["url"], headers=headers)


def test_a_title_stops_when_its_persons_limits_change_while_it_plays(app, monkeypatch):
    """Before 1.40.0, Media was checked only as it started: an Admin who
    put someone on Kid mid-movie left the R movie playing to its end."""
    monkeypatch.setattr(ondemand, "LIMITS_RECHECK_S", 0.0)
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        heist = phone.post("/api/internal/play", json={"key": "301", "device": TV}, headers=as_kit)
        assert heist.status_code == 200, heist.text
        heist = heist.json()
        assert file_of(phone, heist, as_kit).status_code == 200

        # Kit is put on Kid while Heist (R) plays.
        changed = admin.put(
            f"/api/access/users/{kit['id']}/viewing", json={"level": kid_level(admin)}
        )
        assert changed.status_code == 200, changed.text
        refused = file_of(phone, heist, as_kit)
        assert refused.status_code == 403
        assert refused.json() == {"detail": "This title is restricted.", "code": "restricted"}
        # Its play is over: nothing more of it, as for any play that ended.
        assert file_of(phone, heist, as_kit).status_code == 404
        # What's still allowed plays on through a change: Picnic (PG), as Kit
        # moves from Kid to Teen.
        picnic = phone.post("/api/internal/play", json={"key": "300", "device": TV}, headers=as_kit)
        assert picnic.status_code == 200, picnic.text
        levels = admin.get("/api/access/viewing").json()["levels"]
        teen = next(lv["id"] for lv in levels if lv["builtin"] == "teen")
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": teen})
        assert file_of(phone, picnic.json(), as_kit).status_code == 200
        logs = admin.get("/api/logs?access_log=true").json()["text"]
        assert "Kit's Heist" in logs and "stopped: their limits no longer allow it" in logs


def test_a_check_that_cant_reach_the_library_leaves_the_title_playing(app, monkeypatch):
    """Plex going quiet mid-movie never stops what's already allowed: the
    last check stands until one can be made (a Station's unknown pieces are
    different: they're what it's about to send)."""
    monkeypatch.setattr(ondemand, "LIMITS_RECHECK_S", 0.0)
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        admin.post("/api/access/users", json={**KIT, "role": "user"})
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        played = phone.post("/api/internal/play", json={"key": "300", "device": TV}, headers=as_kit)
        assert played.status_code == 200, played.text
        from app.library import LibraryError

        async def unreachable(*_a, **_k):
            raise LibraryError("Plex didn't answer")

        monkeypatch.setattr(app.state.ctx.catalog, "entry", unreachable)
        assert file_of(phone, played.json(), as_kit).status_code == 200


@pytest.mark.parametrize("ask", ["index.m3u8", "piece-0.ts"])
def test_a_copy_stops_too(app, monkeypatch, ask):
    monkeypatch.setattr(ondemand, "LIMITS_RECHECK_S", 0.0)
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        session = phone.post(
            "/api/internal/play", json={"key": "301", "device": TV}, headers=as_kit
        ).json()["session"]
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": kid_level(admin)})
        refused = phone.get(f"/play/{session}/{ask}", headers=as_kit)
        assert refused.status_code == 403
        assert refused.json()["code"] == "restricted"


def test_the_card_preview_never_plays_or_names_a_station_blocked_for_its_maker(app, monkeypatch):
    """Before 1.40.0, someone who makes Stations could preview an Intro
    Bumper for any Station by its id, hearing a few seconds of what it
    plays now and seeing what's on, even one an Admin blocked for them."""
    from app import intro

    asked: list[str] = []

    def whats_on(station, at_ms):
        asked.append("whats_on")
        return (("", "Shift 1", "S1 E1"), None)

    async def find_show_audio(ctx, station, at_ms, seconds):
        asked.append("audio")
        return

    monkeypatch.setattr(intro, "whats_on", whats_on)
    monkeypatch.setattr(intro, "find_show_audio", find_show_audio)
    with TestClient(app) as admin:
        ids = set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"stations": {str(ids[5]): False}})
        page = TestClient(app)
        assert page.post("/api/access/sign-in", json=KIT).status_code == 200
        card = {"number": 5, "name": "Late Night", "seconds": 3, "sound": False}
        made = page.post("/api/intro/preview", json={**card, "channelId": ids[5]})
        assert made.status_code == 200, made.text
        assert asked == []
        # (A Station they may see is previewed with what it plays, as before.)
        assert (
            page.post("/api/intro/preview", json={**card, "channelId": ids[3]}).status_code == 200
        )
        assert "whats_on" in asked


def test_the_up_next_preview_never_names_whats_next_on_a_station_blocked_for_its_maker(
    app, monkeypatch
):
    """The same, for the Up Next Banner's preview: it named what's up next
    on any Station by its id."""
    from app import intro

    named: list[str] = []
    real = intro.describe

    def describe(item):
        named.append(item.rating_key)
        return real(item)

    monkeypatch.setattr(intro, "describe", describe)
    with TestClient(app) as admin:
        ids = set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"stations": {str(ids[5]): False}})
        page = TestClient(app)
        assert page.post("/api/access/sign-in", json=KIT).status_code == 200
        banner = {"number": 5, "name": "Late Night", "seconds": 10}
        made = page.post("/api/upnext/preview", json={**banner, "channelId": ids[5]})
        assert made.status_code == 200, made.text
        assert named == []
        assert (
            page.post("/api/upnext/preview", json={**banner, "channelId": ids[3]}).status_code
            == 200
        )
        assert named

"""The one program check (1.40.0; the owner, October 18, Q-2 and Q-7: "one
shared program-level access-control mechanism", enforced the same on every
playback path). Every way of watching asks viewing.Viewer.sees: a Station's
pieces as they air (1.39.0), Media as it starts, and now Media while it
plays. Two of its rules wait for their features: episodes hidden for
someone (the hiding release) and Viewing Levels that need Clean audio
(Clean audio's release C), which never takes "not known" for ready (D04).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app import applibrary, ondemand, viewing
from app.db import Item
from app.titles import Judged
from app.viewing import EVERYONE, UNRESTRICTED, Level, Viewer

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


def test_the_rules_still_to_come_refuse_even_someone_without_limits():
    """The hiding handoff: hidden episodes and required Clean audio are
    checked before `everything`, which keeps its meaning (no limits decide
    what they see), so neither makes anyone limited. 1.40.0's cold audit:
    they were checked after it, so they never refused anyone it covered."""
    ada = Viewer(OPEN, everything=True, hidden=frozenset({"212"}))
    assert not ada.sees(episode("212")) and ada.sees(episode("211"))
    clean = Viewer(OPEN, everything=True, needs_clean=True)
    assert not clean.sees(episode("211")) and clean.sees(episode("211", clean=True))
    # (Media's shortcuts skip the check only when nothing at all is checked.)
    assert EVERYONE.unchecked and not ada.unchecked and not clean.unchecked


def test_the_rules_still_to_come_reach_media_and_stations_without_limiting_anyone(
    app, monkeypatch
):
    """Wired the way the hiding release and Clean audio's release C will
    fill them: an episode hidden for Kit (who has no limits) is gone from
    the show's episodes, never plays and is blanked as it airs; yet Kit
    still sees everything else, makes Stations and isn't watch-only."""
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        ctx = app.state.ctx
        user = ctx.db.user(kit["id"])
        monkeypatch.setattr(
            viewing.Viewing, "hidden_for",
            lambda self, u: frozenset({"212"}) if u.id == kit["id"] else frozenset(),
        )  # fmt: skip
        viewer = ctx.viewing.viewer(user)
        assert viewer.everything and viewer.hidden == frozenset({"212"})
        assert not ctx.viewing.watches_only(user)  # (unchanged: the hiding handoff)
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        episodes = phone.get("/api/internal/items/110/episodes", headers=as_kit)
        assert episodes.status_code == 200, episodes.text
        keys = {e["key"] for e in episodes.json()["episodes"]}
        assert "211" in keys and "212" not in keys
        played = phone.post("/api/internal/play", json={"key": "212", "device": TV}, headers=as_kit)
        assert played.status_code == 404
        played = phone.post("/api/internal/play", json={"key": "211", "device": TV}, headers=as_kit)
        assert played.status_code == 200, played.text
        airing = Item(0, 0, 1000, "212", "episode", "Shift 2", "Night Shift", "110", 1, 2)
        assert not ctx.viewing.may_watch(viewer, airing)
        assert ctx.viewing.may_watch(viewer, Item(0, 0, 1000, "211", "episode", "Shift 1",
                                                  "Night Shift", "110", 1, 1))  # fmt: skip

        # Clean audio needed: nothing plays whose Clean audio isn't known
        # to be ready (none is, yet), and Kit still isn't limited.
        monkeypatch.setattr(viewing.Viewing, "needs_clean", lambda self, u: u.id == kit["id"])
        viewer = ctx.viewing.viewer(user)
        assert viewer.everything and viewer.needs_clean and not ctx.viewing.watches_only(user)
        played = phone.post("/api/internal/play", json={"key": "300", "device": TV}, headers=as_kit)
        assert played.status_code == 404


def file_of(phone: TestClient, played: dict, headers: dict):
    return phone.get(played["url"], headers=headers)


def until(check, seconds: float = 5.0):
    """Waits for `check()` to give something (the background check runs
    every LIMITS_WATCH_S)."""
    ends = time.monotonic() + seconds
    while True:
        got = check()
        if got or time.monotonic() > ends:
            return got
        time.sleep(0.02)


def test_a_title_stops_when_its_persons_limits_change_while_it_plays(app, monkeypatch, caplog):
    """Before 1.40.0, Media was checked only as it started: an Admin who
    put someone on Kid mid-movie left the R movie playing to its end."""
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(ondemand, "LIMITS_WATCH_S", 0.05)
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

        # Kit is put on Kid while Heist (R) plays: the background check stops
        # it, with nothing asked of the player.
        changed = admin.put(
            f"/api/access/users/{kit['id']}/viewing", json={"level": kid_level(admin)}
        )
        assert changed.status_code == 200, changed.text
        assert until(lambda: app.state.ctx.plays.find(heist["session"]) is None)
        refused = file_of(phone, heist, as_kit)
        assert refused.status_code == 403
        assert refused.json() == {"detail": "This title is restricted.", "code": "restricted"}
        # (And again: its app may ask more than once before it shows it.)
        assert file_of(phone, heist, as_kit).status_code == 403
        # Its app starting it again, or saying where it was, is told the same,
        # never that it isn't in a Media folder (the cold audit: the apps
        # said it "didn't start" and reported a problem with its file).
        again = phone.post("/api/internal/play", json={"key": "301", "device": TV}, headers=as_kit)
        assert again.status_code == 403
        assert again.json() == {"detail": "This title is restricted.", "code": "restricted"}
        where = phone.post(
            "/api/internal/progress",
            json={"key": "301", "positionMs": 60_000, "session": heist["session"]},
            headers=as_kit,
        )
        assert where.status_code == 403 and where.json()["code"] == "restricted"
        # (A title they never watched stays unseen: 404, as before.)
        assert (
            phone.post("/api/internal/play", json={"key": "211", "device": TV}, headers=as_kit)
            .status_code
            == 404
        )

        # What's still allowed plays on through a change: Picnic (PG), as Kit
        # moves from Kid to Teen.
        picnic = phone.post("/api/internal/play", json={"key": "300", "device": TV}, headers=as_kit)
        assert picnic.status_code == 200, picnic.text
        levels = admin.get("/api/access/viewing").json()["levels"]
        teen = next(lv["id"] for lv in levels if lv["builtin"] == "teen")
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": teen})
        time.sleep(0.3)  # (several checks)
        assert file_of(phone, picnic.json(), as_kit).status_code == 200
        logs = admin.get("/api/logs?access_log=true").json()["text"]
        assert logs.count("Kit's Heist") == 1
        assert "stopped: their limits no longer allow it" in logs
        said = [r.getMessage() for r in caplog.records]
        assert any(m.startswith("Kit stopped Heist") for m in said)  # (as any stop is said)


def test_an_admin_who_allows_it_again_lets_it_play(app, monkeypatch):
    monkeypatch.setattr(ondemand, "LIMITS_WATCH_S", 3600.0)
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        heist = phone.post("/api/internal/play", json={"key": "301", "device": TV}, headers=as_kit)
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": kid_level(admin)})
        assert admin.portal.call(app.state.ctx.stop_restricted) == 1
        assert admin.portal.call(app.state.ctx.stop_restricted) == 0  # (said once)
        levels = admin.get("/api/access/viewing").json()["levels"]
        everyone = next(lv["id"] for lv in levels if lv["builtin"] == UNRESTRICTED)
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": everyone})
        again = phone.post("/api/internal/play", json={"key": "301", "device": TV}, headers=as_kit)
        assert again.status_code == 200, again.text
        assert again.json()["session"] != heist.json()["session"]


def test_playing_never_waits_on_plex_for_the_check(app, monkeypatch):
    """The cold audit: the check asked Plex on the player's own requests,
    so a slow Plex held up every range request (and Plex down stopped what
    was allowed). Now it's judged in the background, from what's known."""
    monkeypatch.setattr(ondemand, "LIMITS_WATCH_S", 0.05)
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": kid_level(admin)})
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        played = phone.post(
            "/api/internal/play", json={"key": "201", "device": TV}, headers=as_kit
        )  # (Puppets 1: TV-Y7, an episode, judged by its show)
        assert played.status_code == 200, played.text
        cat = app.state.ctx.catalog
        asked: list[str] = []

        async def slow(*_a, **_k):
            asked.append("Plex")
            await asyncio.sleep(30)

        monkeypatch.setattr(cat, "entry", slow)
        monkeypatch.setattr(cat.titles, "ensure", slow)
        began = time.monotonic()
        for _ in range(3):
            assert file_of(phone, played.json(), as_kit).status_code == 200
        assert time.monotonic() - began < 3
        assert admin.portal.call(app.state.ctx.stop_restricted) == 0
        assert asked == []
        assert app.state.ctx.plays.find(played.json()["session"]) is not None


def test_what_isnt_known_now_leaves_an_allowed_title_playing(app, monkeypatch):
    """The cold audit: tags not known as it's checked again (Plex down, or
    just forgotten) stopped a title its limits allow. It was allowed, so it
    stands; only what's known to be refused stops."""
    monkeypatch.setattr(ondemand, "LIMITS_WATCH_S", 3600.0)
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        hides = {"own": {"blocks": {"genres": ["horror"]}}}
        assert admin.put(f"/api/access/users/{kit['id']}/viewing", json=hides).status_code == 200
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        picnic = phone.post("/api/internal/play", json={"key": "300", "device": TV}, headers=as_kit)
        assert picnic.status_code == 200, picnic.text
        on_tv = sign_in_app(app, KIT)  # (another device: one plays at a time on each)
        shift = phone.post("/api/internal/play", json={"key": "211", "device": TV}, headers=on_tv)
        assert shift.status_code == 200, shift.text
        ctx = app.state.ctx
        monkeypatch.setattr(ctx.catalog.titles, "tags", lambda key: None)
        session = ctx.plays.find(shift.json()["session"])
        if session is not None:
            session.show = None  # (its show not known either)
        assert admin.portal.call(ctx.stop_restricted) == 0
        assert file_of(phone, picnic.json(), as_kit).status_code == 200


@pytest.mark.parametrize("ask", ["index.m3u8", "piece-0.ts"])
def test_a_copy_stops_too(app, monkeypatch, ask):
    monkeypatch.setattr(ondemand, "LIMITS_WATCH_S", 3600.0)
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
        assert admin.portal.call(app.state.ctx.stop_restricted) == 1
        refused = phone.get(f"/play/{session}/{ask}", headers=as_kit)
        assert refused.status_code == 403
        assert refused.json()["code"] == "restricted"


def test_no_problem_is_reported_for_a_title_its_limits_stopped(app, monkeypatch):
    """The cold audit: the apps report a title that stops as a problem with
    its file (an Admin's Problems row, and its file checked)."""
    monkeypatch.setattr(ondemand, "LIMITS_WATCH_S", 3600.0)
    from app import scanner

    checked: list[str] = []
    monkeypatch.setattr(scanner, "trouble", lambda ctx, e, *a: checked.append(e.key))
    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        as_kit = sign_in_app(app, KIT)
        phone = TestClient(app)
        heist = phone.post("/api/internal/play", json={"key": "301", "device": TV}, headers=as_kit)
        session = heist.json()["session"]
        admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": kid_level(admin)})
        assert admin.portal.call(app.state.ctx.stop_restricted) == 1
        device = {"app": "tapiOca for Android", "version": "0.7.0", "device": "Pixel 8"}
        for about in ({"session": session}, {}):  # (its own, or the device's last)
            sent = phone.post(
                "/api/internal/problem",
                json={"kind": "library-failed", "title": "Heist", "detail": "This title is "
                      "restricted.", **device, **about},
                headers=as_kit,
            )  # fmt: skip
            assert sent.status_code == 200, sent.text
        assert checked == []
        problems = admin.get("/api/problems?days=7").json()["problems"]
        assert problems == []


# A long request, over a real connection --------------------------------------------


PAGE = {"X-tapiOca-Page": "1"}  # (as the page sends: access.PAGE_HEADER)


class Endless(httpx.AsyncByteStream):
    """A file from Plex that never ends, sent as fast as it's read."""

    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self):
        while True:
            await asyncio.sleep(0)
            yield b"\0" * 65536

    async def aclose(self) -> None:
        self.closed = True


async def _a_long_request_is_cut(app, tmp_path, where: str) -> dict:
    ctx = app.state.ctx
    upstream = Endless()
    if where == "plex":
        ctx.play_transport = httpx.MockTransport(
            lambda request: httpx.Response(
                206, headers={"content-range": "bytes 0-9999999999/10000000000",
                              "content-length": "10000000000"}, stream=upstream,
            )
        )  # fmt: skip
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(0.01)
    said: list[str] = []

    class Said(logging.Handler):
        def emit(self, record):
            said.append(record.getMessage())

    heard = Said()
    logging.getLogger("uvicorn.error").addHandler(heard)
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", headers=PAGE) as admin:
            for number, (name, sources) in who.STATIONS.items():
                made = await admin.post(
                    "/api/channels", json={"number": number, "name": name, "sources": sources}
                )
                assert made.status_code == 201, made.text
            await ctx.titles.filled()
            await admin.put("/api/app-libraries", json={"libraries": ["1", "2"]})
            await admin.post("/api/access/users", json=ADA)
            kit = (await admin.post("/api/access/users", json={**KIT, "role": "user"})).json()
            signed = await admin.post("/api/internal/sign-in", json=KIT)
            as_kit = {"Authorization": f"Bearer {signed.json()['token']}"}
            levels = (await admin.get("/api/access/viewing")).json()["levels"]
            kid = next(lv["id"] for lv in levels if lv["builtin"] == "kid")
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", headers=PAGE) as phone:
            played = await phone.post(
                "/api/internal/play", json={"key": "301", "device": TV}, headers=as_kit
            )
            assert played.status_code == 200, played.text
            played = played.json()
            if where == "disk":
                big = tmp_path / "heist.mkv"
                with big.open("wb") as f:
                    f.truncate(2_000_000_000)
                ctx.plays.find(played["session"]).path = str(big)
            got = 0
            cut = False
            async with phone.stream("GET", played["url"], headers={**as_kit, "Range": "bytes=0-"}) as r:
                assert r.status_code == 206
                chunks = r.aiter_raw()
                got += len(await chunks.__anext__())
                await asyncio.sleep(0.3)  # (the player's buffer is full: it stops reading)
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", headers=PAGE) as admin2:
                    await admin2.post("/api/access/sign-in", json=ADA)
                    changed = await admin2.put(
                        f"/api/access/users/{kit['id']}/viewing", json={"level": kid}
                    )
                    assert changed.status_code == 200, changed.text
                await asyncio.sleep(0.5)  # (the background check stops it)
                try:
                    async for chunk in chunks:
                        got += len(chunk)
                        assert got < 1_000_000_000, "never cut"
                except httpx.RemoteProtocolError:
                    cut = True
            return {"cut": cut, "got": got, "said": said, "closed": upstream.closed}
    finally:
        logging.getLogger("uvicorn.error").removeHandler(heard)
        server.should_exit = True
        await serving


@pytest.mark.parametrize("where", ["disk", "plex"])
def test_a_long_request_is_cut_as_its_title_stops(app, monkeypatch, tmp_path, where):
    """The cold audit: a direct play's one long range request (ExoPlayer's
    "bytes=0-") kept streaming the whole file after the stop, as only new
    requests were checked."""
    monkeypatch.setattr(ondemand, "LIMITS_WATCH_S", 0.05)
    found = asyncio.run(_a_long_request_is_cut(app, tmp_path, where))
    assert found["cut"]
    assert not [s for s in found["said"] if "ASGI" in s or "Exception" in s], found["said"]
    if where == "plex":
        assert found["closed"]  # (nothing left open to Plex)


def test_only_a_cut_quiets_the_unfinished_answer_line():
    quiet = applibrary._QuietCut()
    line = logging.LogRecord("uvicorn.error", logging.ERROR, "", 0, applibrary.UNFINISHED, (), None)
    assert quiet.filter(line)  # (anything else unfinished is still said)
    token = applibrary._cut.set(True)
    try:
        assert not quiet.filter(line)
        other = logging.LogRecord("uvicorn.error", logging.ERROR, "", 0, "Exception", (), None)
        assert quiet.filter(other)
    finally:
        applibrary._cut.reset(token)


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

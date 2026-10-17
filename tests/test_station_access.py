"""Station access and program access (1.39.0, the owner, October 17,
2:49 PM): "Station visibility determines what users can choose. Program
restrictions determine what they can actually watch."

Which Stations someone with limits sees is as before: one whose lineup is
above their level is hidden, unless an Admin allows it for them by hand.
Allowing a Station never allows what's on it: on every Station, the program
actually airing is checked against their level, ratings, tags and what's
hidden or allowed for them. While one they may not watch is on, their app's
stream refuses them ("This program is restricted..."), and every guide
shows it to them as "Restricted program", its times and nothing else. The
shared broadcast never stops, and their stream is back when permitted
programming is. Unrated titles follow their level unless an Admin allows
the title for them."""

from __future__ import annotations

import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import hls
from app.config import Settings
from app.db import NewEra
from app.main import RESTRICTED_PROGRAM, create_app
from app.plex import PlexClient

from .fakeplex_library import LibraryPlex
from .test_who_sees_what import ADA, KIT, kid_level, set_up, sign_in_app

HOUR = 3_600_000


@pytest.fixture
def app(tmp_path):
    """As tests/test_who_sees_what.py's (Puppet Town, TV-Y7; Night Shift,
    TV-MA; Picnic, PG; Heist, R), and Beach Day, a home video with no
    rating."""
    fp = LibraryPlex()
    fp.add_show("100", "Puppet Town", contentRating=["TV-Y7"])
    for n in range(1, 4):
        fp.add_episode(f"20{n}", "100", 1, n, f"Puppets {n}", f"/tv/p/{n}.mkv", 22 * 60_000)
    fp.add_show("110", "Night Shift", contentRating=["TV-MA"])
    for n in range(1, 3):
        fp.add_episode(f"21{n}", "110", 1, n, f"Shift {n}", f"/tv/n/{n}.mkv", 44 * 60_000)
    fp.add_section("2", "Movies", "movie")
    fp.add_movie("300", "Picnic", "/m/picnic.mkv", 90 * 60_000, section="2", contentRating=["PG"])
    fp.add_movie("301", "Heist", "/m/heist.mkv", 100 * 60_000, section="2", contentRating=["R"])
    fp.add_movie("302", "Beach Day", "/m/beach.mkv", 30 * 60_000, section="2")
    for key in ("201", "211", "300", "301", "302"):
        fp.describe(key)
        fp.files[key] = b"a program" * 100
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data")
    made = create_app(settings, PlexClient("http://plex.test", "token", transport=fp.transport()))
    made.state.ctx.play_transport = fp.transport()
    return made


def kid(admin: TestClient, stations: dict[str, bool] | None = None) -> int:
    """Ada (the Admin), and Kit, on the Kid level (with `stations` allowed
    or blocked by hand): Kit's id."""
    admin.post("/api/access/users", json=ADA)
    kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
    body: dict = {"level": kid_level(admin)}
    if stations:
        body["stations"] = stations
    assert admin.put(f"/api/access/users/{kit['id']}/viewing", json=body).status_code == 200
    return kit["id"]


def numbers(phone: TestClient, headers: dict) -> list[int]:
    return [s["number"] for s in phone.get("/api/v1/stations", headers=headers).json()["stations"]]


def items(ctx, keys: set[str]) -> list:
    """Programs that are `keys`, from any station's lineup."""
    found = {}
    for c in ctx.db.list_channels():
        for e in ctx.db.eras(c.id):
            for i in e.items:
                if i.rating_key in keys:
                    found.setdefault(i.rating_key, i)
    return [found[k] for k in sorted(found)]


def loop(programs: list) -> list:
    out, at = [], 0
    for n, item in enumerate(programs):
        out.append(replace(item, position=n, start_ms=at))
        at += item.duration_ms
    return out


def plays(ctx, channel_id: int, programs: list, since_ms: int) -> None:
    """The station plays `programs`, in order, over and over, from `since_ms`."""
    old = [e.id for e in ctx.db.eras(channel_id)]
    now = int(time.time() * 1000)
    ctx.db.replace_eras(
        channel_id, old, [NewEra(loop(programs), None, since_ms, "a", "in-order", now, "test")]
    )


def test_a_station_allowed_by_hand_stays_listed(app):
    """Mixed plays Puppet Town and Heist (R), over and over. Allowed for
    Kit by hand, it's listed for her the whole time (1.38.0's rule for which
    stations someone sees, kept); Late Night, never allowed, stays hidden."""
    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[7]): True})
        assert numbers(TestClient(app), sign_in_app(app, KIT)) == [3, 7, 9]


def test_her_guide_shows_what_she_may_not_watch_as_restricted(app):
    """Kit's guide for Mixed: Heist, past, now and later, is "Restricted
    program", its times and nothing else; Puppet Town is as it is. Ada's
    has Heist."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[7]): True})
        now = int(time.time() * 1000)
        plays(ctx, ids[7], items(ctx, {"201", "301"}), now - 30 * 60_000)  # (Heist on now)
        as_kit, as_ada = sign_in_app(app, KIT), sign_in_app(app, ADA)
        phone = TestClient(app)
        ask = f"/api/v1/guide?from={now - 3 * HOUR}&to={now + 6 * HOUR}"
        got = phone.get(ask, headers=as_kit)
        assert got.status_code == 200 and "Heist" not in got.text and "/art/301" not in got.text
        seven = next(s for s in got.json()["stations"] if s["number"] == 7)
        hidden = [p for p in seven["programs"] if p["restricted"]]
        shown = [p for p in seven["programs"] if not p["restricted"]]
        assert hidden and shown
        assert all(
            (p["title"], p["episodeTitle"], p["summary"], p["year"], p["art"], p["special"])
            == ("Restricted program", None, "", None, "/art/0", None)
            and p["end"] - p["start"] == 100 * 60_000
            for p in hidden
        )
        assert {p["title"] for p in shown} == {"Puppet Town"}
        assert "Heist" in phone.get(ask, headers=as_ada).text
        # Now and next, and the page's guide and list of stations: the same.
        stations = {
            s["number"]: s for s in phone.get("/api/v1/stations", headers=as_kit).json()["stations"]
        }
        assert (
            stations[7]["now"]["restricted"] and stations[7]["now"]["title"] == "Restricted program"
        )
        page = TestClient(app)
        page.post("/api/access/sign-in", json=KIT)
        assert "Heist" not in page.get(f"/api/channels/{ids[7]}/guide").text
        assert "Heist" not in page.get("/api/channels").text
        # Search never finds a station by what she may not watch.
        found = phone.get("/api/internal/search?q=heist", headers=as_kit).json()
        assert all(s["number"] != 7 for s in found.get("onNow", []))


def test_unrated_needs_an_admins_exception_for_her(app):
    """Beach Day has no rating, and Kid hides what isn't rated. A station of
    it allowed for Kit by hand shows, but Beach Day is restricted for her
    until an Admin allows that title for her: allowing the station never
    does."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        made = admin.post("/api/channels", json={
            "number": 4, "name": "Family", "sources": [{"type": "movie", "ratingKey": "302"}]})  # fmt: skip
        assert made.status_code == 201, made.text
        home = made.json()["id"]
        admin.portal.call(ctx.titles.filled)
        kit_id = kid(admin, {str(home): True})
        kit = ctx.viewing.viewer(ctx.db.user(kit_id))
        beach = items(ctx, {"302"})[0]
        assert 4 in numbers(TestClient(app), sign_in_app(app, KIT))
        assert not ctx.viewing.may_watch(kit, beach)
        own = {"blocks": {}, "allowTitles": [{"key": "302", "title": "Beach Day"}]}
        assert (
            admin.put(f"/api/access/users/{kit_id}/viewing", json={"own": own}).status_code == 200
        )
        assert ctx.viewing.may_watch(ctx.viewing.viewer(ctx.db.user(kit_id)), beach)
        assert ids  # (the other stations as set up)


def test_an_episode_rated_above_its_show_is_restricted(app):
    ctx = app.state.ctx
    with TestClient(app) as admin:
        set_up(admin)
        now = int(time.time() * 1000)
        ctx.db.save_titles([("202", "episode", "TV-14", "1", now, now)])
        ctx.titles.__init__(ctx.db)  # (read again, as on a restart)
        kit = ctx.viewing.viewer(ctx.db.user(kid(admin)))
        assert not ctx.viewing.may_watch(kit, items(ctx, {"202"})[0])
        assert ctx.viewing.may_watch(kit, items(ctx, {"201"})[0])


class FakeStream:
    """A station's stream for apps, with pieces s1 to s3 holding `holds`."""

    def __init__(self, holds: dict[str, tuple]) -> None:
        self.holds = holds

    def asked_by(self, *args, **kwargs) -> None: ...

    def still_watching(self, client) -> None: ...

    async def playlist(self) -> str:
        return "#EXTM3U\n" + "".join(f"#EXTINF:2.0,\n{n}\n" for n in self.holds)

    listed = hls.HlsStream.listed

    def pieces_hold(self, names) -> tuple:
        return tuple(c for n in names for c in self.holds.get(n, (hls.UNKNOWN,)))

    async def piece(self, name: str) -> bytes | None:
        return b"piece" if name in self.holds else None


def test_her_stream_refuses_a_restricted_program_and_comes_back(app, monkeypatch):
    """While a piece of Heist is in Mixed's stream, Kit's app is refused
    its playlist and that piece (her app says so, and when the schedule
    says the station's back); Ada's isn't. Once only Puppet Town is in it,
    Kit's is back, with nothing to do. And when she's put on Kid while
    watching, her next ask is refused."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kit_id = kid(admin, {str(ids[7]): True})
        heist, puppet = items(ctx, {"301"})[0], items(ctx, {"201"})[0]
        stream = FakeStream({"s1.ts": (puppet,), "s2.ts": (None, heist), "s3.ts": (heist,)})
        monkeypatch.setattr(ctx.hls_streams, "get", lambda cid, night=False: stream)
        as_kit, as_ada = sign_in_app(app, KIT), sign_in_app(app, ADA)
        phone, tablet = TestClient(app), TestClient(app)

        def address(client: TestClient, headers: dict) -> str:
            got = client.get("/api/v1/stations", headers=headers).json()["stations"]
            return next(s for s in got if s["number"] == 7)["hls"].split("?")[0]

        kits, adas = address(phone, as_kit), address(tablet, as_ada)
        refused = phone.get(kits)
        assert refused.status_code == 403, refused.text
        said = refused.json()
        assert said["detail"] == RESTRICTED_PROGRAM and said["code"] == "restricted"
        assert said["resumesAtMs"] is None or said["resumesAtMs"] >= int(time.time() * 1000) - 1000
        assert phone.get(kits.replace("index.m3u8", "s2.ts")).status_code == 403
        assert phone.get(kits.replace("index.m3u8", "s1.ts")).status_code == 200
        assert tablet.get(adas).status_code == 200
        assert tablet.get(adas.replace("index.m3u8", "s3.ts")).status_code == 200
        # Night mode's sound: the same.
        assert phone.get(kits.replace("index.m3u8", "night/index.m3u8")).status_code == 403
        # Heist over: only Puppet Town in it, so it's hers again.
        stream.holds = {"s4.ts": (puppet,), "s5.ts": (None,), "s6.ts": (puppet,)}
        assert phone.get(kits).status_code == 200
        # What can't be told is kept from her, to be safe.
        stream.holds = {"s7.ts": (hls.UNKNOWN,)}
        assert phone.get(kits).status_code == 403
        assert tablet.get(adas).status_code == 200
        # Put on Unrestricted, then on Kid while watching: refused at once.
        stream.holds = {"s8.ts": (heist,)}
        admin.put(f"/api/access/users/{kit_id}/viewing", json={"level": None, "stations": {}})
        unrestricted = next(
            lv["id"] for lv in admin.get("/api/access/viewing").json()["levels"]
            if lv["builtin"] == "unrestricted"
        )  # fmt: skip
        admin.put(f"/api/access/users/{kit_id}/viewing", json={"level": unrestricted})
        assert phone.get(kits).status_code == 200
        admin.put(f"/api/access/users/{kit_id}/viewing", json={"level": kid_level(admin)})
        assert phone.get(kits).status_code in (403, 404)


def test_a_piece_holds_what_was_sent_around_it(tmp_path):
    """Which programs a piece holds: whatever the station sent from a little
    before the piece before it appeared until it did (MARGIN_S either side,
    to be safe), and what it was sending when it began; UNKNOWN for what
    was sent before the station's record of it begins."""
    a, b = SimpleNamespace(rating_key="a"), SimpleNamespace(rating_key="b")
    t = time.monotonic()
    station = SimpleNamespace(fed=[(t - 100, a), (t - 10, None), (t - 9, b)])
    stream = hls.HlsStream.__new__(hls.HlsStream)
    stream.b, stream.folder, stream.holds = station, tmp_path, {}
    stream._newest_at, stream._born = None, t - 5
    assert stream.contents(t - 50, t - 20) == (a,)
    assert stream.contents(t - 20, t) == (a, None, b)
    assert stream.contents(t - 200, t) == (hls.UNKNOWN, a, None, b)
    (tmp_path / "s1.ts").write_bytes(b"x")
    stream.label_new_pieces()
    held = stream.holds["s1.ts"]  # (from up to RECENT_S before it began)
    assert a in held and None in held and b in held
    stream._newest_at = time.monotonic() - 0.2
    station.fed.append((time.monotonic(), a))
    (tmp_path / "s2.ts").write_bytes(b"x")
    stream.label_new_pieces()
    assert b in stream.holds["s2.ts"] and a in stream.holds["s2.ts"]
    (tmp_path / "s1.ts").unlink()
    stream.label_new_pieces()
    assert "s1.ts" not in stream.holds
    assert stream.pieces_hold(["s9.ts"]) == (hls.UNKNOWN,)


def test_the_station_never_names_on_screen_what_someone_it_is_allowed_for_may_not_watch(app):
    """One shared picture: on Mixed, allowed for Kit by hand, its Up Next
    Banner and cards say "Stay tuned" before Heist, and name Puppet Town;
    with no one it's allowed for by hand, they name Heist."""
    from app.broadcaster import Broadcaster

    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kit_id = kid(admin, {str(ids[7]): True})
        now = int(time.time() * 1000)
        plays(ctx, ids[7], items(ctx, {"201", "301"}), now - 30 * 60_000)
        station = ctx.station(ids[7])
        on = station.locate(now)
        fake = SimpleNamespace(ctx=ctx, channel_id=ids[7], _skipped=lambda key: False)
        before_heist = on if on.item.rating_key == "201" else station.after(on)
        after_heist = station.after(before_heist)
        assert Broadcaster._up_next(fake, station, before_heist) == ["", "Stay tuned", ""]
        assert Broadcaster._up_next(fake, station, after_heist)[1] == "Puppet Town"
        admin.put(f"/api/access/users/{kit_id}/viewing", json={"stations": {}})
        assert Broadcaster._up_next(fake, station, before_heist)[1] == "Heist"


def test_breaks_go_no_higher_than_the_strictest_level_its_allowed_for(app):
    """Mixed's lineup has an R movie, so its commercials and trailers could
    be rated up to R; allowed for Kit (Kid: 10), no higher than 10, so a
    break never blocks her."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        assert ctx.viewing.clip_most(ids[7], 17) == 17
        kid(admin, {str(ids[7]): True})
        assert ctx.viewing.clip_most(ids[7], 17) == 10
        assert ctx.viewing.clip_most(ids[7], None) is None


@pytest.mark.info_station
def test_info_is_for_everyone(app):
    ctx = app.state.ctx
    with TestClient(app) as admin:
        set_up(admin)
        info = next(c for c in ctx.db.list_channels() if c.number == 99)
        kit = ctx.viewing.viewer(ctx.db.user(kid(admin, {str(info.id): True})))
        slot = ctx.guide(info).locate(int(time.time() * 1000))
        assert slot is not None and ctx.viewing.may_watch(kit, slot.item)


def test_the_page_names_nothing_an_allowed_station_plays(app):
    """(The cold audit of 1.39.0.) A time-of-day block four days out that
    plays Heist, and a Feature Presentation from it: on the page, Kit's
    Puppets (allowed by hand) never names Heist anywhere."""
    import datetime

    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[3]): True})
        far = (datetime.datetime.now().weekday() + 4) % 7
        changed = admin.put(f"/api/channels/{ids[3]}", json={
            "number": 3, "name": "Puppets",
            "sources": [{"type": "show", "ratingKey": "100", "title": "Puppet Town"}],
            "blocks": [{"name": "Late show", "days": str(far), "start": "23:00", "end": "23:59",
                        "sources": [{"type": "movie", "ratingKey": "301", "title": "Heist"}]}],
            "featureMode": "on", "featureDays": str(far),
            "featureSource": {"type": "section", "key": "2", "sectionType": "movie",
                              "title": "Heist"},
        })  # fmt: skip
        assert changed.status_code == 200, changed.text
        page = TestClient(app)
        page.post("/api/access/sign-in", json=KIT)
        got = page.get("/api/channels")
        assert 3 in [c["number"] for c in got.json()]
        assert "Heist" not in got.text
        assert "Heist" in admin.get("/api/channels").text


def test_someone_who_may_change_it_gets_all_of_it(app):
    """(The second cold audit of 1.39.0.) A User on Unrestricted with one
    station blocked has limits, but a station they made and are allowed by
    hand comes whole, blocks and Feature Presentation too, so saving it
    from the editor never wipes them."""
    import datetime

    with TestClient(app) as admin:
        ids = set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        page = TestClient(app)
        page.post("/api/access/sign-in", json=KIT)
        far = (datetime.datetime.now().weekday() + 4) % 7
        made = page.post("/api/channels", json={
            "number": 12, "name": "Mine", "sources": [{"type": "show", "ratingKey": "100"}],
            "blocks": [{"name": "Late show", "days": str(far), "start": "23:00", "end": "23:59",
                        "sources": [{"type": "movie", "ratingKey": "300", "title": "Picnic"}]}],
        })  # fmt: skip
        assert made.status_code == 201, made.text
        mine = made.json()["id"]
        assert admin.put(f"/api/access/users/{kit['id']}/viewing",
                         json={"stations": {str(ids[5]): False, str(mine): True}}).status_code == 200  # fmt: skip
        got = {c["number"]: c for c in page.get("/api/channels").json()}
        assert got[12]["mayChange"] and got[12]["blocks"] and got[12]["sources"]


def test_a_station_they_made_but_may_no_longer_change_names_nothing_either(app):
    """(The last check of 1.39.0's cold audit.) Kit made a station, then was
    put on Kid and allowed it by hand: she only watches now, so she may not
    change it (the page says so: mayChange false), and it comes without
    what it's made of, a block of Heist four days out included."""
    import datetime

    with TestClient(app) as admin:
        set_up(admin)
        admin.post("/api/access/users", json=ADA)
        kit = admin.post("/api/access/users", json={**KIT, "role": "user"}).json()
        page = TestClient(app)
        assert page.post("/api/access/sign-in", json=KIT).status_code == 200
        made = page.post("/api/channels", json={
            "number": 4, "name": "Kit's", "sources": [{"type": "show", "ratingKey": "100"}]})  # fmt: skip
        assert made.status_code == 201, made.text
        cid = made.json()["id"]
        far = (datetime.datetime.now().weekday() + 4) % 7
        changed = admin.put(f"/api/channels/{cid}", json={
            "number": 4, "name": "Kit's", "sources": [{"type": "show", "ratingKey": "100"}],
            "blocks": [{"name": "Late show", "days": str(far), "start": "23:00", "end": "23:59",
                        "sources": [{"type": "movie", "ratingKey": "301", "title": "Heist"}]}],
        })  # fmt: skip
        assert changed.status_code == 200, changed.text
        assert admin.put(f"/api/access/users/{kit['id']}/viewing",
                         json={"level": kid_level(admin), "stations": {str(cid): True}}).status_code == 200  # fmt: skip
        got = page.get("/api/channels")
        mine = {c["number"]: c for c in got.json()}
        assert 4 in mine and mine[4]["mayChange"] is False and "Heist" not in got.text
        refused = page.put(f"/api/channels/{cid}", json={
            "number": 4, "name": "x", "sources": [{"type": "show", "ratingKey": "100"}]})  # fmt: skip
        assert refused.status_code == 403

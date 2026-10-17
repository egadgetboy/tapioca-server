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

import asyncio
import time
from collections import deque
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
        self.watching: list = []
        self.blocked_for = []
        self.order: list[str] = []  # (what it was asked to do, in order)

    def asked_by(self, client=None, *args, **kwargs) -> None:
        if client is not None:
            self.watching.append(client)

    def blocked(self, client, away=False) -> None:
        self.blocked_for.append(client)

    def holds_place(self, client, away=False) -> None:
        self.order.append("holds a place")

    def still_watching(self, client) -> None: ...

    async def playlist(self) -> str:
        self.order.append("playlist")
        return "#EXTM3U\n" + "".join(f"#EXTINF:2.0,\n{n}\n" for n in self.holds)

    listed = hls.HlsStream.listed

    async def pieces_hold(self, names) -> tuple:
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


def bare_stream(folder, fed=(), whole=True, born=None, given=0) -> hls.HlsStream:
    """A station's stream for apps, without its ffmpeg: what it was given
    (`fed`: from when, from how many bytes in, which program)."""
    stream = hls.HlsStream.__new__(hls.HlsStream)
    stream.fed, stream.fed_whole = deque(fed, maxlen=hls.FED_KEPT), whole
    stream.given = given
    stream.folder, stream.holds, stream.ended_because = folder, {}, ""
    stream._born = time.monotonic() if born is None else born
    stream._looked, stream._before_newest = (stream._born, 0), None
    stream._labeling = asyncio.Lock()
    return stream


async def test_a_piece_holds_what_was_sent_around_it(tmp_path):
    """Which programs a piece holds: whatever was given to ffmpeg from a
    little before the piece before it appeared until it did (MARGIN_S either
    side, to be safe), and what it was being given when it began; UNKNOWN
    for what was given before the stream's record of it begins."""
    a, b = SimpleNamespace(rating_key="a"), SimpleNamespace(rating_key="b")
    t = time.monotonic()
    fed = [(t - 100, 0, a), (t - 10, 1000, None), (t - 9, 2000, b)]
    stream = bare_stream(tmp_path, fed, whole=False, born=t - 20, given=3000)
    assert stream.contents(t - 50, t - 20) == (a,)
    assert stream.contents(t - 20, t) == (a, None, b)
    assert stream.contents(t - 200, t) == (hls.UNKNOWN, a, None, b)
    # (By bytes, from whichever is earlier.)
    assert stream.contents(t - 9.5, t, 1500) == (None, b)
    assert stream.contents(t - 9.5, t, 500) == (a, None, b)
    (tmp_path / "s1.ts").write_bytes(b"x")
    await stream.label_new_pieces()
    held = stream.holds["s1.ts"]  # (all since a little before it began)
    assert a in held and None in held and b in held
    stream._before_newest = (time.monotonic() - 0.2, 3000)
    stream.fed.append((time.monotonic(), 3000, a))
    (tmp_path / "s2.ts").write_bytes(b"x")
    await stream.label_new_pieces()
    assert b in stream.holds["s2.ts"] and a in stream.holds["s2.ts"]
    (tmp_path / "s1.ts").unlink()
    await stream.label_new_pieces()
    assert "s1.ts" not in stream.holds
    assert await stream.pieces_hold(["s9.ts"]) == (hls.UNKNOWN,)


async def test_a_piece_after_ffmpeg_stalls_holds_what_it_was_given_before(tmp_path):
    """(The fourth cold audit of 1.39.0.) ffmpeg read the start of a piece,
    then stalled (a slow disk) more than MARGIN_S before the piece before
    it appeared; what it was given just before is Heist's end, older than
    that by the clock. By bytes (what ffmpeg can't have been given and not
    yet put in a piece) the piece still holds Heist, so it isn't Kit's."""
    heist = SimpleNamespace(rating_key="301")
    t = time.monotonic()
    fed = [(t - 60, 0, heist), (t - 4.0, 5_000_000, None)]
    stream = bare_stream(tmp_path, fed, born=t - 70, given=5_100_000)
    stream._before_newest = (t - 0.2, 5_050_000)
    (tmp_path / "s9.ts").write_bytes(b"x")
    await stream.label_new_pieces()
    assert heist in stream.holds["s9.ts"], stream.holds


async def test_several_new_pieces_at_once_each_hold_all_since_the_last(tmp_path):
    """(The cold audit of 1.39.0.) Pieces that appear together (ffmpeg
    catching up) can't be told apart, so each holds everything since the
    last time, Heist's tail included: the first ones, and later ones."""
    heist, ok = SimpleNamespace(rating_key="301"), SimpleNamespace(rating_key="201")
    t = time.monotonic()
    fed = [(t - 60, 0, heist), (t - 5, 9_000_000, ok)]
    stream = bare_stream(tmp_path, fed, born=t - 70, given=9_500_000)
    for n in range(4):
        (tmp_path / f"s{n}.ts").write_bytes(b"x")
    await stream.label_new_pieces()
    assert all(heist in stream.holds[f"s{n}.ts"] for n in range(4))
    # Later: a look with nothing new, one with s4, then Heist and back, and
    # three at once.
    await stream.label_new_pieces()
    (tmp_path / "s4.ts").write_bytes(b"x")
    await stream.label_new_pieces()
    now = time.monotonic()
    stream.fed.extend([(now, 9_500_000, heist), (now + 0.01, 9_600_000, ok)])
    stream.given = 9_700_000
    for n in range(5, 8):
        (tmp_path / f"s{n}.ts").write_bytes(b"x")
    await stream.label_new_pieces()
    held = [stream.holds[f"s{n}.ts"] for n in range(5, 8)]
    assert all(heist in h and ok in h for h in held), held


def test_a_new_stream_starts_its_record_from_nothing(tmp_path):
    """(The cold audit of 1.39.0.) A stream's record starts from nothing
    given to its ffmpeg: its first pieces hold what it was given, never
    UNKNOWN; once its start is forgotten, what came before can't be told."""
    puppet = SimpleNamespace(rating_key="201")
    t = time.monotonic()
    stream = bare_stream(tmp_path, [(t - 2, 0, None), (t - 1.5, 100, puppet)], born=t)
    assert stream.contents(t - 40, t) == (None, None, puppet)
    assert stream.contents(t - 40, t, -hls.SLACK_BYTES) == (None, None, puppet)
    stream.fed_whole = False  # (its start forgotten: what came before can't be told)
    assert stream.contents(t - 40, t)[0] is hls.UNKNOWN


async def test_a_piece_holds_what_ffmpeg_was_given_however_long_ago_it_was_sent(
    tmp_path, monkeypatch
):
    """(The second cold audit of 1.39.0.) What a piece holds goes by what
    the stream's ffmpeg was given, as it was, not when the station sent it.
    Heist's tail and then a card, sent a while before (here, more than
    MARGIN_S): given to ffmpeg late, as a stream that's behind does, and as
    a new stream gets the station's recent bytes after a stall, the pieces
    made from them hold Heist. (By when they were sent, they held only the
    card, and went to Kit.) And a session's old bytes carry their own
    program."""
    from app.broadcaster import Broadcaster

    monkeypatch.setattr(hls, "MARGIN_S", 0.05)
    heist = SimpleNamespace(rating_key="301")
    b = Broadcaster(ctx=SimpleNamespace(), channel_id=1)
    b._task = asyncio.get_running_loop().create_future()  # (as if it's running)
    behind = b.subscribe("app viewers on 7", counted=False)
    b._content = heist
    b._emit(b"heist")
    b._content = None
    b._emit(b"card")
    await asyncio.sleep(0.3)  # (the stall, or the stream behind)
    late = b.subscribe("night-mode app viewers on 7", counted=False)  # (its recent bytes)

    class Ffmpeg:
        def write(self, chunk: bytes) -> None: ...

        async def drain(self) -> None: ...

    for n, viewer in enumerate((behind, late)):
        folder = tmp_path / str(n)
        folder.mkdir()
        # (Long running: a piece just before, with a lot given already.)
        stream = bare_stream(folder, given=50_000_000)
        stream._before_newest = (time.monotonic(), stream.given)
        stream._viewer = viewer
        viewer.queue.put_nowait(None)  # (then the station stops)
        await stream._feed(Ffmpeg())
        assert [c for _at, _byte, c in stream.fed] == [heist, None]
        (folder / "s1.ts").write_bytes(b"x")
        await stream.label_new_pieces()
        assert heist in stream.holds["s1.ts"], (n, stream.holds)
    b._task.cancel()


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


def test_a_refused_app_isnt_watching_and_a_gone_piece_is_just_gone(app, monkeypatch):
    """(The cold audit of 1.39.0.) While Kit's app is refused, it isn't
    counted as watching (her stats never get the restricted program), and
    its watching is ended at once (it keeps its place among the devices an
    Admin allows: see the next test); a piece that's gone is 404, never
    "restricted"."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[7]): True})
        heist, puppet = items(ctx, {"301"})[0], items(ctx, {"201"})[0]
        stream = FakeStream({"s1.ts": (heist,)})
        monkeypatch.setattr(ctx.hls_streams, "get", lambda cid, night=False: stream)
        phone = TestClient(app)
        as_kit = sign_in_app(app, KIT)
        got = phone.get("/api/v1/stations", headers=as_kit).json()["stations"]
        kits = next(s for s in got if s["number"] == 7)["hls"].split("?")[0]
        assert phone.get(kits).status_code == 403
        assert stream.watching == [] and len(stream.blocked_for) == 1
        # (Her place is kept before the wait for the playlist: the second
        # cold audit of 1.39.0.)
        assert stream.order[:2] == ["holds a place", "playlist"], stream.order
        assert phone.get(kits.replace("index.m3u8", "s9.ts")).status_code == 404
        stream.holds = {"s2.ts": (puppet,)}
        assert phone.get(kits).status_code == 200 and len(stream.watching) == 1


def test_a_restricted_programs_special_isnt_named(app):
    """(The cold audit of 1.39.0.) A marathon of Night Shift, on a station
    allowed for Kit by hand: on the page, its programs are "Restricted
    program" with no special (which would name it)."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[5]): True})
        page = TestClient(app)
        page.post("/api/access/sign-in", json=KIT)
        guide = page.get(f"/api/channels/{ids[5]}/guide").json()
        assert guide and all(p.get("restricted") and p["special"] is None for p in guide)
        now = {c["number"]: c for c in page.get("/api/channels").json()}[5]["now"]
        assert now["restricted"] and now["special"] is None
        assert "Night Shift" not in page.get("/api/channels").text
        assert ctx  # (as set up)


def test_a_restricted_programs_picture_isnt_asked_of_plex(app):
    with TestClient(app) as admin:
        set_up(admin)
        assert admin.get("/art/0").status_code == 404


def test_a_report_from_a_station_is_never_of_a_program_they_may_not_watch(app):
    """(The cold audit of 1.39.0.) Kit reports a problem from Mixed while
    Heist is on: not filed in her name against Heist, as for nothing on."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[7]): True})
        now = int(time.time() * 1000)
        plays(ctx, ids[7], items(ctx, {"301"}), now - 10 * 60_000)
        phone = TestClient(app)
        said = phone.post("/api/internal/report-problem", headers=sign_in_app(app, KIT),
                          json={"choice": "wrong-language", "station": 7})  # fmt: skip
        assert said.status_code == 404, said.text


def test_commercials_go_by_the_tv_age_and_trailers_by_the_movie_age(app):
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[7]): True})
        levels = {lv["builtin"]: lv for lv in admin.get("/api/access/viewing").json()["levels"]}
        kid_level_ = levels["kid"]
        assert ctx.viewing.clip_most(ids[7], 17, tv=True) == kid_level_["tvAge"]
        assert ctx.viewing.clip_most(ids[7], 17, tv=False) == kid_level_["movieAge"]


def test_a_bumper_ending_in_a_break_holds_and_names_what_it_says_is_up_next(app):
    """The cold audit of 1.39.0: an Intro Bumper that ends in the break after
    Puppet Town says "UP NEXT" Heist. Its pieces hold Heist (not Puppet
    Town), so Kit doesn't get them. And on Mixed, allowed for Kit by hand,
    it names neither Heist nor anything else she may not watch; with no one
    it's allowed for by hand, it names Heist."""
    from app.broadcaster import Broadcaster

    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kit_id = kid(admin, {str(ids[7]): True})
        now = int(time.time() * 1000)
        puppets, heist = items(ctx, {"201", "301"})
        # (Puppet Town with two minutes of break after it.)
        puppets = replace(
            puppets, duration_ms=puppets.duration_ms + 120_000, breaks=[("@id", 120_000)]
        )
        plays(ctx, ids[7], [puppets, heist], now - 60 * 60_000)
        station = ctx.station(ids[7])
        on = station.locate(now)
        first = on if on.item.rating_key == "201" else station.after(on)
        in_break = first.start_ms + puppets.program_end_ms + 30_000
        assert station.locate(in_break).item.rating_key == "201"
        fake = SimpleNamespace(ctx=ctx, channel_id=ids[7], _skipped=lambda key: False)
        fake._bumper_names = lambda *a: Broadcaster._bumper_names(fake, *a)
        assert Broadcaster._bumper_names(fake, station, in_break).rating_key == "301"
        assert Broadcaster._bumper_names(fake, station, first.start_ms + 60_000).rating_key == "201"
        assert Broadcaster._whats_on(fake, station, in_break) == ("", "", "")
        assert Broadcaster._whats_on(fake, station, first.start_ms + 60_000)[1] == "Puppet Town"
        admin.put(f"/api/access/users/{kit_id}/viewing", json={"stations": {}})
        assert Broadcaster._whats_on(fake, station, in_break)[:2] == ("UP NEXT", "Heist")


def test_a_refused_app_keeps_its_place_among_the_devices_allowed(app):
    """(The second cold audit of 1.39.0.) With one device allowed, Kit's app
    holds its place while it waits for its first check and while it's
    refused (watching nothing), so another device can't take it and she's
    back on her own. Once she tunes away, or stops asking, it's free."""
    from app.capacity import Limits

    ctx = app.state.ctx
    with TestClient(app):
        stream = hls.HlsStream.__new__(hls.HlsStream)
        stream.clients, stream.away, stream.since, stream.who = {}, set(), {}, {}
        stream.waiting = {}
        stream.label = stream.label_mid = "station 7, Mixed"
        stream.ended = stream._stopping = False
        stream.b = SimpleNamespace(channel_id=7, ctx=ctx, behind_ms=0)
        stream.last_asked = time.monotonic()
        stream.stop = lambda because: None
        ctx.hls_streams._by_station[(7, False)] = stream
        try:
            ctx.capacity.limits = Limits(1, None)

            def turned_away(client: str, away: bool = False):
                return ctx.capacity.refusal(ctx.app_watchers(), client, away)

            stream.holds_place("kit", True)  # (her first ask, before its check)
            assert stream.watchers() == {} and ctx.app_watchers() == {"kit": True}
            assert turned_away("tablet") == ("devices", 1) and turned_away("kit", True) is None
            stream.asked_by("kit", True)
            assert stream.watchers() == {"kit": True} and stream.waiting == {}
            stream.blocked("kit", True)  # (a program she may not watch came on)
            assert stream.watchers() == {} and ctx.app_watchers() == {"kit": True}
            assert turned_away("tablet") == ("devices", 1) and turned_away("kit", True) is None
            stream.left_by("kit")
            assert ctx.app_watchers() == {} and turned_away("tablet") is None
            stream.blocked("kit")  # (refused, not watching: still holds one)
            assert ctx.app_watchers() == {"kit": False}
            stream.waiting["kit"] = (time.monotonic() - hls.IDLE_S - 1, False)
            assert ctx.app_watchers() == {} and turned_away("tablet") is None
        finally:
            del ctx.hls_streams._by_station[(7, False)]


async def test_a_stopping_station_never_hands_a_new_viewer_what_it_sent_before():
    """(The second cold audit of 1.39.0.) While a station stops (up to 10
    seconds), someone tuning in gets none of its recent bytes: the next
    session's record starts from nothing sent, so they'd hold a program
    no one could tell."""
    import asyncio

    from app.broadcaster import Broadcaster

    b = Broadcaster(ctx=SimpleNamespace(), channel_id=1)
    b._recent.append((b"Heist", None))
    b._recent_bytes = 5
    started = asyncio.Event()
    late = asyncio.Event()

    async def ending():
        started.set()
        await late.wait()

    b._task = asyncio.create_task(ending())
    await started.wait()
    stopping = asyncio.create_task(b.stop())
    await asyncio.sleep(0.05)
    assert list(b._recent) == [] and b._recent_bytes == 0
    late.set()
    await stopping


def test_the_last_one_watching_leaving_keeps_the_station_for_a_refused_app(app):
    """(The third cold audit of 1.39.0.) Ada watching, Kit refused (holding
    her place, away from home): Ada tuning away doesn't stop the stream, so
    Kit's place isn't given up; a second refusal keeps her away from home.
    Once Kit tunes away too, it stops."""
    ctx = app.state.ctx
    with TestClient(app):
        stream = hls.HlsStream.__new__(hls.HlsStream)
        stream.clients, stream.away, stream.since, stream.who = {}, set(), {}, {}
        stream.waiting = {}
        stream.label = stream.label_mid = "station 7, Mixed"
        stream.ended = stream._stopping = False
        stream.b = SimpleNamespace(channel_id=7, ctx=ctx, behind_ms=0)
        stream.last_asked = time.monotonic()
        stopped = []
        stream.stop = stopped.append
        stream.asked_by("ada")
        stream.asked_by("kit", True)
        stream.blocked("kit")
        stream.blocked("kit")  # (a second refused piece)
        assert stream.places() == {"ada": False, "kit": True}
        stream.left_by("ada")
        assert stopped == [] and stream.places() == {"kit": True}
        stream.left_by("kit")
        assert stopped == ["the last app watching it tuned away"]


async def test_someone_tuning_in_while_a_station_stops_gets_a_new_session(monkeypatch):
    """(The third cold audit of 1.39.0; older than it.) Someone who tunes in
    while a station stops is watching once it has: a new session starts for
    them, rather than nothing, forever. Not for a station that's gone."""
    from app.broadcaster import Broadcaster

    sessions = []

    async def session(self):
        sessions.append(self.channel_id)
        await asyncio.Event().wait()

    monkeypatch.setattr(Broadcaster, "_supervise", session)
    for gone in (False, True):
        b = Broadcaster(ctx=SimpleNamespace(broadcasters={}), channel_id=1)
        if not gone:
            b.ctx.broadcasters[1] = b
        started, late = asyncio.Event(), asyncio.Event()

        async def ending(started=started, late=late):
            started.set()
            await late.wait()

        b._task = asyncio.create_task(ending())
        await started.wait()
        stopping = asyncio.create_task(b.stop())
        await asyncio.sleep(0.05)
        viewer = b.subscribe("app viewers on 1", counted=False)
        late.set()
        await stopping
        await asyncio.sleep(0.05)
        if gone:
            assert sessions == [1] and viewer.closed and viewer not in b.viewers
        else:
            assert sessions == [1] and b._task is not None and not b._task.done()
            assert viewer in b.viewers and not viewer.closed and not b._stopping
            b._task.cancel()


def test_her_app_is_told_when_her_station_is_back_by_what_it_really_plays(app, monkeypatch):
    """(The third cold audit of 1.39.0.) `resumesAtMs` goes by where the
    station really is: Heist ends 40 minutes from now on its schedule, but
    a station 30 minutes behind it (tuned in from a program's start) plays
    its end 70 minutes from now."""
    ctx = app.state.ctx
    with TestClient(app) as admin:
        ids = set_up(admin)
        kid(admin, {str(ids[7]): True})
        puppet, heist = items(ctx, {"201", "301"})
        now = int(time.time() * 1000)
        plays(ctx, ids[7], [heist, puppet], now - 60 * 60_000)
        stream = FakeStream({"s1.ts": (heist,)})
        monkeypatch.setattr(ctx.hls_streams, "get", lambda cid, night=False: stream)
        phone = TestClient(app)
        as_kit = sign_in_app(app, KIT)
        got = phone.get("/api/v1/stations", headers=as_kit).json()["stations"]
        kits = next(s for s in got if s["number"] == 7)["hls"].split("?")[0]
        back = phone.get(kits).json()["resumesAtMs"]
        assert abs(back - (now + 40 * 60_000)) < 5_000, back - now
        ctx.broadcaster(ids[7]).behind_ms = 30 * 60_000
        back = phone.get(kits).json()["resumesAtMs"]
        assert abs(back - (now + 70 * 60_000)) < 5_000, back - now


async def test_someone_tuning_in_as_a_station_stops_after_its_grace_gets_a_new_session(
    monkeypatch,
):
    """(The fourth cold audit of 1.39.0.) The usual way a station stops:
    the last viewer leaves, and after its grace it stops. Someone tuning in
    while it does (its engine slow to end) gets a new session once it has,
    rather than being turned away."""
    from app.broadcaster import Broadcaster

    sessions, late = [], asyncio.Event()

    async def session(self):
        sessions.append(self.channel_id)
        await (late.wait() if len(sessions) == 1 else asyncio.Event().wait())

    monkeypatch.setattr(Broadcaster, "_supervise", session)
    ctx = SimpleNamespace(broadcasters={}, settings=SimpleNamespace(idle_grace_seconds=0.01))
    b = Broadcaster(ctx=ctx, channel_id=1)
    ctx.broadcasters[1] = b
    first = b.subscribe("Plex on 1", counted=False)
    await asyncio.sleep(0.01)
    b.unsubscribe(first)
    await asyncio.sleep(0.1)  # (its grace over: it's stopping, waiting for its engine)
    assert b._stopping and sessions == [1]
    newcomer = b.subscribe("an app on 1", counted=False)
    await asyncio.sleep(0.05)
    late.set()  # (its engine has ended)
    await asyncio.sleep(0.1)
    assert sessions == [1, 1], sessions
    assert newcomer in b.viewers and not newcomer.closed and b.running
    b._task.cancel()

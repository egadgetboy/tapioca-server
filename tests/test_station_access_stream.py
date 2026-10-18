"""A restricted program on a real station (1.39.0, the owner, October 17):
real ffmpeg, a fake Plex. Kit (Kid) watches a station allowed for her by
hand, in an app, at its own address. Episode 1 is TV-14 (30 seconds of a
440 Hz tone); the others are TV-Y7 (good2 and good3: 660 Hz and 330 Hz). She tunes in first, so
the station starts with its Intro Bumper, which names that episode: three
ways (the second cold audit of 1.39.0). Tuning in at a program's start;
tuning in while it plays, so the bumper plays its sound as it ends; and
in the break before it, so the bumper says it's up next. Not one piece her
app gets has that episode in it, by what's really in it (its sound), not
by what tapiOca says; she's refused while it's on and back on her own once
it's over; and Ada, an Admin, gets every piece, one shared stream."""

from __future__ import annotations

import asyncio
import math
import re
import shutil
import struct
import subprocess
import time
from dataclasses import replace

import httpx
import pytest

from app.breaks import ID_CARD
from app.db import NewEra
from app.main import RESTRICTED_PROGRAM

from .fakeplex import FakePlex
from .helpers import PAGE
from .test_e2e import (
    CLIP_S,
    make_channel,
    media,  # noqa: F401  (a fixture)
    start_server,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

ADA = {"name": "Ada", "password": "correct horse"}
KIT = {"name": "Kit", "password": "battery staple"}
TV = {"app": "tapiOca for Android", "deviceName": "Den"}
RATE = 8000
# Episode 1's length, and the Intro Bumper's: long enough that the show's
# sound in its last third (5 seconds) is more than MARGIN_S before the
# episode itself, so only the bumper's own label keeps it from her (the
# third cold audit of 1.39.0).
LONG_S = 30
BUMPER_S = 15


@pytest.fixture(scope="module")
def long_one(tmp_path_factory):
    path = tmp_path_factory.mktemp("long") / "long.mkv"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x480:r=24000/1001",
         "-f", "lavfi", "-i", "sine=f=440", "-t", str(LONG_S), "-c:v", "libx264",
         "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )  # fmt: skip
    return path


def pieces(playlist: str) -> list[str]:
    return re.findall(r"^(s\d+\.ts)$", playlist, re.M)


def tones(path) -> dict[int, float]:
    """How strong 330, 440 and 660 Hz are in a piece's sound, each against
    the strongest of them (Goertzel, on 8 kHz mono)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(RATE),
         "-f", "s16le", "-"],
        capture_output=True, check=False,
    ).stdout  # fmt: skip
    samples = struct.unpack(f"<{len(raw) // 2}h", raw[: len(raw) // 2 * 2])
    power = {}
    for f in (330, 440, 660):
        k = 2 * math.cos(2 * math.pi * f / RATE)
        a = b = 0.0
        for x in samples:
            a, b = x + k * a - b, a
        power[f] = a * a + b * b - k * a * b
    most = max(power.values()) or 1.0
    return {f: p / most for f, p in power.items()}


def plays_from(ctx, channel_id: int, order: list[str], into_s: float, break_s: int = 0) -> None:
    """The station plays episodes `order` over and over, `into_s` into the
    first now; with `break_s` of Station ID card after the first."""
    lineup = {i.rating_key: i for e in ctx.db.eras(channel_id) for i in e.items}
    out, at = [], 0
    for n, key in enumerate(order):
        item = replace(lineup[key], position=n, start_ms=at, breaks=None)
        if n == 0 and break_s:
            item = replace(
                item,
                duration_ms=item.duration_ms + break_s * 1000,
                breaks=[(ID_CARD, break_s * 1000)],
            )
        out.append(item)
        at += item.duration_ms
    now = int(time.time() * 1000)
    old = [e.id for e in ctx.db.eras(channel_id)]
    since = now - round(into_s * 1000)
    ctx.db.replace_eras(channel_id, old, [NewEra(out, None, since, "a", "in-order", now, "test")])


@pytest.mark.parametrize(
    "tune_in",
    [
        "start",  # (at episode 1's start)
        "now",  # (1 second into episode 1: the bumper plays its sound)
        "break",  # (in the break before it: the bumper says it's up next)
    ],
)
async def test_her_app_never_gets_the_restricted_episode_and_comes_back(
    tmp_path,
    media,  # noqa: F811  (the fixture)
    long_one,
    monkeypatch,
    tune_in,
):
    from app.broadcaster import Broadcaster

    # (What the station says it's sending while its Intro Bumper plays: the
    # program it names, whose sound it plays as it ends. The cold audit of
    # 1.39.0: it was nothing, so its pieces went to her.)
    during_bumper = []
    bumper = Broadcaster._play_intro

    async def noted(self, *args, **kwargs):
        during_bumper.append(getattr(self._content, "rating_key", None))
        return await bumper(self, *args, **kwargs)

    monkeypatch.setattr(Broadcaster, "_play_intro", noted)
    # (And whether it found the show's sound to play as it ends.)
    from app import intro

    show_sound = []
    finding = intro.find_show_audio

    async def found(*args, **kwargs):
        got = await finding(*args, **kwargs)
        show_sound.append(got is not None)
        return got

    monkeypatch.setattr(intro, "find_show_audio", found)
    plex = FakePlex()
    plex.add_show("100", "Test Show", contentRating=["TV-Y7"])
    plex.add_episode("201", "100", 1, 1, "long", str(long_one), LONG_S * 1000)
    for n, name in ((2, "good2"), (3, "good3")):
        plex.add_episode(str(200 + n), "100", 1, n, name, str(media[name]), CLIP_S * 1000)
    # (Plex's own ratings, as it gives them each time it's asked: tapiOca
    # takes an episode's from Plex again as it plays, so without this, the
    # episode became unrated, its show's TV-Y7, after a minute or so.)
    plex._set_tags(plex.episodes["201"], {"contentRating": ["TV-14"]})
    base, app, _settings, srv, task = await start_server(tmp_path, plex)
    ctx = app.state.ctx
    try:
        channel = await make_channel(base)
        now = int(time.time() * 1000)
        # (Its ratings, as Plex would give them: the show TV-Y7, episode 1 TV-14.)
        ctx.db.save_titles([
            ("100", "show", "TV-Y7", "1", now, now),
            ("201", "episode", "TV-14", "1", now, now),
        ])  # fmt: skip
        ctx.titles.__init__(ctx.db)
        async with httpx.AsyncClient(headers=PAGE, base_url=base, timeout=60) as admin:
            assert (await admin.post("/api/access/users", json=ADA)).status_code == 201
            assert (await admin.post("/api/access/sign-in", json=ADA)).status_code == 200
            kit = (await admin.post("/api/access/users", json={**KIT, "role": "user"})).json()
            levels = (await admin.get("/api/access/viewing")).json()["levels"]
            kid = next(lv["id"] for lv in levels if lv["builtin"] == "kid")
            changed = await admin.put(f"/api/access/users/{kit['id']}/viewing", json={
                "level": kid, "stations": {str(channel["id"]): True}})  # fmt: skip
            assert changed.status_code == 200, changed.text
            on = (await admin.put(f"/api/channels/{channel['id']}", json={
                "number": 7, "name": "Test TV", "orderMode": "rotate",
                "sources": [{"type": "show", "ratingKey": "100"}],
                "tuneIn": "start" if tune_in == "start" else "now",
                "introSeconds": BUMPER_S})).json()  # fmt: skip
            assert on.get("tuneIn") == ("start" if tune_in == "start" else "now"), on

        async def address(who: dict) -> tuple[httpx.AsyncClient, str]:
            app_client = httpx.AsyncClient(base_url=base, timeout=60)
            token = (await app_client.post("/api/internal/sign-in", json={**who, **TV})).json()
            app_client.headers["Authorization"] = f"Bearer {token['token']}"
            got = (await app_client.get("/api/v1/stations")).json()["stations"]
            return app_client, next(s for s in got if s["number"] == 7)["hls"].split("?")[0]

        kits_app, kits = await address(KIT)
        adas_app, adas = await address(ADA)
        if tune_in == "now":
            plays_from(ctx, channel["id"], ["201", "202", "203"], 1.0)
        elif tune_in == "break":
            # (Episode 2, then 8 seconds of break, then episode 1: tuning in
            # a second into episode 2, the bumper ends in the break.)
            plays_from(ctx, channel["id"], ["202", "201", "203"], 1.0, break_s=8)
        if tune_in != "start":
            at = ctx.station(channel["id"]).locate(int(time.time() * 1000))
            assert at.item.rating_key == ("201" if tune_in == "now" else "202")
        kit_got: dict[str, bytes] = {}
        ada_got: dict[str, bytes] = {}
        answers: list[int] = []
        deadline = time.monotonic() + LONG_S + 2 * CLIP_S + BUMPER_S + 60
        while time.monotonic() < deadline:
            # Kit first: she tunes in, and the station starts for her.
            mine = await kits_app.get(kits)
            answers.append(mine.status_code)
            if mine.status_code == 403:
                said = mine.json()
                assert said["detail"] == RESTRICTED_PROGRAM and said["code"] == "restricted"
            else:
                assert mine.status_code in (200, 503), mine.text
            for name in pieces(mine.text) if mine.status_code == 200 else []:
                if name not in kit_got:
                    piece = await kits_app.get(kits.replace("index.m3u8", name))
                    assert piece.status_code in (200, 403, 404), piece.text
                    if piece.status_code == 200:
                        kit_got[name] = piece.content
            listed = await adas_app.get(adas)
            for name in pieces(listed.text) if listed.status_code == 200 else []:
                if name not in ada_got:
                    piece = await adas_app.get(adas.replace("index.m3u8", name))
                    assert piece.status_code == 200, f"Ada, {name}: {piece.status_code}"
                    ada_got[name] = piece.content
            refused_then_back = 403 in answers and 200 in answers[answers.index(403) :]
            if refused_then_back and len(kit_got) >= 4:
                break
            await asyncio.sleep(1)
        await kits_app.aclose()
        await adas_app.aclose()

        def heard(got: dict[str, bytes]) -> dict[str, dict[int, float]]:
            out = {}
            for name, data in got.items():
                path = tmp_path / f"{len(out)}-{name}"
                path.write_bytes(data)
                out[name] = tones(path)
            return out

        adas, kits_heard = heard(ada_got), heard(kit_got)
        # The TV-14 episode (440 Hz) went out to Ada.
        assert any(t[440] > 0.5 for t in adas.values()), adas
        # Kit was refused while it was on, and back on her own after.
        assert answers[0] in (403, 503) and 403 in answers, answers
        assert 200 in answers[answers.index(403) :], answers
        # Not one piece she got has any of it, bumper included.
        assert kits_heard, "Kit got no pieces"
        leaked = {n: t for n, t in kits_heard.items() if t[440] > 0.2}
        assert not leaked, leaked
        assert any(max(t[330], t[660]) > 0.5 for t in kits_heard.values())
        assert during_bumper and during_bumper[0] == "201", during_bumper
        # (In the "now" run, the bumper played the TV-14 episode's sound as
        # it ended, and she got none of it: what the audit asked to catch.)
        # (From a program's start, it isn't looked for: see _play_intro.)
        assert show_sound == {"start": [], "now": [True], "break": [False]}[tune_in], show_sound
        # (Episode 1 was TV-14 all along, as Plex gives it.)
        episode_1 = next(
            i for e in ctx.db.eras(channel["id"]) for i in e.items if i.rating_key == "201"
        )
        assert ctx.titles.judge(episode_1).age == 14
        # One shared stream all along.
        b = ctx.broadcasters[channel["id"]]
        assert b.running and len(b.viewers) == 1
    finally:
        srv.should_exit = True
        await task

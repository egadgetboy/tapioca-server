"""A restricted program on a real station (1.39.0, the owner, October 17):
real ffmpeg, a fake Plex. Kit (Kid) watches a station allowed for her by
hand, in an app, at its own address; one of its three episodes is TV-14.
Her app is refused the pieces of that episode (and its playlist while one
is in it), and is back on its own once the next episode is on; Ada, an
Admin, watches every piece the whole time, one shared stream."""

from __future__ import annotations

import asyncio
import re
import shutil
import time

import httpx
import pytest

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


def pieces(playlist: str) -> list[str]:
    return re.findall(r"^(s\d+\.ts)$", playlist, re.M)


async def test_her_app_is_refused_the_restricted_episode_and_comes_back(tmp_path, media):  # noqa: F811
    plex = FakePlex()
    plex.add_show("100", "Test Show")
    for n, name in enumerate(("good1", "good2", "good3"), start=1):
        plex.add_episode(str(200 + n), "100", 1, n, name, str(media[name]), CLIP_S * 1000)
    base, app, _settings, srv, task = await start_server(tmp_path, plex)
    ctx = app.state.ctx
    try:
        channel = await make_channel(base)
        now = int(time.time() * 1000)
        # (Its ratings, as Plex would give them: the show TV-Y7, episode 2 TV-14.)
        ctx.db.save_titles([
            ("100", "show", "TV-Y7", "1", now, now),
            ("202", "episode", "TV-14", "1", now, now),
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

        async def address(who: dict) -> tuple[httpx.AsyncClient, str]:
            app_client = httpx.AsyncClient(base_url=base, timeout=60)
            token = (await app_client.post("/api/internal/sign-in", json={**who, **TV})).json()
            app_client.headers["Authorization"] = f"Bearer {token['token']}"
            got = (await app_client.get("/api/v1/stations")).json()["stations"]
            return app_client, next(s for s in got if s["number"] == 7)["hls"].split("?")[0]

        kits_app, kits = await address(KIT)
        adas_app, adas = await address(ADA)
        stream = None
        kit_got: list[tuple[str, tuple]] = []
        ada_got: dict[str, tuple] = {}
        refused = []
        back_after_refusal = False
        deadline = time.monotonic() + 3 * CLIP_S * 2 + 20
        while time.monotonic() < deadline:
            listed = await adas_app.get(adas)
            assert listed.status_code in (200, 503), listed.text
            stream = stream or ctx.hls_streams.get(channel["id"])
            for name in pieces(listed.text) if listed.status_code == 200 else []:
                if name not in ada_got:
                    piece = await adas_app.get(adas.replace("index.m3u8", name))
                    assert piece.status_code == 200, f"Ada, {name}: {piece.status_code}"
                    ada_got[name] = stream.holds.get(name, ())
            mine = await kits_app.get(kits)
            if mine.status_code == 403:
                said = mine.json()
                assert said["detail"] == RESTRICTED_PROGRAM and said["code"] == "restricted"
                refused.append(time.monotonic())
            else:
                assert mine.status_code in (200, 503), mine.text
                if refused and mine.status_code == 200:
                    back_after_refusal = True
                for name in pieces(mine.text) if mine.status_code == 200 else []:
                    piece = await kits_app.get(kits.replace("index.m3u8", name))
                    if piece.status_code == 200:
                        kit_got.append((name, stream.holds.get(name, ())))
                    else:
                        assert piece.status_code in (403, 404), piece.text
            if back_after_refusal and len(ada_got) > 12:
                break
            await asyncio.sleep(1)
        await kits_app.aclose()
        await adas_app.aclose()

        def keys(contents: tuple) -> set:
            return {getattr(c, "rating_key", None) for c in contents}

        # The TV-14 episode went out, Ada got its pieces, Kit was refused,
        # and was back, with nothing done, once it was over.
        assert any("202" in keys(c) for c in ada_got.values()), ada_got
        assert refused, "Kit's app was never refused"
        assert back_after_refusal, "Kit's app wasn't back after the TV-14 episode"
        # Not one piece Kit got held any of it (as tapiOca knew it then).
        assert kit_got and not any("202" in keys(c) for _, c in kit_got), kit_got
        # One shared stream all along.
        b = ctx.broadcasters[channel["id"]]
        assert b.running and len(b.viewers) == 1
    finally:
        srv.should_exit = True
        await task

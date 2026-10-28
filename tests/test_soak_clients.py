"""The soak with headless clients (the plan's release gate, DL369: a soak
before a Class D release publishes): a real tapiOca with real FFmpeg, and
clients that play as tapiOca's apps do, for as long as STATIONPLAY_SOAK_MINUTES
says, with a restart half way and connections dropped part way through:

- two Stations watched as HLS, the playlist asked for every second and each
  new piece fetched, as a player does;
- Media copies played from the start and from anywhere, with jumps, and left;
- Media played as the file, in ranges from all over it, as a player seeks;
- downloads dropped part way, again and again.

It passes when, apart from the seconds around the restart, every answer is
whole and on time (a Station tunes in within its own wait, READY_WAIT_S, and
never goes longer without a new piece than a player holds, the playlist's
LISTED pieces), nothing is logged as a warning or an error, and nothing is
still running at the end. The log is its telemetry until One playback contract's
channel exists. Weekly in quality.yml, and for each Class D candidate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import resource
import shutil
import subprocess
import time
from dataclasses import dataclass, field

import httpx
import pytest

from app import hls
from app.main import create_app
from app.plex import PlexClient

from .fakeplex_library import LibraryPlex
from .helpers import PAGE
from .test_e2e import CLIP_S, make_channel, media, start_server

pytestmark = [
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg"),
    pytest.mark.skipif(
        not os.environ.get("STATIONPLAY_SOAK"), reason="set STATIONPLAY_SOAK=1 for the long run"
    ),
]
__all__ = ["media"]

# What tapiOca's apps tell it they play (a phone: MP4 and Matroska, H.264
# and AAC, and copies as HLS).
PHONE = {
    "containers": ["mp4", "mkv"],
    "video": [{"codec": "h264", "width": 1920, "height": 1080, "bitDepth": 8}],
    "hdr": [],
    "audio": ["aac"],
    "hls": ["ts"],
}
COPY_S = 60.0
GRACE_S = 25.0  # around the restart: from its stop until this long after it's back


def make(path, *args: str, seconds: float = COPY_S) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=24:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}", *args, str(path)],
        check=True,
    )  # fmt: skip


@dataclass
class Soak:
    base: str
    deadline: float
    down: tuple[float, float] | None = None  # the restart's window (monotonic), once it starts
    down_wall: tuple[float, float] | None = None  # the same, in the log's own clock
    faults: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def excused(self) -> bool:
        return self.down is not None and self.down[0] <= time.monotonic() <= self.down[1] + GRACE_S

    def fault(self, what: str) -> None:
        if not self.excused():
            self.faults.append(f"{time.strftime('%H:%M:%S')} {what}")

    def count(self, what: str) -> None:
        self.counts[what] = self.counts.get(what, 0) + 1


def device(n: int, **kw) -> httpx.AsyncClient:
    """A client as its own device: at home, tapiOca tells devices apart by
    their address (one play at a time on each), so each has its own."""
    return httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(local_address=f"127.0.0.{n}"), **kw)


def sequence(playlist: str) -> int:
    """The playlist's first piece's number (#EXT-X-MEDIA-SEQUENCE)."""
    found = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", playlist)
    return int(found.group(1)) if found else 0


def pieces(playlist: str) -> list[str]:
    return [line for line in playlist.splitlines() if line and not line.startswith("#")]


async def get(soak: Soak, client: httpx.AsyncClient, path: str, **kw) -> httpx.Response | None:
    try:
        r = await client.get(soak.base + path, **kw)
    except httpx.HTTPError as e:
        soak.fault(f"{path}: {type(e).__name__}")
        return None
    if r.status_code not in (200, 206):
        soak.fault(f"{path}: {r.status_code}")
        return None
    return r


async def leave(soak: Soak, client: httpx.AsyncClient, path: str) -> None:
    """Says it's done, as an app does; a failure is a fault, but around the restart."""
    try:
        r = await client.post(soak.base + path)
    except httpx.HTTPError as e:
        soak.fault(f"{path}: {type(e).__name__}")
        return
    if r.status_code != 204:
        soak.fault(f"{path}: {r.status_code}")


async def watch_station(soak: Soak, number: int, n: int) -> None:
    """Plays a Station as an app's player does, timing each new piece."""
    seen: set[str] = set()
    first = 0  # (the playlist's media sequence, last asked)
    asked = time.monotonic()
    last_new: float | None = None  # (from its first piece: tuning in is timed on its own)
    held = hls.LISTED * hls.PIECE_S
    async with device(n, headers=PAGE, timeout=30) as client:
        while time.monotonic() < soak.deadline:
            listed = await get(soak, client, f"/hls/{number}/index.m3u8")
            if listed is not None:
                at = sequence(listed.text)
                if at < first:
                    # (A new stream, as after a restart: its pieces' names
                    # start again, and an app tunes in to it afresh.)
                    seen.clear()
                    soak.count(f"station {number} tuned in again")
                first = at
                for name in pieces(listed.text):
                    if name in seen:
                        continue
                    piece = await get(soak, client, f"/hls/{number}/{name}")
                    if piece is not None:
                        if piece.content[:1] != b"\x47":
                            soak.fault(f"station {number}: {name} isn't MPEG-TS")
                        seen.add(name)
                        last_new = time.monotonic()
                        soak.count(f"station {number} pieces")
            now = time.monotonic()
            if last_new is None and now - asked > hls.READY_WAIT_S + 5:
                soak.fault(f"station {number}: not tuned in after {now - asked:.0f} s")
                asked = now
            elif last_new is not None and now - last_new > held and not soak.excused():
                soak.fault(
                    f"station {number}: no new piece for {now - last_new:.0f} s, more than a player holds ({held} s)"
                )
                last_new = now
            await asyncio.sleep(1)
        await leave(soak, client, f"/hls/{number}/leave")


async def play_copies(soak: Soak, key: str, n: int, rng: random.Random) -> None:
    """Starts a Media copy from anywhere, plays some of it, jumps, and leaves."""
    async with device(n, headers=PAGE, timeout=60) as client:
        while time.monotonic() < soak.deadline:
            start = rng.choice([0, rng.uniform(0, COPY_S - 10)])
            try:
                answer = await client.post(
                    soak.base + "/api/internal/play",
                    json={"key": key, "device": PHONE, "startMs": int(start * 1000)},
                )
            except httpx.HTTPError as e:
                soak.fault(f"play {key}: {type(e).__name__}")
                await asyncio.sleep(2)
                continue
            if answer.status_code != 200:
                soak.fault(f"play {key}: {answer.status_code} {answer.text[:120]}")
                await asyncio.sleep(2)
                continue
            url = answer.json()["url"]
            listed = await get(soak, client, url)
            if listed is not None:
                names = pieces(listed.text)
                here = url.rsplit("/", 1)[0]
                order = names[: rng.randint(1, len(names))] + rng.sample(names, min(2, len(names)))
                for name in order:
                    if (piece := await get(soak, client, f"{here}/{name}")) is not None:
                        soak.count("copy pieces")
                        if piece.content[:1] != b"\x47":
                            soak.fault(f"copy {key}: {name} isn't MPEG-TS")
            await leave(soak, client, answer.json()["leave"])
            await asyncio.sleep(rng.uniform(0.5, 3))


async def play_file(soak: Soak, key: str, size: int, n: int, rng: random.Random) -> None:
    """Plays Media as the file, reading ranges from all over it, as a seeking player does."""
    async with device(n, headers=PAGE, timeout=60) as client:
        while time.monotonic() < soak.deadline:
            try:
                answer = await client.post(
                    soak.base + "/api/internal/play", json={"key": key, "device": PHONE}
                )
            except httpx.HTTPError as e:
                soak.fault(f"play {key}: {type(e).__name__}")
                await asyncio.sleep(2)
                continue
            if answer.status_code != 200:
                soak.fault(f"play {key}: {answer.status_code} {answer.text[:120]}")
                await asyncio.sleep(2)
                continue
            url = answer.json()["url"]
            for _ in range(rng.randint(3, 10)):
                at = rng.randrange(0, size - 1)
                end = min(size - 1, at + rng.randint(1, 256 * 1024))
                got = await get(soak, client, url, headers={"Range": f"bytes={at}-{end}"})
                if got is not None:
                    soak.count("file ranges")
                    if len(got.content) != end - at + 1:
                        soak.fault(
                            f"file {key}: asked {end - at + 1} bytes from {at}, got {len(got.content)}"
                        )
            await leave(soak, client, answer.json()["leave"])
            await asyncio.sleep(rng.uniform(0.5, 2))


async def drop_downloads(soak: Soak, n: int, rng: random.Random) -> None:
    """Starts a Station's stream and hangs up part way, again and again."""
    async with device(n, headers=PAGE, timeout=30) as client:
        while time.monotonic() < soak.deadline:
            try:
                async with client.stream("GET", soak.base + "/stream/8") as r:
                    async for _ in r.aiter_bytes():
                        break  # (hung up after the first bytes)
                soak.count("dropped")
            except httpx.HTTPError:
                pass
            await asyncio.sleep(rng.uniform(2, 6))


async def restart(soak: Soak, state: dict, minutes: float, plex: LibraryPlex) -> None:
    """Half way, the server stops and starts again on the same data."""
    await asyncio.sleep(minutes * 30)
    soak.down = (time.monotonic(), time.monotonic() + 3600)
    began = time.time()
    state["srv"].should_exit = True
    await state["task"]
    settings = state["settings"]
    app = create_app(settings, PlexClient("http://plex.test", "token", transport=plex.transport()))
    app.state.ctx.play_transport = plex.transport()
    import uvicorn

    from .test_e2e import free_port

    port = free_port()
    srv = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    task = asyncio.create_task(srv.serve())
    while not srv.started:
        await asyncio.sleep(0.05)
    state.update(app=app, srv=srv, task=task)
    soak.base = f"http://127.0.0.1:{port}"
    soak.down = (soak.down[0], time.monotonic())
    soak.down_wall = (began, time.time())
    soak.count("restarts")


async def test_soak_with_headless_clients(tmp_path, media, caplog):
    minutes = float(os.environ.get("STATIONPLAY_SOAK_MINUTES", "8"))
    plex = LibraryPlex()
    plex.add_show("100", "Test Show")
    for n, name in enumerate(("good1", "good2", "good3"), start=1):
        plex.add_episode(str(200 + n), "100", 1, n, name, str(media[name]), CLIP_S * 1000)
    plex.add_section("2", "Movies", "movie")
    copy = tmp_path / "copy.mkv"  # (Dolby Digital sound: played as a repackaged copy)
    make(copy, "-c:v", "libx264", "-x264-params", "keyint=72:scenecut=0", "-c:a", "ac3")
    plex.add_movie("400", "A Copy", str(copy), int(COPY_S * 1000), section="2")
    plex.describe("400", audio="ac3", width=320, height=180)
    whole = tmp_path / "whole.mp4"  # (H.264 and AAC in MP4: played as the file)
    make(whole, "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart")
    plex.add_movie("401", "As It Is", str(whole), int(COPY_S * 1000), section="2")
    plex.describe("401", container="mp4", width=320, height=180)
    plex.files["401"] = whole.read_bytes()

    caplog.set_level(logging.WARNING)
    base, app, settings, srv, task = await start_server(tmp_path, plex)
    app.state.ctx.play_transport = plex.transport()
    state = {"app": app, "settings": settings, "srv": srv, "task": task}
    soak = Soak(base, time.monotonic() + minutes * 60)
    rng = random.Random(7)
    try:
        await make_channel(base, 7)
        await make_channel(base, 8)
        async with httpx.AsyncClient(headers=PAGE, base_url=base, timeout=30) as client:
            assert (
                await client.put("/api/app-libraries", json={"libraries": ["2"]})
            ).status_code in (200, 204)
        await asyncio.gather(
            watch_station(soak, 7, 11),
            watch_station(soak, 7, 12),
            watch_station(soak, 8, 13),
            play_copies(soak, "400", 14, random.Random(rng.random())),
            play_file(soak, "401", len(plex.files["401"]), 15, random.Random(rng.random())),
            drop_downloads(soak, 16, random.Random(rng.random())),
            restart(soak, state, minutes, plex),
        )
        await asyncio.sleep(settings.idle_grace_seconds + 8)
        ctx = state["app"].state.ctx
        still = [n for n, b in ctx.broadcasters.items() if b.running]
    finally:
        state["srv"].should_exit = True
        await state["task"]

    me, kids = (
        resource.getrusage(resource.RUSAGE_SELF),
        resource.getrusage(resource.RUSAGE_CHILDREN),
    )
    cpu = me.ru_utime + me.ru_stime + kids.ru_utime + kids.ru_stime
    # (The release's hard limits, in its manifest: this run's memory at its
    # most and its processor time each minute, FFmpeg's included.)
    print(f"soak: {minutes} minutes; {soak.counts}")
    print(f"limits: memory_mb={me.ru_maxrss / 1024:.0f} cpu_s_per_min={cpu / minutes:.1f}")
    logged = [
        f"{r.levelname} {r.name}: {r.getMessage()[:200]}"
        for r in caplog.records
        if r.levelno >= logging.WARNING
        and not (soak.down_wall and soak.down_wall[0] <= r.created <= soak.down_wall[1] + GRACE_S)
    ]
    assert not soak.faults, "\n".join(soak.faults[:40])
    assert not logged, "\n".join(logged[:40])
    assert not still, f"still running after everyone left: {still}"
    assert soak.counts.get("restarts") == 1
    for what in ("station 7 pieces", "station 8 pieces", "copy pieces", "file ranges", "dropped"):
        assert soak.counts.get(what, 0) > 0, f"nothing counted for {what}: {soak.counts}"

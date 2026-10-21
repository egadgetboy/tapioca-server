#!/usr/bin/env python3
"""How fast pictures and folders answer under a fast roll's load, against a
running tapiOca (the plan's release gate: "No release may make browsing
slower"; DL282). The standard library and httpx only.

It first asks once for a quarter of the folder's posters at the width it
measures (these are "kept"), then waits until the folder's kept list is
stale (past the server's WHOLE_S, 120 s), so its pages have to ask the
library whether it changed. Then it sends N picture requests at once, as a
fast roll does (the kept ones again, and others never asked for, "cold"),
64 at a time, giving up on half of them partway (the app scrolled past).
About 50 ms in, it opens `--open`, another folder not opened since the
server started, so its whole list has to be fetched behind the pictures'
work, as when 1.42.1's folders failed; and it asks the first folder's
first page every second meanwhile. Each request is timed from when it's
sent, never while it waits for one of the 64, on connections opened before
the roll. It prints p50 and p95 for kept pictures, cold pictures and folder
pages, the opened folder's time, and the count of 503s.

    python tools/picture_load.py --url http://192.168.1.20:3310 \\
        --token <an app's sign-in> --folder 2 --open 3 --pictures 300

Start the server fresh first, so `--open` hasn't been opened. The budget
(p95 at most): a folder page during the roll, and the folder opened, 1.5 s,
never a 503; a kept picture 30 ms (on the server's own network); a cold
picture 800 ms. Run it on
the plan's low-end server against 1.41.0 (the baseline), 1.42.1 (which
fails it) and the release being checked, and record the numbers in its
readiness record.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import sys
import time

import httpx

BUDGET = {"folder": 1.5, "opened": 1.5, "kept": 0.030, "cold": 0.800}


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


AT_ONCE = 64  # (the requests in flight at once, as many as the client's connections)
WIDTH = 480  # (the width every picture is asked for at, kept or cold)
STALE_S = 125  # (past the server's WHOLE_S, 120 s: the folder's kept list must be asked for again)


async def run(
    url: str,
    token: str,
    folder: str,
    n: int,
    wait_s: float,
    transport: httpx.AsyncBaseTransport | None = None,
    other: str = "",
) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    limits = httpx.Limits(max_connections=AT_ONCE)
    async with httpx.AsyncClient(
        base_url=url, headers=headers, timeout=30, limits=limits, transport=transport
    ) as c:
        keys: list[str] = []
        while len(keys) < n:
            listed = await c.get(f"/api/internal/libraries/{folder}?start={len(keys)}&size=200")
            listed.raise_for_status()
            page = [i["key"] for i in listed.json().get("items", [])]
            if not page:
                break
            keys += page
        if len(keys) < 8:
            print("That folder has too few titles.")
            return 2
        # (Two sets that never meet: a quarter kept, the rest cold, each asked for once in the roll.)
        kept_keys = keys[: max(1, len(keys) // 4)]
        cold_keys = keys[len(kept_keys) :]
        for k in kept_keys:  # (kept: asked once first, at the width measured)
            await c.get(f"/api/internal/art/{k}?kind=poster&w={WIDTH}")
        if wait_s > 0:
            print(f"Waiting {wait_s:.0f} s for the folder's kept list to go stale...")
            await asyncio.sleep(wait_s)
        # (The connections opened again before the roll: the wait outlasts the server's keep-alive,
        # and a new connection's setup isn't the server's time.)
        await asyncio.gather(*(c.get("/api/v1/server") for _ in range(AT_ONCE)))
        kept: list[float] = []
        cold: list[float] = []
        pages: list[float] = []
        failures = {"picture": 0, "folder": 0}
        turns = asyncio.Semaphore(AT_ONCE)

        async def picture(key: str, bucket: list[float]) -> None:
            async with turns:  # (timed from when it's sent, never while it waits for a turn)
                began = time.monotonic()
                got = await c.get(f"/api/internal/art/{key}?kind=poster&w={WIDTH}")
            if got.status_code == 503:
                failures["picture"] += 1
            elif got.status_code == 200:
                bucket.append(time.monotonic() - began)

        stop = asyncio.Event()

        async def folder_pages() -> None:
            while not stop.is_set():
                began = time.monotonic()
                got = await c.get(f"/api/internal/libraries/{folder}?start=0&size=50")
                if got.status_code == 503:
                    failures["folder"] += 1
                pages.append(time.monotonic() - began)
                await asyncio.sleep(1)

        opened: list[float] = []

        async def open_other() -> None:
            await asyncio.sleep(0.05)
            began = time.monotonic()
            got = await c.get(f"/api/internal/libraries/{other}?start=0&size=50")
            if got.status_code == 503:
                failures["folder"] += 1
            opened.append(time.monotonic() - began)

        roll = [(k, kept) for k in kept_keys] + [(k, cold) for k in cold_keys]
        random.shuffle(roll)
        asks = [asyncio.create_task(picture(k, bucket)) for k, bucket in roll[:n]]
        # (After the roll's own: the pages queue behind the pictures' work, as in an app.)
        watcher = asyncio.create_task(folder_pages())
        opening = asyncio.create_task(open_other()) if other else None
        await asyncio.sleep(0.3)
        for a in asks[::2]:
            a.cancel()  # (half given up: scrolled past)
        await asyncio.gather(*asks, return_exceptions=True)
        if opening is not None:
            await opening
        await asyncio.sleep(2)
        stop.set()
        await watcher
    if not other:
        print("No --open folder: the opened folder isn't measured (1.42.1's failure needs it).")
    rows = (("folder", pages), ("opened", opened), ("kept", kept), ("cold", cold))
    over = False
    for name, values in rows:
        if not values:
            continue
        p50, p95 = pct(values, 50), pct(values, 95)
        bad = p95 > BUDGET[name]
        over |= bad
        print(f"{name:7} n={len(values):4} p50={p50 * 1000:7.0f} ms  p95={p95 * 1000:7.0f} ms"
              f"  budget {BUDGET[name] * 1000:.0f} ms{'  OVER' if bad else ''}")  # fmt: skip
    print(f"503s: folder {failures['folder']}, pictures {failures['picture']}")
    if pages:
        print(f"(folder pages: mean {statistics.mean(pages) * 1000:.0f} ms)")
    return 1 if over or failures["folder"] else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--token", default="", help="an app's sign-in, when signing in is on")
    ap.add_argument("--folder", default="2", help="a Movies or Shows folder's key")
    ap.add_argument(
        "--open", default="", help="another folder's key, not opened since the server started"
    )
    ap.add_argument("--pictures", type=int, default=300)
    ap.add_argument(
        "--wait",
        type=float,
        default=STALE_S,
        help="seconds to wait for the folder's list to go stale (0: don't)",
    )
    args = ap.parse_args()
    return asyncio.run(
        run(
            args.url.rstrip("/"), args.token, args.folder, args.pictures, args.wait, other=args.open
        )
    )


if __name__ == "__main__":
    sys.exit(main())

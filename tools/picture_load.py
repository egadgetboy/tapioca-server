#!/usr/bin/env python3
"""How fast pictures and folders answer under a fast roll's load, against a
running tapiOca (the plan's release gate: "No release may make browsing
slower"; DL282). The standard library and httpx only.

It sends N picture requests at once, as a fast roll does, giving up on half
of them partway (the app scrolled past), and asks a folder's first page
every second meanwhile. Then it prints p50 and p95 for kept pictures, cold
pictures and folder pages, with the count of 503s.

    python tools/picture_load.py --url http://192.168.1.20:3310 \\
        --token <an app's sign-in> --folder 2 --pictures 300

The budget (p95 at most): a folder page during the roll 1.5 s, never a
503; a kept picture 30 ms (server time); a cold picture 800 ms. Run it on
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

BUDGET = {"folder": 1.5, "kept": 0.030, "cold": 0.800}


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


async def run(url: str, token: str, folder: str, n: int) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    limits = httpx.Limits(max_connections=64)
    async with httpx.AsyncClient(base_url=url, headers=headers, timeout=30, limits=limits) as c:
        listed = await c.get(f"/api/internal/libraries/{folder}?start=0&size=200")
        listed.raise_for_status()
        keys = [i["key"] for i in listed.json().get("items", [])]
        if not keys:
            print("That folder has no titles.")
            return 2
        kept_keys = keys[: max(1, len(keys) // 4)]
        for k in kept_keys:  # (kept: asked once first)
            await c.get(f"/api/internal/art/{k}?kind=poster&w=320")
        kept: list[float] = []
        cold: list[float] = []
        pages: list[float] = []
        failures = {"picture": 0, "folder": 0}

        async def picture(key: str, bucket: list[float]) -> None:
            began = time.monotonic()
            got = await c.get(f"/api/internal/art/{key}?kind=poster&w=480")
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

        watcher = asyncio.create_task(folder_pages())
        asks = []
        for i in range(n):
            if i % 4 == 0:
                asks.append(asyncio.create_task(picture(random.choice(kept_keys), kept)))
            else:
                asks.append(asyncio.create_task(picture(keys[i % len(keys)] + "", cold)))
        await asyncio.sleep(0.3)
        for a in asks[::2]:
            a.cancel()  # (half given up: scrolled past)
        await asyncio.gather(*asks, return_exceptions=True)
        await asyncio.sleep(2)
        stop.set()
        await watcher
    rows = (("folder", pages), ("kept", kept), ("cold", cold))
    over = False
    for name, values in rows:
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
    ap.add_argument("--pictures", type=int, default=300)
    args = ap.parse_args()
    return asyncio.run(run(args.url.rstrip("/"), args.token, args.folder, args.pictures))


if __name__ == "__main__":
    sys.exit(main())

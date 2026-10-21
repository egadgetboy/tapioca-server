"""The server's proof (1.43.0): POST /api/internal/proof, where tapiOca's
apps check that the server answering at an address is the one they set up
with, by its key (serverkey.py), before anything else goes there (the apps
repo's docs/threat-models/server-proof.md, section 3).

An app sends a fresh nonce and the address it's asking. Requests waiting
in a lane are signed together, in one statement that names each only by a
hash, `SHA-256("tapioca/1 proof-entry\\n" + nonce + "\\n" + address)`, among
exactly 64 entries (the rest random, all sorted), with what /api/v1/server
would answer in that lane:

    {"time": ms, "server": {...}, "proofs": [64 lowercase hex entries]}

- **Two lanes,** home and outside (`lane_for`: the Gate's `outside`, with
  door "name", the away name at the home port with no forwarding headers,
  in the outside lane). A statement carries one lane's `server`, built at
  each signature. A missing Gate state is never taken as home: 503.
- **The pace:** a lane signs when a request is waiting and the larger of
  25 ms and three times the last signature's own time has passed since
  the last began (a failed one counts as 25 ms), at most 64 entries a
  statement. So a lane uses at most about a third of a core.
- **Refused:** a nonce that isn't 64 lowercase hex digits, or an address
  that isn't printable ASCII of 200 characters at most (400); any request
  with an Origin (403: no web page can make tapiOca sign); at home, a Host
  that isn't home's or the away address's host (403, with one Admin alert
  that names nothing); an https:// address that isn't, in its one
  canonical form, one of the server's own; an http:// address from
  outside (403); too many (429); no key (503).
- **Limits:** per source (an address; IPv6 per /56 from outside), 60 a
  minute and 4 waiting; a relay (relays.py), 600 a minute and 8 waiting;
  from outside, 600 a minute for each IPv6 /48; at most 256 waiting in a
  lane. The tables of sources are bounded.
- Every answer at the route, refusals included, carries `Tapioca-Proof: 1`
  (ProofMarker, outside the Gate), so an app can tell a 1.43.0 server's
  refusal from an older server's 401 or 403.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import re
import secrets
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from . import access, alerts, networks, reconnect, serverkey

if TYPE_CHECKING:
    from .main import AppContext

log = logging.getLogger(__name__)

ROUTE = "/api/internal/proof"
MARKER = (b"tapioca-proof", b"1")

WAITING_MOST = 256  # (in each lane: four full statements)
PER_SOURCE_MINUTE = 60
PER_SOURCE_WAITING = 4  # (one device's round asks up to three at once)
RELAY_MINUTE = 600  # (a relay carries a whole household)
RELAY_WAITING = 8
PREFIX48_MINUTE = 600  # (from outside, each IPv6 /48)
SOURCES_MOST = 4096  # (each table of sources; the oldest dropped first)
ENTRIES = 64
PACE_LEAST_S = 0.025
PACE_TIMES = 3
STATEMENT_MOST = 12 * 1024
ADDRESS_MOST = 200
NONCE = re.compile(r"[0-9a-f]{64}")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")

TOO_LONG = (
    "tapiOca's name is too long for its apps. Shorten FRIENDLY_NAME where tapiOca is installed "
    "(its app settings on TrueNAS, or docker-compose.yml), then restart tapiOca."
)
UNKNOWN_NAME = "An app at home used a name tapiOca doesn't know. See Access."


def lane_for(scope: dict) -> str | None:
    """Which lane a request is signed in: "home", "outside", or None when
    the Gate's state says nothing (never a guess)."""
    state = scope.get("state") or {}
    if "outside" not in state:
        return None
    verdict = state.get("verdict")
    if state["outside"] or (verdict is not None and getattr(verdict, "door3", False)):
        return "outside"
    return "home"


def entry(nonce: str, address: str) -> str:
    return hashlib.sha256(f"tapioca/1 proof-entry\n{nonce}\n{address}".encode("ascii")).hexdigest()


def canonical(address: str) -> str | None:
    """An https:// address in its one canonical form (https://, a lowercase
    host, :port only if it isn't 443, nothing after), or None: the one
    grammar both the server and the apps compare by (the apps also cut a
    typed path first; the server never does). Never urlsplit."""
    if address[:8].lower() != "https://":
        return None
    rest = address[8:]
    if (
        not rest
        or any(c in rest for c in "/\\@?#% ")
        or not rest.isascii()
        or not rest.isprintable()
    ):
        return None
    if rest.startswith("["):
        close = rest.find("]")
        if close < 0:
            return None
        host, after = rest[: close + 1].lower(), rest[close + 1 :]
        try:
            ip = ipaddress.IPv6Address(host[1:-1])
        except ValueError:
            return None
        if ip.compressed != host[1:-1]:
            return None
    else:
        host, colon, port = rest.partition(":")
        after = colon + port
        host = host.lower()
        if host.endswith("."):
            host = host[:-1]
        if host and set(host) <= set("0123456789."):
            parts = host.split(".")
            if len(parts) != 4 or not all(
                p.isdigit() and (p == "0" or not p.startswith("0")) and int(p) <= 255 for p in parts
            ):
                return None
        elif not host or len(host) > 253 or not all(_LABEL.fullmatch(lb) for lb in host.split(".")):
            return None
    if after:
        digits = after[1:]
        if not after.startswith(":") or not digits.isdigit() or digits.startswith("0"):
            return None
        if not 1 <= int(digits) <= 65535:
            return None
        if int(digits) == 443:
            after = ""
    made = "https://" + host + after
    return made if len(made) <= ADDRESS_MOST else None


def counted(scope: dict, lane: str) -> tuple[str, bool, str | None]:
    """Who a request counts against: (the source, whether it's a relay, its
    IPv6 /48 from outside, if any)."""
    state = scope.get("state") or {}
    verdict = state.get("verdict")
    if state.get("relay") and verdict is not None and verdict.peer is not None:
        return f"relay {verdict.peer}", True, None
    where = access.address(scope)
    try:
        ip = ipaddress.ip_address(where)
    except ValueError:
        return where, False, None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is None and lane == "outside":
        return (
            str(ipaddress.IPv6Network(f"{ip}/56", strict=False)),
            False,
            str(ipaddress.IPv6Network(f"{ip}/48", strict=False)),
        )
    return access.counted_as(where), False, None


class Limited(Exception):
    """Too many: 429."""


class Full(Exception):
    """The lane has WAITING_MOST waiting: 429."""


class TooLong(Exception):
    """The statement would be over STATEMENT_MOST: 503."""


class Sources:
    """How many each source asked in the last minute, and has waiting."""

    def __init__(self) -> None:
        self._times: OrderedDict[str, deque[float]] = OrderedDict()
        self._waiting: dict[str, int] = {}

    def _recent(self, key: str, now: float) -> deque[float]:
        times = self._times.pop(key, None) or deque()
        while times and now - times[0] >= 60:
            times.popleft()
        self._times[key] = times  # (now the newest)
        while len(self._times) > SOURCES_MOST:
            old, _ = self._times.popitem(last=False)
            if not self._waiting.get(old):
                self._waiting.pop(old, None)
        return times

    def would(self, key: str, minute: int, waiting: int, now: float) -> bool:
        return len(self._recent(key, now)) < minute and self._waiting.get(key, 0) < waiting

    def take(self, key: str, now: float) -> None:
        self._recent(key, now).append(now)
        self._waiting[key] = self._waiting.get(key, 0) + 1

    def done(self, key: str) -> None:
        left = self._waiting.get(key, 0) - 1
        if left > 0:
            self._waiting[key] = left
        else:
            self._waiting.pop(key, None)


class Lane:
    """One lane's waiting requests, signed together at its pace."""

    def __init__(
        self,
        name: str,
        key: serverkey.ServerKey,
        server: Callable[[], dict],
        too_long: Callable[[], None],
    ) -> None:
        self.name = name
        self.key = key
        self.server = server
        self.too_long = too_long
        self._waiting: list[tuple[str, asyncio.Future]] = []
        self._wake: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._last_start: float | None = None
        self._pace = PACE_LEAST_S

    def __len__(self) -> int:
        return len(self._waiting)

    async def ask(self, hashed: str) -> tuple[str, str]:
        """The statement and its signature (base64) for one request's entry."""
        if len(self._waiting) >= WAITING_MOST:
            raise Full()
        loop = asyncio.get_running_loop()
        if self._wake is None:
            self._wake = asyncio.Event()
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._run())
        future: asyncio.Future = loop.create_future()
        self._waiting.append((hashed, future))
        self._wake.set()
        return await future

    def statement(self, entries: list[str]) -> str:
        pads = [secrets.token_hex(32) for _ in range(ENTRIES - len(entries))]
        body = {
            "time": int(time.time() * 1000),
            "server": self.server(),
            "proofs": sorted([*entries, *pads]),
        }
        return json.dumps(body, separators=(",", ":"), ensure_ascii=True)

    async def _run(self) -> None:
        assert self._wake is not None
        while True:
            await self._wake.wait()
            if not self._waiting:
                self._wake.clear()
                continue
            if self._last_start is not None:
                wait = self._last_start + self._pace - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
            batch: list[tuple[str, asyncio.Future]] = []
            entries: list[str] = []
            rest: list[tuple[str, asyncio.Future]] = []
            for hashed, future in self._waiting:
                if hashed in entries or len(entries) < ENTRIES:
                    if hashed not in entries:
                        entries.append(hashed)
                    batch.append((hashed, future))
                else:
                    rest.append((hashed, future))
            self._waiting = rest
            began = self._last_start = time.monotonic()
            try:
                text = self.statement(entries)
                if len(text) > STATEMENT_MOST:
                    self.too_long()
                    raise TooLong()
                signature = await self.key.sign("server-proof", text.encode("ascii"))
            except Exception as e:  # (each waiting request gets it: 503)
                self._pace = PACE_LEAST_S
                for _, future in batch:
                    if not future.done():
                        future.set_exception(e)
                        future.exception()  # (retrieved, should its request be gone)
            else:
                self._pace = max(PACE_LEAST_S, PACE_TIMES * (time.monotonic() - began))
                answer = (text, base64.b64encode(signature).decode("ascii"))
                for _, future in batch:
                    if not future.done():
                        future.set_result(answer)
            if not self._waiting:
                self._wake.clear()


class Proofs:
    """The two lanes, and who's asked how often."""

    def __init__(self, key: serverkey.ServerKey, server: Callable[[bool], dict],
                 too_long: Callable[[], None]) -> None:  # fmt: skip
        self.key = key
        self.lanes = {
            "home": Lane("home", key, lambda: server(False), too_long),
            "outside": Lane("outside", key, lambda: server(True), too_long),
        }
        self.sources = Sources()
        self.prefixes = Sources()

    def fits(self) -> bool:
        """Whether a statement fits STATEMENT_MOST in either lane (checked at
        start, and again before each signature)."""
        filler = ["0" * 64] * ENTRIES
        return all(len(lane.statement(filler)) <= STATEMENT_MOST for lane in self.lanes.values())

    async def ask(self, scope: dict, lane: str, hashed: str) -> tuple[str, str]:
        source, relay, prefix = counted(scope, lane)
        now = time.monotonic()
        minute, waiting = (
            (RELAY_MINUTE, RELAY_WAITING) if relay else (PER_SOURCE_MINUTE, PER_SOURCE_WAITING)
        )
        if not self.sources.would(source, minute, waiting, now):
            raise Limited()
        if prefix is not None and not self.prefixes.would(
            prefix, PREFIX48_MINUTE, WAITING_MOST, now
        ):
            raise Limited()
        if len(self.lanes[lane]) >= WAITING_MOST:
            raise Full()
        self.sources.take(source, now)
        if prefix is not None:
            self.prefixes.take(prefix, now)
        try:
            return await self.lanes[lane].ask(hashed)
        finally:
            self.sources.done(source)
            if prefix is not None:
                self.prefixes.done(prefix)


class ProofMarker:
    """`Tapioca-Proof: 1` on every answer at the proof route, refusals by
    the Gate included: a plain ASGI layer, outside the others."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(
        self, scope: dict, receive: Callable[[], Awaitable[Any]], send: Callable
    ) -> None:
        if scope["type"] != "http" or scope["path"] != ROUTE:
            await self.app(scope, receive, send)
            return

        async def sending(message: dict) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*(message.get("headers") or ()), MARKER]}
            await send(message)

        await self.app(scope, receive, sending)


def origins(ctx: AppContext) -> set[str]:
    """The server's own https:// origins, in their canonical form: the away
    address, and https:// with each name an Admin listed for home."""
    found = set()
    scheme, _, rest = (ctx.away.address or "").partition("://")
    if scheme.lower() == "https":
        # (A stored address may end with a slash or a path: cut, as the apps do.)
        made = canonical("https://" + rest.split("/", 1)[0])
        if made is not None:
            found.add(made)
    for name in ctx.trusted.home_names:
        made = canonical(f"https://{name}")
        if made is not None:
            found.add(made)
    return found


def _away_host(ctx: AppContext) -> str:
    if not ctx.away.address:
        return ""
    rest = ctx.away.address.split("://", 1)[-1].split("/", 1)[0]
    return networks._host_name(rest)


def routes(app: FastAPI, ctx: AppContext) -> None:
    app.add_middleware(ProofMarker)
    host_said: dict[str, float] = {}

    def refuse(status: int, detail: str) -> HTTPException:
        return HTTPException(status, detail)

    @app.post(ROUTE)
    async def proof(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise refuse(400, "tapiOca didn't understand that request") from None
        if not isinstance(body, dict):
            raise refuse(400, "tapiOca didn't understand that request")
        nonce, address, again = body.get("nonce"), body.get("address"), body.get("reconnect", False)
        if not isinstance(nonce, str) or not NONCE.fullmatch(nonce):
            raise refuse(400, "The nonce must be 64 lowercase hex digits.")
        if (
            not isinstance(address, str)
            or not address
            or len(address) > ADDRESS_MOST
            or not all(" " <= c <= "~" for c in address)
        ):
            raise refuse(400, "The address must be printable text of 200 characters at most.")
        if not isinstance(again, bool):
            raise refuse(400, "reconnect must be true or false.")
        if request.headers.get("origin") is not None:
            raise refuse(403, "tapiOca's proof isn't for web pages.")
        scope = request.scope
        lane = lane_for(scope)
        if lane is None:
            raise refuse(503, "tapiOca is getting ready.")
        if not access.outside(scope):
            host = request.headers.get("host", "")
            also_home, never_home = ctx.gate_hosts()
            kind = networks.host_kind(host, ctx.trusted.home_names, also_home, never_home)
            away_host = _away_host(ctx)
            if kind != "home" and not (away_host and networks._host_name(host) == away_host):
                now = time.time()
                if now - host_said.get("at", 0.0) >= 86_400:
                    host_said["at"] = now
                    ctx.alerts.start(alerts.ACCESS, UNKNOWN_NAME, about="proof-host")
                ctx.proof_host_refused = host.strip()[:100]
                raise refuse(
                    403,
                    "tapiOca doesn't know this name at home. An Admin can add it under Names for "
                    "tapiOca at home, on the Access tab.",
                )
        if address.lower().startswith("https://"):
            made = canonical(address)
            if made is None or made not in origins(ctx):
                raise refuse(403, "tapiOca proves itself only at its own addresses.")
        elif lane == "outside":
            raise refuse(403, "From outside your home, tapiOca proves itself only over HTTPS.")
        elif not address.lower().startswith("http://"):
            raise refuse(403, "tapiOca proves itself only at its own addresses.")
        if ctx.server_key.state != "ready":
            raise refuse(503, "tapiOca is getting ready.")
        try:
            text, signature = await ctx.proofs.ask(scope, lane, entry(nonce, address))
        except (Limited, Full):
            raise refuse(429, "tapiOca is busy. Try again in a moment.") from None
        except (serverkey.NotReady, serverkey.SignFailed, TooLong):
            raise refuse(503, "tapiOca is getting ready.") from None
        said = {"statement": text, "signature": signature, "key": ctx.server_key.public_text}
        if again:
            said.update(ctx.reconnect.fields(nonce, ctx.server_key.public_text))
        return Response(json.dumps(said, separators=(",", ":")), media_type="application/json")

    @app.post("/api/access/reconnect")
    async def make_code(request: Request):
        user = access.signed_in(request)
        try:
            code, seconds = ctx.reconnect.make(user.id if user else None)
        except reconnect.TooMany:
            raise refuse(
                429, "Five codes were made in the last 10 minutes. Try again soon."
            ) from None
        log.info("A Reconnect apps code was made")
        return {"code": code, "seconds": seconds}

    @app.delete("/api/access/reconnect")
    async def end_code():
        ctx.reconnect.end()
        log.info("The Reconnect apps code was ended")
        return {"active": False}

    @app.get("/api/access/reconnect")
    async def code_status(request: Request):
        user = access.signed_in(request)
        return ctx.reconnect.status(user.id if user else None)

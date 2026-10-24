"""One vetted way out (the security suite's SSRF-01 to SSRF-08; DL287).

Every request tapiOca's own code makes to another machine goes through a
transport made here, which decides before it connects, by where the address
came from (the owner, October 21, 1:37 PM: "The right security principle is
provenance"):

- TYPED: an address an Admin typed into a setting (Plex, Sonarr or Radarr,
  an alert address, this tapiOca's own away address). It may be on the home
  network, loopback included, and may carry a user name and password (sent
  to that address only, as the client's Basic sign-in).
- FIXED: an address in tapiOca's own code (GitHub's releases). It must be
  public.
- DATA: an address that came from data (a list, a linked server, a picture's
  address). It must be public, and may not carry a user name or password.

For all three: http or https only; the cloud metadata addresses and every
link-local address refused; the name looked up once, within the request's
connect timeout, on a lookup pool of its own (never the one disk reads
use), checked, and the request sent only to the addresses it found and
allowed, tried in order (so a second answer from the name's DNS can't move
it: rebinding); TLS checked against the name, on connections kept for that
name alone; and tapiOca's own User-Agent. No client here follows a redirect
(each caller sets that, and the census checks it). FFmpeg reads Plex's own
stream addresses itself: they're built by PlexClient.stream_url, whose host
is always the typed Plex address.

A refusal is a Refused, an httpx.TransportError, so every caller's existing
handling of an unreachable address handles it; a name that can't be found
is a NotFound, also an httpx.ConnectError, as it was before this module;
a lookup too slow is an httpx.ConnectTimeout.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import __version__

TYPED, FIXED, DATA = "typed", "fixed", "data"
KINDS = (TYPED, FIXED, DATA)

USER_AGENT = f"tapiOca/{__version__}"

# The cloud metadata addresses, refused for every kind (SSRF-03).
_METADATA = tuple(
    ipaddress.ip_network(n)
    for n in (
        "169.254.169.254/32",  # (most clouds)
        "fd00:ec2::254/128",  # (AWS, over IPv6)
        "100.100.100.200/32",  # (Alibaba Cloud)
        "192.0.0.192/32",  # (Oracle Cloud)
    )
)
# NAT64's well-known prefix: an address there is the IPv4 address it carries (RFC 6052).
_NAT64 = ipaddress.ip_network("64:ff9b::/96")

# How long a lookup may take when the request names no connect timeout.
LOOKUP_S = 10.0
# How long a looked-up name's addresses are kept, for each transport (the
# request still goes only to them: pinning holds).
KEEP_S = 30.0
# How long they're still used if looking the name up again fails (an
# internet outage with Plex at home by name): only addresses already vetted.
STALE_S = 600.0
# Lookups run here, never on the event loop's default pool, which disk reads
# for playback share: a dead DNS server can't hold up a stream. One lookup
# at a time for each name, however many ask, so a dead one ties up one
# thread, not all of them.
_LOOKUPS = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tapioca-lookup")
_FLYING: dict[tuple[int, str], asyncio.Future] = {}


class Refused(httpx.TransportError):
    """tapiOca won't send this request (its address, by where it came from).
    `why` says what's wrong without naming the address."""

    def __init__(self, message: str, why: str = "") -> None:
        super().__init__(message)
        self.why = why or message


class NotFound(Refused, httpx.ConnectError):
    """The name couldn't be found (its message keeps the system's reason, so
    callers that read it, such as Plex's trouble(), still can)."""


Address = ipaddress.IPv4Address | ipaddress.IPv6Address


def _as_ipv4(ip: Address) -> Address:
    """An IPv6 address that carries an IPv4 one (mapped, IPv4-compatible,
    NAT64's, 6to4's or Teredo's), as that IPv4 address."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped
        if ip in _NAT64 or 1 < int(ip) < 2**32:
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if ip.sixtofour is not None:
            return ip.sixtofour
        if ip.teredo is not None:
            return ip.teredo[1]
    return ip


def host_of(url: httpx.URL) -> str:
    """The name to look up and to check TLS against: the URL's host as sent
    (IDNA-encoded ASCII), never its Unicode form."""
    return url.raw_host.decode("ascii")


async def _resolve(host: str) -> list[Address]:
    """The addresses a name has (an address is its own). NotFound if none."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    key = (id(loop), host)
    flying = _FLYING.get(key)
    if flying is not None and (flying.get_loop() is not loop or loop.is_closed()):
        flying = None  # (left by a loop that's gone, whose id() this one now has)
    if flying is None:
        flying = loop.run_in_executor(
            _LOOKUPS, lambda: socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        )
        _FLYING[key] = flying

        def done(f: asyncio.Future) -> None:
            _FLYING.pop(key, None)
            if not f.cancelled():
                f.exception()  # (read, so a lookup no one still waits for logs nothing)

        flying.add_done_callback(done)
    try:
        # (Shielded: one asker's time limit never ends the lookup for the others.)
        found = await asyncio.shield(flying)
    except (OSError, UnicodeError) as e:
        # (UnicodeError: a name with an empty or overlong label, such as a mistyped "192.168.1..5".)
        raise NotFound(f"tapiOca can't find {host}: {e}", "a name that can't be found") from e
    out: list[Address] = []
    for *_, sockaddr in found:
        ip = ipaddress.ip_address(sockaddr[0].split("%", 1)[0])
        if ip not in out:
            out.append(ip)
    return out


# How a name is resolved: the system's, unless the tests set their own (tests/conftest.py).
RESOLVE: Callable[[str], Awaitable[list[Address]]] = _resolve


def _home_or_inside(ip: Address) -> bool:
    """Not on the public internet: private, loopback, unique-local, CGNAT, reserved or unspecified."""
    ip = _as_ipv4(ip)
    return (
        not ip.is_global or ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_reserved
    )


def refusal(ip: Address, kind: str) -> str | None:
    """Why an address may not be asked for this kind, or None."""
    ip = _as_ipv4(ip)
    if any(ip in net for net in _METADATA):
        return "a cloud metadata address"
    if ip.is_link_local:
        return "a link-local address"
    if ip.is_multicast or ip.is_unspecified:
        return "not an address a request can go to"
    if kind != TYPED and _home_or_inside(ip):
        return "not on the public internet"
    return None


async def _lookup(host: str, timeout: float | None) -> list[Address]:
    try:
        found = await asyncio.wait_for(RESOLVE(host), timeout or LOOKUP_S)
    except TimeoutError:
        raise httpx.ConnectTimeout(f"Looking up {host} took too long") from None
    if not found:
        raise NotFound(f"tapiOca can't find {host}", "a name that can't be found")
    return found


async def lookup(host: str, timeout: float | None = None) -> list[Address]:
    """A name's addresses, looked up as every request's are: on the lookup
    pool, within `timeout` (LOOKUP_S if None). NotFound or ConnectTimeout."""
    return await _lookup(host, timeout)


def allowed(host: str, found: list[Address], kind: str) -> list[Address]:
    """The addresses among `found` a request may go to, in order, or Refused.
    A typed name keeps its allowed answers (a home name that also answers a
    link-local address still reaches home); a fixed or data name with any
    answer refused is refused whole, so DNS can't slip an inside address in."""
    reasons = [(ip, refusal(ip, kind)) for ip in found]
    ok = [ip for ip, why in reasons if why is None]
    bad = [why for _, why in reasons if why is not None]
    if bad and (kind != TYPED or not ok):
        raise Refused(f"{host} is {bad[0]}", bad[0])
    return ok


def _host_checked(url: httpx.URL, kind: str) -> str:
    """The name a request to `url` would look up, once its address is one that may be asked."""
    if kind not in KINDS:
        raise ValueError(kind)
    if url.scheme not in ("http", "https"):
        raise Refused("That isn't a web address (http or https)", "not a web address")
    if url.userinfo and kind != TYPED:
        raise Refused("An address with a name or password in it", "an address with a name or password in it")
    if not url.raw_host:
        raise Refused("An address with no host", "an address with no host")
    return host_of(url)


async def vet(url: httpx.URL, kind: str, timeout: float | None = None) -> list[Address]:
    """The addresses a request to `url` may go to, in order, or Refused."""
    host = _host_checked(url, kind)
    return allowed(host, await _lookup(host, timeout), kind)


def _connect_timeout(request: httpx.Request) -> float | None:
    timeouts = request.extensions.get("timeout") or {}
    return timeouts.get("connect") if isinstance(timeouts, dict) else None


class GuardedTransport(httpx.AsyncBaseTransport):
    """Vets every request before it's sent. With no `inner` transport (the
    real network), it sends to the addresses it vetted and nowhere else,
    over connections kept for that name alone; an `inner` one (the tests'
    stand-ins) gets the request as it was, after the same decision."""

    def __init__(self, kind: str, inner: httpx.AsyncBaseTransport | None = None) -> None:
        if kind not in KINDS:
            raise ValueError(kind)
        self.kind = kind
        self.inner = inner
        # (One pool of connections for each scheme, name and port: a kept TLS
        # connection checked for one name is never used for another.)
        self._real: dict[tuple[str, str, int | None], httpx.AsyncHTTPTransport] = {}
        # (For each name: when it was looked up, what was allowed, and until when it's used as is.)
        self._kept: dict[str, tuple[float, list[Address], float]] = {}

    async def _addresses(self, request: httpx.Request) -> list[Address]:
        url = request.url
        if self.inner is not None:
            return await vet(url, self.kind, _connect_timeout(request))
        host = _host_checked(url, self.kind)
        kept = self._kept.get(host)
        now = time.monotonic()
        if kept and now < kept[2]:
            return kept[1]
        try:
            found = allowed(host, await _lookup(host, _connect_timeout(request)), self.kind)
        except (NotFound, httpx.ConnectTimeout):
            # (Looking it up again failed: what was vetted before still goes, for a while, and
            # only the next request after KEEP_S tries the lookup again, not every one.)
            if kept and now - kept[0] < STALE_S:
                self._kept[host] = (kept[0], kept[1], now + KEEP_S)
                return kept[1]
            raise
        self._kept[host] = (now, found, now + KEEP_S)
        return found

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        ips = await self._addresses(request)
        if "user-agent" not in request.headers or request.headers["user-agent"].startswith(
            "python-httpx"
        ):
            request.headers["User-Agent"] = USER_AGENT
        if self.inner is not None:
            return await self.inner.handle_async_request(request)
        original = request.url
        host = host_of(original)
        key = (original.scheme, host, original.port)
        real = self._real.get(key)
        if real is None:
            real = self._real[key] = httpx.AsyncHTTPTransport(trust_env=False)
        if "host" not in request.headers:
            request.headers["Host"] = original.netloc.decode("ascii")
        if original.scheme == "https":
            request.extensions = {**request.extensions, "sni_hostname": host}
        try:
            for n, ip in enumerate(ips):
                # (The user name and password, if typed, already went into the
                # client's Authorization header; the address carries neither.)
                request.url = original.copy_with(host=str(ip), username=None, password=None)
                try:
                    return await real.handle_async_request(request)
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    if n == len(ips) - 1:
                        # (None of them answers: the name is looked up again next time, in case
                        # it's moved. The cold audit of 1.44.0's second round.)
                        self._kept.pop(host, None)
                        raise
            raise Refused(f"{host} has no address to go to", "a name with no address to go to")
        finally:
            # (What the caller sees, such as a redirect's base, is the name, never the address.)
            request.url = original

    async def aclose(self) -> None:
        if self.inner is not None:
            await self.inner.aclose()
        for real in self._real.values():
            await real.aclose()


def transport(kind: str, inner: httpx.AsyncBaseTransport | None = None) -> GuardedTransport:
    """The transport every outbound client takes (`transport=safefetch.transport(...)`)."""
    return GuardedTransport(kind, inner)


async def at_home(address: str) -> bool:
    """Whether a typed address points inside the home (the page asks before
    saving one: DL287). False when it can't be read or found: saving it is
    then up to the address's own checks."""
    try:
        url = httpx.URL(address.strip())
        if not url.raw_host:
            return False
        found = await _lookup(host_of(url), None)
    except (httpx.InvalidURL, httpx.TransportError, ValueError, UnicodeError):
        return False
    return any(_home_or_inside(ip) for ip in found)


async def typed_refusal(address: str) -> str | None:
    """Why a typed address will never be sent to, said without the address
    (a cloud metadata or link-local address, or not a web address), or None.
    Asked before one is saved, so a refused address is never kept (DL287).
    A name that can't be found now isn't refused: it may be found later."""
    try:
        url = httpx.URL(address.strip())
        await vet(url, TYPED)
    except NotFound:
        return None
    except Refused as e:
        return e.why
    except (httpx.InvalidURL, httpx.TransportError, ValueError, UnicodeError):
        return None
    return None

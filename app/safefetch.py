"""One vetted way out (the security suite's SSRF-01 to SSRF-08; DL287).

Every request tapiOca makes to another machine goes through a transport
made here, which decides before it connects, by where the address came from
(the owner, October 21, 1:37 PM: "The right security principle is
provenance"):

- TYPED: an address an Admin typed into a setting (Plex, Sonarr or Radarr,
  an alert address, this tapiOca's own away address). It may be on the home
  network, loopback included.
- FIXED: an address in tapiOca's own code (GitHub's releases). It must be
  public.
- DATA: an address that came from data (a list, a linked server, a picture's
  address). It must be public.

For all three: http or https only; no name with a user or password in it;
the cloud metadata addresses and every link-local address refused; the name
resolved once and checked, and the request sent to that address only (so a
second answer from the name's DNS can't move it: rebinding); and tapiOca's
own User-Agent. No client here follows a redirect (each caller sets that,
and the census checks it).

A refusal is a Refused, an httpx.TransportError, so every caller's existing
handling of an unreachable address handles it.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

import httpx

from . import __version__

TYPED, FIXED, DATA = "typed", "fixed", "data"
KINDS = (TYPED, FIXED, DATA)

USER_AGENT = f"tapiOca/{__version__}"

# The cloud metadata addresses, refused for every kind (SSRF-03).
_METADATA = (ipaddress.ip_network("169.254.169.254/32"), ipaddress.ip_network("fd00:ec2::254/128"))


class Refused(httpx.TransportError):
    """tapiOca won't send this request (its address, by where it came from)."""


Address = ipaddress.IPv4Address | ipaddress.IPv6Address


async def _resolve(host: str) -> list[Address]:
    """The addresses a name has (an address is its own)."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    loop = asyncio.get_running_loop()
    try:
        found = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as e:
        raise Refused(f"Couldn't find {host}") from e
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
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _home_or_inside(ip.ipv4_mapped)
    return (
        not ip.is_global or ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_reserved
    )


def refusal(ip: Address, kind: str) -> str | None:
    """Why an address may not be asked for this kind, or None."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if any(ip in net for net in _METADATA):
        return "a cloud metadata address"
    if ip.is_link_local:
        return "a link-local address"
    if ip.is_multicast or ip.is_unspecified:
        return "not an address a request can go to"
    if kind != TYPED and _home_or_inside(ip):
        return "not on the public internet"
    return None


async def vet(url: httpx.URL, kind: str) -> Address:
    """The one address a request to `url` may go to, or Refused."""
    if kind not in KINDS:
        raise ValueError(kind)
    if url.scheme not in ("http", "https"):
        raise Refused(f"Only web addresses (http or https), not {url.scheme}:")
    if url.userinfo:
        raise Refused("An address with a name or password in it")
    host = url.host
    if not host:
        raise Refused("An address with no host")
    found = await RESOLVE(host)
    if not found:
        raise Refused(f"Couldn't find {host}")
    for ip in found:
        why = refusal(ip, kind)
        if why:
            # (Every answer must be allowed: a name that answers one allowed and one not is refused.)
            raise Refused(f"{host} is {why}")
    return found[0]


class GuardedTransport(httpx.AsyncBaseTransport):
    """Vets every request before it's sent. With no `inner` transport (the
    real network), it sends to the address it vetted and nowhere else; an
    `inner` one (the tests' stand-ins) gets the request as it was, after
    the same decision."""

    def __init__(self, kind: str, inner: httpx.AsyncBaseTransport | None = None) -> None:
        if kind not in KINDS:
            raise ValueError(kind)
        self.kind = kind
        self.inner = inner
        self._real: httpx.AsyncHTTPTransport | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        ip = await vet(request.url, self.kind)
        if "user-agent" not in request.headers or request.headers["user-agent"].startswith(
            "python-httpx"
        ):
            request.headers["User-Agent"] = USER_AGENT
        if self.inner is not None:
            return await self.inner.handle_async_request(request)
        if self._real is None:
            self._real = httpx.AsyncHTTPTransport(trust_env=False)
        host = request.url.host
        pinned = request.url.copy_with(host=str(ip))
        if "host" not in request.headers:
            request.headers["Host"] = request.url.netloc.decode("ascii")
        if request.url.scheme == "https":
            request.extensions = {**request.extensions, "sni_hostname": host}
        request.url = pinned
        return await self._real.handle_async_request(request)

    async def aclose(self) -> None:
        if self.inner is not None:
            await self.inner.aclose()
        if self._real is not None:
            await self._real.aclose()


def transport(kind: str, inner: httpx.AsyncBaseTransport | None = None) -> GuardedTransport:
    """The transport every outbound client takes (`transport=safefetch.transport(...)`)."""
    return GuardedTransport(kind, inner)

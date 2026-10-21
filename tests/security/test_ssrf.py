"""Outbound requests (DL287 §3): where tapiOca sends what, decided before it
connects. These assert tapiOca's own decision (the address it builds, or its
refusal), never that a socket failed."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from app.plex import PlexClient, PlexError


@pytest.mark.parametrize(
    "part_key",
    [
        "@attacker.test/x",  # (userinfo: "http://plex.test@attacker.test/x")
        "//attacker.test/x",
        ".attacker.test/x",
        ":1@attacker.test/x",
        "/library/parts/1/../../../x",
        "/library/parts/1/file.mkv\r\nHost: attacker.test",
    ],
)
def test_a_file_address_from_plexs_data_never_leaves_plexs_host_or_carries_its_token_elsewhere(
    part_key,
):
    # (SSRF-01, SSRF-08: the file's path comes from Plex's answers. A part key that changes the address's
    # host would send Plex's token to that host, and ffmpeg or the player's proxy there.)
    plex = PlexClient("http://plex.test:32400", "secret-token")
    try:
        address = plex.stream_url(part_key)
    except PlexError:
        return  # (refused: fine)
    parts = urlsplit(address)
    assert (parts.hostname, parts.port) == ("plex.test", 32400), address
    assert parts.username is None and "\r" not in address and "\n" not in address, address
    assert "/.." not in parts.path, address


def test_a_real_part_key_still_makes_its_address():
    plex = PlexClient("http://plex.test:32400", "secret-token")
    address = plex.stream_url("/library/parts/1234/1690000000/file.mkv")
    assert (
        address
        == "http://plex.test:32400/library/parts/1234/1690000000/file.mkv?X-Plex-Token=secret-token"
    )


# --- safefetch: the one vetted way out -----------------------------------------------------------

import ipaddress  # noqa: E402

import httpx  # noqa: E402

from app import safefetch  # noqa: E402


def _names(table: dict[str, list[str]]):
    async def resolve(host: str):
        try:
            return [ipaddress.ip_address(host)]
        except ValueError:
            pass
        if host not in table:
            raise safefetch.Refused(f"Couldn't find {host}")
        return [ipaddress.ip_address(a) for a in table[host]]

    return resolve


NAMES = {
    "plex.home": ["192.168.50.2"],
    "public.example": ["93.184.216.34"],
    "rebinds.example": ["93.184.216.34", "10.0.0.5"],
    "metadata.example": ["169.254.169.254"],
    "v6meta.example": ["fd00:ec2::254"],
    "linklocal.example": ["fe80::1"],
    "mapped.example": ["::ffff:192.168.1.1"],
    "loop.example": ["127.0.0.1"],
}


@pytest.fixture
def names(monkeypatch):
    monkeypatch.setattr(safefetch, "RESOLVE", _names(NAMES))


def _ask(kind: str, url: str) -> int:
    seen: list[httpx.Request] = []

    async def go():
        inner = httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200))
        async with httpx.AsyncClient(
            transport=safefetch.transport(kind, inner), follow_redirects=False
        ) as c:
            return (await c.get(url)).status_code

    import asyncio

    try:
        return asyncio.run(go())
    except safefetch.Refused:
        assert not seen, "refused, but the request was sent anyway"
        return 0


@pytest.mark.parametrize(
    ("kind", "url", "sent"),
    [
        # (Typed by an Admin: the home network and loopback allowed: Plex, a home Gotify; DL287.)
        ("typed", "http://plex.home:32400/identity", True),
        ("typed", "http://192.168.1.9:8123/api/webhook/x", True),
        ("typed", "http://loop.example:8989/api", True),
        ("typed", "http://public.example/x", True),
        # (SSRF-03: the cloud metadata addresses and link-local, never, typed or not.)
        ("typed", "http://169.254.169.254/latest/meta-data/", False),
        ("typed", "http://metadata.example/latest/", False),
        ("typed", "http://v6meta.example/", False),
        ("typed", "http://linklocal.example/", False),
        ("typed", "http://[fe80::1]/", False),
        # (SSRF-05: web addresses only.)
        ("typed", "file:///etc/passwd", False),
        ("typed", "gopher://plex.home/", False),
        ("typed", "ftp://plex.home/", False),
        # (SSRF-01: a name or password in the address.)
        ("typed", "http://plex.home@public.example/", False),
        # (Fixed and from data: public only.)
        ("fixed", "https://public.example/releases", True),
        ("fixed", "http://plex.home/", False),
        ("data", "http://192.168.1.9/x", False),
        ("data", "http://loop.example/x", False),
        ("data", "http://127.0.0.1/x", False),
        ("data", "http://[::1]/x", False),
        ("data", "http://mapped.example/x", False),
        ("data", "http://10.1.2.3/x", False),
        ("data", "http://100.64.0.1/x", False),
        ("data", "http://public.example/x", True),
        # (SSRF-02: a name that answers one public and one private address is refused, so DNS can't move it.)
        ("data", "http://rebinds.example/x", False),
        # (No answer: refused.)
        ("typed", "http://nowhere.example/x", False),
    ],
)
def test_each_kind_of_address_goes_only_where_its_provenance_allows(names, kind, url, sent):
    assert (_ask(kind, url) == 200) is sent


def test_with_no_stand_in_the_request_goes_to_the_address_vetted_and_keeps_its_name(
    names, monkeypatch
):
    # (SSRF-02: pinned. The real transport is given the vetted address, with the name as Host and SNI.)
    sent: list[httpx.Request] = []

    class Real(httpx.AsyncBaseTransport):
        def __init__(self, **_):
            pass

        async def handle_async_request(self, request):
            sent.append(request)
            return httpx.Response(200)

    monkeypatch.setattr(safefetch.httpx, "AsyncHTTPTransport", Real)
    import asyncio

    async def go():
        async with httpx.AsyncClient(
            transport=safefetch.transport("typed"), follow_redirects=False
        ) as c:
            await c.get("https://plex.home:32400/identity")

    asyncio.run(go())
    (request,) = sent
    assert request.url.host == "192.168.50.2" and request.url.port == 32400
    assert request.headers["host"] == "plex.home:32400"
    assert request.extensions["sni_hostname"] == "plex.home"
    assert request.headers["user-agent"].startswith("tapiOca/")


def test_a_refusal_is_a_transport_error_every_caller_already_handles():
    assert issubclass(safefetch.Refused, httpx.TransportError)

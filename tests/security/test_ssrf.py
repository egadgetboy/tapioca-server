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
        # (SSRF-01: a name or password in the address. Typed, it's the Admin's sign-in for that
        # address, as 1.43.0 sent it (the cold audit of 1.44.0); from data or fixed, refused.)
        ("typed", "http://alice:s3cret@plex.home/", True),
        ("data", "http://public.example@public.example/", False),
        ("fixed", "https://u:p@public.example/releases", False),
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
            # (As it was when sent: the transport puts the name back on the request afterward.)
            sent.append((request.url, dict(request.headers), dict(request.extensions)))
            return httpx.Response(200)

    monkeypatch.setattr(safefetch.httpx, "AsyncHTTPTransport", Real)
    import asyncio

    async def go():
        async with httpx.AsyncClient(
            transport=safefetch.transport("typed"), follow_redirects=False
        ) as c:
            return await c.get("https://alice:s3cret@plex.home:32400/identity")

    got = asyncio.run(go())
    ((url, headers, extensions),) = sent
    assert url.host == "192.168.50.2" and url.port == 32400
    assert headers["host"] == "plex.home:32400"
    assert extensions["sni_hostname"] == "plex.home"
    assert headers["user-agent"].startswith("tapiOca/")
    # (A typed name and password go only as that request's Basic sign-in, never in the address.)
    assert not url.userinfo and headers["authorization"].startswith("Basic ")
    # (What the caller sees afterward is the name, never the address: the cold audit of 1.44.0,
    # where the away-address check joined a redirect to the bare address.)
    assert got.request.url.host == "plex.home"


def test_a_refusal_is_a_transport_error_every_caller_already_handles():
    assert issubclass(safefetch.Refused, httpx.TransportError)


# --- The cold and security audits of 1.44.0: the lookup itself -----------------------------------

import asyncio  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402


def _system_names(monkeypatch, answer):
    """The real lookup (safefetch._resolve), with the system's getaddrinfo answering `answer(host)`."""
    monkeypatch.setattr(safefetch, "RESOLVE", safefetch._resolve)
    monkeypatch.setattr(safefetch.socket, "getaddrinfo", lambda host, *a, **k: answer(host))


def _info(*ips):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
            for ip in ips]  # fmt: skip


def test_a_slow_lookup_ends_with_the_requests_connect_timeout_and_never_holds_up_disk_reads(monkeypatch):
    # (Audit finding: the lookup ran outside the client's timeout, on the default pool that playback's
    # disk reads share, so a dead DNS server for Plex could stall a stream.)
    gate = threading.Event()

    def hang(host):
        gate.wait(5)
        return _info("192.168.1.9")

    _system_names(monkeypatch, hang)

    async def go():
        began = time.monotonic()
        client = httpx.AsyncClient(transport=safefetch.transport("typed"), timeout=httpx.Timeout(2, connect=0.3))
        asks = [asyncio.ensure_future(client.get(f"http://slow{n}.example/")) for n in range(12)]
        await asyncio.sleep(0.05)
        read_began = time.monotonic()
        await asyncio.to_thread(lambda: None)  # (a disk read, on the default pool)
        disk_wait = time.monotonic() - read_began
        results = await asyncio.gather(*asks, return_exceptions=True)
        await client.aclose()
        return time.monotonic() - began, disk_wait, results

    try:
        took, disk_wait, results = asyncio.run(go())
    finally:
        gate.set()
    assert all(isinstance(r, httpx.ConnectTimeout) for r in results), results
    assert took < 1.5, took
    assert disk_wait < 0.5, disk_wait


@pytest.mark.parametrize("address", ["http://192.168.1..5:8989/", "http://" + "a" * 70 + ".example/"])
def test_a_mistyped_name_is_a_connect_error_callers_handle_never_a_unicode_error(monkeypatch, address):
    # (Audit finding: an empty or overlong label made the lookup raise UnicodeError, a 500 on Test.)
    def _idna(host):
        host.encode("idna")  # (what the system's lookup does first)
        return _info("192.168.1.9")

    _system_names(monkeypatch, _idna)

    async def go():
        async with httpx.AsyncClient(transport=safefetch.transport("typed")) as c:
            return await c.get(address)

    with pytest.raises(httpx.ConnectError) as caught:
        asyncio.run(go())
    assert isinstance(caught.value, safefetch.NotFound)


def test_a_name_not_found_says_so_in_the_systems_words(monkeypatch):
    # (Audit finding: Plex's trouble() read "nothing answered" for a mistyped PLEX_URL.)
    def missing(host):
        raise socket.gaierror(-2, "Name or service not known")

    _system_names(monkeypatch, missing)
    from app.plex import _connection_kind

    async def go():
        async with httpx.AsyncClient(transport=safefetch.transport("typed")) as c:
            return await c.get("http://plex.example:32400/")

    with pytest.raises(httpx.ConnectError) as caught:
        asyncio.run(go())
    assert _connection_kind(caught.value) == "unknown-host"


def test_a_name_in_another_script_is_looked_up_as_sent(monkeypatch):
    # (Audit finding: faß.de was looked up as fass.de, a different domain, while Host said xn--fa-hia.de.)
    asked: list[str] = []

    def answer(host):
        asked.append(host)
        return _info("93.184.216.34")

    _system_names(monkeypatch, answer)
    found = asyncio.run(safefetch.vet(httpx.URL("https://faß.de/"), "data"))
    assert asked == ["xn--fa-hia.de"] and found == [ipaddress.ip_address("93.184.216.34")]


def _server(host: str):
    """A plain HTTP answer on host:port, on this machine; its port, and how many it answered."""
    sock = socket.create_server((host, 0))
    port, came = sock.getsockname()[1], []

    def run():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            came.append(1)
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            conn.close()

    threading.Thread(target=run, daemon=True).start()
    return sock, port, came


def test_every_allowed_address_is_tried_in_order(monkeypatch):
    # (Audit finding: only the first answer was tried; a name whose first address doesn't answer failed.)
    sock, port, came = _server("127.0.0.3")
    try:
        async def resolve(host):
            return [ipaddress.ip_address("127.0.0.2"), ipaddress.ip_address("127.0.0.3")]

        monkeypatch.setattr(safefetch, "RESOLVE", resolve)

        async def go():
            async with httpx.AsyncClient(transport=safefetch.transport("typed"), timeout=3) as c:
                return await c.get(f"http://plex.home:{port}/")

        assert asyncio.run(go()).text == "ok" and came == [1]
    finally:
        sock.close()


def test_a_typed_name_keeps_its_allowed_answers_and_a_data_name_is_refused_whole(monkeypatch):
    # (Audit finding: a home name that also answers fe80:: was refused. Data stays strict: rebinding.)
    async def resolve(host):
        return [ipaddress.ip_address("fe80::1"), ipaddress.ip_address("192.168.1.9")]

    monkeypatch.setattr(safefetch, "RESOLVE", resolve)
    assert asyncio.run(safefetch.vet(httpx.URL("http://nas.home/"), "typed")) == [ipaddress.ip_address("192.168.1.9")]
    with pytest.raises(safefetch.Refused):
        asyncio.run(safefetch.vet(httpx.URL("http://nas.example/"), "data"))


@pytest.mark.parametrize(
    "ip, kind, ok",
    [
        ("64:ff9b::5db8:d822", "fixed", True),  # (93.184.216.34, through NAT64: public)
        ("64:ff9b::a9fe:a9fe", "typed", False),  # (169.254.169.254: the metadata address)
        ("64:ff9b::c0a8:109", "data", False),  # (192.168.1.9: home)
    ],
)
def test_a_nat64_address_is_judged_by_the_ipv4_address_it_carries(ip, kind, ok):
    # (Audit finding: on a DNS64 network, GitHub's answers were "reserved", so the update check always failed.)
    assert (safefetch.refusal(ipaddress.ip_address(ip), kind) is None) is ok


def test_each_name_has_its_own_connections_so_tls_is_never_shared(monkeypatch):
    # (Audit finding: connections were kept by the pinned address, so a TLS connection checked for one
    # name could carry a request for another name at the same address.)
    made: list[object] = []

    class Real(httpx.AsyncBaseTransport):
        def __init__(self, **_):
            made.append(self)

        async def handle_async_request(self, request):
            return httpx.Response(200)

    monkeypatch.setattr(safefetch.httpx, "AsyncHTTPTransport", Real)

    async def resolve(host):
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(safefetch, "RESOLVE", resolve)

    async def go():
        async with httpx.AsyncClient(transport=safefetch.transport("data")) as c:
            await c.get("https://good.example/")
            await c.get("https://evil.example/")
            await c.get("https://good.example/again")

    asyncio.run(go())
    assert len(made) == 2


def test_a_name_is_looked_up_once_while_its_answer_is_kept(monkeypatch):
    # (Audit finding: every request did a fresh lookup, on browsing's and pictures' hot path.)
    asked: list[str] = []

    class Real(httpx.AsyncBaseTransport):
        def __init__(self, **_):
            pass

        async def handle_async_request(self, request):
            return httpx.Response(200)

    monkeypatch.setattr(safefetch.httpx, "AsyncHTTPTransport", Real)

    async def resolve(host):
        asked.append(host)
        return [ipaddress.ip_address("192.168.1.9")]

    monkeypatch.setattr(safefetch, "RESOLVE", resolve)

    async def go():
        async with httpx.AsyncClient(transport=safefetch.transport("typed")) as c:
            for _ in range(5):
                await c.get("http://plex.home:32400/library/sections")

    asyncio.run(go())
    assert asked == ["plex.home"]


@pytest.mark.parametrize(
    "address, why",
    [
        ("http://169.254.169.254/latest/meta-data/", "a cloud metadata address"),
        ("http://[::ffff:169.254.169.254]/x", "a cloud metadata address"),
        ("http://[fe80::1]/x", "a link-local address"),
        ("ftp://192.168.1.9/x", "not a web address"),
        ("http://192.168.1.9:8123/hook", None),
        ("http://nowhere-yet.example/hook", None),
    ],
)
def test_a_typed_address_that_will_never_be_sent_to_is_named_before_saving(monkeypatch, address, why):
    # (Audit finding: homeOk saved a metadata or link-local address, which every send then refused.)
    async def resolve(host):
        if host == "nowhere-yet.example":
            raise safefetch.NotFound("tapiOca can't find it", "a name that can't be found")
        return [ipaddress.ip_address(host)]

    monkeypatch.setattr(safefetch, "RESOLVE", resolve)
    assert asyncio.run(safefetch.typed_refusal(address)) == why


# --- The audits' second round ------------------------------------------------------------------


def test_dead_lookups_for_one_name_never_starve_another_names_lookup(monkeypatch):
    # (Round 2: four alert lookups to a dead DNS server took every lookup thread, so Plex's own
    # lookup, which answers at once, timed out.)
    gate = threading.Event()

    def answer(host):
        if host.startswith("dead"):
            gate.wait(5)
        return _info("192.168.1.9")

    _system_names(monkeypatch, answer)

    async def go():
        dead = [asyncio.ensure_future(safefetch.lookup("dead.example", 3)) for _ in range(12)]
        await asyncio.sleep(0.05)
        began = time.monotonic()
        found = await safefetch.lookup("plex.example", 1)
        took = time.monotonic() - began
        for d in dead:
            d.cancel()
        return found, took

    try:
        found, took = asyncio.run(go())
    finally:
        gate.set()
    assert found == [ipaddress.ip_address("192.168.1.9")] and took < 0.5, took


def test_a_name_whose_lookup_fails_later_keeps_its_last_vetted_answer_for_a_while(monkeypatch):
    # (Round 2: during an internet outage, Plex by name would stop once its kept answer ran out.)
    answers = iter([[ipaddress.ip_address("192.168.1.9")]])

    async def resolve(host):
        try:
            return next(answers)
        except StopIteration:
            raise safefetch.NotFound("tapiOca can't find it", "a name that can't be found") from None

    monkeypatch.setattr(safefetch, "RESOLVE", resolve)
    sent: list[str] = []

    class Real(httpx.AsyncBaseTransport):
        def __init__(self, **_):
            pass

        async def handle_async_request(self, request):
            sent.append(request.url.host)
            return httpx.Response(200)

    monkeypatch.setattr(safefetch.httpx, "AsyncHTTPTransport", Real)
    now = [1000.0]
    monkeypatch.setattr(safefetch.time, "monotonic", lambda: now[0])

    async def go():
        async with httpx.AsyncClient(transport=safefetch.transport("typed")) as c:
            await c.get("http://plex.home:32400/")
            now[0] += safefetch.KEEP_S + 1  # (kept answer out of date: looked up again, which fails)
            await c.get("http://plex.home:32400/")
            now[0] += safefetch.STALE_S  # (far too old to trust)
            with pytest.raises(httpx.ConnectError):
                await c.get("http://plex.home:32400/")

    asyncio.run(go())
    assert sent == ["192.168.1.9", "192.168.1.9"]


@pytest.mark.parametrize(
    "ip",
    ["100.100.100.200", "192.0.0.192", "::169.254.169.254", "2002:a9fe:a9fe::", "::ffff:100.100.100.200"],
)
def test_every_clouds_metadata_address_is_refused_however_its_written(ip):
    # (Round 2: Alibaba's and Oracle's metadata addresses, and IPv4-compatible and 6to4 forms.)
    assert safefetch.refusal(ipaddress.ip_address(ip), "typed") == "a cloud metadata address"


def test_a_name_whose_kept_addresses_all_fail_is_looked_up_again(monkeypatch):
    # (The cold audit's second round: after a name moved to a new address, requests kept going to
    # the dead old one for KEEP_S.)
    answers = iter([[ipaddress.ip_address("192.168.1.8")], [ipaddress.ip_address("192.168.1.9")]])

    async def resolve(host):
        return next(answers)

    monkeypatch.setattr(safefetch, "RESOLVE", resolve)
    sent: list[str] = []

    class Real(httpx.AsyncBaseTransport):
        def __init__(self, **_):
            pass

        async def handle_async_request(self, request):
            sent.append(request.url.host)
            if request.url.host == "192.168.1.8":
                raise httpx.ConnectError("All connection attempts failed")
            return httpx.Response(200)

    monkeypatch.setattr(safefetch.httpx, "AsyncHTTPTransport", Real)

    async def go():
        async with httpx.AsyncClient(transport=safefetch.transport("typed")) as c:
            with pytest.raises(httpx.ConnectError):
                await c.get("http://plex.home:32400/")
            return await c.get("http://plex.home:32400/")

    assert asyncio.run(go()).status_code == 200 and sent == ["192.168.1.8", "192.168.1.9"]


def test_a_name_that_cant_be_looked_up_at_all_is_an_unknown_host_to_plexs_trouble():
    # (The cold audit's second round: "http://192.168.1..10:32400" said "nothing answered".)
    from app.plex import _connection_kind

    assert _connection_kind(safefetch.NotFound("tapiOca can't find 192.168.1..10: label empty")) == "unknown-host"


def test_a_file_address_says_its_not_a_web_address():
    # (The cold audit's second round: "Only web addresses (http or https), not no kind of address".)
    with pytest.raises(safefetch.Refused) as caught:
        asyncio.run(safefetch.vet(httpx.URL("/etc/passwd"), "typed"))
    assert str(caught.value) == "That isn't a web address (http or https)"

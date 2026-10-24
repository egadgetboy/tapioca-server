"""The census is whole (DL287, A.1): every outbound request, started program
and file write in the code is declared with what it is, and nothing declared
is gone. A new one fails here until it's declared and gets its checks."""

from __future__ import annotations

import pytest

from . import inventory


@pytest.mark.parametrize(
    ("found", "declared", "what"),
    [
        (inventory.egress_sites, inventory.EGRESS, "outbound request"),
        (inventory.spawn_sites, inventory.SPAWN, "started program"),
        (inventory.write_sites, inventory.WRITE, "file write"),
    ],
)
def test_every_site_in_the_code_is_declared_and_every_declared_one_is_there(found, declared, what):
    seen = {str(site) for site in found()}
    new = sorted(seen - set(declared))
    gone = sorted(set(declared) - seen)
    assert not new, f"A new {what}, not in tests/security/inventory.py: {new}"
    assert not gone, f"Declared but no longer in the code (take it out of inventory.py): {gone}"


def test_every_outbound_request_says_where_its_address_comes_from():
    # (DL287, the owner's provenance rule: typed by an Admin, fixed in the code, or from data.)
    for site, what in inventory.EGRESS.items():
        assert what.split(":", 1)[0] in ("typed", "fixed", "data", "guard"), site


def test_no_program_is_started_through_a_shell():
    # (DEP-04, INJ-02: an argument list, never a shell.)
    for site in inventory.spawn_sites():
        assert site.call not in ("asyncio.create_subprocess_shell", "os.system", "os.popen"), site


def test_every_write_says_where_it_lands():
    for site, what in inventory.WRITE.items():
        assert what.split(":", 1)[0] in ("data", "temp", "no file"), site


def test_the_census_finds_what_it_should():
    # (The census itself: if a refactor of inventory.py stopped it finding anything, every check above
    # would pass on nothing.)
    assert len(inventory.egress_sites()) >= 6
    assert len(inventory.spawn_sites()) >= 10
    assert len(inventory.write_sites()) >= 30


def test_every_outbound_client_goes_through_safefetch_as_its_declared_kind_and_follows_no_redirect():
    # (DEP-03 and SSRF-04, DL287: one vetted way out. A client made any other way fails here.)
    guards = inventory.egress_guards()
    assert set(guards) == set(inventory.EGRESS)
    for site, (kind, redirects) in guards.items():
        declared = inventory.EGRESS[site].split(":", 1)[0]
        if declared == "guard":
            # (Only safefetch itself makes a real connection or looks a name up.)
            assert site.startswith("app/safefetch.py:"), site
            continue
        assert kind == declared, (
            f"{site}: its transport is {kind!r}, but it's declared {declared!r}"
        )
        assert redirects in (None, False), f"{site} follows redirects"


def test_this_version_has_its_security_manifest():
    # (DL287, the source's §0.4: every release answers the six questions, "none" where it applies.)
    from pathlib import Path

    from app import __version__

    manifest = Path(__file__).resolve().parents[2] / "docs" / "security" / f"manifest-{__version__}.md"
    assert manifest.exists(), f"Write {manifest.name}: the six questions, for this release's readiness record"
    text = manifest.read_text(encoding="utf-8")
    for n in range(1, 7):
        assert f"\n{n}. **" in text, f"{manifest.name} doesn't answer question {n}"


# (The security audit of 1.44.0: the census saw only "httpx.AsyncClient(...)" as written, so an
# aliased import, httpx.get, urllib, http.client or a raw socket would pass as no way out at all.)
SNEAKY = '''
import httpx as hx
import socket
import urllib.request
import http.client
import asyncio
from httpx import AsyncClient as AC
from urllib.request import urlopen
from socket import create_connection

async def one():
    AC()
async def two():
    hx.AsyncClient()
async def three():
    httpx_get = hx.get("http://x")
def four():
    urlopen("http://x")
def five():
    http.client.HTTPSConnection("x").request("GET", "/")
def six():
    socket.socket().connect(("x", 1))
def seven():
    create_connection(("x", 1))
async def eight():
    await asyncio.get_running_loop().create_connection(None, "x", 1)
def nine():
    socket.socket().connect_ex(("x", 1))
async def ten():
    await asyncio.get_running_loop().getaddrinfo("x", None)
'''


def _census_of(tmp_path, monkeypatch, source: str):
    folder = tmp_path / "app"
    folder.mkdir()
    (folder / "sneaky.py").write_text(source)
    monkeypatch.setattr(inventory, "APP", folder)
    return {s.function for s in inventory.egress_sites()}


def test_the_census_sees_every_way_out_however_its_written(tmp_path, monkeypatch):
    found = _census_of(tmp_path, monkeypatch, SNEAKY)
    assert found == {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}, found


def test_a_client_that_could_route_around_the_guard_or_follow_a_redirect_is_named(tmp_path, monkeypatch):
    folder = tmp_path / "app"
    folder.mkdir()
    (folder / "sneaky.py").write_text(
        "import httpx\n"
        "from app import safefetch\n"
        "async def a():\n    httpx.AsyncClient(transport=safefetch.transport(safefetch.TYPED), proxy='http://p')\n"
        "async def b():\n    httpx.AsyncClient(transport=safefetch.transport(safefetch.TYPED), mounts={})\n"
        "async def c(client):\n    await client.get('http://x', follow_redirects=True)\n"
        "async def d():\n    httpx.AsyncClient(transport=safefetch.transport(safefetch.TYPED), trust_env=True)\n"
    )
    monkeypatch.setattr(inventory, "APP", folder)
    assert {s.function for s in inventory.unsafe_options()} == {"a", "b", "c", "d"}


def test_no_client_in_tapiOca_routes_around_the_guard_or_follows_a_redirect():
    assert inventory.unsafe_options() == []


@pytest.mark.parametrize("how", ["connect", "connect_ex", "sendto"])
def test_the_suites_guard_stops_every_way_a_socket_leaves_this_machine(how):
    # (The security audit of 1.44.0: connect_ex and UDP's sendto weren't stopped.)
    import socket

    from .conftest import LeftTheMachine

    kind = socket.SOCK_DGRAM if how == "sendto" else socket.SOCK_STREAM
    with socket.socket(socket.AF_INET, kind) as sock, pytest.raises(LeftTheMachine):
        sock.setblocking(False)
        if how == "sendto":
            sock.sendto(b"x", ("192.0.2.1", 53))
        else:
            getattr(sock, how)(("192.0.2.1", 80))


def test_the_census_sees_a_client_kept_under_another_name_or_made_later(tmp_path, monkeypatch):
    # (The cold audit's second round: Maker = httpx.AsyncClient, functools.partial and anyio were
    # missed, and of two clients in one function only the last was judged.)
    found = _census_of(tmp_path, monkeypatch, (
        "import functools, httpx, anyio\n"
        "def kept():\n    Maker = httpx.AsyncClient\n    return Maker()\n"
        "def partly():\n    return functools.partial(httpx.AsyncClient, timeout=3)\n"
        "async def tcp():\n    await anyio.connect_tcp('x', 1)\n"
        "def typed(client: httpx.AsyncClient) -> httpx.AsyncClient:\n    return client\n"
    ))  # fmt: skip
    assert found == {"kept", "partly", "tcp"}, found


def test_two_clients_in_one_function_are_each_judged(tmp_path, monkeypatch):
    folder = tmp_path / "app"
    folder.mkdir()
    (folder / "sneaky.py").write_text(
        "import httpx\nfrom app import safefetch\n"
        "async def both():\n"
        "    httpx.AsyncClient()\n"
        "    httpx.AsyncClient(transport=safefetch.transport(safefetch.FIXED), follow_redirects=False)\n"
    )
    monkeypatch.setattr(inventory, "APP", folder)
    assert inventory.egress_guards()["app/sneaky.py:both httpx.AsyncClient"][0] is None


@pytest.mark.parametrize("how", ["name", "sendmsg"])
def test_the_suites_guard_stops_a_name_and_sendmsg(how):
    import socket

    from .conftest import LeftTheMachine

    kind = socket.SOCK_DGRAM if how == "sendmsg" else socket.SOCK_STREAM
    with socket.socket(socket.AF_INET, kind) as sock, pytest.raises(LeftTheMachine):
        sock.setblocking(False)
        if how == "sendmsg":
            sock.sendmsg([b"x"], [], 0, ("192.0.2.1", 53))
        else:
            sock.connect(("example.com", 80))

"""The four scripted chains (DL287, B1): the Plex2Shell shape, where small
quirks join into a takeover. These are scripts of known shapes against the
running tapiOca, not a general chain-finder (the plan says so plainly); a
path that reaches its end is Critical even if each step alone is small."""

from __future__ import annotations

import re
import socket
import threading

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.plex import PlexClient
from tests.fakeplex_library import LibraryPlex

from .authz_matrix import MATRIX

ADA = {"name": "Ada", "password": "correct horse battery"}
SAM = {"name": "Sam", "password": "staple battery horse", "role": "user"}
HOME = ("192.168.1.50", 50000)
INTERNET = ("203.0.113.7", 41000)
PAGE = {"X-Tapioca-Page": "1"}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("chains")
    fp = LibraryPlex()
    fp.add_section("2", "Movies", "movie")
    fp.add_movie("300", "Picnic", "/m/picnic.mkv", 90 * 60_000, section="2", contentRating=["PG"])
    settings = Settings(
        plex_url="http://plex.test", plex_token="token", data_dir=tmp / "data", public_port=30021
    )
    app = create_app(settings, PlexClient("http://plex.test", "token", transport=fp.transport()))
    app.state.ctx.play_transport = fp.transport()
    with TestClient(app, client=HOME, headers=PAGE) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code in (200, 201)
        assert admin.post("/api/access/sign-in", json=ADA).status_code == 200
        assert admin.post("/api/access/users", json=SAM).status_code in (200, 201)
        yield app, admin


def _signed_in(app, who) -> dict[str, str]:
    got = TestClient(app, client=HOME).post("/api/internal/sign-in", json=who)
    assert got.status_code == 200, got.text
    return {"Authorization": f"Bearer {got.json()['token']}"}


def _sample(route: str) -> str:
    return MATRIX[route][1]


class Listener:
    """Counts connections to one port on this machine: tapiOca's own routes stand in for "internal"."""

    def __init__(self) -> None:
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.came = 0
        self.sock.settimeout(0.2)
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.came += 1
            conn.close()

    def close(self) -> None:
        self.running = False
        self.thread.join(1)
        self.sock.close()


URL_FIELDS = ("url", "address", "addresses", "webhook", "link", "server", "source", "image", "picture", "logo",
              "stream", "target", "href", "src", "feed", "callback", "redirect", "next", "plexUrl", "plex_url")  # fmt: skip


def test_chain_01_no_one_but_an_admin_can_make_tapioca_fetch_an_inside_address(world):
    # (outsider or User → any field that might be an address → a request from tapiOca to this machine.)
    app, _ = world
    listener = Listener()
    inside = f"http://127.0.0.1:{listener.port}/api/access/users"
    sam = _signed_in(app, SAM)
    try:
        for route, (cls, _) in MATRIX.items():
            method = route.split(" ", 1)[0]
            if method not in ("POST", "PUT") or cls == "admin":
                continue
            body = {name: inside for name in URL_FIELDS}
            body["addresses"] = [inside]
            for headers in ({}, sam):
                TestClient(app, client=HOME, headers=PAGE).request(
                    method, _sample(route), json=body, headers=headers
                )
        assert listener.came == 0, (
            f"CHAIN-01: tapiOca was made to connect to this machine {listener.came} times"
        )
    finally:
        listener.close()


def test_chain_02_no_answer_to_a_user_or_outsider_carries_anyones_token(world):
    # (an information leak → a token → an Admin's route.)
    app, admin = world
    ada_app = _signed_in(app, ADA)["Authorization"].split()[1]
    cookie = admin.cookies.get("stationplay_session") or ""
    made = admin.post("/api/api-tokens", json={"name": "script", "scope": "admin"})
    api = made.json().get("token", "") if made.status_code in (200, 201) else ""
    secrets_seen = [t for t in (ada_app, cookie, api) if t]
    assert len(secrets_seen) >= 2
    sam = _signed_in(app, SAM)
    for route, (cls, sample) in MATRIX.items():
        method = route.split(" ", 1)[0]
        if method != "GET" or cls == "capability":
            continue
        for headers in ({}, sam):
            got = TestClient(app, client=HOME, headers=PAGE).get(sample, headers=headers)
            for token in secrets_seen:
                assert token not in got.text, (
                    f"CHAIN-02: {route} gave someone else's token to {headers or 'no one'}"
                )


def test_chain_03_nothing_written_by_a_request_is_served_back_as_a_page_or_a_script(world):
    # (a file write → a served path → code in a browser: an upload served as HTML or a script.)
    app, admin = world
    html = b"<html><script>alert(1)</script></html>"
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    for body, name in ((html, "x.png"), (svg, "x.svg"), (html, "x.html")):
        got = admin.post("/api/logos", files={"file": (name, body, "image/png")})
        if got.status_code not in (200, 201):
            continue  # (refused: fine, FILE-01)
        found = re.search(r'"id"\s*:\s*"?([A-Za-z0-9_-]+)', got.text)
        if not found:
            continue
        served = admin.get(f"/logos/{found.group(1)}.png")
        kind = served.headers.get("content-type", "")
        assert not kind.startswith(
            ("text/html", "image/svg", "application/javascript", "text/javascript")
        ), kind
        assert served.headers.get("x-content-type-options") == "nosniff"


SPOOFS = [
    {"X-Forwarded-For": "127.0.0.1"},
    {"X-Forwarded-For": "192.168.1.10"},
    {"X-Real-IP": "127.0.0.1"},
    {"Forwarded": "for=127.0.0.1;proto=https"},
    {"CF-Connecting-IP": "192.168.1.10"},
    {"X-Forwarded-Host": "localhost", "X-Forwarded-Proto": "https"},
    {"Host": "localhost"},
    {"X-Original-URL": "/api/access/users", "X-Rewrite-URL": "/api/access/users"},
]


@pytest.mark.parametrize("spoof", SPOOFS, ids=lambda s: ",".join(s))
def test_chain_04_a_header_claiming_home_never_opens_an_inside_route_from_the_internet(
    world, spoof
):
    # (a localhost or trusted-header spoof → an internal route → an Admin's power.) From an internet
    # address, with each header, no Admin route answers and no tuner route serves.
    app, _ = world
    stranger = TestClient(app, client=INTERNET)
    for address in ("/api/access/users", "/api/backups", "/api/logs"):
        got = stranger.get(address, headers={**PAGE, **spoof})
        assert got.status_code in (401, 403, 404, 421), (
            f"CHAIN-04: {address} with {spoof}: {got.status_code}"
        )
    for address in ("/lineup.json", "/discover.json", "/stations.m3u"):
        got = stranger.get(address, headers=spoof)
        assert got.status_code in (401, 403, 404, 421), (
            f"CHAIN-04: the tuner's {address} with {spoof}: {got.status_code}"
        )


def test_the_listener_counts_a_real_connection():
    # (A control: CHAIN-01's listener isn't blind.)
    listener = Listener()
    try:
        with socket.create_connection(("127.0.0.1", listener.port), timeout=1):
            pass
        for _ in range(20):
            if listener.came:
                break
            threading.Event().wait(0.05)
        assert listener.came == 1
    finally:
        listener.close()

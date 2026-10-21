"""The server proves who it is (1.43.0, planned): its own key, signing a
fresh challenge from each app, and Access -> Reconnect apps. The design is
the apps repo's docs/threat-models/server-proof.md (its ninth version, with
its cold audit's fixes); the apps' side is their shared cases
(shared/cases/proofs.json there). Written before the code, to fail first.

What these tests take as the code's shape (the design's sections 1 to 3
and 6):
- app/serverkey.py: KEY_FILE ("server-key.pem", in the data folder),
  OPENSSL ("/usr/bin/openssl") and NICE ("/usr/bin/nice"); `spawn`, what
  starts each openssl (asyncio.create_subprocess_exec, whose process is
  read with `communicate()` and stopped by its PID), so a test can watch or
  replace it; `read_file(path) -> bytes` (how the key file is read),
  `write_all(fd, data)` (how a new one is written) and `flush_folder(path)`
  (the folder's fsync), so a test can make them fail; and
  `ctx.server_key`, with `.state` ("making", "ready" or "unusable"),
  `.public_text` (the 564-letter base64 public key) and
  `async sign(purpose, body) -> bytes`.
- app/proofs.py: the two lanes and their limits, as module constants a
  test may lower: WAITING_MOST (256), PER_SOURCE_MINUTE (60),
  PER_SOURCE_WAITING (4), RELAY_MINUTE (600), RELAY_WAITING (8),
  PREFIX48_MINUTE (600), SOURCES_MOST (4,096); `lane_for(scope)` ("home",
  "outside", or None when the Gate's state has no `outside`); and pads made
  with `secrets.token_hex(32)`.
- app/reconnect.py: Reconnect apps' code, with `clock` (time.monotonic) for
  its 10 minutes.
- POST /api/internal/proof; Access -> Reconnect apps at
  /api/access/reconnect: POST makes a code (an Admin), DELETE ends it, GET
  says whether one is active and until when, with the code itself only for
  the Admin who made it.
- alerts.PROOF ("proof"): the Admin alert for the key and for signing.

Proof requests go from an app's client, without the page's header that
conftest.py gives every test client.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import errno
import hashlib
import hmac
import importlib
import json
import logging
import os
import re
import secrets
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import access, backups, links
from app.config import Settings
from app.main import create_app
from app.plex import PlexClient

from .fakeplex import FakePlex
from .helpers import PROXY_PEER, list_proxy

PUBLIC_PORT = 8443
PAT = {"name": "Pat", "password": "correct horse"}
LEE = {"name": "Lee", "password": "harbor violet quill"}
SAM = {"name": "Sam", "password": "battery staple"}
ROUTE = "/api/internal/proof"
PREFIX = b"tapioca/1 server-proof\n"
SPKI_HEAD = bytes.fromhex("308201a2300d06092a864886f70d01010105000382018f003082018a0282018100")
SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
AWAY = "https://tv.example.com"
HOME = "http://testserver"


def module(name: str):
    """The module the code will have (imported here, so each test fails on
    its own until it exists)."""
    return importlib.import_module(f"app.{name}")


def make_app(tmp_path: Path, **settings) -> object:
    s = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data",
                 public_port=PUBLIC_PORT, **settings)  # fmt: skip
    return create_app(s, PlexClient("http://plex.test", "token", transport=FakePlex().transport()))


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path)


def key_file(tmp_path: Path) -> Path:
    return tmp_path / "data" / "server-key.pem"


def as_app(client: TestClient, running: TestClient) -> TestClient:
    """`client` as one of tapiOca's apps (no page header), on `running`'s
    event loop, where the app's lanes live."""
    client.headers.pop("X-Tapioca-Page", None)
    client.portal = running.portal
    return client


def at_home(app, running: TestClient, ip: str = "192.168.1.60") -> TestClient:
    return as_app(TestClient(app, client=(ip, 50001)), running)


def away(app, running: TestClient, ip: str = "203.0.113.5", https: bool = True) -> TestClient:
    """A device away from home, through the trusted reverse proxy, at `ip`."""
    list_proxy(app)
    headers = {"X-Real-IP": ip, "X-Forwarded-For": ip}
    if https:
        headers["X-Forwarded-Proto"] = "https"
    c = TestClient(app, base_url=f"http://testserver:{PUBLIC_PORT}", client=(PROXY_PEER, 50000),
                   headers=headers)  # fmt: skip
    return as_app(c, running)


def nonce() -> str:
    return secrets.token_hex(32)


def ask(client: TestClient, address: str = HOME, n: str | None = None,
        reconnect: bool = False, **kw):  # fmt: skip
    return client.post(
        ROUTE, json={"nonce": n or nonce(), "address": address, "reconnect": reconnect}, **kw
    )


def until(what, seconds: float = 20, why: str = "") -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if what():
            return
        time.sleep(0.05)
    raise AssertionError(f"not within {seconds} s: {why}")


def ready(app) -> None:
    """Waits for the key (made in the background at the first start)."""
    until(lambda: app.state.ctx.server_key.state == "ready", why="the key is ready")


def settled(app) -> str:
    until(lambda: app.state.ctx.server_key.state != "making", why="the key's start check ends")
    return app.state.ctx.server_key.state


def signing_on(home: TestClient) -> None:
    assert home.post("/api/access/users", json=PAT).status_code == 201


def entry(n: str, address: str) -> str:
    return hashlib.sha256(f"tapioca/1 proof-entry\n{n}\n{address}".encode()).hexdigest()


def checks(answer: dict, n: str, address: str) -> dict:
    """The answer's signature checked in plain Python over the prefix and the
    statement's exact bytes, with its entry among exactly 64: the statement."""
    key = base64.b64decode(answer["key"], validate=True)
    sig = base64.b64decode(answer["signature"], validate=True)
    assert (
        len(answer["key"]) == 564 and len(key) == 422 and key[:33] == SPKI_HEAD and key[33] & 0x80
    )
    assert key[-5:] == bytes.fromhex("0203010001") and len(sig) == 384
    n_ = int.from_bytes(key[33:417], "big")
    st = answer["statement"]
    assert st.isascii()
    digest = SHA256_INFO + hashlib.sha256(PREFIX + st.encode()).digest()
    want = b"\x00\x01" + b"\xff" * (384 - 3 - len(digest)) + b"\x00" + digest
    assert pow(int.from_bytes(sig, "big"), 65537, n_).to_bytes(384, "big") == want
    body = json.loads(st)
    proofs = body["proofs"]
    assert len(proofs) == 64 and proofs == sorted(proofs)
    assert all(re.fullmatch("[0-9a-f]{64}", p) for p in proofs)
    assert proofs.count(entry(n, address)) == 1
    return body


def proofs_alerts(app) -> list:
    alerts = module("alerts")
    return [a for a in app.state.ctx.alerts.now() if a.kind == alerts.PROOF]


def one_alert(app):
    until(lambda: proofs_alerts(app), why="the proof's alert")
    [alert] = proofs_alerts(app)
    return alert


def openssl(*args: str) -> bytes:
    return subprocess.run(["openssl", *args], capture_output=True, check=True).stdout


def public_text(pem: Path) -> str:
    return base64.b64encode(openssl("pkey", "-in", str(pem), "-pubout", "-outform", "DER")).decode()


class Signing:
    """Watches openssl's signatures: when each began (`started`), and set
    once the first has begun (`began`); `delay` seconds added to each."""

    def __init__(self, monkeypatch, delay: float = 0.0) -> None:
        self.serverkey = module("serverkey")
        self.real = self.serverkey.spawn
        self.delay = delay
        self.started: list[float] = []
        self.began = threading.Event()
        monkeypatch.setattr(self.serverkey, "spawn", self.spawn)

    async def spawn(self, *args, **kw):
        if "dgst" in args:
            self.started.append(time.monotonic())
            self.began.set()
            if self.delay:
                await asyncio.sleep(self.delay)
        return await self.real(*args, **kw)


# The key (the design's section 1).


def test_a_key_is_made_at_the_first_start(app, tmp_path):
    with TestClient(app) as home:
        ready(app)
        pem = key_file(tmp_path)
        assert stat.S_IMODE(pem.stat().st_mode) == 0o600
        assert pem.read_text().splitlines()[0] == "-----BEGIN PRIVATE KEY-----"
        text = openssl("pkey", "-in", str(pem), "-noout", "-text").decode()
        assert "3072 bit" in text and "65537" in text
        answered = ask(at_home(app, home)).json()
        assert answered["key"] == public_text(pem) == app.state.ctx.server_key.public_text


def test_the_key_is_kept_across_restarts(tmp_path):
    first = make_app(tmp_path)
    with TestClient(first) as home:
        ready(first)
        key = ask(at_home(first, home)).json()["key"]
    again = make_app(tmp_path)
    with TestClient(again) as home:
        ready(again)
        assert ask(at_home(again, home)).json()["key"] == key


def test_a_wider_mode_is_made_0600_again(tmp_path):
    first = make_app(tmp_path)
    with TestClient(first):
        ready(first)
    pem = key_file(tmp_path)
    pem.chmod(0o644)
    again = make_app(tmp_path)
    with TestClient(again):
        ready(again)
        assert stat.S_IMODE(pem.stat().st_mode) == 0o600


@pytest.mark.parametrize("what", ["not a key", "encrypted", "rsa-2048"])
def test_a_key_file_that_isnt_one_is_left_alone(tmp_path, what):
    pem = key_file(tmp_path)
    pem.parent.mkdir(parents=True)
    if what == "not a key":
        pem.write_text("this isn't a key\n")
    elif what == "encrypted":
        pem.write_bytes(openssl("genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072",
                                "-aes256", "-pass", "pass:secret"))  # fmt: skip
    else:
        pem.write_bytes(openssl("genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"))
    pem.chmod(0o600)
    before = pem.read_bytes()
    app = make_app(tmp_path)
    with TestClient(app) as home:
        assert settled(app) == "unusable"
        got = ask(at_home(app, home))
        assert got.status_code == 503 and got.headers["tapioca-proof"] == "1"
        assert pem.read_bytes() == before
        assert (
            "delete" in one_alert(app).sentence.lower()
        )  # (this cause's fix: delete it, then restart)


@pytest.mark.parametrize(
    "error", [PermissionError(errno.EACCES, "denied"), OSError(errno.EIO, "I/O")]
)
def test_a_key_file_that_cant_be_read_is_never_replaced(tmp_path, monkeypatch, error):
    serverkey = module("serverkey")
    first = make_app(tmp_path)
    with TestClient(first):
        ready(first)
    before = key_file(tmp_path).read_bytes()

    def fails(path):
        raise error

    monkeypatch.setattr(serverkey, "read_file", fails)
    app = make_app(tmp_path)
    with TestClient(app) as home:
        assert settled(app) == "unusable"
        assert ask(at_home(app, home)).status_code == 503
        assert key_file(tmp_path).read_bytes() == before
        assert (
            "delete" not in one_alert(app).sentence.lower()
        )  # (its owner or permissions: never delete it)


def test_two_makers_at_once_make_one_key(tmp_path, monkeypatch):
    """Two processes on one data folder, both making a key: both get to
    writing before either links, and the one that links second loads the
    first's."""
    serverkey = module("serverkey")
    both = threading.Barrier(2, timeout=30)
    real = serverkey.write_all

    def together(fd, data):
        both.wait()
        return real(fd, data)

    monkeypatch.setattr(serverkey, "write_all", together)
    keys: list[str] = []

    def start():
        a = make_app(tmp_path)
        with TestClient(a) as home:
            ready(a)
            keys.append(ask(at_home(a, home)).json()["key"])

    threads = [threading.Thread(target=start) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(keys) == 2 and keys[0] == keys[1] == public_text(key_file(tmp_path))
    assert [p.name for p in (tmp_path / "data").iterdir() if "key" in p.name] == ["server-key.pem"]


def test_a_full_disk_leaves_no_half_made_key(tmp_path, monkeypatch):
    serverkey = module("serverkey")

    def full(fd, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(serverkey, "write_all", full)
    app = make_app(tmp_path)
    with TestClient(app) as home:
        assert settled(app) == "unusable"
        assert ask(at_home(app, home)).status_code == 503
    left = [
        p.name for p in (tmp_path / "data").iterdir() if "key" in p.name or p.name.startswith(".")
    ]
    assert left == []


@pytest.mark.parametrize("code", [errno.EPERM, errno.ENOTSUP, errno.EXDEV])
def test_a_mount_with_no_hard_links_still_gets_a_key(tmp_path, monkeypatch, code):
    serverkey = module("serverkey")

    def no_links(src, dst, *a, **kw):
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(serverkey.os, "link", no_links)
    app = make_app(tmp_path)
    with TestClient(app) as home:
        ready(app)
        pem = key_file(tmp_path)
        assert stat.S_IMODE(pem.stat().st_mode) == 0o600
        assert ask(at_home(app, home)).json()["key"] == public_text(pem)


def test_a_folder_that_cant_be_flushed_is_used_with_a_warning(tmp_path, monkeypatch, caplog):
    serverkey = module("serverkey")

    def cant(path):
        raise OSError(errno.EINVAL, "Invalid argument")

    monkeypatch.setattr(serverkey, "flush_folder", cant)
    app = make_app(tmp_path)
    with TestClient(app):
        ready(app)
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_a_key_swapped_under_a_running_server_stops_proofs(app, tmp_path):
    with TestClient(app) as home:
        ready(app)
        phone = at_home(app, home)
        pem = key_file(tmp_path)
        pem.write_bytes(openssl("genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072"))
        assert ask(phone).status_code == 503
        # At once (not after three), and never "delete".
        sentence = one_alert(app).sentence
        assert "changed while" in sentence and "delete" not in sentence.lower()


def test_no_backup_or_restore_holds_the_key():
    assert "server-key.pem" not in backups.FILES and not backups.LOGO_NAME.fullmatch(
        "server-key.pem"
    )
    assert backups.DB_NAME != "server-key.pem"


# The protocol (the design's section 3).


def test_the_answer_proves_its_statement(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        n = nonce()
        got = ask(at_home(app, home), HOME, n)
        assert got.status_code == 200, got.text
        assert got.headers["tapioca-proof"] == "1" and got.headers["stationplay-api"] == "1"
        answer = got.json()
        assert set(answer) == {"statement", "signature", "key"}
        body = checks(answer, n, HOME)
        assert isinstance(body["time"], int)


def test_the_statement_is_what_a_server_is(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        phone = at_home(app, home)
        n = nonce()
        body = checks(ask(phone, HOME, n).json(), n, HOME)
        assert body["server"] == phone.get("/api/v1/server").json()
        assert body["server"]["outside"] is False
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        outside = away(app, home)
        n = nonce()
        body = checks(ask(outside, AWAY, n).json(), n, AWAY)
        assert body["server"] == outside.get("/api/v1/server").json()
        assert body["server"]["outside"] is True


def test_the_server_is_built_at_each_signature(app):
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        phone = at_home(app, home)
        n = nonce()
        assert checks(ask(phone, HOME, n).json(), n, HOME)["server"]["awayAddress"] == AWAY
        assert home.put(
            "/api/away", json={"on": True, "address": "https://tv2.example.com"}
        ).is_success
        n = nonce()
        assert (
            checks(ask(phone, HOME, n).json(), n, HOME)["server"]["awayAddress"]
            == "https://tv2.example.com"
        )


def test_home_and_internet_requests_are_never_signed_together(app, monkeypatch):
    """Two lanes: held together behind a slow signature, a request from
    home and one from the internet get two statements, outside false and
    true (one queue would sign the internet's request as from home)."""
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        phone, outside = at_home(app, home), away(app, home)
        signing = Signing(monkeypatch, delay=0.4)
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            first = pool.submit(ask, at_home(app, home, ip="192.168.1.61"))
            assert signing.began.wait(5)
            n1, n2 = nonce(), nonce()
            a = pool.submit(ask, phone, HOME, n1)
            b = pool.submit(ask, outside, AWAY, n2)
            assert first.result().status_code == 200
            sa, sb = a.result().json(), b.result().json()
        assert checks(sa, n1, HOME)["server"]["outside"] is False
        assert checks(sb, n2, AWAY)["server"]["outside"] is True
        assert sa["statement"] != sb["statement"]


def test_a_full_internet_lane_never_holds_home(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        monkeypatch.setattr(proofs, "WAITING_MOST", 1)
        signing = Signing(monkeypatch, delay=0.5)
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            first = pool.submit(ask, away(app, home, ip="198.51.100.1"), AWAY)
            assert signing.began.wait(5)
            outside = [
                pool.submit(ask, away(app, home, ip=f"198.51.100.{i}"), AWAY) for i in (2, 3)
            ]
            mine = pool.submit(ask, at_home(app, home), HOME)
            assert first.result().status_code == 200
            assert sorted(f.result().status_code for f in outside) == [200, 429]
            assert mine.result().status_code == 200


def test_a_missing_gate_state_is_never_taken_as_home(app, monkeypatch):
    proofs = module("proofs")
    assert proofs.lane_for({"type": "http", "state": {}}) is None
    assert proofs.lane_for({"type": "http"}) is None
    assert proofs.lane_for({"type": "http", "state": {"outside": False}}) == "home"
    assert proofs.lane_for({"type": "http", "state": {"outside": True}}) == "outside"
    with TestClient(app) as home:
        ready(app)
        monkeypatch.setattr(proofs, "lane_for", lambda scope: None)
        got = ask(at_home(app, home))
        assert got.status_code == 503 and got.headers["tapioca-proof"] == "1"


def test_the_away_name_at_home_is_signed_from_the_outside_lane(app):
    """Door "name": the away name reaching the home port from a home peer
    with no forwarding headers is the outside lane's."""
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        n = nonce()
        got = ask(at_home(app, home), AWAY, n, headers={"Host": "tv.example.com"})
        assert got.status_code == 200, got.text
        assert checks(got.json(), n, AWAY)["server"]["outside"] is True


@pytest.mark.parametrize("body", [
    {"nonce": "A" * 64, "address": HOME, "reconnect": False},
    {"nonce": "a" * 63, "address": HOME, "reconnect": False},
    {"nonce": "g" * 64, "address": HOME, "reconnect": False},
    {"address": HOME, "reconnect": False},
    {"nonce": "a" * 64, "address": HOME + "/é", "reconnect": False},
    {"nonce": "a" * 64, "address": HOME + "/\n", "reconnect": False},
    {"nonce": "a" * 64, "address": HOME + "/" + "x" * 183, "reconnect": False},
])  # fmt: skip
def test_a_request_the_server_wont_sign_is_400(app, body):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        got = at_home(app, home).post(ROUTE, json=body)
        assert got.status_code == 400 and got.headers["tapioca-proof"] == "1"
        assert "statement" not in got.text


def test_a_request_from_a_web_page_is_refused(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        got = ask(at_home(app, home), headers={"Origin": "http://evil.example"})
        assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


def test_a_name_tapioca_doesnt_know_at_home_is_refused(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        phone = at_home(app, home)
        before = len(app.state.ctx.alerts.now())
        # (An Origin is refused first, with no alert.)
        assert (
            ask(phone, headers={"Origin": "http://x.example", "Host": "evil.example"}).status_code
            == 403
        )
        assert len(app.state.ctx.alerts.now()) == before
        for _ in range(2):
            got = ask(phone, "http://evil.example", headers={"Host": "evil.example"})
            assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"
            assert "Names for tapiOca at home" in got.text
        said = [a for a in app.state.ctx.alerts.now() if "doesn't know" in a.sentence]
        assert len(said) == 1 and "evil" not in said[0].sentence  # (once a day, naming nothing)


def test_a_listed_home_name_is_signed_over_https_at_home(app):
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/access/trusted", json={"homeNames": ["nas.home.lan"]}).is_success
        ready(app)
        phone = at_home(app, home)
        n = nonce()
        got = ask(phone, "https://nas.home.lan", n, headers={"Host": "nas.home.lan"})
        assert got.status_code == 200, got.text
        checks(got.json(), n, "https://nas.home.lan")
        refused = ask(phone, "https://tapioca-help.example", headers={"Host": "nas.home.lan"})
        assert refused.status_code == 403 and refused.headers["tapioca-proof"] == "1"


@pytest.mark.parametrize("asked,signed", [
    (AWAY, True),
    ("https://tv.example.com:443", True),
    ("https://tv.example.com.", True),
    ("https://TV.example.com", True),
    ("https://tapioca-help.example", False),
    ("https://tv.example.com#x", False),
    ("https://tv.example.com?x", False),
    ("https://tv.example.com/", False),
    ("https://tv.example.com:0443", False),
    ("https://tv.example.com/..", False),
    (" https://tv.example.com", False),
    ("https://evil.example\\@tv.example.com", False),
    ("https://me@tv.example.com", False),
])  # fmt: skip
def test_only_the_servers_own_https_addresses_are_signed(app, asked, signed):
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        n = nonce()
        got = ask(away(app, home), asked, n)
        if signed:
            assert got.status_code == 200, got.text
            checks(got.json(), n, asked)  # (signed as asked, compared in its canonical form)
        else:
            assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


@pytest.mark.parametrize(
    "stored", ["https://TV.example.com:443", "https://tv.example.com.", "https://tv.example.com/"]
)
def test_a_stored_away_address_matches_its_plain_form(app, stored):
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": stored}).is_success
        ready(app)
        n = nonce()
        got = ask(away(app, home), AWAY, n)
        assert got.status_code == 200, got.text


def test_an_away_address_the_apps_cant_check_is_refused_when_saved(app):
    with TestClient(app) as home:
        signing_on(home)
        got = home.put("/api/away", json={"on": True, "address": "https://tv_box.example.com"})
        assert got.status_code == 400 and "plain letters, digits and hyphens" in got.text


def test_an_http_address_on_the_internet_lane_is_refused(app):
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        got = ask(away(app, home), "http://192.168.1.20:3310")
        assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"
        assert "statement" not in got.text


def test_http_from_outside_is_refused_with_the_marker(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        got = ask(away(app, home, https=False), "http://testserver:8443")
        assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


def test_signing_in_off_from_outside_is_refused_with_the_marker(app):
    with TestClient(app) as home:
        ready(app)
        got = ask(away(app, home), AWAY)
        assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


def test_every_answer_at_the_route_carries_the_marker(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        phone = at_home(app, home)
        assert phone.get(ROUTE).headers["tapioca-proof"] == "1"  # (405)
        assert ask(phone).headers["tapioca-proof"] == "1"
        assert "tapioca-proof" not in phone.get("/api/v1/server").headers


def test_the_route_is_open_and_needs_nothing(app):
    assert ROUTE in access.OPEN
    assert not any(ROUTE in paths for paths in access.FOR_USERS.values())
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        assert (
            ask(at_home(app, home)).status_code == 200
        )  # (no cookie, no token: an app before it trusts)


# Batching, the pace and the limits.


def test_many_sources_at_once_share_signatures(app, monkeypatch):
    """65 sources, each under its limit, waiting behind one signature: all
    answered, 64 in one statement and the 65th in the next."""
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        signing = Signing(monkeypatch, delay=0.5)
        asks = [
            (away(app, home, ip=f"198.51.{100 + i // 200}.{1 + i % 200}"), nonce())
            for i in range(66)
        ]
        with concurrent.futures.ThreadPoolExecutor(66) as pool:
            first = pool.submit(ask, asks[0][0], AWAY, asks[0][1])
            assert signing.began.wait(5)
            rest = [pool.submit(ask, c, AWAY, n) for c, n in asks[1:]]
            assert first.result().status_code == 200
            got = [f.result() for f in rest]
        assert all(g.status_code == 200 for g in got), [g.status_code for g in got]
        for g, (_, n) in zip(got, asks[1:], strict=True):
            checks(g.json(), n, AWAY)
        sizes = sorted(sum(1 for g in got if g.json()["statement"] == st)
                       for st in {g.json()["statement"] for g in got})  # fmt: skip
        assert sizes == [1, 64]


def test_pads_come_from_secrets_and_differ(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        phone = at_home(app, home)
        n1, n2 = nonce(), nonce()
        a = set(checks(ask(phone, HOME, n1).json(), n1, HOME)["proofs"])
        b = set(checks(ask(phone, HOME, n2).json(), n2, HOME)["proofs"])
        assert len(a & b) == 0
        made = []

        def token_hex(k):
            made.append(secrets.token_hex(k))
            return made[-1]

        monkeypatch.setattr(proofs.secrets, "token_hex", token_hex)
        n = nonce()
        c = set(checks(ask(phone, HOME, n).json(), n, HOME)["proofs"])
        assert c - {entry(n, HOME)} == set(made) and len(made) == 63


def test_the_same_nonce_and_address_share_an_entry(app, monkeypatch):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        signing = Signing(monkeypatch, delay=0.3)
        n = nonce()
        clients = [at_home(app, home, ip=f"192.168.1.{70 + i}") for i in range(4)]
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            first = pool.submit(ask, clients[0])
            assert signing.began.wait(5)  # (the first is being signed: these wait for the next)
            same = [pool.submit(ask, c, HOME, n) for c in clients[1:3]]
            other = pool.submit(ask, clients[3], "http://testserver:3310", n)
            first.result()
            a, b = (f.result().json() for f in same)
            c = other.result().json()
        assert a["statement"] == b["statement"] == c["statement"]
        checks(a, n, HOME)
        checks(c, n, "http://testserver:3310")


def test_the_pace_is_three_times_the_last_signature(app, monkeypatch):
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        signing = Signing(monkeypatch, delay=0.2)
        clients = [at_home(app, home, ip=f"192.168.1.{80 + i}") for i in range(3)]
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            jobs = [pool.submit(ask, clients[0])]
            assert signing.began.wait(5)
            jobs += [pool.submit(ask, c) for c in clients[1:]]
            for j in jobs:
                assert j.result().status_code == 200
        [one, two] = signing.started
        assert 0.6 <= two - one < 1.2  # (never sooner than three times 0.2 s, and not much later)


def test_a_failed_signature_counts_as_25_ms(app, monkeypatch):
    serverkey = module("serverkey")
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        real = serverkey.spawn
        stuck = {"on": True}

        async def first_hangs(*args, **kw):
            if "dgst" in args and stuck["on"]:
                stuck["on"] = False
                return await asyncio.create_subprocess_exec("/bin/sleep", "30", stdin=kw.get("stdin"),
                                                            stdout=kw.get("stdout"), stderr=kw.get("stderr"))  # fmt: skip
            return await real(*args, **kw)

        monkeypatch.setattr(serverkey, "spawn", first_hangs)
        phone = at_home(app, home)
        assert ask(phone).status_code == 503  # (stopped at its 2 seconds)
        began = time.monotonic()
        assert ask(phone).status_code == 200
        assert time.monotonic() - began < 1  # (never three times those 2 seconds)


def test_per_source_limits(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        monkeypatch.setattr(proofs, "PER_SOURCE_MINUTE", 3)
        phone = away(app, home, ip="2001:db8:1:1::1")
        neighbor = away(app, home, ip="2001:db8:1:2::1")  # (another /64, the same /56: one source)
        elsewhere = away(app, home, ip="2001:db8:1:200::1")  # (another /56)
        assert [ask(c, AWAY).status_code for c in (phone, neighbor, phone)] == [200, 200, 200]
        assert ask(neighbor, AWAY).status_code == 429
        assert ask(elsewhere, AWAY).status_code == 200


def test_per_source_waiting(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        monkeypatch.setattr(proofs, "PER_SOURCE_WAITING", 2)
        signing = Signing(monkeypatch, delay=0.5)
        with concurrent.futures.ThreadPoolExecutor(5) as pool:
            first = pool.submit(ask, away(app, home, ip="198.51.100.9"), AWAY)
            assert signing.began.wait(5)
            mine = [pool.submit(ask, away(app, home, ip="198.51.100.10"), AWAY) for _ in range(4)]
            assert first.result().status_code == 200
            assert sorted(f.result().status_code for f in mine) == [200, 200, 429, 429]


def test_home_sources_are_counted_apart(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        monkeypatch.setattr(proofs, "PER_SOURCE_MINUTE", 2)
        a, b = at_home(app, home, ip="192.168.1.90"), at_home(app, home, ip="192.168.1.91")
        assert [ask(a).status_code for _ in range(3)] == [200, 200, 429]
        assert ask(b).status_code == 200


def test_a_relay_gets_a_households_budget(app, monkeypatch):
    """A relay found from the routing tables (Docker's gateway: conftest's
    fixed_relays) carries a whole household: its own limits."""
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        monkeypatch.setattr(proofs, "PER_SOURCE_MINUTE", 1)
        monkeypatch.setattr(proofs, "RELAY_MINUTE", 3)
        relay = at_home(app, home, ip="172.17.0.1")
        assert [ask(relay).status_code for _ in range(4)] == [200, 200, 200, 429]


def test_the_tables_of_sources_are_bounded(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        monkeypatch.setattr(proofs, "PER_SOURCE_MINUTE", 1)
        monkeypatch.setattr(proofs, "SOURCES_MOST", 2)
        a, b, c = (at_home(app, home, ip=f"192.168.1.{i}") for i in (101, 102, 103))
        assert [ask(x).status_code for x in (a, b, c)] == [200, 200, 200]
        assert ask(a).status_code == 200  # (a was the oldest, dropped when c came)


def test_a_48s_limit(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        monkeypatch.setattr(proofs, "PREFIX48_MINUTE", 2)
        got = [ask(away(app, home, ip=f"2001:db8:1:{n}00::1"), AWAY).status_code for n in (1, 2, 3)]
        assert got == [200, 200, 429]


def test_a_full_lane_answers_429(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(app)
        monkeypatch.setattr(proofs, "WAITING_MOST", 2)
        signing = Signing(monkeypatch, delay=0.5)
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            first = pool.submit(ask, away(app, home, ip="198.51.100.1"), AWAY)
            assert signing.began.wait(5)
            rest = [
                pool.submit(ask, away(app, home, ip=f"198.51.100.{i}"), AWAY) for i in range(2, 6)
            ]
            codes = sorted(f.result().status_code for f in rest)
            assert first.result().status_code == 200
        assert codes == [200, 200, 429, 429]


def test_a_name_too_long_for_a_statement_is_never_signed(tmp_path):
    app = make_app(tmp_path, friendly_name="x" * 13_000)
    with TestClient(app) as home:
        settled(app)
        assert ask(at_home(app, home)).status_code == 503
        assert "FRIENDLY_NAME" in one_alert(app).sentence


# Calling openssl (the design's section 2).


def test_openssl_is_called_as_the_design_says(app, tmp_path, monkeypatch):
    serverkey = module("serverkey")
    calls = []
    real = serverkey.spawn

    async def watched(*args, **kw):
        calls.append((args, kw))
        return await real(*args, **kw)

    monkeypatch.setattr(serverkey, "spawn", watched)
    with TestClient(app) as home:
        ready(app)
        calls.clear()
        assert ask(at_home(app, home)).status_code == 200
    [(args, kw)] = [c for c in calls if "dgst" in c[0]]
    assert list(args) == ["/usr/bin/nice", "-n", "10", "/usr/bin/openssl", "dgst", "-sha256", "-sign",
                          str(key_file(tmp_path)), "-passin", "pass:"]  # fmt: skip
    assert set(kw["env"]) == {"PATH"}
    assert "preexec_fn" not in kw and not kw.get("shell")
    assert serverkey.OPENSSL == "/usr/bin/openssl" and serverkey.NICE == "/usr/bin/nice"


def test_a_hung_openssl_is_stopped(app, monkeypatch):
    serverkey = module("serverkey")
    hung = []

    async def hangs(*args, **kw):
        if "dgst" not in args:
            return await asyncio.create_subprocess_exec(*args, **kw)
        p = await asyncio.create_subprocess_exec("/bin/sleep", "30", stdin=kw.get("stdin"),
                                                 stdout=kw.get("stdout"), stderr=kw.get("stderr"))  # fmt: skip
        hung.append(p.pid)
        return p

    with TestClient(app) as home:
        ready(app)
        monkeypatch.setattr(serverkey, "spawn", hangs)
        began = time.monotonic()
        assert ask(at_home(app, home)).status_code == 503
        assert time.monotonic() - began < 4
        [pid] = hung

        def gone():
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            return False

        until(gone, 2, "the hung openssl stopped")


class Faulty:
    """A signer that exits 0 with 384 bytes that aren't a signature. Its PID
    is None, so code that stops a process without checking it fails here
    rather than signalling PID 0."""

    returncode = 0
    pid = None

    async def communicate(self, data=None):
        return os.urandom(384), b""

    async def wait(self):
        return 0

    def kill(self):
        pass


def test_a_faulty_signature_is_never_sent(app, monkeypatch):
    serverkey = module("serverkey")

    async def faulty(*args, **kw):
        if "dgst" in args:
            return Faulty()
        return await asyncio.create_subprocess_exec(*args, **kw)

    with TestClient(app) as home:
        ready(app)
        monkeypatch.setattr(serverkey, "spawn", faulty)
        phone = at_home(app, home)
        for _ in range(3):
            assert proofs_alerts(app) == []  # (no alert before the third)
            got = ask(phone)
            assert got.status_code == 503 and "signature" not in got.text
        # Three in a row, the key file unchanged: the alert for a cause
        # that's none of the named ones.
        sentence = one_alert(app).sentence
        assert "restart tapiOca" in sentence and "delete" not in sentence.lower()


def test_an_exit_of_127_is_the_openssl_alert(app, monkeypatch):
    serverkey = module("serverkey")

    async def missing(*args, **kw):
        if "dgst" in args:
            return await asyncio.create_subprocess_exec("/bin/sh", "-c", "exit 127", stdin=kw.get("stdin"),
                                                        stdout=kw.get("stdout"), stderr=kw.get("stderr"))  # fmt: skip
        return await asyncio.create_subprocess_exec(*args, **kw)

    with TestClient(app) as home:
        ready(app)
        monkeypatch.setattr(serverkey, "spawn", missing)
        phone = at_home(app, home)
        for _ in range(3):
            assert ask(phone).status_code == 503
        sentence = one_alert(app).sentence
        assert "OpenSSL" in sentence and "delete" not in sentence.lower()


@pytest.mark.parametrize("which", ["NICE", "OPENSSL"])
def test_nice_or_openssl_missing_at_start(tmp_path, monkeypatch, which):
    serverkey = module("serverkey")
    monkeypatch.setattr(serverkey, which, "/nonexistent/" + which.lower())
    app = make_app(tmp_path)
    with TestClient(app) as home:
        assert settled(app) == "unusable"
        assert ask(at_home(app, home)).status_code == 503
        sentence = one_alert(app).sentence
        assert "OpenSSL" in sentence and "delete" not in sentence.lower()


def test_the_key_never_leaves(app, tmp_path, caplog, monkeypatch):
    serverkey = module("serverkey")
    calls = []
    real = serverkey.spawn

    async def watched(*args, **kw):
        calls.append(args)
        return await real(*args, **kw)

    monkeypatch.setattr(serverkey, "spawn", watched)
    caplog.set_level(logging.DEBUG)
    with TestClient(app) as home:
        signing_on(home)
        ready(app)
        phone = at_home(app, home)
        answers = [
            ask(phone).text,
            ask(phone, reconnect=True).text,
            phone.get("/api/v1/server").text,
        ]
        secret = [
            ln for ln in key_file(tmp_path).read_text().splitlines() if not ln.startswith("-----")
        ]
    said = caplog.text + "".join(answers) + "".join(" ".join(a) for a in calls)
    assert "PRIVATE" not in "".join(answers)
    assert not any(line in said for line in secret)


def test_only_server_proof_is_signed(app):
    with TestClient(app) as home:
        ready(app)
        key = app.state.ctx.server_key
        for purpose in ("standins", "play-plan", "home-tls", "server-proof\nx", "anything"):
            with pytest.raises(ValueError):
                home.portal.call(key.sign, purpose, b"{}")
        assert home.portal.call(key.sign, "server-proof", b"{}")


# Access -> Reconnect apps (the design's section 6).


def admins_and_user(app, home: TestClient) -> tuple[TestClient, TestClient, TestClient]:
    signing_on(home)
    assert home.post("/api/access/users", json={**LEE, "role": "admin"}).status_code == 201
    assert home.post("/api/access/users", json={**SAM, "role": "user"}).status_code == 201
    lee = TestClient(app, client=("192.168.1.51", 50000))
    lee.portal = home.portal
    assert lee.post("/api/access/sign-in", json=LEE).status_code == 200
    sam = TestClient(app, client=("192.168.1.52", 50000))
    sam.portal = home.portal
    assert sam.post("/api/access/sign-in", json=SAM).status_code == 200
    return home, lee, sam


def reconnect_mac(code: str, salt: str, n: str, key: str) -> str:
    message = f"tapioca/1 reconnect\n{salt}\n{n}\n{key}".encode()
    return base64.b64encode(
        hmac.new(code.replace("-", "").encode(), message, hashlib.sha256).digest()
    ).decode()


def test_only_an_admin_makes_a_code_and_only_they_see_it(app):
    with TestClient(app) as home:
        pat, lee, sam = admins_and_user(app, home)
        assert sam.post("/api/access/reconnect").status_code == 403
        nobody = TestClient(app, client=("192.168.1.53", 50000))  # (a browser, not signed in)
        nobody.portal = home.portal
        assert nobody.post("/api/access/reconnect").status_code == 401
        made = pat.post("/api/access/reconnect")
        assert made.status_code == 200
        code = made.json()["code"]
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code)
        assert set(code.replace("-", "")) <= set(links.ALPHABET)
        assert pat.get("/api/access/reconnect").json()["code"] == code
        seen = lee.get("/api/access/reconnect").json()
        assert seen["active"] is True and "code" not in seen and code not in json.dumps(seen)


def test_reconnect_answers(app, monkeypatch):
    reconnect = module("reconnect")
    with TestClient(app) as home:
        pat, _, _ = admins_and_user(app, home)
        ready(app)
        phone = at_home(app, home)
        assert set(ask(phone).json()) == {"statement", "signature", "key"}  # (not asked)

        def asked():
            n = nonce()
            a = ask(phone, n=n, reconnect=True).json()
            assert len(base64.b64decode(a["reconnectSalt"], validate=True)) == 32
            assert len(base64.b64decode(a["reconnect"], validate=True)) == 32
            return a, n

        a, n = asked()  # (no code: still both fields)
        b, _ = asked()
        assert a["reconnectSalt"] != b["reconnectSalt"]  # (a fresh salt in every answer)
        code = pat.post("/api/access/reconnect").json()["code"]
        a, n = asked()
        assert a["reconnect"] == reconnect_mac(code, a["reconnectSalt"], n, a["key"])
        # End it: the code no longer matches.
        assert pat.delete("/api/access/reconnect").is_success
        a, n = asked()
        assert a["reconnect"] != reconnect_mac(code, a["reconnectSalt"], n, a["key"])
        # A new code ends the old.
        first = pat.post("/api/access/reconnect").json()["code"]
        second = pat.post("/api/access/reconnect").json()["code"]
        a, n = asked()
        assert a["reconnect"] == reconnect_mac(second, a["reconnectSalt"], n, a["key"])
        assert a["reconnect"] != reconnect_mac(first, a["reconnectSalt"], n, a["key"])
        # 10 minutes.
        now = time.monotonic()
        monkeypatch.setattr(reconnect, "clock", lambda: now + 601)
        a, n = asked()
        assert a["reconnect"] != reconnect_mac(second, a["reconnectSalt"], n, a["key"])


def test_at_most_5_codes_in_10_minutes(app):
    with TestClient(app) as home:
        pat, _, _ = admins_and_user(app, home)
        got = [pat.post("/api/access/reconnect").status_code for _ in range(6)]
        assert got == [200] * 5 + [429]


def test_a_code_is_never_kept(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    app = make_app(tmp_path)
    with TestClient(app) as home:
        pat, _, _ = admins_and_user(app, home)
        ready(app)
        code = pat.post("/api/access/reconnect").json()["code"]
    plain = code.replace("-", "")
    assert code not in caplog.text and plain not in caplog.text
    for f in (tmp_path / "data").rglob("*"):
        if f.is_file():
            data = f.read_bytes()
            assert plain.encode() not in data and code.encode() not in data, f.name
    # A restart ends it.
    again = make_app(tmp_path)
    with TestClient(again) as home:
        ready(again)
        n = nonce()
        a = ask(at_home(again, home), n=n, reconnect=True).json()
        assert a["reconnect"] != reconnect_mac(code, a["reconnectSalt"], n, a["key"])


def test_the_route_and_page_are_documented():
    doc = (Path(__file__).resolve().parent.parent / "docs/internal-api.md").read_text()
    assert "POST /api/internal/proof" in doc and "Tapioca-Proof" in doc

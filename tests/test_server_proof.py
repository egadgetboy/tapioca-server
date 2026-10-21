"""The server proves who it is (1.43.0, planned): its own key, signing a
fresh challenge from each app, and Access -> Reconnect apps. The design is
the apps repo's docs/threat-models/server-proof.md (its ninth version); the
apps' side is their shared cases (shared/cases/proofs.json there). Written
before the code, to fail first.

What these tests take as the code's shape (the design's sections 1 to 3
and 6):
- app/serverkey.py: KEY_FILE ("server-key.pem", in the data folder),
  OPENSSL ("/usr/bin/openssl") and NICE ("/usr/bin/nice"); `spawn`, what
  starts each openssl (asyncio.create_subprocess_exec), so a test can watch
  or replace it; `read_file` (how the key file is read) and `write_all` (how
  a new one is written), so a test can make them fail; and `ctx.server_key`,
  with `.state` ("making", "ready" or "unusable"), `.public_text` (the
  564-letter base64 public key) and `async sign(purpose, body) -> bytes`.
- app/proofs.py: the two lanes and their limits, as module constants a
  test may lower: WAITING_MOST (256), PER_SOURCE_MINUTE (60),
  PER_SOURCE_WAITING (4), PREFIX48_MINUTE (600).
- app/reconnect.py: Reconnect apps' code, with `clock` (time.monotonic) for
  its 10 minutes.
- POST /api/internal/proof; POST and DELETE /api/access/reconnect (an
  Admin makes a code, or ends it).
- alerts.PROOF ("proof"): the Admin alert for the key and for signing.
"""

from __future__ import annotations

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
SAM = {"name": "Sam", "password": "battery staple"}
ROUTE = "/api/internal/proof"
PREFIX = b"tapioca/1 server-proof\n"
SPKI_HEAD = bytes.fromhex("308201a2300d06092a864886f70d01010105000382018f003082018a0282018100")
SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
AWAY = "https://tv.example.com"


def module(name: str):
    """The module the code will have (importing here, so each test fails on
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


def joined(client: TestClient, running: TestClient) -> TestClient:
    """`client` on `running`'s event loop, where the app's lanes live."""
    client.portal = running.portal
    return client


def away(app, running: TestClient, ip: str = "203.0.113.5", https: bool = True) -> TestClient:
    """A device away from home, through the trusted reverse proxy, at `ip`."""
    list_proxy(app)
    headers = {"X-Real-IP": ip, "X-Forwarded-For": ip}
    if https:
        headers["X-Forwarded-Proto"] = "https"
    c = TestClient(app, base_url=f"http://testserver:{PUBLIC_PORT}", client=(PROXY_PEER, 50000),
                   headers=headers)  # fmt: skip
    return joined(c, running)


def nonce() -> str:
    return secrets.token_hex(32)


def ask(client: TestClient, address: str = "http://testserver", n: str | None = None,
        reconnect: bool = False, **kw):  # fmt: skip
    return client.post(ROUTE, json={"nonce": n or nonce(), "address": address, "reconnect": reconnect}, **kw)


def ready(client: TestClient, seconds: float = 20) -> None:
    """Waits for the key (made in the background at the first start)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if ask(client).status_code != 503:
            return
        time.sleep(0.1)
    raise AssertionError("the proof route still answers 503")


def signing_on(home: TestClient) -> None:
    assert home.post("/api/access/users", json=PAT).status_code == 201


def entry(n: str, address: str) -> str:
    return hashlib.sha256(f"tapioca/1 proof-entry\n{n}\n{address}".encode()).hexdigest()


def checks(answer: dict, n: str, address: str) -> dict:
    """The answer's signature checked in plain Python over the prefix and the
    statement's exact bytes, with its entry among exactly 64: the statement."""
    key = base64.b64decode(answer["key"], validate=True)
    sig = base64.b64decode(answer["signature"], validate=True)
    assert len(answer["key"]) == 564 and len(key) == 422 and key[:33] == SPKI_HEAD and key[33] & 0x80
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


def openssl(*args: str) -> bytes:
    return subprocess.run(["openssl", *args], capture_output=True, check=True).stdout


def public_text(pem: Path) -> str:
    return base64.b64encode(openssl("pkey", "-in", str(pem), "-pubout", "-outform", "DER")).decode()


# The key (the design's section 1).


def test_a_key_is_made_at_the_first_start(app, tmp_path):
    with TestClient(app) as home:
        ready(home)
        pem = key_file(tmp_path)
        assert stat.S_IMODE(pem.stat().st_mode) == 0o600
        assert pem.read_text().splitlines()[0] == "-----BEGIN PRIVATE KEY-----"
        text = openssl("pkey", "-in", str(pem), "-noout", "-text").decode()
        assert "3072 bit" in text and "65537" in text
        answered = ask(home).json()
        assert answered["key"] == public_text(pem) == app.state.ctx.server_key.public_text
        assert app.state.ctx.server_key.state == "ready"


def test_the_key_is_kept_across_restarts(tmp_path):
    with TestClient(make_app(tmp_path)) as first:
        ready(first)
        key = ask(first).json()["key"]
    with TestClient(make_app(tmp_path)) as again:
        ready(again)
        assert ask(again).json()["key"] == key


def test_a_wider_mode_is_made_0600_again(tmp_path):
    with TestClient(make_app(tmp_path)) as first:
        ready(first)
    pem = key_file(tmp_path)
    pem.chmod(0o644)
    with TestClient(make_app(tmp_path)) as again:
        ready(again)
        assert stat.S_IMODE(pem.stat().st_mode) == 0o600


@pytest.mark.parametrize("what", ["not a key", "encrypted", "rsa-2048"])
def test_a_key_file_that_cant_be_used_is_left_alone(tmp_path, what):
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
        time.sleep(1)
        assert ask(home).status_code == 503
        assert pem.read_bytes() == before
        assert app.state.ctx.server_key.state == "unusable"
        [alert] = proofs_alerts(app)
        assert "delete" in alert.sentence.lower() or "key" in alert.sentence.lower()


@pytest.mark.parametrize("error", [PermissionError(errno.EACCES, "denied"), OSError(errno.EIO, "I/O")])
def test_only_a_missing_file_makes_a_key(tmp_path, monkeypatch, error):
    serverkey = module("serverkey")
    with TestClient(make_app(tmp_path)) as first:
        ready(first)
    before = key_file(tmp_path).read_bytes()

    def fails(path):
        raise error

    monkeypatch.setattr(serverkey, "read_file", fails)
    app = make_app(tmp_path)
    with TestClient(app) as home:
        time.sleep(1)
        assert ask(home).status_code == 503
        assert key_file(tmp_path).read_bytes() == before
        assert proofs_alerts(app)


def test_two_makers_at_once_make_one_key(tmp_path):
    keys = []

    def start():
        with TestClient(make_app(tmp_path)) as c:
            ready(c)
            keys.append(ask(c).json()["key"])
            time.sleep(0.5)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(keys) == 2 and keys[0] == keys[1]
    assert [p.name for p in (tmp_path / "data").iterdir() if "key" in p.name] == ["server-key.pem"]


def test_a_full_disk_leaves_no_half_made_key(tmp_path, monkeypatch):
    serverkey = module("serverkey")

    def full(fd, data):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(serverkey, "write_all", full)
    app = make_app(tmp_path)
    with TestClient(app) as home:
        time.sleep(2)
        assert ask(home).status_code == 503
    left = [p.name for p in (tmp_path / "data").iterdir() if "key" in p.name or p.name.startswith(".")]
    assert left == []


def test_a_key_swapped_under_a_running_server_stops_proofs(app, tmp_path):
    with TestClient(app) as home:
        ready(home)
        pem = key_file(tmp_path)
        pem.write_bytes(openssl("genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072"))
        assert ask(home).status_code == 503
        assert proofs_alerts(app)


# The protocol (the design's section 3).


def test_the_answer_proves_its_statement(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        n = nonce()
        got = ask(home, "http://testserver", n)
        assert got.status_code == 200, got.text
        assert got.headers["tapioca-proof"] == "1" and got.headers["stationplay-api"] == "1"
        answer = got.json()
        assert set(answer) == {"statement", "signature", "key"}
        body = checks(answer, n, "http://testserver")
        assert isinstance(body["time"], int)


def test_the_statement_is_what_a_server_is(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        n = nonce()
        body = checks(ask(home, "http://testserver", n).json(), n, "http://testserver")
        assert body["server"] == home.get("/api/v1/server").json()
        assert body["server"]["outside"] is False
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        phone = away(app, home)
        n = nonce()
        body = checks(ask(phone, AWAY, n).json(), n, AWAY)
        assert body["server"] == phone.get("/api/v1/server").json()
        assert body["server"]["outside"] is True


def test_the_away_name_at_home_is_signed_from_the_outside_lane(app):
    """Door "name": the away name reaching the home port from a home peer
    with no forwarding headers is the outside lane's."""
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(home)
        n = nonce()
        got = ask(home, AWAY, n, headers={"Host": "tv.example.com"})
        assert got.status_code == 200, got.text
        assert checks(got.json(), n, AWAY)["server"]["outside"] is True


@pytest.mark.parametrize("body", [
    {"nonce": "A" * 64, "address": "http://testserver", "reconnect": False},
    {"nonce": "a" * 63, "address": "http://testserver", "reconnect": False},
    {"nonce": "g" * 64, "address": "http://testserver", "reconnect": False},
    {"address": "http://testserver", "reconnect": False},
    {"nonce": "a" * 64, "address": "http://testserver/é", "reconnect": False},
    {"nonce": "a" * 64, "address": "http://testserver/\n", "reconnect": False},
    {"nonce": "a" * 64, "address": "http://testserver/" + "x" * 183, "reconnect": False},
])  # fmt: skip
def test_a_request_the_server_wont_sign_is_400(app, body):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        got = home.post(ROUTE, json=body)
        assert got.status_code == 400 and got.headers["tapioca-proof"] == "1"
        assert "statement" not in got.text


def test_a_request_from_a_web_page_is_refused(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        got = ask(home, headers={"Origin": "http://evil.example"})
        assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


def test_a_name_tapioca_doesnt_know_at_home_is_refused(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        before = len(app.state.ctx.alerts.now())
        # (An Origin is refused first, with no alert.)
        assert ask(home, headers={"Origin": "http://x.example", "Host": "evil.example"}).status_code == 403
        assert len(app.state.ctx.alerts.now()) == before
        for _ in range(2):
            got = ask(home, "http://evil.example", headers={"Host": "evil.example"})
            assert got.status_code == 403 and "Names for tapiOca at home" in got.text
        said = [a for a in app.state.ctx.alerts.now() if "doesn't know" in a.sentence]
        assert len(said) == 1 and "evil" not in said[0].sentence  # (once a day, naming nothing)


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
        ready(home)
        n = nonce()
        got = ask(away(app, home), asked, n)
        if signed:
            assert got.status_code == 200, got.text
            checks(got.json(), n, asked)  # (signed as asked, compared in its canonical form)
        else:
            assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


def test_an_http_address_on_the_internet_lane_is_refused(app):
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(home)
        got = ask(away(app, home), "http://192.168.1.20:3310")
        assert got.status_code == 403 and "statement" not in got.text


def test_http_from_outside_is_refused_with_the_marker(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        got = ask(away(app, home, https=False), "http://testserver:8443")
        assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


def test_signing_in_off_from_outside_is_refused_with_the_marker(app):
    with TestClient(app) as home:
        ready(home)
        got = ask(away(app, home), AWAY)
        assert got.status_code == 403 and got.headers["tapioca-proof"] == "1"


def test_every_answer_at_the_route_carries_the_marker(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        assert home.get(ROUTE).headers["tapioca-proof"] == "1"  # (405)
        assert ask(home).headers["tapioca-proof"] == "1"
        assert "tapioca-proof" not in home.get("/api/v1/server").headers


def test_the_route_is_open(app):
    assert ROUTE in access.OPEN
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        phone = joined(TestClient(app), home)  # (no cookie, no token: an app before it trusts)
        assert ask(phone).status_code == 200


# Batching, the pace and the limits.


def test_many_requests_share_signatures(app, monkeypatch):
    serverkey = module("serverkey")
    started = []
    real = serverkey.spawn

    async def watched(*args, **kw):
        if "dgst" in args:
            started.append(time.monotonic())
        return await real(*args, **kw)

    monkeypatch.setattr(serverkey, "spawn", watched)
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        started.clear()
        asks = [(nonce(), "http://testserver") for _ in range(24)]
        with concurrent.futures.ThreadPoolExecutor(24) as pool:
            got = list(pool.map(lambda a: ask(home, a[1], a[0]), asks))
        assert all(g.status_code in (200, 429) for g in got)
        answered = [(g.json(), a) for g, a in zip(got, asks, strict=True) if g.status_code == 200]
        for answer, (n, address) in answered:
            checks(answer, n, address)
        statements = {answer["statement"] for answer, _ in answered}
        assert len(statements) == len(started) < len(answered)


def test_pads_differ_between_statements(app):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        n1, n2 = nonce(), nonce()
        a = set(checks(ask(home, "http://testserver", n1).json(), n1, "http://testserver")["proofs"])
        b = set(checks(ask(home, "http://testserver", n2).json(), n2, "http://testserver")["proofs"])
        assert len(a & b) == 0


def slow_signer(monkeypatch, seconds: float, started: list | None = None):
    serverkey = module("serverkey")
    real = serverkey.spawn

    async def slow(*args, **kw):
        if "dgst" in args:
            if started is not None:
                started.append(time.monotonic())
            import asyncio

            await asyncio.sleep(seconds)
        return await real(*args, **kw)

    monkeypatch.setattr(serverkey, "spawn", slow)


def test_the_same_nonce_and_address_share_an_entry(app, monkeypatch):
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        slow_signer(monkeypatch, 0.3)
        n = nonce()
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            first = pool.submit(ask, home)
            time.sleep(0.1)  # (the first is being signed: these wait for the next)
            same = [pool.submit(ask, home, "http://testserver", n) for _ in range(2)]
            other = pool.submit(ask, home, "http://testserver:3310", n)
            first.result()
            a, b = (f.result().json() for f in same)
            c = other.result().json()
        assert a["statement"] == b["statement"] == c["statement"]
        body = checks(a, n, "http://testserver")
        checks(c, n, "http://testserver:3310")
        assert entry(n, "http://testserver") != entry(n, "http://testserver:3310")
        assert len(body["proofs"]) == 64


def test_the_pace_waits_three_times_the_last_signature(app, monkeypatch):
    started: list[float] = []
    with TestClient(app) as home:
        signing_on(home)
        ready(home)
        slow_signer(monkeypatch, 0.2, started)
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            jobs = [pool.submit(ask, home)]
            time.sleep(0.05)
            jobs += [pool.submit(ask, home) for _ in range(2)]
            for j in jobs:
                assert j.result().status_code == 200
        assert len(started) == 2 and started[1] - started[0] >= 0.6


def test_per_source_limits(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(home)
        monkeypatch.setattr(proofs, "PER_SOURCE_MINUTE", 3)
        phone = away(app, home, ip="2001:db8:1:1::1")
        neighbor = away(app, home, ip="2001:db8:1:1::2")  # (the same /56: one source)
        elsewhere = away(app, home, ip="2001:db8:1:200::1")  # (another /56)
        assert [ask(c, AWAY).status_code for c in (phone, neighbor, phone)] == [200, 200, 200]
        assert ask(neighbor, AWAY).status_code == 429
        assert ask(elsewhere, AWAY).status_code == 200


def test_a_48s_limit(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(home)
        monkeypatch.setattr(proofs, "PREFIX48_MINUTE", 2)
        got = [ask(away(app, home, ip=f"2001:db8:1:{n}00::1"), AWAY).status_code for n in (1, 2, 3)]
        assert got == [200, 200, 429]


def test_a_full_lane_answers_429(app, monkeypatch):
    proofs = module("proofs")
    with TestClient(app) as home:
        signing_on(home)
        assert home.put("/api/away", json={"on": True, "address": AWAY}).is_success
        ready(home)
        monkeypatch.setattr(proofs, "WAITING_MOST", 2)
        slow_signer(monkeypatch, 0.5)
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            first = pool.submit(ask, away(app, home, ip="198.51.100.1"), AWAY)
            time.sleep(0.1)
            rest = [pool.submit(ask, away(app, home, ip=f"198.51.100.{i}"), AWAY) for i in range(2, 6)]
            codes = sorted(f.result().status_code for f in rest)
            assert first.result().status_code == 200
        assert codes == [200, 200, 429, 429]


def test_a_name_too_long_for_a_statement_is_never_signed(tmp_path):
    app = make_app(tmp_path, friendly_name="x" * 13_000)
    with TestClient(app) as home:
        time.sleep(1)
        assert ask(home).status_code == 503
        assert any("FRIENDLY_NAME" in a.sentence for a in proofs_alerts(app))


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
        ready(home)
        calls.clear()
        assert ask(home).status_code == 200
    [(args, kw)] = [c for c in calls if "dgst" in c[0]]
    assert list(args) == ["/usr/bin/nice", "-n", "10", "/usr/bin/openssl", "dgst", "-sha256", "-sign",
                          str(key_file(tmp_path)), "-passin", "pass:"]  # fmt: skip
    assert set(kw["env"]) == {"PATH"}
    assert "preexec_fn" not in kw and not kw.get("shell")
    assert serverkey.OPENSSL == "/usr/bin/openssl" and serverkey.NICE == "/usr/bin/nice"


def test_a_hung_openssl_is_stopped(app, monkeypatch):
    serverkey = module("serverkey")
    import asyncio

    hung = []

    async def hangs(*args, **kw):
        if "dgst" not in args:
            return await asyncio.create_subprocess_exec(*args, **kw)
        p = await asyncio.create_subprocess_exec("/bin/sleep", "30", stdin=kw.get("stdin"),
                                                 stdout=kw.get("stdout"), stderr=kw.get("stderr"))  # fmt: skip
        hung.append(p.pid)
        return p

    with TestClient(app) as home:
        ready(home)
        monkeypatch.setattr(serverkey, "spawn", hangs)
        began = time.monotonic()
        assert ask(home).status_code == 503
        assert time.monotonic() - began < 4
        time.sleep(0.2)
        [pid] = hung
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_a_faulty_signature_is_never_sent(app, monkeypatch):
    serverkey = module("serverkey")
    import asyncio

    class Faulty:
        returncode = 0
        pid = 0

        async def communicate(self, data=None):
            return os.urandom(384), b""

        async def wait(self):
            return 0

        def kill(self):
            pass

    async def faulty(*args, **kw):
        if "dgst" in args:
            return Faulty()
        return await asyncio.create_subprocess_exec(*args, **kw)

    with TestClient(app) as home:
        ready(home)
        monkeypatch.setattr(serverkey, "spawn", faulty)
        for _ in range(3):
            got = ask(home)
            assert got.status_code == 503 and "signature" not in got.text
        # Three in a row: the alert for a cause that's none of the named ones.
        [alert] = proofs_alerts(app)
        assert "restart tapiOca" in alert.sentence and "delete" not in alert.sentence.lower()


@pytest.mark.parametrize("which", ["NICE", "OPENSSL"])
def test_nice_or_openssl_missing_at_start(tmp_path, monkeypatch, which):
    serverkey = module("serverkey")
    monkeypatch.setattr(serverkey, which, "/nonexistent/" + which.lower())
    app = make_app(tmp_path)
    with TestClient(app) as home:
        time.sleep(1)
        assert ask(home).status_code == 503
        [alert] = proofs_alerts(app)
        assert "OpenSSL" in alert.sentence and "delete" not in alert.sentence.lower()


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
        ready(home)
        answers = [ask(home).text, ask(home, reconnect=True).text, home.get("/api/v1/server").text]
        secret = [ln for ln in key_file(tmp_path).read_text().splitlines() if not ln.startswith("-----")]
    said = caplog.text + "".join(answers) + "".join(" ".join(a) for a in calls)
    assert "PRIVATE" not in "".join(answers)
    assert not any(line in said for line in secret)


def test_no_backup_holds_the_key():
    assert "server-key.pem" not in backups.FILES


def test_only_server_proof_is_signed(app):
    with TestClient(app) as home:
        ready(home)
        key = app.state.ctx.server_key
        for purpose in ("standins", "play-plan", "home-tls", "server-proof\nx", "anything"):
            with pytest.raises(ValueError):
                home.portal.call(key.sign, purpose, b"{}")
        assert home.portal.call(key.sign, "server-proof", b"{}")


# Access -> Reconnect apps (the design's section 6).


def admin_and_user(app, home: TestClient) -> tuple[TestClient, TestClient]:
    signing_on(home)
    assert home.post("/api/access/users", json={**SAM, "role": "user"}).status_code == 201
    sam = joined(TestClient(app), home)
    assert sam.post("/api/access/sign-in", json=SAM).status_code == 200
    return home, sam


def reconnect_mac(code: str, salt: str, n: str, key: str) -> str:
    message = f"tapioca/1 reconnect\n{salt}\n{n}\n{key}".encode()
    return base64.b64encode(hmac.new(code.replace("-", "").encode(), message, hashlib.sha256).digest()).decode()


def test_only_an_admin_makes_a_code(app):
    with TestClient(app) as home:
        pat, sam = admin_and_user(app, home)
        assert sam.post("/api/access/reconnect").status_code == 403
        assert joined(TestClient(app), home).post("/api/access/reconnect").status_code == 401
        made = pat.post("/api/access/reconnect")
        assert made.status_code == 200
        code = made.json()["code"]
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code)
        assert set(code.replace("-", "")) <= set(links.ALPHABET)


def test_reconnect_answers(app, monkeypatch):
    reconnect = module("reconnect")
    with TestClient(app) as home:
        pat, _ = admin_and_user(app, home)
        ready(home)
        assert set(ask(home).json()) == {"statement", "signature", "key"}  # (not asked)

        def asked():
            n = nonce()
            a = ask(home, n=n, reconnect=True).json()
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
        pat, _ = admin_and_user(app, home)
        got = [pat.post("/api/access/reconnect").status_code for _ in range(6)]
        assert got == [200] * 5 + [429]


def test_a_code_is_never_kept(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    app = make_app(tmp_path)
    with TestClient(app) as home:
        pat, _ = admin_and_user(app, home)
        ready(home)
        code = pat.post("/api/access/reconnect").json()["code"]
    plain = code.replace("-", "")
    assert code not in caplog.text and plain not in caplog.text
    for f in (tmp_path / "data").rglob("*"):
        if f.is_file():
            data = f.read_bytes()
            assert plain.encode() not in data and code.encode() not in data, f.name
    # A restart ends it.
    with TestClient(make_app(tmp_path)) as again:
        ready(again)
        n = nonce()
        a = ask(again, n=n, reconnect=True).json()
        assert a["reconnect"] != reconnect_mac(code, a["reconnectSalt"], n, a["key"])


def test_the_route_and_page_are_documented():
    doc = (Path(__file__).resolve().parent.parent / "docs/internal-api.md").read_text()
    assert "POST /api/internal/proof" in doc and "Tapioca-Proof" in doc

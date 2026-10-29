"""Every route, from every vantage point (DL287 §2.1, AZ-01 to AZ-03; AUTH-01,
AUTH-02): the matrix in authz_matrix.py says each route's class, and here
the running tapiOca is asked each route as an outsider with no sign-in, with
a made-up token, as a Kid on a limited Level, as a User and as an Admin. A
route that isn't in the matrix fails (the suite can't go stale), and so does
any answer the class doesn't allow.

"Let through" means tapiOca's gate didn't refuse it: the handler may still
answer 404 or 422 for the sample address, which is fine here; what's checked
is who gets past the gate.
"""

from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient

from app import access
from app.config import Settings
from app.main import create_app
from app.plex import PlexClient
from tests.fakeplex_library import LibraryPlex

from .authz_matrix import MATRIX

ADA = {"name": "Ada", "password": "correct horse battery"}
SAM = {"name": "Sam", "password": "staple battery horse", "role": "user"}
KIT = {"name": "Kit", "password": "battery horse staple", "role": "user"}

# What the gate says when it refuses (access.py): an answer with one of these is the gate's, not a handler's.
GATE_REFUSALS = {
    "Sign in to tapiOca",
    access.IDLE_SIGNED_OUT,
    access.ADMINS_ONLY,
    access.WATCHES_ONLY,
    access.BAD_TOKEN,
    access.TOKEN_API_ONLY,
    access.TOKEN_READS_ONLY,
    access.ADMIN_PASSWORD_NEEDED,
    access.WATCHING_ONLY,
}
CLASSES = {"public", "tuner", "capability", "device", "watcher", "user", "admin"}
# What the Gate lets through to tapiOca's apps with no sign-in it takes, each with why (access.OPEN,
# beside the page's own files and the tuner's): adding to it is a security decision, made here on purpose.
OPEN_FOR_APPS = {
    "/api/internal/reach": "the reach check: says nothing unless asked with the value it waits for",
    "/api/access/sign-in": "signing in",
    "/api/access/sign-out": "signing out of a browser",
    "/api/access/pin-sign-in": "signing in with a PIN, on a browser that's someone's",
    "/api/access/browser/forget": "Remove from this browser: its own cookie says which",
    "/api/internal/sign-in": "an app signing in",
    "/api/internal/link": "an app asking for a code to link with",
    "/api/internal/link/check": "an app asking whether its code was entered",
    "/api/internal/picker": "a linked device's picker: its key says which",
    "/api/internal/picker/choose": "picking someone there: its key, and their PIN or password",
    "/api/internal/picker/sign-in": "signing in there by name",
    "/api/internal/picker/remove": "Sign out there: its key, and a sign-in of the person's there (1.44.3)",
    "/api/access/trusted-sign-in": "a trusted network's browser: where it comes from says who may",
    "/api/internal/trusted": "a trusted network's device: where it comes from says who may",
}


# (A device at home, as tapiOca's page asks: the module's tapiOca is made before the tests' own fixtures run.)
HOME = {"client": ("192.168.1.50", 50000), "headers": {"X-Tapioca-Page": "1"}}


def _client(app) -> TestClient:
    return TestClient(app, client=HOME["client"], headers=HOME["headers"])


def _routes(app) -> set[str]:
    found = set()
    for route in app.routes:
        for method in getattr(route, "methods", None) or {"GET"}:
            if method != "HEAD":
                found.add(f"{method} {route.path}")
    return found


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("authz")
    fp = LibraryPlex()
    fp.add_section("2", "Movies", "movie")
    fp.add_movie("300", "Picnic", "/m/picnic.mkv", 90 * 60_000, section="2", contentRating=["PG"])
    fp.describe("300")
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp / "data")
    app = create_app(settings, PlexClient("http://plex.test", "token", transport=fp.transport()))
    app.state.ctx.play_transport = fp.transport()
    with _client(app) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code in (200, 201)
        assert admin.post("/api/access/sign-in", json=ADA).status_code == 200
        assert admin.post("/api/access/users", json=SAM).status_code in (200, 201)
        kit = admin.post("/api/access/users", json=KIT).json()
        levels = admin.get("/api/access/viewing").json()["levels"]
        kid = next(lv["id"] for lv in levels if lv["builtin"] == "kid")
        assert (
            admin.put(f"/api/access/users/{kit['id']}/viewing", json={"level": kid}).status_code
            == 200
        )
        yield app


def _token(app, who: dict) -> str:
    signed = _client(app).post("/api/internal/sign-in", json=who)
    assert signed.status_code == 200, signed.text
    return signed.json()["token"]


def _ask(app, method: str, address: str, token: str | None) -> tuple[int, str]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    # (No cookies: each ask is one vantage alone. A body of {} gets past no handler's checks.)
    client = _client(app)
    got = client.request(
        method, address, headers=headers, json={} if method in ("POST", "PUT", "PATCH") else None
    )
    detail = ""
    if got.headers.get("content-type", "").startswith("application/json"):
        try:
            body = got.json()
            detail = body.get("detail", "") if isinstance(body, dict) else ""
        except ValueError:
            pass
    return got.status_code, detail if isinstance(detail, str) else ""


def _refused_by_gate(answer: tuple[int, str]) -> bool:
    status, detail = answer
    return status in (401, 403) and detail in GATE_REFUSALS


def test_every_route_tapioca_serves_is_in_the_matrix_and_every_matrix_route_is_served(world):
    served = _routes(world)
    assert not sorted(served - set(MATRIX)), (
        f"Routes not in tests/security/authz_matrix.py: {sorted(served - set(MATRIX))}"
    )
    assert not sorted(set(MATRIX) - served), (
        f"In the matrix but no longer served: {sorted(set(MATRIX) - served)}"
    )
    assert {cls for cls, _ in MATRIX.values()} <= CLASSES


@pytest.mark.parametrize("route", sorted(MATRIX))
def test_each_route_lets_in_exactly_whom_its_class_says(world, route):
    cls, address = MATRIX[route]
    method = route.split(" ", 1)[0]
    tokens = {
        who: _token(world, person) for who, person in (("kid", KIT), ("user", SAM), ("admin", ADA))
    }
    nobody = _ask(world, method, address, None)
    forged = _ask(
        world, method, address, secrets.token_urlsafe(32)
    )  # (AUTH-02: present, not valid)
    kid = _ask(world, method, address, tokens["kid"])
    user = _ask(world, method, address, tokens["user"])
    admin = _ask(world, method, address, tokens["admin"])
    if cls in ("public", "tuner"):
        for name, answer in (
            ("no sign-in", nobody),
            ("the Kid", kid),
            ("a User", user),
            ("an Admin", admin),
        ):
            assert not _refused_by_gate(answer), f"{route} ({cls}) refused {name}: {answer}"
        return
    if cls == "device":
        # (The key is asked first: with none, a sign-in or a made-up token gets the same 401.)
        for name, answer in (
            ("no sign-in", nobody),
            ("a made-up token", forged),
            ("the Kid", kid),
            ("an Admin", admin),
        ):
            assert answer[0] == 401, (
                f"{route} (device) let in {name} with no device's key: {answer}"
            )
        return
    if cls == "capability":
        # (A made-up session or key is never let in, by anyone: its address is what lets a player in.)
        # (Leaving with a made-up address does nothing and says so with 204: there's no one there to leave.
        # What it may never do is answer with a stream or act on someone else's: its own tests prove that.)
        allowed = (401, 403, 404, 204) if route.endswith("/leave") else (401, 403, 404)
        for name, answer in (
            ("no sign-in", nobody),
            ("a made-up token", forged),
            ("an Admin", admin),
        ):
            assert answer[0] in allowed, f"{route} let in {name} with a made-up address: {answer}"
        return
    assert nobody[0] == 401, f"AUTH-01: {route} ({cls}) let in someone with no sign-in: {nobody}"
    assert forged[0] == 401, f"AUTH-02: {route} ({cls}) let in a made-up token: {forged}"
    assert not _refused_by_gate(admin), f"{route} ({cls}) refused an Admin: {admin}"
    if cls == "admin":
        assert _refused_by_gate(user) and user[0] == 403, f"AZ-02: {route} let in a User: {user}"
        assert _refused_by_gate(kid) and kid[0] == 403, f"AZ-02: {route} let in a Kid: {kid}"
    elif cls == "user":
        assert not _refused_by_gate(user), f"{route} (user) refused a User: {user}"
        assert _refused_by_gate(kid) and kid[0] == 403, (
            f"{route} (user) let in a Kid on a limited Level: {kid}"
        )
    elif cls == "watcher":
        assert not _refused_by_gate(user), f"{route} (watcher) refused a User: {user}"
        assert not _refused_by_gate(kid), f"{route} (watcher) refused a Kid: {kid}"


def test_the_gates_open_list_is_exactly_what_it_should_be():
    assert set(access.OPEN) == access.PAGE | access.FOR_PLEX | set(OPEN_FOR_APPS)


def test_every_signed_in_class_is_gated_and_every_device_route_is_open():
    # (A device route's handler answers 401 itself, which would pass a watcher's checks: so its
    # place in the Gate's open list is checked here, both ways. The 1.44.3 design audit's SO-D2-03.)
    for route, (cls, _) in MATRIX.items():
        path = route.split(" ", 1)[1]
        if cls in ("watcher", "user", "admin"):
            assert path not in access.OPEN, f"{route} ({cls}) is open at the Gate"
        if cls == "device":
            assert path in access.OPEN, f"{route} (device) isn't open at the Gate"


@pytest.fixture
def tv(tmp_path):
    """Sam on a linked TV, with an older sign-in there and their newest; and a Den Roku of
    theirs too: the app, the TV's key, the Den's, Sam's sign-ins (older, newest, the Den's) and
    an Admin's page."""
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data")
    app = create_app(
        settings, PlexClient("http://plex.test", "token", transport=LibraryPlex().transport())
    )
    with _client(app) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code in (200, 201)
        assert admin.post("/api/access/sign-in", json=ADA).status_code == 200
        sam = admin.post("/api/access/users", json={**SAM, "showOn": "signed-in"})
        assert sam.status_code in (200, 201)

        def linked(name: str) -> str:
            made = _client(app).post(
                "/api/internal/sign-in",
                json={**ADA, "app": "Roku", "deviceName": name, "picker": True},
            )
            return made.json()["deviceKey"]

        def picked(key: str) -> str:
            got = _client(app).post(
                "/api/internal/picker/sign-in",
                json={"name": SAM["name"], "password": SAM["password"]},
                headers={"StationPlay-Device": key},
            )
            assert got.status_code == 200, got.text
            return got.json()["token"]

        tv_key, den_key = linked("Living Room"), linked("Den")
        older, newest, den = picked(tv_key), picked(tv_key), picked(den_key)
        phone = _token(app, {**SAM, "app": "Phone", "deviceName": "Sam's phone"})
        changed = _client(app).post(
            "/api/internal/password",
            json={"current": SAM["password"], "new": "a brand new long password"},
            headers={"Authorization": f"Bearer {phone}"},
        )
        assert changed.status_code == 200, changed.text
        yield app, admin, tv_key, {"older": older, "newest": newest, "den": den}


def test_a_device_route_takes_only_its_own_devices_newest_sign_in(tv):
    # (The security suite's device class, 1.44.3: each with the TV's key.)
    app, admin, tv_key, signed = tv
    script = admin.post("/api/api-tokens", json={"name": "Script", "scope": "viewer"})
    assert script.status_code in (200, 201), script.text

    def remove(token: str | None) -> int:
        headers = {"StationPlay-Device": tv_key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return _client(app).post("/api/internal/picker/remove", headers=headers).status_code

    assert remove(None) == 401
    assert remove(secrets.token_urlsafe(32)) == 401
    assert remove(script.json()["token"]) == 403
    assert remove(signed["den"]) == 401
    assert remove(signed["older"]) == 401
    assert remove(signed["newest"]) == 200
    assert remove(signed["newest"]) == 401

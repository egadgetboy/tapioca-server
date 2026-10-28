"""Sign-in tokens, end to end (DL287 §1: AUTH-06, AUTH-06b, AUTH-07): a
token that's ended is refused at once everywhere; a token never travels in
an address or a log line; the three kinds can't stand in for one another;
and a sign-in never keeps a token made before it."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app import access
from app.config import Settings
from app.main import create_app

ADA = {"name": "Ada", "password": "correct horse battery"}
SAM = {"name": "Sam", "password": "staple battery horse", "role": "user"}


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"))
    with TestClient(app) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code in (200, 201)
        assert admin.post("/api/access/sign-in", json=ADA).status_code == 200
        assert admin.post("/api/access/users", json=SAM).status_code in (200, 201)
        yield app  # (started: the database stays open while the test runs)


def _app_token(app, who) -> str:
    got = TestClient(app).post("/api/internal/sign-in", json=who)
    assert got.status_code == 200, got.text
    return got.json()["token"]


def _page_token(app, who) -> tuple[TestClient, str]:
    page = TestClient(app)
    assert page.post("/api/access/sign-in", json=who).status_code == 200
    return page, page.cookies[access.COOKIE]


def _users(page) -> list[dict]:
    got = page.get("/api/access/users").json()
    return got["users"] if isinstance(got, dict) else got


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_an_apps_sign_out_ends_its_token_everywhere_at_once(app):
    token = _app_token(app, SAM)
    phone = TestClient(app)
    assert phone.get("/api/internal/me", headers=_bearer(token)).status_code == 200
    assert phone.post("/api/internal/sign-out", headers=_bearer(token)).status_code in (200, 204)
    for route in ("/api/internal/me", "/api/internal/home", "/api/v1/stations", "/api/channels"):
        assert phone.get(route, headers=_bearer(token)).status_code == 401, route


def test_removing_someone_ends_their_tokens_at_once(app):
    token = _app_token(app, SAM)
    page, _ = _page_token(app, ADA)
    sam = next(u for u in _users(page) if u["name"] == "Sam")
    assert page.delete(f"/api/access/users/{sam['id']}").status_code in (200, 204)
    assert TestClient(app).get("/api/internal/me", headers=_bearer(token)).status_code == 401


def test_an_admin_made_a_user_is_signed_out_at_once(app):
    # (AUTH-06: a change of role ends the sign-in: 401, not just 403 on Admin routes.)
    page, _ = _page_token(app, ADA)
    page.post("/api/access/users", json={"name": "Bea", "password": "horse staple battery", "role": "admin"})
    bea = TestClient(app)
    assert bea.post("/api/access/sign-in", json={"name": "Bea", "password": "horse staple battery"}).status_code == 200
    assert bea.get("/api/access/users").status_code == 200
    who = next(u for u in _users(page) if u["name"] == "Bea")
    assert page.put(f"/api/access/users/{who['id']}", json={"role": "user"}).status_code == 200
    assert bea.get("/api/access/users").status_code == 401


def test_a_token_in_an_address_is_never_a_sign_in(app):
    token = _app_token(app, SAM)
    phone = TestClient(app)
    for name in ("token", "access_token", "X-Plex-Token", "auth"):
        assert phone.get(f"/api/internal/me?{name}={token}").status_code == 401, name


def test_no_token_or_password_reaches_the_log(app, caplog):
    caplog.set_level(logging.DEBUG)
    token = _app_token(app, SAM)
    phone = TestClient(app)
    phone.get("/api/internal/me", headers=_bearer(token))
    phone.get("/api/internal/me", headers=_bearer(token + "x"))
    TestClient(app).post("/api/internal/sign-in", json={"name": "Sam", "password": "wrong password here"})
    said = caplog.text
    assert token not in said and SAM["password"] not in said and "wrong password here" not in said


def test_an_apps_token_is_never_a_browsers_cookie(app):
    # (AUTH-06b: the kinds can't stand in for one another. An app's sign-in kept as a browser's cookie
    # would skip the page's own rules: its hour without activity, and the one browser sign-in, D10.)
    token = _app_token(app, ADA)
    browser = TestClient(app)
    browser.cookies.set(access.COOKIE, token)
    assert browser.get("/api/access/users").status_code == 401


def test_a_browsers_cookie_is_never_an_apps_token(app):
    _, cookie = _page_token(app, ADA)
    phone = TestClient(app)
    assert phone.get("/api/internal/me", headers=_bearer(cookie)).status_code == 401


def test_an_api_token_is_never_a_sign_in_outside_the_api(app):
    page, _ = _page_token(app, ADA)
    made = page.post("/api/api-tokens", json={"name": "script", "scope": "admin"})
    assert made.status_code in (200, 201), made.text
    api = made.json()["token"]
    assert TestClient(app).get("/api/internal/me", headers=_bearer(api)).status_code == 403
    browser = TestClient(app)
    browser.cookies.set(access.COOKIE, api)
    assert browser.get("/api/access/users").status_code in (401, 403)


def test_a_cookie_set_before_signing_in_is_never_the_sign_ins(app):
    # (AUTH-07: a sign-in makes its own token; one an attacker planted first is never kept.)
    browser = TestClient(app)
    planted = "planted-" + "x" * 40
    browser.cookies.set(access.COOKIE, planted)
    signed = browser.post("/api/access/sign-in", json=ADA)
    assert signed.status_code == 200
    assert signed.cookies.get(access.COOKIE) not in (None, planted)
    other = TestClient(app)
    other.cookies.set(access.COOKIE, planted)
    assert other.get("/api/access/users").status_code == 401

"""Every sign-in says how it was made, and only one made with a password,
an invite code or a code linked by a password makes credentials (1.42.1; the
owner's handoff of October 20, part 4).

The gap in 1.42.0: a User picked with their PIN on an ordinary device carried
none of the flags 1.38.0 checks (unlocked, trusted, watching, admin_pin), so
that sign-in could link an app by code at /api/access/link (a 30-day sign-in
with no device attached, which outlives Remove this device) and set their
own PIN: a 4-digit PIN typed on a shared screen made a credential. Now a
sign-in made by a PIN, by picking with nothing or by a trusted network, and
every sign-in from before (old), keeps watching and makes nothing. An Admin's
Light PIN at home keeps its Admin tools (the owner, October 17), still
without these routes: test_admin_sign_in.py's 1.38.0 tests stay."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import access
from app.db import Database

from .test_admin_sign_in import PAT, SAM, browser, light
from .test_admin_sign_in import app as app  # (the fixture)
from .test_admin_sign_in import pat as pat  # (the fixture)
from .test_picker import TV, bearer, device

HOWS = ("password", "invite", "code", "picker", "pin", "admin_pin", "trusted", "old")
# (Those that may make credentials: a password, typed for it; an invite code,
# made by an Admin with theirs; a code an app was linked by, with theirs.)
MAKES = ("password", "invite", "code")


def tv_with_sam(pat, app) -> tuple[TestClient, str]:
    """The family TV, linked by Sam with his password: Pat signs in on it
    with his password too, so both are on its picker."""
    tv = TestClient(app)
    key = tv.post("/api/internal/sign-in", json={**SAM, **TV}).json()["deviceKey"]
    signed = tv.post("/api/internal/picker/sign-in", json=PAT, headers=device(key))
    assert signed.status_code == 200, signed.text
    return tv, key


def picked(tv: TestClient, key: str, user_id: int, pin: str) -> dict:
    got = tv.post(
        "/api/internal/picker/choose", json={"id": user_id, "pin": pin}, headers=device(key)
    )
    assert got.status_code == 200, got.text
    return bearer(got.json()["token"])


def a_code(app) -> str:
    phone = TestClient(app)
    return phone.post("/api/internal/link", json={"app": "tapiOca for Android"}).json()["code"]


# The gap ------------------------------------------------------------------------------


def test_a_users_pin_on_a_tv_links_no_app_and_sets_nothing(pat, app):
    """Sam picked with his PIN on the family TV: watching, and nothing that
    works anywhere else: no app linked by code, no PIN, no password. (He
    changes his PIN with his password.)"""
    tv, key = tv_with_sam(pat, app)
    sams = picked(tv, key, pat.ids["Sam"], "5555")
    assert tv.get("/api/v1/stations", headers=sams).status_code == 200
    code = a_code(app)
    preview = tv.get(f"/api/access/link/{code}", headers=sams)
    assert preview.status_code == 403 and preview.json()["detail"] == access.LINK_BOUND
    linked = tv.post("/api/access/link", json={"code": code}, headers=sams)
    assert linked.status_code == 403 and linked.json()["detail"] == access.LINK_BOUND
    own_pin = tv.post("/api/internal/pin", json={"pin": "9999"}, headers=sams)
    assert own_pin.status_code == 403 and own_pin.json()["detail"] == access.STEP_UP
    own_password = tv.post(
        "/api/internal/password",
        json={"current": SAM["password"], "new": "a whole new password"},
        headers=sams,
    )
    assert own_password.status_code == 403 and own_password.json()["detail"] == access.STEP_UP
    # (His PIN and password are as they were.)
    assert browser(app, SAM).get("/api/access/me").json()["user"]["name"] == "Sam"


# Every way a sign-in is made ------------------------------------------------------------


def made(app, user_id: int, how: str) -> str:
    """A sign-in made `how`, in an app, as each path makes it."""
    ctx = app.state.ctx
    user = ctx.db.user(user_id)
    if how == "old":
        token = ctx.access.start_session(user, "tapiOca for Android", how="password")
        with ctx.db._lock, ctx.db._conn:
            ctx.db._conn.execute(
                "UPDATE sessions SET how = 'old' WHERE token_hash = ?",
                (access.session_hash(token),),
            )
        return token
    if how == "admin_pin":
        return ctx.access.start_session(user, "tapiOca for Android", admin_pin=True, how=how)
    return ctx.access.start_session(user, "tapiOca for Android", how=how)


@pytest.mark.parametrize("how", [h for h in HOWS if h != "admin_pin"])
def test_only_a_secrets_sign_in_makes_credentials(pat, app, how):
    """For each way a User's sign-in is made: a password's, an invite
    code's or a linked code's links an app, sets a PIN and changes a
    password; every other is refused each."""
    with TestClient(app) as c:
        h = bearer(made(app, pat.ids["Sam"], how))
        code = a_code(app)
        tries = {
            "preview": c.get(f"/api/access/link/{code}", headers=h),
            "pin": c.post("/api/internal/pin", json={"pin": "8642"}, headers=h),
            "password": c.post(
                "/api/internal/password",
                json={"current": SAM["password"], "new": "another long password"},
                headers=h,
            ),
        }
        if how in MAKES:
            assert all(r.status_code == 200 for r in tries.values()), {
                k: r.text for k, r in tries.items()
            }
        else:
            assert all(r.status_code == 403 for r in tries.values()), {
                k: r.text for k, r in tries.items()
            }


@pytest.mark.parametrize("how", HOWS)
def test_an_admins_sign_in_makes_credentials_only_from_a_secret(pat, app, how):
    """An Admin's sign-in made any way but a password, an invite code or a
    linked code makes no invite, PIN or linked app. (Whether it has their
    Admin tools is 1.38.0's rule, unchanged: test_admin_sign_in.py.)"""
    with TestClient(app) as c:
        h = bearer(made(app, pat.ids["Pat"], how))
        assert c.get("/api/v1/stations", headers=h).status_code == 200
        invite = c.post(f"/api/access/users/{pat.ids['Kids']}/invite", headers=h)
        pin = c.put(f"/api/access/users/{pat.ids['Sam']}/picker", json={"pin": "0000"}, headers=h)
        linked = c.post("/api/access/link", json={"code": a_code(app)}, headers=h)
        if how in MAKES:
            assert [r.status_code for r in (invite, pin, linked)] == [200, 200, 200], [
                r.text for r in (invite, pin, linked)
            ]
        else:
            assert [r.status_code for r in (invite, pin, linked)] == [403, 403, 403]


def test_start_session_always_says_how():
    """Every caller says how its sign-in was made: there's no default."""
    import inspect

    p = inspect.signature(access.Access.start_session).parameters["how"]
    assert p.default is inspect.Parameter.empty and p.kind is inspect.Parameter.KEYWORD_ONLY


# Each path, as it's made ----------------------------------------------------------------


def hows(app) -> dict[str, str]:
    """Each person's newest sign-in's how, by name."""
    ctx = app.state.ctx
    with ctx.db._lock:
        rows = ctx.db._conn.execute(
            "SELECT users.name, sessions.how FROM sessions JOIN users ON users.id = "
            "sessions.user_id ORDER BY sessions.created_ms, sessions.rowid"
        ).fetchall()
    return {r["name"]: r["how"] for r in rows}


def test_each_path_notes_how(pat, app):
    """The page's password and Light PIN; an app's password; a picker's
    password, PIN and no PIN; an invite code; a code linked on the page."""
    assert hows(app)["Pat"] == "password"  # (the first Admin)
    pc = browser(app, SAM)
    assert hows(app)["Sam"] == "password"
    tv, key = tv_with_sam(pat, app)
    assert hows(app)["Pat"] == "password"
    picked(tv, key, pat.ids["Sam"], "5555")
    assert hows(app)["Sam"] == "pin"
    # Kids, with no PIN and no password, joins the TV with an invite code,
    # then is picked there with nothing.
    code = pat.post(f"/api/access/users/{pat.ids['Kids']}/invite").json()["code"]
    joined = tv.post(
        "/api/internal/picker/sign-in", json={"name": "Kids", "code": code}, headers=device(key)
    )
    assert joined.status_code == 200, joined.text
    assert hows(app)["Kids"] == "invite"
    got = tv.post("/api/internal/picker/choose", json={"id": pat.ids["Kids"]}, headers=device(key))
    assert got.status_code == 200, got.text
    assert hows(app)["Kids"] == "picker"
    # Pat, in Light, picked with his PIN where his password signed in, at home.
    light(pat)
    picked(tv, key, pat.ids["Pat"], "1234")
    assert hows(app)["Pat"] == "admin_pin"
    pc2 = browser(app, PAT)
    light(pc2)
    pc2.cookies.delete(access.COOKIE)
    assert pc2.post(
        "/api/access/pin-sign-in", json={"id": pat.ids["Pat"], "pin": "1234"}
    ).is_success
    assert hows(app)["Pat"] == "admin_pin"
    phone = TestClient(app)
    started = phone.post("/api/internal/link", json={"app": "tapiOca for Android"}).json()
    assert pc.post("/api/access/link", json={"code": started["code"]}).status_code == 200
    assert hows(app)["Sam"] == "code"
    handed = phone.post("/api/internal/link/check", json={"poll": started["poll"]})
    assert handed.status_code == 200


# Upgrade --------------------------------------------------------------------------------


def test_sign_ins_from_before_are_old_and_keep_watching(tmp_path):
    """Sign-ins made before 1.42.1 are "old": kept (nobody is signed out),
    watching, and making no credential. (An Admin's from before 1.38.0 is
    for watching, as 1.38.0 made it.)"""
    path = tmp_path / "old.db"
    old = Database(path)
    pat = old.add_user("Pat", access.hash_password(PAT["password"]), "admin", 1, None, "x")
    sam = old.add_user("Sam", access.hash_password(SAM["password"]), "user", 1, None, "x")
    old._conn.execute("ALTER TABLE sessions DROP COLUMN how")  # (as before 1.42.1)
    for name, user in (("pats", pat), ("sams", sam)):
        old._conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_ms, seen_ms) VALUES (?, ?, 1, 1)",
            (name, user.id),
        )
    old._conn.commit()
    old.close()
    upgraded = Database(path)
    try:
        for name in ("pats", "sams"):
            made = upgraded.session_user(name, 0)
            assert made is not None and made.how == "old"
            assert access.without_secret(made)
    finally:
        upgraded.close()


# The cold audit of 1.42.1 ---------------------------------------------------------------


def test_a_pin_only_accounts_pin_makes_nothing_and_is_told_why(pat, app):
    """Lu has only a PIN: joined the TV with an invite, then picked with her
    PIN, she links no app and sets no PIN, and is told an Admin changes it
    (she has no password to sign in with)."""
    lu = pat.post("/api/access/users", json={"name": "Lu", "role": "user", "pin": "1111"})
    assert lu.status_code == 201, lu.text
    tv, key = tv_with_sam(pat, app)
    code = pat.post(f"/api/access/users/{lu.json()['id']}/invite").json()["code"]
    joined = tv.post(
        "/api/internal/picker/sign-in", json={"name": "Lu", "code": code}, headers=device(key)
    )
    assert joined.status_code == 200, joined.text
    hers = picked(tv, key, lu.json()["id"], "1111")
    link = a_code(app)
    for said in (
        tv.get(f"/api/access/link/{link}", headers=hers),
        tv.post("/api/access/link", json={"code": link}, headers=hers),
    ):
        assert said.status_code == 403 and said.json()["detail"] == access.LINK_BOUND
    said = tv.post("/api/internal/pin", json={"pin": "2222"}, headers=hers)
    assert said.status_code == 403 and said.json()["detail"] == access.NO_PASSWORD_STEP_UP
    me = tv.get("/api/internal/me", headers=hers).json()["user"]
    assert (me["canChangePin"], me["canChangePassword"]) == (False, False)


def test_the_pages_own_password_needs_a_passwords_sign_in(pat, app):
    """POST /api/access/me/password: refused for an Admin's Light PIN on the
    page, a User's PIN token from an app and an old sign-in, even with the
    right current password; a password's changes it."""
    pc = browser(app, PAT)
    light(pc)
    pc.cookies.delete(access.COOKIE)
    assert pc.post("/api/access/pin-sign-in", json={"id": pat.ids["Pat"], "pin": "1234"}).is_success
    change = {"current": PAT["password"], "password": "a brand new long one"}
    said = pc.post("/api/access/me/password", json=change)
    assert said.status_code == 403 and said.json()["detail"] == access.STEP_UP, said.text
    tv, key = tv_with_sam(pat, app)
    sams = picked(tv, key, pat.ids["Sam"], "5555")
    said = tv.post(
        "/api/access/me/password",
        json={"current": SAM["password"], "password": "a brand new long one"},
        headers=sams,
    )
    assert said.status_code == 403, said.text
    by_password = browser(app, PAT)
    assert by_password.post("/api/access/me/password", json=change).status_code == 200
    with TestClient(app) as c:
        old = bearer(made(app, pat.ids["Sam"], "old"))
        said = c.post(
            "/api/access/me/password",
            json={"current": SAM["password"], "password": "a brand new long one"},
            headers=old,
        )
        assert said.status_code == 403 and said.json()["detail"] == access.OLD_STEP_UP


def test_an_old_sign_in_keeps_watching_and_is_told_why(pat, app):
    """A User's old sign-in still watches; what it can't do says it's from
    before the update, not that no password made it; /me says so too."""
    with TestClient(app) as c:
        old = bearer(made(app, pat.ids["Sam"], "old"))
        assert c.get("/api/v1/stations", headers=old).status_code == 200
        said = c.post("/api/internal/pin", json={"pin": "8642"}, headers=old)
        assert said.status_code == 403 and said.json()["detail"] == access.OLD_STEP_UP
        link = c.post("/api/access/link", json={"code": a_code(app)}, headers=old)
        assert link.status_code == 403 and link.json()["detail"] == access.OLD_LINK_BOUND
        me = c.get("/api/internal/me", headers=old).json()["user"]
        assert (me["canChangePin"], me["canChangePassword"]) == (False, False)
        fresh = bearer(made(app, pat.ids["Sam"], "password"))
        me = c.get("/api/internal/me", headers=fresh).json()["user"]
        assert (me["canChangePin"], me["canChangePassword"]) == (True, True)


def test_a_sign_in_without_how_is_old(tmp_path):
    """A sign-in 1.42.0 makes after going back, on a database that has the
    column: it's old (SQL's default), and makes no credential."""
    db = Database(tmp_path / "back.db")
    try:
        sam = db.add_user("Sam", access.hash_password(SAM["password"]), "user", 1, None, "x")
        with db._lock, db._conn:
            db._conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_ms, seen_ms) "
                "VALUES ('back', ?, 1, 1)",
                (sam.id,),
            )
        made_then = db.session_user("back", 0)
        assert made_then is not None and made_then.how == "old"
        assert access.without_secret(made_then)
    finally:
        db.close()


@pytest.mark.parametrize("how", ("pin", "picker", "trusted"))
def test_an_admins_pin_picker_or_network_sign_in_is_for_watching_whatever_its_flags(pat, app, how):
    """Defense in depth: an Admin's sign-in made by a PIN outside Light, a
    picker or a trusted network is for watching even without the 1.38.0
    flags that say so."""
    with TestClient(app) as c:
        h = bearer(made(app, pat.ids["Pat"], how))
        said = c.get("/api/internal/alerts", headers=h)
        assert said.status_code == 403 and said.json()["detail"] == access.WATCHING_ONLY


def test_a_new_pin_from_an_admin_ends_the_old_pins_sign_ins(pat, app):
    """An Admin sets Sam a new PIN: the sign-in his old one made on the TV
    ends; his password's don't."""
    tv, key = tv_with_sam(pat, app)
    sams = picked(tv, key, pat.ids["Sam"], "5555")
    pc = browser(app, SAM)
    assert tv.get("/api/v1/stations", headers=sams).status_code == 200
    assert pat.put(f"/api/access/users/{pat.ids['Sam']}/picker", json={"pin": "7777"}).is_success
    assert tv.get("/api/v1/stations", headers=sams).status_code == 401
    assert pc.get("/api/access/me").json()["user"]["name"] == "Sam"


def test_more_paths_note_how(pat, app):
    """The rest of the paths: a trusted network's; a new password, on the
    page and in an app; the picker with a password; an app linked by code
    with a picker; the picker's one box; an Admin's PIN in Full."""
    ctx = app.state.ctx
    # The picker with Pat's password (an Admin), and its one box.
    tv, key = tv_with_sam(pat, app)
    chose = tv.post(
        "/api/internal/picker/choose",
        json={"id": pat.ids["Pat"], "password": PAT["password"]},
        headers=device(key),
    )
    assert chose.status_code == 200 and hows(app)["Pat"] == "password"
    boxed = tv.post(
        "/api/internal/picker/sign-in",
        json={"name": "Pat", "secret": PAT["password"]},
        headers=device(key),
    )
    assert boxed.status_code == 200 and hows(app)["Pat"] == "password"
    # Pat's PIN in Full (his PIN for watching): a PIN's.
    picked(tv, key, pat.ids["Pat"], "1234")
    assert hows(app)["Pat"] == "pin"
    # An app with a picker, linked by code on the page.
    started = TestClient(app).post(
        "/api/internal/link", json={"app": "tapiOca for Roku", "deviceName": "Den Roku"}
    )
    started = started.json()
    pat_pc = browser(app, PAT)
    assert pat_pc.post("/api/access/link", json={"code": started["code"]}).status_code == 200
    assert hows(app)["Pat"] == "code"
    # A trusted network's (as trustedapi makes them).
    entry = {"id": "home"}
    user = ctx.db.user(pat.ids["Sam"])
    ctx.access.start_session(user, unlocked=True, trusted=entry["id"], how=access.HOW_TRUSTED)
    assert hows(app)["Sam"] == "trusted"
    # A new password on the page, and in an app.
    sam_pc = browser(app, SAM)
    new = {"current": SAM["password"], "password": "sam's new long password"}
    assert sam_pc.post("/api/access/me/password", json=new).status_code == 200
    assert hows(app)["Sam"] == "password"
    phone = TestClient(app)
    signed = phone.post(
        "/api/internal/sign-in", json={"name": "Sam", "password": new["password"], **TV}
    ).json()
    changed = phone.post(
        "/api/internal/password",
        json={"current": new["password"], "new": "sam's third long password"},
        headers=bearer(signed["token"]),
    )
    assert changed.status_code == 200, changed.text
    assert hows(app)["Sam"] == "password"

"""Sign out takes the person off the device's list, even when the sign-in its
remove carries has ended (1.44.3): a device's newest sign-in for a person,
and the one a changed password renewed it from, still count for that one
thing, while they're on that device's list. Nothing else."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import access, db as dbmod
from app.db import Database

from .test_picker import ADA, TV, app, away_from_home, bearer, device, people, two_ports  # noqa: F401

PAT = {"name": "Pat", "password": "pat's long password"}
PHONE = {"app": "tapiOca for Android", "deviceName": "Pat's phone"}
REMOVE = "/api/internal/picker/remove"


@pytest.fixture
def tv_room(app):
    """Ada (an Admin) and Pat (a User with a password); Ada links the TV,
    which Pat then signs in on by name: the page's client, the TV's, its key
    and Pat's ID."""
    with TestClient(app) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code == 201
        pat = admin.post("/api/access/users", json={**PAT, "role": "user", "showOn": "signed-in"})
        assert pat.status_code == 201, pat.text
        tv = TestClient(app)
        key = tv.post("/api/internal/sign-in", json={**ADA, **TV}).json()["deviceKey"]
        yield admin, tv, key, pat.json()["id"]


def pat_on(tv: TestClient, key: str) -> str:
    signed = tv.post("/api/internal/picker/sign-in", json=PAT, headers=device(key))
    assert signed.status_code == 200, signed.text
    return signed.json()["token"]


def remove(tv: TestClient, key: str, token: str):
    return tv.post(REMOVE, headers={**device(key), **bearer(token)})


def phone_password_change(app) -> None:
    phone = TestClient(app)
    token = phone.post("/api/internal/sign-in", json={**PAT, **PHONE}).json()["token"]
    changed = phone.post(
        "/api/internal/password",
        json={"current": PAT["password"], "new": "a brand new password"},
        headers=bearer(token),
    )
    assert changed.status_code == 200, changed.text


# The paths a remove can take (the threat model's §4) --------------------------------


def test_a_live_sign_in_is_removed_as_today(tv_room):
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    assert remove(tv, key, t1).status_code == 200
    assert people(tv, key) == ["Ada"]


def test_a_password_changed_on_another_device_still_signs_out_here(app, tv_room):
    # (P2: the careful path: a new password on the phone, then Sign out on the TV.)
    admin, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    phone_password_change(app)
    assert tv.get("/api/v1/stations", headers=bearer(t1)).status_code == 401
    gone = remove(tv, key, t1)
    assert gone.status_code == 200 and gone.json() == {"ok": True}
    assert people(tv, key) == ["Ada"]
    log = admin.get("/api/logs?access_log=true").json()["text"]
    assert "Pat took themselves off" in log and "(their sign-in there had ended)" in log
    assert t1 not in log and access.session_hash(t1) not in log


def test_a_role_changed_still_signs_out_here(tv_room):
    # (P3)
    admin, tv, key, pat_id = tv_room
    t1 = pat_on(tv, key)
    assert admin.put(f"/api/access/users/{pat_id}", json={"role": "admin"}).status_code == 200
    assert remove(tv, key, t1).status_code == 200
    assert people(tv, key) == ["Ada"]


def test_a_sign_in_unused_for_a_day_still_signs_out(tv_room, monkeypatch):
    # (P5)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    later = access._now() + access.PICKED_MS + 60_000
    monkeypatch.setattr(access, "_now", lambda: later)
    assert tv.get("/api/v1/stations", headers=bearer(t1)).status_code == 401
    assert remove(tv, key, t1).status_code == 200
    assert people(tv, key) == ["Ada"]


def test_someone_else_signing_in_on_the_tv_still_leaves_the_newest_able(tv_room):
    # (P8: one sign-in per device: Ada's ended Pat's.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    ada = tv.post("/api/internal/picker/sign-in", json=ADA, headers=device(key))
    assert ada.status_code == 200
    assert tv.get("/api/v1/stations", headers=bearer(t1)).status_code == 401
    assert remove(tv, key, t1).status_code == 200
    assert people(tv, key) == ["Ada"]


def test_the_sign_in_a_changed_password_renewed_from_still_signs_out(tv_room):
    # (P9: the password changed on the TV, its answer lost: the app still holds T1.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    changed = tv.post(
        "/api/internal/password",
        json={"current": PAT["password"], "new": "a brand new password"},
        headers=bearer(t1),
    )
    t2 = changed.json()["token"]
    assert remove(tv, key, t1).status_code == 200
    assert people(tv, key) == ["Ada"]
    # (None is left that no one holds.)
    assert tv.get("/api/v1/stations", headers=bearer(t2)).status_code == 401


def test_renewed_from_ends_once_the_new_sign_in_is_seen(tv_room, monkeypatch):
    # (P12's second half: after its first use 5 minutes or more after it was made.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    t2 = tv.post(
        "/api/internal/password",
        json={"current": PAT["password"], "new": "a brand new password"},
        headers=bearer(t1),
    ).json()["token"]
    later = access._now() + access.SEEN_EVERY_MS + 1_000
    monkeypatch.setattr(access, "_now", lambda: later)
    assert tv.get("/api/v1/stations", headers=bearer(t2)).status_code == 200
    assert remove(tv, key, t1).status_code == 401
    assert people(tv, key) == ["Ada", "Pat"]
    assert remove(tv, key, t2).status_code == 200


def test_an_older_sign_in_never_signs_out(tv_room):
    # (P12: they've signed in there since.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    t3 = pat_on(tv, key)
    assert remove(tv, key, t1).status_code == 401
    assert people(tv, key) == ["Ada", "Pat"]
    assert tv.get("/api/v1/stations", headers=bearer(t3)).status_code == 200


def test_another_devices_ended_sign_in_never_signs_out_here(app, tv_room):
    # (P13)
    _, tv, key, _ = tv_room
    pat_on(tv, key)
    den = TestClient(app)
    den_key = den.post(
        "/api/internal/sign-in", json={**ADA, **TV, "deviceName": "Den Roku"}
    ).json()["deviceKey"]
    t_den = pat_on(den, den_key)
    phone_password_change(app)
    assert remove(tv, key, t_den).status_code == 401
    assert people(tv, key) == ["Ada", "Pat"]


def test_a_browsers_cookie_never_signs_out_a_device(tv_room):
    # (P14: Bearer only. Today a page's cookie with a device's key took its
    # person off that device's list; nothing sends one.)
    admin, tv, key, _ = tv_room
    pat_on(tv, key)
    sent = admin.post(REMOVE, headers=device(key))
    assert sent.status_code == 401
    assert people(tv, key) == ["Ada", "Pat"]


def test_an_unknown_api_token_is_answered_as_the_gate_answers_it(tv_room):
    # (P15b)
    _, tv, key, _ = tv_room
    sent = remove(tv, key, "spk_" + "x" * 43)
    assert sent.status_code == 401 and "API token" in sent.json()["detail"]


def test_an_ended_sign_in_does_nothing_else(app, tv_room):
    # (§3, rule 1: the Gate refuses it everywhere else, as today.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    phone_password_change(app)
    for method, path in (("GET", "/api/internal/me"), ("GET", "/api/v1/stations"),
                         ("POST", "/api/internal/sign-out"), ("GET", "/api/internal/home")):
        got = tv.request(method, path, headers={**device(key), **bearer(t1)})
        assert got.status_code == 401, (path, got.status_code)
    assert people(tv, key) == ["Ada", "Pat"]


def test_someone_listed_only_at_home_signs_out_from_away(tmp_path):
    # (P11b: no password, no PIN, so listed only at home; their ended sign-in
    # sent from away still takes them off.)
    app = two_ports(tmp_path)
    with TestClient(app) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code == 201
        kids = admin.post("/api/access/users", json={"name": "Kids", "role": "user"}).json()
        tv = TestClient(app)
        key = tv.post("/api/internal/sign-in", json={**ADA, **TV}).json()["deviceKey"]
        code = admin.post(f"/api/access/users/{kids['id']}/invite").json()["code"]
        token = tv.post(
            "/api/internal/picker/sign-in", json={"name": "Kids", "code": code},
            headers=device(key),
        ).json()["token"]  # fmt: skip
        assert people(tv, key) == ["Ada", "Kids"]
        assert admin.put(f"/api/access/users/{kids['id']}", json={"role": "admin"}).status_code == 200
        away = away_from_home(app)
        gone = away.post(REMOVE, headers={**device(key), **bearer(token)})
        assert gone.status_code == 200, gone.text
        assert people(tv, key) == ["Ada"]


def test_a_database_error_is_never_hidden(app, tv_room, monkeypatch):
    # (§3, rule 8: a bare 500, which every app tries again; never a 401, and
    # never one with a sentence, which they'd take as final.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    phone_password_change(app)

    def broken(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(app.state.ctx.db, "remove_by_ended_sign_in", broken)
    loose = TestClient(app, raise_server_exceptions=False)
    got = loose.post(REMOVE, headers={**device(key), **bearer(t1)})
    assert got.status_code == 500
    assert "detail" not in got.text


# The record itself ------------------------------------------------------------------


def test_backups_never_say_who_signed_in_where(app, tv_room, tmp_path):
    # (§2: copy_database empties it with the sessions; a before-update copy keeps it.)
    _, tv, key, _ = tv_room
    pat_on(tv, key)
    source = Path(app.state.ctx.db.path)
    plain, kept = tmp_path / "plain.db", tmp_path / "kept.db"
    dbmod.copy_database(source, plain)
    dbmod.copy_database(source, kept, sign_ins=True)
    with sqlite3.connect(plain) as c:
        assert c.execute("SELECT COUNT(*) FROM device_sign_ins").fetchone() == (0,)
    with sqlite3.connect(kept) as c:
        assert c.execute("SELECT COUNT(*) FROM device_sign_ins").fetchone()[0] >= 1


def _fresh(tmp_path: Path) -> Path:
    path = tmp_path / "stationplay.db"
    Database(path)
    return path


@pytest.mark.parametrize(
    ("version", "mark", "unrowed", "fills"),
    [
        ("1.44.3", True, False, False),
        ("1.45.0", True, False, False),
        ("", True, False, False),
        ("1.44.2", True, False, True),
        ("1.33.9", True, False, True),
        ("junk", True, False, True),
        ("1.44.3", False, False, True),
        ("1.44.3", True, True, True),
    ],
)
def test_the_fill_is_decided_once_by_one_rule(version, mark, unrowed, fills):
    # (§2: changes_needed and _upgrade both ask it, so a rebuild is never made
    # without a backup, or a backup for nothing.)
    assert dbmod.device_sign_ins_fill(
        table=True, mark=mark, version_started=version, unrowed=unrowed
    ) == fills
    assert dbmod.device_sign_ins_fill(table=False, mark=False, version_started=version, unrowed=False)


def test_an_older_version_having_run_rebuilds_the_table(tmp_path):
    # (P24: rows left by 1.44.2 are gone; the sign-ins still in sessions get theirs.)
    path = _fresh(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO meta (key, value) VALUES ('version_started', '1.44.2') "
                  "ON CONFLICT(key) DO UPDATE SET value = excluded.value")  # fmt: skip
    assert "device sign-ins rebuilt" in " ".join(dbmod.changes_needed(path))


def test_a_file_without_meta_never_stops_a_start(tmp_path):
    path = tmp_path / "bare.db"
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE stations (id INTEGER PRIMARY KEY)")
    dbmod.changes_needed(path)


def test_only_the_remove_reads_the_record():
    # (§2's census, in app/: the schema, the rule, the fill, add_session, seen,
    # the remove's method and the live path's forgetting, and copy_database.)
    allowed = {"db.py"}
    found = {
        p.name
        for p in (Path(__file__).resolve().parent.parent / "app").rglob("*.py")
        if "device_sign_ins" in p.read_text()
    }
    assert found == allowed, found

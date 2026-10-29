"""Sign out takes the person off the device's list, even when the sign-in its
remove carries has ended (1.44.3): a device's newest sign-in for a person,
and the one a changed password renewed it from, still count for that one
thing, while they're on that device's list. Nothing else."""

# ruff: noqa: F811 (pytest's fixtures, `app` among them, are imported from test_picker and named as parameters)

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import access
from app import db as dbmod
from app.db import Database

from .test_picker import (  # noqa: F401  # fmt: skip
    ADA,
    TV,
    app,
    away_from_home,
    bearer,
    device,
    people,
    two_ports,
)

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
    for method, path in (
        ("GET", "/api/internal/me"),
        ("GET", "/api/v1/stations"),
        ("POST", "/api/internal/sign-out"),
        ("GET", "/api/internal/home"),
    ):
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
        assert (
            admin.put(f"/api/access/users/{kids['id']}", json={"role": "admin"}).status_code == 200
        )
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
    assert (
        dbmod.device_sign_ins_fill(table=True, mark=mark, version_started=version, unrowed=unrowed)
        == fills
    )
    assert dbmod.device_sign_ins_fill(
        table=False, mark=False, version_started=version, unrowed=False
    )


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


# The rest of §4's paths -------------------------------------------------------------


def _rows(app) -> list[tuple]:
    """The record, read straight from the database file: (device, person,
    newest, renewed from)."""
    with sqlite3.connect(Path(app.state.ctx.db.path)) as c:
        return c.execute(
            "SELECT device_id, user_id, session_hash, renewed_from FROM device_sign_ins "
            "ORDER BY device_id, user_id"
        ).fetchall()


def test_a_live_sign_in_of_another_device_also_ends_theirs_here(app, tv_room):
    # (P1b: as today, and now every sign-in of theirs on this device ends too.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    phone = TestClient(app)
    t_phone = phone.post("/api/internal/sign-in", json={**PAT, **PHONE}).json()["token"]
    assert remove(tv, key, t_phone).status_code == 200
    assert people(tv, key) == ["Ada"]
    assert tv.get("/api/v1/stations", headers=bearer(t1)).status_code == 401
    assert phone.get("/api/v1/stations", headers=bearer(t_phone)).status_code == 401
    assert all(row[1] != tv_room[3] or row[0] != _tv_id(app) for row in _rows(app))


def _tv_id(app) -> int:
    with sqlite3.connect(Path(app.state.ctx.db.path)) as c:
        return c.execute(
            "SELECT id FROM linked_devices WHERE name = ?", (TV["deviceName"],)
        ).fetchone()[0]


def test_a_browsers_sign_in_sent_as_a_bearer_never_signs_out_a_device(tv_room):
    # (P14b)
    admin, tv, key, _ = tv_room
    browser = admin.cookies.get(access.COOKIE)
    assert browser
    assert remove(tv, key, browser).status_code == 401
    assert people(tv, key) == ["Ada"]


def test_a_known_api_token_is_answered_as_the_gate_answers_it(tv_room):
    # (P15: decided once, by the Gate's own rule.)
    admin, tv, key, _ = tv_room
    made = admin.post("/api/api-tokens", json={"name": "Script", "scope": "viewer"})
    assert made.status_code in (200, 201), made.text
    sent = remove(tv, key, made.json()["token"])
    assert sent.status_code == 403 and sent.json()["detail"] == access.TOKEN_API_ONLY


def test_the_key_is_asked_for_first(tv_room):
    # (P15c, P22: an API token, or a sign-in, with no key or a wrong one.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    for headers in (bearer("spk_" + "x" * 43), bearer(t1), {**device("not a key"), **bearer(t1)}):
        sent = tv.post(REMOVE, headers=headers)
        assert sent.status_code == 401 and "isn't linked" in sent.json()["detail"], sent.text
    assert people(tv, key) == ["Ada", "Pat"]


def test_no_token_or_one_tapioca_never_gave_never_signs_out(tv_room):
    # (P16)
    _, tv, key, _ = tv_room
    pat_on(tv, key)
    for headers in (device(key), {**device(key), **bearer("made up")}):
        sent = tv.post(REMOVE, headers=headers)
        assert sent.status_code == 401 and sent.json()["detail"] == "Sign in to tapiOca"
    assert people(tv, key) == ["Ada", "Pat"]


def test_once_off_the_list_the_same_remove_finds_no_one(app, tv_room):
    # (P18, and R1 one after the other.)
    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    phone_password_change(app)
    assert remove(tv, key, t1).status_code == 200
    assert remove(tv, key, t1).status_code == 401
    assert _rows(app) == [] or all(row[1] != tv_room[3] for row in _rows(app))


def test_the_record_goes_with_its_person_and_its_device(app, tv_room):
    # (P19, P20: cascades.)
    admin, tv, key, pat_id = tv_room
    t1 = pat_on(tv, key)
    assert any(row[1] == pat_id for row in _rows(app))
    assert admin.delete(f"/api/access/users/{pat_id}").status_code in (200, 204)
    assert not any(row[1] == pat_id for row in _rows(app))
    assert remove(tv, key, t1).status_code == 401
    ada = tv.post("/api/internal/picker/sign-in", json=ADA, headers=device(key))
    assert ada.status_code == 200 and _rows(app)
    listed = admin.get("/api/access/devices").json()["devices"]
    assert admin.delete(f"/api/access/devices/{listed[0]['id']}").status_code == 204
    assert _rows(app) == []
    assert remove(tv, key, ada.json()["token"]).status_code == 401


def test_signing_in_off_is_said_as_today(app):
    # (P23)
    with TestClient(app) as tv:
        sent = tv.post(REMOVE, headers={**device("any"), **bearer("any")})
        assert sent.status_code == 400


def test_two_removes_at_once_remove_once(app, tv_room):
    # (R1: one transaction under the database's lock.)
    import threading

    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    phone_password_change(app)
    ctx = app.state.ctx
    found = ctx.devices.device(key)
    start = threading.Barrier(8)
    took: list[object] = []

    def one() -> None:
        start.wait()
        took.append(ctx.devices.remove_ended(found, access.session_hash(t1)))

    threads = [threading.Thread(target=one) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for x in took if x is not None) == 1
    assert people(tv, key) == ["Ada"]


def test_a_remove_while_a_password_change_is_being_checked(app, tv_room, monkeypatch):
    # (R3, a known limit: removed; the password then makes a sign-in on this
    # device for someone off its list, held by no one.)
    import threading
    import time as _time

    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    checking, go = threading.Event(), threading.Event()
    real = app.state.ctx.access.check_password

    async def held(*args, **kwargs):
        import asyncio

        checking.set()
        while not go.is_set():
            await asyncio.sleep(0.01)
        return await real(*args, **kwargs)

    monkeypatch.setattr(app.state.ctx.access, "check_password", held)
    answers: dict[str, int] = {}

    def change() -> None:
        answers["password"] = tv.post(
            "/api/internal/password",
            json={"current": PAT["password"], "new": "a brand new password"},
            headers=bearer(t1),
        ).status_code

    worker = threading.Thread(target=change)
    worker.start()
    assert checking.wait(10)
    answers["remove"] = remove(tv, key, t1).status_code
    go.set()
    worker.join(10)
    _time.sleep(0)
    assert answers["remove"] == 200
    assert people(tv, key) == ["Ada"]


def test_the_same_ended_sign_in_is_refused_on_every_other_route(app, tv_room):
    # (§3, rule 1, every route the apps use, and the API's: the Gate's 401.)
    from fastapi.routing import APIRoute

    _, tv, key, _ = tv_room
    t1 = pat_on(tv, key)
    phone_password_change(app)
    asked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith(("/api/internal/", "/api/v1/")) or route.path in access.OPEN:
            continue
        address = route.path
        for name in route.param_convertors:
            address = address.replace("{" + name + "}", "1").replace("{" + name + ":path}", "1")
        for method in route.methods - {"HEAD"}:
            got = tv.request(method, address, headers={**device(key), **bearer(t1)},
                             json={} if method in ("POST", "PUT", "PATCH") else None)  # fmt: skip
            assert got.status_code == 401, (method, route.path, got.status_code, got.text)
            asked += 1
    assert asked > 30
    assert people(tv, key) == ["Ada", "Pat"]


def test_a_networks_device_away_from_its_network_is_refused_first(tmp_path):
    # (P21: this_device's 403, as today; the person comes off on that network.)
    from .test_trusted import device_at, home

    gen = home.__wrapped__(tmp_path)
    made = next(gen)
    try:
        tablet = device_at(made, "192.168.1.61")
        key = tablet.post("/api/internal/trusted", json={"app": "Tablet", "picker": True}).json()[
            "deviceKey"
        ]
        away = device_at(made, "192.168.20.5", stationplay_device=key)
        sent = away.post(REMOVE, headers=bearer("anything"))
        assert sent.status_code == 403
    finally:
        with contextlib.suppress(StopIteration):
            next(gen)


# The record, at an update -----------------------------------------------------------


def _as_if_1_44_2_ran(path: Path, keep_table: bool = False, stale: bool = False) -> None:
    """The database as 1.44.2 leaves it: no record (or, restored from a
    backup 1.44.2 made of an updated one, a record it never kept up), no
    mark, and 1.44.2 the version that last started."""
    with sqlite3.connect(path) as c:
        if keep_table:
            if stale:
                c.execute("UPDATE device_sign_ins SET session_hash = 'stale'")
        else:
            c.execute("DROP TABLE IF EXISTS device_sign_ins")
            c.execute("DELETE FROM meta WHERE key = 'device_sign_ins_filled'")
        c.execute(
            "INSERT INTO meta (key, value) VALUES ('version_started', '1.44.2') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )


def _started_as_1_44_3(path: Path) -> None:
    """What the lifespan's note_version does at the end of a start."""
    with sqlite3.connect(path) as c:
        c.execute(
            "INSERT INTO meta (key, value) VALUES ('version_started', '1.44.3') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )


def _table(path: Path) -> list[tuple]:
    with sqlite3.connect(path) as c:
        return c.execute(
            "SELECT device_id, user_id, session_hash, renewed_from FROM device_sign_ins "
            "ORDER BY device_id, user_id"
        ).fetchall()


def test_the_update_fills_the_record_once_and_a_second_start_changes_nothing(
    app, tv_room, monkeypatch
):
    # (P5's sign-in, unused for a day, still in sessions: its row is filled.)
    _, tv, key, pat_id = tv_room
    t1 = pat_on(tv, key)
    path = Path(app.state.ctx.db.path)
    _as_if_1_44_2_ran(path)
    assert "a new table, device_sign_ins" in dbmod.changes_needed(path)
    Database(path).close()
    rows = _table(path)
    assert (_tv_id(app), pat_id, access.session_hash(t1), None) in rows
    _started_as_1_44_3(path)
    assert dbmod.changes_needed(path) == []
    Database(path).close()
    assert _table(path) == rows


def test_a_start_stopped_before_the_fill_finished_fills_at_the_next(app, tv_room):
    _, tv, key, pat_id = tv_room
    t1 = pat_on(tv, key)
    path = Path(app.state.ctx.db.path)
    with sqlite3.connect(path) as c:
        c.execute("DELETE FROM device_sign_ins")
        c.execute("DELETE FROM meta WHERE key = 'device_sign_ins_filled'")
    assert "device sign-ins rebuilt" in " ".join(dbmod.changes_needed(path))
    Database(path).close()
    assert (_tv_id(app), pat_id, access.session_hash(t1), None) in _table(path)


def test_a_restored_older_backup_keeps_none_of_its_rows(app, tv_room):
    # (P24, P25: rows 1.44.2 never kept up are gone; the sign-ins still in
    # sessions get theirs.)
    _, tv, key, pat_id = tv_room
    t1 = pat_on(tv, key)
    path = Path(app.state.ctx.db.path)
    _as_if_1_44_2_ran(path, keep_table=True, stale=True)
    Database(path).close()
    rows = _table(path)
    assert all(row[2] != "stale" for row in rows)
    assert (_tv_id(app), pat_id, access.session_hash(t1), None) in rows


def test_a_device_sign_in_without_its_row_rebuilds(app, tv_room):
    # (SO-D3-03: a build that signed someone in without keeping the record.)
    _, tv, key, pat_id = tv_room
    t1 = pat_on(tv, key)
    path = Path(app.state.ctx.db.path)
    with sqlite3.connect(path) as c:
        c.execute("DELETE FROM device_sign_ins WHERE user_id = ?", (pat_id,))
    assert "device sign-ins rebuilt" in " ".join(dbmod.changes_needed(path))
    Database(path).close()
    assert (_tv_id(app), pat_id, access.session_hash(t1), None) in _table(path)


def test_a_doubled_or_orphaned_sign_in_never_breaks_the_fill(app, tv_room):
    _, tv, key, pat_id = tv_room
    t1 = pat_on(tv, key)
    path = Path(app.state.ctx.db.path)
    tv_id = _tv_id(app)
    with sqlite3.connect(path) as c:
        c.execute("PRAGMA foreign_keys = OFF")
        made = c.execute(
            "SELECT created_ms FROM sessions WHERE token_hash = ?", (access.session_hash(t1),)
        ).fetchone()[0]
        c.execute(
            "INSERT INTO sessions (token_hash, user_id, created_ms, seen_ms, app, device_id, how) "
            "VALUES ('older', ?, ?, ?, 'x', ?, 'password')",
            (pat_id, made - 1000, made - 1000, tv_id),
        )
        c.execute(
            "INSERT INTO sessions (token_hash, user_id, created_ms, seen_ms, app, device_id, how) "
            "VALUES ('orphan', ?, ?, ?, 'x', 999, 'password')",
            (pat_id, made, made),
        )
    _as_if_1_44_2_ran(path)
    Database(path).close()
    rows = _table(path)
    assert (tv_id, pat_id, access.session_hash(t1), None) in rows
    assert all(row[2] not in ("older", "orphan") for row in rows)


def test_two_starts_make_one_before_update_copy_and_keep_the_record(tmp_path):
    from app.config import Settings
    from app.main import create_app
    from app.plex import PlexClient

    from .fakeplex import FakePlex

    def started():
        settings = Settings(
            plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data"
        )
        return create_app(
            settings, PlexClient("http://plex.test", "token", transport=FakePlex().transport())
        )

    first = started()
    with TestClient(first) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code == 201
        key = (
            TestClient(first).post("/api/internal/sign-in", json={**ADA, **TV}).json()["deviceKey"]
        )
        assert key
    first.state.ctx.db.close()
    path = tmp_path / "data" / "stationplay.db"
    _as_if_1_44_2_ran(path)
    for _ in range(2):
        again = started()
        with TestClient(again):
            pass
        again.state.ctx.db.close()
    copies = list((tmp_path / "data").rglob("before-*.db"))
    assert len(copies) == 1, copies
    assert _table(path)

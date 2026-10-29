"""Only the remove reads the device sign-ins' record (1.44.3: the threat
model's §2 and §6, docs/threat-models/signout-ends.md): an ended sign-in
counts for nothing else, so no other code may read or write
device_sign_ins. Pinned twice: by the code that names it (never a
docstring), and by what touches it as tapiOca runs, which a name built at
run time can't slip past. A new reader or writer fails here until this
file says it may."""

from __future__ import annotations

import ast
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import access
from app import db as dbmod
from app.config import Settings
from app.main import create_app
from app.plex import PlexClient
from tests.fakeplex import FakePlex

APP = Path(__file__).resolve().parents[2] / "app"
TABLE = "device_sign_ins"
# The places in db.py whose code names the table.
NAMING = {
    "SCHEMA",
    "FILLED_META",
    "_UNROWED",
    "copy_database",
    "forget_device_sign_ins",
    "changes_needed",
    "Database.__post_init__",
    "Database._upgrade",
    "Database.add_session",
    "Database.seen",
    "Database.remove_by_ended_sign_in",
    "Database._take_off",
}
# What touches it as tapiOca runs: those, the rule's check, and the deletes that
# cascade to it from a person or a device.
TOUCHING = {
    "db.py:Database.__post_init__",
    "db.py:Database._upgrade",
    "db.py:_fills_device_sign_ins",
    "db.py:changes_needed",
    "db.py:copy_database",
    "db.py:forget_device_sign_ins",
    "db.py:Database.add_session",
    "db.py:Database.seen",
    "db.py:Database.remove_by_ended_sign_in",
    "db.py:Database._take_off",
    "db.py:Database.delete_user",
    "db.py:Database.unlink_device",
}
ADA = {"name": "Ada", "password": "correct horse battery"}
PAT = {"name": "Pat", "password": "pat's long password"}
TV = {"app": "tapiOca for Roku", "deviceName": "Living Room", "picker": True}
HOME = {"client": ("192.168.1.50", 50000), "headers": {"X-Tapioca-Page": "1"}}


def _naming(tree: ast.Module) -> set[str]:
    """The module's places whose code names the table: a constant's, a
    function's or a method's (a body's docstring, a lone string first, isn't
    code)."""
    found: set[str] = set()

    def visit(node: ast.AST, scope: str) -> None:
        body = getattr(node, "body", [])
        first = body[0] if body else None
        docstring = (
            first
            if isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            else None
        )
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                visit(child, f"{scope}.{child.name}" if scope else child.name)
            elif child is not docstring and any(
                isinstance(n, ast.Constant) and isinstance(n.value, str) and TABLE in n.value
                for n in ast.walk(child)
            ):
                targets = getattr(child, "targets", None) or [getattr(child, "target", None)]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                found.add(scope or (names[0] if names else "<module>"))

    visit(tree, "")
    return found


def test_only_these_places_name_the_record():
    elsewhere = {
        p.name for p in APP.rglob("*.py") if p.name != "db.py" and _naming(ast.parse(p.read_text()))
    }
    assert elsewhere == set()
    assert _naming(ast.parse((APP / "db.py").read_text())) == NAMING


def test_the_census_sees_code_first_in_a_body():
    # (Only a docstring is skipped: an expression that reads the table first is code.)
    found = _naming(
        ast.parse(
            "def reader(conn):\n"
            '    conn.execute("SELECT * FROM device_sign_ins")\n'
            "def documented():\n"
            '    """About device_sign_ins."""\n'
        )
    )
    assert found == {"reader"}


@pytest.fixture
def touched(monkeypatch, tmp_path):
    """Every sqlite3 connection opened while a test runs reports what touches
    the table: the innermost place in app/ that asked."""
    seen: set[str] = set()
    real = sqlite3.connect

    def watch(action, first, second, *_):
        if TABLE in (first, second):
            frame = sys._getframe(1)
            while frame is not None and not frame.f_code.co_filename.startswith(str(APP)):
                frame = frame.f_back
            seen.add(
                f"{Path(frame.f_code.co_filename).name}:{frame.f_code.co_qualname}"
                if frame
                else "outside app/"
            )
        return sqlite3.SQLITE_OK

    def connect(*args, **kwargs):
        conn = real(*args, **kwargs)
        conn.set_authorizer(watch)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    return seen


def test_only_these_places_touch_the_record_as_tapioca_runs(touched, tmp_path, monkeypatch):
    settings = Settings(plex_url="http://plex.test", plex_token="token", data_dir=tmp_path / "data")
    app = create_app(
        settings, PlexClient("http://plex.test", "token", transport=FakePlex().transport())
    )
    app.state.ctx.restart = lambda: None
    with TestClient(app, client=HOME["client"], headers=HOME["headers"]) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code == 201
        assert admin.post("/api/access/sign-in", json=ADA).status_code == 200
        pat = admin.post("/api/access/users", json={**PAT, "role": "user", "showOn": "signed-in"})
        tv = TestClient(app, client=HOME["client"])
        key = {
            "StationPlay-Device": tv.post("/api/internal/sign-in", json={**ADA, **TV}).json()[
                "deviceKey"
            ]
        }
        on_tv = tv.post("/api/internal/picker/sign-in", json=PAT, headers=key).json()["token"]
        phone = TestClient(app, client=HOME["client"])
        signed = phone.post(
            "/api/internal/sign-in", json={**PAT, "app": "Phone", "deviceName": "Phone"}
        )
        changed = phone.post(
            "/api/internal/password",
            json={"current": PAT["password"], "new": "a brand new long password"},
            headers={"Authorization": f"Bearer {signed.json()['token']}"},
        )
        assert changed.status_code == 200
        # (Its new sign-in used 5 minutes on: seen, which ends "renewed from".)
        later = access._now() + access.SEEN_EVERY_MS + 1_000
        monkeypatch.setattr(access, "_now", lambda: later)
        renewed = {"Authorization": f"Bearer {changed.json()['token']}"}
        assert phone.get("/api/internal/me", headers=renewed).status_code == 200
        ended = tv.post(
            "/api/internal/picker/remove", headers={**key, "Authorization": f"Bearer {on_tv}"}
        )
        assert ended.status_code == 200
        name = admin.post("/api/backups").json()["name"]
        backup = admin.get(f"/api/backups/{name}").content
        assert admin.delete(f"/api/access/users/{pat.json()['id']}").status_code in (200, 204)
        devices = admin.get("/api/access/devices").json()["devices"]
        assert admin.delete(f"/api/access/devices/{devices[0]['id']}").status_code == 204
        assert admin.post("/api/restore", content=backup).status_code == 200
    # (Started again: the restore is put in place, and the record's rows forgotten.)
    again = create_app(
        settings, PlexClient("http://plex.test", "token", transport=FakePlex().transport())
    )
    with TestClient(again, client=HOME["client"], headers=HOME["headers"]):
        pass
    dbmod.changes_needed(tmp_path / "data" / "stationplay.db")
    assert touched == TOUCHING, sorted(touched ^ TOUCHING)

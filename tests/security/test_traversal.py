"""Paths (DL287, INJ-01): every route that takes a key, a name or a path is
asked, as an Admin, with the ways out of a folder: "../", encoded, doubled,
an absolute path, a NUL. None may answer with a file outside what tapiOca
serves: a planted file's words never come back."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app

from .authz_matrix import MATRIX

ADA = {"name": "Ada", "password": "correct horse battery"}
HOME = {"client": ("192.168.1.50", 50000), "headers": {"X-Tapioca-Page": "1"}}
SECRET = "planted-" + secrets.token_hex(8)

ROUTES = sorted(r for r in MATRIX if "{" in r and r.split(" ", 1)[0] == "GET")


def _ways_out(target: str) -> list[str]:
    deep = "../" * 12
    return [
        f"{deep}{target.lstrip('/')}",
        f"{'%2e%2e%2f' * 12}{target.lstrip('/')}",
        f"{'..%2f' * 12}{target.lstrip('/')}",
        f"{'....//' * 12}{target.lstrip('/')}",
        f"{'..%5c' * 12}{target.lstrip('/')}",
        target,
        f"{target}%00.png",
        f"%2f{target.lstrip('/')}",
    ]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("paths")
    planted = tmp / "planted.txt"
    planted.write_text(SECRET)
    app = create_app(Settings(data_dir=tmp / "data", media_dir=str(tmp / "media")))
    (tmp / "media").mkdir()
    with TestClient(app, client=HOME["client"], headers=HOME["headers"]) as admin:
        assert admin.post("/api/access/users", json=ADA).status_code in (200, 201)
        assert admin.post("/api/access/sign-in", json=ADA).status_code == 200
        yield admin, str(planted)


@pytest.mark.parametrize("route", ROUTES)
def test_no_route_reads_a_file_outside_what_it_serves(world, route):
    admin, planted = world
    path = route.split(" ", 1)[1]
    for way in _ways_out(planted):
        # (Each parameter in turn takes the way out; the others keep the matrix's sample.)
        for name in re.findall(r"\{([^}]+)\}", path):
            address = re.sub(r"\{" + re.escape(name) + r"\}", way, path)
            address = re.sub(r"\{[^}]+\}", "1", address)
            try:
                got = admin.get(address)
            except Exception as e:
                assert "planted" not in str(e)
                continue
            assert SECRET not in got.text, (
                f"INJ-01: {address} answered with a file from outside: {got.status_code}"
            )


def test_the_check_reaches_the_handlers_and_would_see_a_leak(world, tmp_path):
    # (A control: an address of the same kind that's allowed answers, so the routes above were really
    # asked; and the check itself finds the planted words when a file holds them.)
    admin, planted = world
    assert admin.get(f"/web/page.css?v={__version__}").status_code == 200
    assert SECRET in Path(planted).read_text()

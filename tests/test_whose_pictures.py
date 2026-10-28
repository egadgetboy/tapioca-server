"""Every app sign-in says who by ID, not only by name (1.43.0; the
restore-fast-pictures handoff, 4b: the apps keep a stamp of whose the
device's saved pictures are, "server ID and user ID", and clear them for
anyone else; the cold audit of the apps: a name can be given to someone else
after a rename or a delete, and a typed name differs in case from the one
kept)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .test_picker import ADA, TV, app, bearer, device, household, signs_in_here  # noqa: F401


def test_every_sign_in_says_the_persons_id(app):  # noqa: F811
    with TestClient(app) as admin:
        admin.post("/api/access/users", json=ADA)
        household(admin)
        kids = admin.post("/api/access/users", json={"name": "Kids", "role": "user"}).json()
        tia = admin.post(
            "/api/access/users",
            json={
                "name": "Tia",
                "password": "teen password",
                "role": "user",
                "showOn": "signed-in",
            },
        ).json()
        ada_id = next(u["id"] for u in admin.get("/api/access/users").json() if u["name"] == "Ada")
        tv = TestClient(app)

        signed = tv.post("/api/internal/sign-in", json={**ADA, **TV}).json()
        assert signed["user"]["id"] == ada_id, signed["user"]
        key = signed["deviceKey"]
        assert tv.get("/api/internal/me", headers=bearer(signed["token"])).json()["user"]["id"] == ada_id

        invited = signs_in_here(tv, key, admin, kids)
        assert invited["user"]["id"] == kids["id"], invited["user"]

        picked = tv.post(
            "/api/internal/picker/choose", json={"id": kids["id"]}, headers=device(key)
        )
        assert picked.json()["user"]["id"] == kids["id"]

        # (Typed in another case: the person's own name and ID come back.)
        tia_in = tv.post(
            "/api/internal/picker/sign-in",
            json={"name": "tia", "password": "teen password"},
            headers=device(key),
        )
        assert tia_in.status_code == 200, tia_in.text
        assert tia_in.json()["user"]["id"] == tia["id"] and tia_in.json()["user"]["name"] == "Tia"

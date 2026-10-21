"""The census is whole (DL287, A.1): every outbound request, started program
and file write in the code is declared with what it is, and nothing declared
is gone. A new one fails here until it's declared and gets its checks."""

from __future__ import annotations

import pytest

from . import inventory


@pytest.mark.parametrize(
    ("found", "declared", "what"),
    [
        (inventory.egress_sites, inventory.EGRESS, "outbound request"),
        (inventory.spawn_sites, inventory.SPAWN, "started program"),
        (inventory.write_sites, inventory.WRITE, "file write"),
    ],
)
def test_every_site_in_the_code_is_declared_and_every_declared_one_is_there(found, declared, what):
    seen = {str(site) for site in found()}
    new = sorted(seen - set(declared))
    gone = sorted(set(declared) - seen)
    assert not new, f"A new {what}, not in tests/security/inventory.py: {new}"
    assert not gone, f"Declared but no longer in the code (take it out of inventory.py): {gone}"


def test_every_outbound_request_says_where_its_address_comes_from():
    # (DL287, the owner's provenance rule: typed by an Admin, fixed in the code, or from data.)
    for site, what in inventory.EGRESS.items():
        assert what.split(":", 1)[0] in ("typed", "fixed", "data"), site


def test_no_program_is_started_through_a_shell():
    # (DEP-04, INJ-02: an argument list, never a shell.)
    for site in inventory.spawn_sites():
        assert site.call not in ("asyncio.create_subprocess_shell", "os.system", "os.popen"), site


def test_every_write_says_where_it_lands():
    for site, what in inventory.WRITE.items():
        assert what.split(":", 1)[0] in ("data", "temp", "no file"), site


def test_the_census_finds_what_it_should():
    # (The census itself: if a refactor of inventory.py stopped it finding anything, every check above
    # would pass on nothing.)
    assert len(inventory.egress_sites()) >= 6
    assert len(inventory.spawn_sites()) >= 10
    assert len(inventory.write_sites()) >= 30

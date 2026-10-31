"""A path Plex reports is read as a file only where it's Media's (MED-01, the
security suite's slice 2: the apps repository's
docs/threat-models/security-suite-2.md). Whatever controls Plex's answers
names the file tapiOca reads, so a place is taken only under a root (the
media folder, a mapped folder, one of Plex's library folders), never one of
tapiOca's own or the system's, its links followed, only a video, and never
the database by another name. A refusal is its own outcome: Plex's stream
plays instead, and without one it's skipped for now, never "file not found",
never broken. Report-only until the soak: each refusal logged, nothing
refused."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from app import mediaread, sources
from app.catalog import Media
from app.config import Settings
from app.db import Item
from app.library import Library
from app.plex import PlexClient
from app.replacing import _MISSING
from app.sources import MediaAccess, resolve_source

from ..fakeplex import FakePlex

APP = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def place(tmp_path, monkeypatch):
    """A data folder with the database and a backup, a media folder with a
    show, a converted copy's piece in tapiOca's own temp folder, a second
    disk a library of links points at, and a folder where Plex's own path
    is mounted as it is."""
    data, media = tmp_path / "data", tmp_path / "media"
    (data / "backups").mkdir(parents=True)
    (data / "stationplay.db").write_bytes(b"SQLite format 3\x00 secrets")
    (data / "backups" / "stationplay-backup-1.zip").write_bytes(b"PK backup")
    media.mkdir()
    (media / "show.mkv").write_bytes(b"x")
    temp = tmp_path / "tmp"
    (temp / "stationplay-copy-1").mkdir(parents=True)
    (temp / "stationplay-copy-1" / "piece.ts").write_bytes(b"x")
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    (tmp_path / "disk2").mkdir()
    (tmp_path / "disk2" / "real.mkv").write_bytes(b"x")
    (tmp_path / "plexmount" / "TV").mkdir(parents=True)
    (tmp_path / "plexmount" / "TV" / "ep.mkv").write_bytes(b"x")
    mediaread._said.clear()
    return tmp_path


def _policy(root: Path, **kw) -> mediaread.Policy:
    settings = Settings(
        data_dir=root / "data", media_dir=kw.pop("media_dir", str(root / "media")), **kw
    )
    return mediaread.Policy.of(settings, [str(root / "plexmount")])


def _hostile(root: Path) -> dict[str, str]:
    """Each way the record lists, as the place a candidate names."""
    data, media = root / "data", root / "media"
    os.symlink(data / "stationplay.db", media / "linked.mkv")
    os.link(data / "stationplay.db", media / "hard.mkv")
    os.symlink(root / "tmp" / "stationplay-copy-1" / "piece.ts", media / "piece.mkv")
    (media / "notes.txt").write_text("x")
    return {
        "the database": str(data / "stationplay.db"),
        "a backup": str(data / "backups" / "stationplay-backup-1.zip"),
        "a converted copy's piece": str(root / "tmp" / "stationplay-copy-1" / "piece.ts"),
        "/etc/passwd": "/etc/passwd",
        "a secret under /run": "/run/secrets/x",
        "a way out with /../": f"{media}/../data/stationplay.db",
        "a link named .mkv to the database": str(media / "linked.mkv"),
        "a hard link to the database": str(media / "hard.mkv"),
        "a link to a converted copy's piece": str(media / "piece.mkv"),
        "a file that isn't a video": str(media / "notes.txt"),
    }


def test_each_hostile_place_is_refused(place):
    policy = _policy(place)
    for what, path in _hostile(place).items():
        assert policy.refusal(path), f"{what} ({path}) would be read"


def test_media_still_plays_from_each_kind_of_library(place):
    """A show in the media folder; Media mounted inside the data folder; a
    library of links to another disk; Plex's own path, mounted as it is; a
    PATH_MAPPINGS target."""
    os.symlink(place / "disk2" / "real.mkv", place / "media" / "real.mkv")
    (place / "data" / "media").mkdir()
    (place / "data" / "media" / "inside.mkv").write_bytes(b"x")
    (place / "mapped").mkdir()
    (place / "mapped" / "film.mp4").write_bytes(b"x")
    assert _policy(place).refusal(str(place / "media" / "show.mkv")) is None
    assert _policy(place).refusal(str(place / "media" / "real.mkv")) is None
    assert _policy(place).refusal(str(place / "plexmount" / "TV" / "ep.mkv")) is None
    inside = _policy(place, media_dir=str(place / "data" / "media"))
    assert inside.refusal(str(place / "data" / "media" / "inside.mkv")) is None
    mapped = _policy(place, path_mappings=[("/plex/films", str(place / "mapped"))])
    assert mapped.refusal(str(place / "mapped" / "film.mp4")) is None


def _plex_reporting(path: str, *, part: bool = True) -> tuple[FakePlex, PlexClient]:
    fp = FakePlex()
    fp.add_show("100", "Show")
    fp.add_episode("201", "100", 1, 1, "Pilot", path, 60000)
    if not part:
        del fp.episodes["201"]["Media"][0]["Part"][0]["key"]
    return fp, PlexClient("http://plex.test", "token", transport=fp.transport())


def _ep() -> Item:
    return Item(
        position=0, start_ms=0, duration_ms=60000, rating_key="201", kind="episode",
        title="Show 1x1", show_title="Show", show_key="show-Show", season=1, episode=1,
    )  # fmt: skip


async def test_a_refused_place_plays_from_plex_and_is_never_read(place, monkeypatch):
    monkeypatch.setattr(mediaread, "ENFORCED", True)
    settings = Settings(data_dir=place / "data", media_dir=str(place / "media"))
    for what, path in _hostile(place).items():
        _fp, client = _plex_reporting(path)
        access = MediaAccess()
        resolved = await resolve_source(settings, Library(client), _ep(), access)
        assert resolved.source and resolved.source.startswith("http://plex.test/"), (
            f"{what}: {resolved}"
        )
        assert access.direct == 0, what


async def test_a_refusal_with_no_stream_is_never_missing_or_broken(place, monkeypatch):
    """Without Plex's stream, a refused file is skipped for now: never "file
    not found", which automatic replacement takes for missing (replacing.py),
    and never broken."""
    monkeypatch.setattr(mediaread, "ENFORCED", True)
    settings = Settings(data_dir=place / "data", media_dir=str(place / "media"))
    _fp, client = _plex_reporting(str(place / "data" / "stationplay.db"), part=False)
    resolved = await resolve_source(settings, Library(client), _ep(), MediaAccess())
    assert resolved.source is None and resolved.error == mediaread.NOT_OURS and resolved.transient
    assert not resolved.error.startswith(_MISSING)
    media = Media(container="mkv", video="h264", file=str(place / "data" / "stationplay.db"))
    located = await sources.locate(settings, Library(client), "201", media, MediaAccess())
    assert located.error == mediaread.NOT_OURS and located.transient
    read = await sources.readable(
        settings, Library(client), replace(_ep(), file_path=media.file), MediaAccess()
    )
    assert read.error == mediaread.NOT_OURS and read.transient
    checked = await sources.readable(
        settings,
        Library(client),
        replace(_ep(), file_path=media.file),
        MediaAccess(),
        sources.ShareCheck(),
    )
    assert checked.error == mediaread.NOT_OURS and checked.transient


async def test_direct_play_never_reads_a_refused_place(place, monkeypatch):
    """Both of Media's play paths take their file from read_here (applibrary.py)."""
    monkeypatch.setattr(mediaread, "ENFORCED", True)
    settings = Settings(data_dir=place / "data", media_dir=str(place / "media"))
    for what, path in _hostile(place).items():
        assert await sources.read_here(settings, MediaAccess(), "201", path, ()) is None, what
    shown = str(place / "media" / "show.mkv")
    assert await sources.read_here(settings, MediaAccess(), "201", shown, ()) == shown
    played = (APP / "applibrary.py").read_text()
    assert "find_file(" not in played and played.count("await read_here(") == 2


async def test_plexs_own_library_folders_are_roots_once_plex_lists_them(place, monkeypatch):
    monkeypatch.setattr(mediaread, "ENFORCED", True)
    path = str(place / "plexmount" / "TV" / "ep.mkv")
    fp, client = _plex_reporting(path)
    fp.add_section("1", "TV", "show", (str(place / "plexmount" / "TV"),))
    settings = Settings(data_dir=place / "data", media_dir=str(place / "media"))
    assert (
        await resolve_source(settings, Library(client), _ep(), MediaAccess())
    ).source.startswith("http")
    await client.sections()
    assert client.locations == (str(place / "plexmount" / "TV"),)
    assert (await resolve_source(settings, Library(client), _ep(), MediaAccess())).source == path


async def test_report_only_reads_as_before_and_says_so_once(place, monkeypatch, caplog):
    """Today's mode: nothing refused; each place it would refuse logged once."""
    monkeypatch.setattr(mediaread, "ENFORCED", False)
    caplog.set_level(logging.WARNING)
    settings = Settings(data_dir=place / "data", media_dir=str(place / "media"))
    db = str(place / "data" / "stationplay.db")
    _fp, client = _plex_reporting(db)
    for _ in range(2):
        assert (await resolve_source(settings, Library(client), _ep(), MediaAccess())).source == db
    said = [r.getMessage() for r in caplog.records if r.name == "app.mediaread"]
    assert said == [
        f"Would not read {db}: it isn't in the media folder, a mapped folder or one of Plex's library folders"
    ]


def test_tapiocas_own_temp_folders_are_named_as_the_check_knows():
    """Every folder tapiOca makes in the temp folder starts with OWN_TEMP_PREFIX
    (or is made in its data folder), so a link to one is refused."""
    made = [
        (source.name, call)
        for source in APP.glob("*.py")
        for call in re.findall(r"mkdtemp\(([^)]*)\)", source.read_text())
    ]
    assert made
    for name, call in made:
        assert (
            f'prefix="{mediaread.OWN_TEMP_PREFIX}' in call
            or 'prefix=f"' + mediaread.OWN_TEMP_PREFIX in call
            or "dir=" in call
        ), (name, call)

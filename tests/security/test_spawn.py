"""Every program tapiOca starts goes through one function, app/spawn.py's start (MED-FFMPEG-01, the security suite's
slice 2): FFmpeg is started with no proxy in its environment, so no proxy ever sees what it reads (Plex's address,
its token in it, among them), and the census knows each place that starts one. Nor is anything loaded into it but
the image's own (MED-03)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys

import pytest

from app import spawn

from . import inventory

PROXIES = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")


def test_a_program_started_has_no_proxy_in_its_environment(monkeypatch):
    for name in PROXIES:
        monkeypatch.setenv(name, "http://proxy.example:3128")
    monkeypatch.setenv("TAPIOCA_KEPT", "yes")

    async def environment() -> dict[str, str]:
        proc = await spawn.start(
            sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))",
            stdout=asyncio.subprocess.PIPE,
        )  # fmt: skip
        out, _ = await proc.communicate()
        return json.loads(out)

    seen = asyncio.run(environment())
    assert not [name for name in seen if name in PROXIES]
    assert seen["TAPIOCA_KEPT"] == "yes" and seen["PATH"], "the rest of its environment kept"


def test_only_spawn_starts_a_program_itself():
    starting = {str(site) for site in inventory.spawn_sites() if site.call != "spawn.start"}
    assert starting == {
        "app/spawn.py:start asyncio.create_subprocess_exec",
        "app/cleanup.py:_idle_disk subprocess.run",
    }, starting


# Enforced, every input FFmpeg is handed carries whitelists of its own (MED-FFMPEG-01, its check at run time, beside
# the census): a Media read's (mediainput.read), an upload's (UPLOADED_*), tapiOca's own files' (mediainput.own) and
# its own stream's pipe; a lavfi graph is made inside FFmpeg. Anything else isn't started.
def _started(monkeypatch, args: list[str]) -> list[list[str]]:
    seen: list[list[str]] = []

    async def fake(*a, **_k):
        seen.append(list(a))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake)
    asyncio.run(spawn.start(*args))
    return seen


def test_enforced_an_input_without_its_whitelists_isnt_started(monkeypatch):
    from app import ffmpeg as ff
    from app import mediainput

    monkeypatch.setattr(mediainput, "ENFORCED", True)
    fine = [
        ["ffmpeg", *mediainput.read("/media/a.mkv"), "-f", "null", "-"],
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=black", "-f", "null", "-"],
        ["ffmpeg", *ff.UPLOADED_VIDEO, "-i", "/data/upload.mp4", "-f", "null", "-"],
        ["ffmpeg", *mediainput.own("/app/assets/bumper/landing.m4a"), "-f", "null", "-"],
        [
            "ffmpeg",
            "-f",
            "mpegts",
            "-protocol_whitelist",
            "pipe",
            "-i",
            "pipe:0",
            "-f",
            "hls",
            "out.m3u8",
        ],
        [
            "ffmpeg",
            "-ss",
            "3",
            *mediainput.read("/media/a.mkv"),
            *mediainput.read("/media/a.mkv"),
            "-f",
            "null",
            "-",
        ],
    ]
    for args in fine:
        assert _started(monkeypatch, args) == [args], args
    for bare in (
        ["ffmpeg", "-i", "/media/a.mkv", "-f", "null", "-"],
        ["ffmpeg", *mediainput.read("/media/a.mkv"), "-i", "/media/b.mkv", "-f", "null", "-"],
        ["ffmpeg", "-f", "mpegts", "-i", "pipe:0", "-f", "null", "-"],
    ):
        with pytest.raises(ValueError, match="without its whitelists"):
            _started(monkeypatch, bare)


def test_report_only_inputs_arent_checked(monkeypatch):
    from app import mediainput

    monkeypatch.setattr(mediainput, "ENFORCED", False)
    bare = ["ffmpeg", "-i", "/media/a.mkv", "-f", "null", "-"]
    assert _started(monkeypatch, bare) == [bare]


# MED-03: no outside codec or plugin. tapiOca never loads a plugin or library of its own choosing into a program it
# starts, nor has it read a filter graph or an option from a file; and in the image, nothing the app's user can
# write is among what FFmpeg runs or loads, nor on the path it's found by.
_LOADING = (
    "load_plugin",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_AUDIT",
    "filter_script",
    "filter_complex_script",
)


def test_no_program_is_given_a_plugin_a_library_or_its_filters_from_a_file():
    found = [
        f"{path.relative_to(inventory.APP)}: {word}"
        for path in sorted(inventory.APP.rglob("*.py"))
        for word in _LOADING
        if word in path.read_text(encoding="utf-8")
    ]
    assert not found
    # (FFmpeg's other way to read an option from a file: "-/vf file".)
    assert not [p for p in inventory.APP.rglob("*.py") if '"-/' in p.read_text(encoding="utf-8")]


def _loaded(program: str) -> list[str]:
    said = subprocess.run(["ldd", program], capture_output=True, text=True, check=True).stdout
    return [part for line in said.splitlines() for part in line.split() if part.startswith("/")]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no FFmpeg here")
@pytest.mark.skipif(
    os.geteuid() == 0, reason="root can write anything (the image's tests run as its user, 1000)"
)
def test_what_ffmpeg_runs_and_loads_cant_be_changed_by_tapiocas_user():
    programs = [shutil.which("ffmpeg"), shutil.which("ffprobe")]
    files = [p for p in programs if p] + [lib for p in programs if p for lib in _loaded(p)]
    places = {os.path.dirname(f) for f in files} | {
        d for d in os.environ.get("PATH", "").split(":") if d
    }
    writable = sorted(p for p in {*files, *places} if os.access(p, os.W_OK))
    assert len(files) > 2 and not writable

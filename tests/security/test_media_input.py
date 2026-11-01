"""A Media read opens only a video container, by its own name only (MED-FFMPEG-01, the security suite's slice 2:
the apps repository's docs/threat-models/security-suite-2.md). An ffconcat list named movie.mkv plays a file
beside it, another title's, a way around a person's limits; an HLS or DASH list, a picture reader or a device
input opens what it names. So a Media read takes an allow-list of video containers, failing closed, its
protocols by its address, mov's references off (by default, pinned), its memory bounded and, over http, no
redirect. Report-only until the release's soak: a read whose container isn't on the list is logged, once, and
read all the same."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import ffmpeg as ff
from app import folderscan, jobs, mediainput
from app.config import Settings

from ..helpers import PAGE

SMALL = Settings(plex_url="", plex_token="", video_width=640, video_height=360)
needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="no FFmpeg here"
)


def _video(path: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x90:r=10:d=1",
            "-c:v",
            "mpeg4",
            str(path),
        ],
        check=True,
    )
    return path


def _with_sound(path: Path, seconds: int) -> Path:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=160x90:r=10:d={seconds}", "-f", "lavfi",
         "-i", f"sine=f=440:d={seconds}", "-c:v", "mpeg4", "-c:a", "aac", str(path)],
        check=True,
    )  # fmt: skip
    return path


def _concat(folder: Path, beside: Path) -> Path:
    """An ffconcat list, named as a movie, naming the file beside it."""
    listed = folder / "movie.mkv"
    listed.write_text(f"ffconcat version 1.0\nfile '{beside.name}'\n")
    return listed


@pytest.mark.parametrize("name", sorted(mediainput.NEVER))
def test_a_demuxer_that_opens_what_it_names_is_never_allowed(name):
    assert name not in mediainput.ALLOWED
    assert not mediainput.allowed(name)


def test_every_video_container_on_the_list_is_read():
    for name in (
        "matroska,webm",
        "mov,mp4,m4a,3gp,3g2,mj2",
        "avi",
        "mpegts",
        "mpeg",
        "asf",
        "flv",
        "ogg",
        "m4v",
    ):
        assert mediainput.allowed(name), name


def test_a_container_partly_off_the_list_isnt_read():
    assert not mediainput.allowed("matroska,concat")
    assert not mediainput.allowed("")


@pytest.mark.parametrize(
    "source, protocols",
    [
        ("/media/Movies/A/a.mkv", "file"),
        ("http://192.168.1.20:32400/library/parts/1/file.mkv?X-Plex-Token=t", "http,tcp"),
        ("https://plex.example.net:32400/library/parts/1/file.mkv?X-Plex-Token=t", "https,tls,tcp"),
    ],
)
def test_a_media_reads_options(source, protocols):
    options = mediainput.options(source)
    said = dict(zip(options[::2], options[1::2], strict=True))
    assert said["-format_whitelist"] == ",".join(mediainput.ALLOWED)
    assert said["-protocol_whitelist"] == protocols
    assert "-enable_drefs" not in said, "mov's alone: see test_movs_references_are_off_by_default"
    assert said["-max_pixels"] == str(mediainput.MAX_PIXELS)
    assert said["-max_alloc"] == str(mediainput.MAX_ALLOC)
    if source.startswith("http"):
        assert said["-max_redirects"] == "0"
    else:
        assert "-max_redirects" not in said


@needs_ffmpeg
def test_with_its_options_an_ffconcat_list_named_as_a_movie_isnt_read(tmp_path):
    other = _video(tmp_path / "other.mp4")
    listed = _concat(tmp_path, other)
    opened = subprocess.run(["ffprobe", "-v", "error", str(listed)], capture_output=True, text=True)
    assert opened.returncode == 0, "today's read opens the file it names"
    refused = subprocess.run(
        ["ffprobe", "-v", "error", *mediainput.options(str(listed)), str(listed)],
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert mediainput.refused(refused.stderr), refused.stderr


@needs_ffmpeg
def test_with_its_options_a_real_video_is_read(tmp_path):
    for name in ("film.mkv", "film.mp4", "film.avi", "film.ts"):
        video = _video(tmp_path / name)
        read = subprocess.run(
            ["ffprobe", "-v", "error", *mediainput.options(str(video)), str(video)],
            capture_output=True,
            text=True,
        )
        assert read.returncode == 0, (name, read.stderr)


@needs_ffmpeg
def test_with_its_options_ffmpeg_plays_a_real_video(tmp_path):
    # (FFmpeg itself, not only ffprobe, refuses a demuxer's option the file's demuxer doesn't have.)
    for name in ("film.mkv", "film.mp4", "film.avi", "film.ts"):
        video = _video(tmp_path / name)
        played = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                *mediainput.options(str(video)),
                "-i",
                str(video),
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        assert played.returncode == 0, (name, played.stderr)


@needs_ffmpeg
def test_movs_references_are_off_by_default():
    # (Pinned here rather than given: the option is mov's alone, and FFmpeg refuses it for any other file.)
    said = subprocess.run(
        ["ffmpeg", "-hide_banner", "-h", "demuxer=mov"], capture_output=True, text=True
    ).stdout
    line = next(line for line in said.splitlines() if line.strip().startswith("-enable_drefs"))
    assert "(default false)" in line, line


@needs_ffmpeg
def test_report_only_a_probe_of_an_ffconcat_list_is_logged_once_and_read(
    tmp_path, caplog, monkeypatch
):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    listed = _concat(tmp_path, _video(tmp_path / "other.mp4"))
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        first = asyncio.run(ff.probe(SMALL, str(listed)))
        asyncio.run(ff.probe(SMALL, str(listed)))
    assert first.ok, "report-only: read as before"
    said = [r.getMessage() for r in caplog.records if "concat" in r.getMessage()]
    assert len(said) == 1, said
    assert listed.name in said[0], "the soak's report names the file"


def test_a_plex_address_is_logged_without_its_token(caplog, monkeypatch):
    monkeypatch.setattr(mediainput, "_said", set())
    source = "http://192.168.1.20:32400/library/parts/1/file.mkv?X-Plex-Token=secret"
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        mediainput.note(ff.redact(source), "concat")
    assert "concat" in caplog.text
    assert "secret" not in caplog.text


@needs_ffmpeg
def test_report_only_a_probe_of_a_real_video_says_nothing(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        assert asyncio.run(ff.probe(SMALL, str(_video(tmp_path / "film.mkv")))).ok
    assert not [r for r in caplog.records if r.name == "app.mediainput"]


@needs_ffmpeg
def test_an_uploads_probe_keeps_its_own_options(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        asyncio.run(
            ff.probe(SMALL, str(_video(tmp_path / "bumper.mp4")), options=ff.UPLOADED_VIDEO)
        )
    assert not [r for r in caplog.records if r.name == "app.mediainput"]


@needs_ffmpeg
def test_report_only_a_folder_scan_of_an_ffconcat_list_is_logged_once_and_read(
    tmp_path, caplog, monkeypatch
):
    # (A folder's Media is read by the folder scan's own ffprobe, not by probe.)
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    monkeypatch.setattr(mediainput, "_said", set())
    listed = _concat(tmp_path, _video(tmp_path / "other.mp4"))
    with caplog.at_level(logging.WARNING, logger="app.mediainput"):
        first = asyncio.run(folderscan.read_file("ffprobe", str(listed)))
        asyncio.run(folderscan.read_file("ffprobe", str(listed)))
    assert first["ok"], "report-only: read as before"
    said = [r.getMessage() for r in caplog.records if "concat" in r.getMessage()]
    assert len(said) == 1, said


# Every FFmpeg input in the server, by what it reads (the census). A Media read takes mediainput.read, which gives
# it its options once enforced; anything else is tapiOca's own (a lavfi graph, its own stream on a pipe, a file it
# made or ships) or an upload under its own options. A new input fails here until it's one of them.
APP = Path(__file__).resolve().parents[2] / "app"
OWN = {
    ("bumpers.py", "str(picture)"): "the Intro Bumper's picture, which tapiOca made",
    ("intro.py", "str(sound.path)"): "a sound tapiOca ships (assets/bumper)",
    ("intro.py", "str(LANDING)"): "a sound tapiOca ships (assets/bumper)",
    ("intro.py", "str(jingle_)"): "a jingle tapiOca ships (assets/ident)",
    ("hls.py", "'pipe:0'"): "tapiOca's own stream, on its pipe",
}
UPLOADS = {"ff.UPLOADED_VIDEO", "ff.UPLOADED_PICTURE", "UPLOADED_PICTURE", "UPLOADED_VIDEO"}


def _inputs():
    import ast

    for file in sorted(APP.rglob("*.py")):
        if file.name == "mediainput.py":
            continue
        for node in ast.walk(ast.parse(file.read_text())):
            if not isinstance(node, (ast.List, ast.Tuple)):
                continue
            items = node.elts
            for n, item in enumerate(items):
                if isinstance(item, ast.Constant) and item.value == "-i":
                    before = [ast.unparse(e) for e in items[max(0, n - 2) : n]]
                    read = ast.unparse(items[n + 1]) if n + 1 < len(items) else ""
                    yield file.name, item.lineno, before, read


def test_every_ffmpeg_input_is_media_through_read_or_tapiocas_own():
    unknown = []
    for name, line, before, read in _inputs():
        lavfi = before[-2:] == ["'-f'", "'lavfi'"]
        upload = bool(before) and before[-1].lstrip("*") in UPLOADS
        if not (lavfi or upload or (name, read) in OWN):
            unknown.append(f"{name}:{line}: -i {read}")
    assert not unknown, "a Media read takes mediainput.read(source):\n" + "\n".join(unknown)


def test_the_census_sees_every_kind_of_input():
    found = list(_inputs())
    assert any(before[-2:] == ["'-f'", "'lavfi'"] for _, _, before, _ in found)
    assert any(before and before[-1].lstrip("*") in UPLOADS for _, _, before, _ in found)
    assert {(name, read) for name, _, _, read in found} >= set(OWN), (
        "an OWN entry no longer in the code"
    )


def test_a_media_input_takes_its_options_only_once_enforced(monkeypatch):
    source = "/media/Movies/A/a.mkv"
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    assert mediainput.read(source) == ["-i", source]
    monkeypatch.setattr(mediainput, "ENFORCED", True)
    assert mediainput.read(source) == [*mediainput.options(source), "-i", source]


def _program(source: str) -> list[str]:
    return ff.program_command(SMALL, source, 0.0, 60.0, 0.0, 0.0, 0, "Night Owl")


def test_a_programs_inputs_are_media_reads(monkeypatch):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    today = _program("/media/Movies/A/a.mkv")
    assert today.count("-format_whitelist") == 0, "report-only: as before"
    monkeypatch.setattr(mediainput, "ENFORCED", True)
    local = _program("/media/Movies/A/a.mkv")
    remote = _program("http://192.168.1.20:32400/library/parts/1/file.mkv?X-Plex-Token=t")
    # (A local file is read twice, for its picture and its sound: see program_command.)
    assert local.count("-i") == 2 and local.count("-format_whitelist") == 2
    assert remote.count("-i") == 1 and remote.count("-format_whitelist") == 1
    for args in (local, remote):
        for at in (n for n, a in enumerate(args) if a == "-i"):
            assert "-protocol_whitelist" in args[max(0, at - 12) : at], (
                "each input's own options, just before it"
            )
    assert remote[remote.index("-max_redirects") + 1] == "0"


@needs_ffmpeg
def test_enforced_a_station_plays_a_real_video_under_the_options(tmp_path, monkeypatch):
    # (A Station's whole command, run for a second: its paced reading for the picture, and a local file's second
    # reading for its sound, each under the options.)
    monkeypatch.setattr(mediainput, "ENFORCED", True)
    video = tmp_path / "film.mkv"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=10:d=2", "-f", "lavfi", "-i",
         "sine=f=440:d=2", "-c:v", "mpeg4", "-c:a", "aac", str(video)],
        check=True,
    )  # fmt: skip
    args = ff.program_command(SMALL, str(video), 0.0, 1.0, 0.0, 5.0, 0, "Night Owl")
    assert args.count("-format_whitelist") == 2
    played = subprocess.run(args, capture_output=True, timeout=60)
    assert played.returncode == 0, played.stderr.decode(errors="replace")[-600:]
    assert len(played.stdout) > 1000, "a stream came out"


# The check at start (failing closed once enforced): this FFmpeg has every vetted demuxer, none that shares a name
# with one (FFmpeg's whitelist lets in a demuxer sharing any part of a name), and an http that refuses a redirect.
DEMUXERS = """File formats:
 D. = Demuxing supported
 .E = Muxing supported
 --
 D  concat          Virtual concatenation script
""" + "".join(f" D  {name:<15} a vetted one\n" for name in mediainput.ALLOWED)
HTTP = "http AVOptions:\n  -max_redirects     <int>        .D.......... Maximum number of redirects"


def test_an_ffmpeg_with_every_vetted_demuxer_and_no_redirects_passes():
    assert mediainput.judge(DEMUXERS, HTTP) is None


def test_an_ffmpeg_missing_a_vetted_demuxer_fails():
    said = mediainput.judge(DEMUXERS.replace(" D  wtv ", " D  wtx "), HTTP)
    assert said is not None and "wtv" in said


def test_an_ffmpeg_with_a_lookalike_demuxer_fails():
    said = mediainput.judge(DEMUXERS + " D  mp4,playlist     a new one\n", HTTP)
    assert said is not None and "mp4,playlist" in said


def test_an_ffmpeg_whose_http_follows_redirects_fails():
    said = mediainput.judge(DEMUXERS, "http AVOptions:\n  -seekable  <boolean>")
    assert said is not None and "redirect" in said


def test_an_ffmpeg_that_cant_list_its_demuxers_fails():
    assert mediainput.judge("", HTTP) is not None


@needs_ffmpeg
def test_this_ffmpeg_has_every_vetted_demuxer_and_no_lookalike():
    said = asyncio.run(mediainput.problem("ffmpeg"))
    # (FFmpeg 6.1, here, has no max_redirects; the image's 7.1.5 has: its own run says None.)
    assert said is None or said == mediainput.NO_REDIRECTS, said


@needs_ffmpeg
def test_report_only_the_check_at_start_is_logged(caplog, monkeypatch):
    monkeypatch.setattr(mediainput, "ENFORCED", False)
    with caplog.at_level(logging.INFO, logger="app.mediainput"):
        asyncio.run(mediainput.check_at_start("/nonexistent/ffmpeg"))
    said = [r for r in caplog.records if r.name == "app.mediainput"]
    assert said and said[-1].levelno == logging.WARNING and "Media" in said[-1].getMessage()
    assert mediainput.FFMPEG_PROBLEM is not None


# Enforced, a read the allow-list refuses is "unsupported" with the one wording, never "broken": an automatic
# replacement removes a broken file, which can't be undone. Each carries what judged it (the allow-list's version and
# FFmpeg's), so it's judged again when either changes.
@needs_ffmpeg
def test_enforced_a_refused_probe_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(mediainput, "ENFORCED", True)
    listed = _concat(tmp_path, _video(tmp_path / "other.mp4"))
    probed = asyncio.run(ff.probe(SMALL, str(listed)))
    assert not probed.ok and probed.refused and probed.error == mediainput.REFUSED
    real = asyncio.run(ff.probe(SMALL, str(_video(tmp_path / "film.mkv"))))
    assert real.ok and not real.refused
    broken = tmp_path / "broken.mkv"
    broken.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)
    unreadable = asyncio.run(ff.probe(SMALL, str(broken)))
    assert not unreadable.ok and not unreadable.refused, "a file that's merely broken stays broken"


@needs_ffmpeg
def test_enforced_the_file_check_calls_a_refused_file_unsupported(tmp_path, monkeypatch):
    from app import scanner
    from app.db import Item
    from app.sources import ResolvedSource

    monkeypatch.setattr(mediainput, "ENFORCED", True)
    listed = _concat(tmp_path, _video(tmp_path / "other.mp4"))
    item = Item(0, 0, 60_000, "201", "episode", "Fog Season", file_path=str(listed))
    ctx = SimpleNamespace(settings=SMALL)
    verdict, _ = asyncio.run(
        scanner._quick_file(ctx, item, ResolvedSource(str(listed), str(listed), 9), None, "201")
    )
    assert (verdict.result, verdict.reason) == ("unsupported", mediainput.REFUSED)
    streamed = ResolvedSource("http://127.0.0.1:9/library/parts/1/file.mkv", str(listed), 9)
    monkeypatch.setattr(ff, "probe", _refused)
    verdict, _ = asyncio.run(scanner._quick_file(ctx, item, streamed, None, "201"))
    assert verdict.result == "unsupported", (
        "refused through Plex too: never skipped as Plex's failure"
    )


async def _refused(*_a, **_k):
    return ff.ProbeResult(ok=False, error=mediainput.REFUSED, refused=True)


def test_a_refusal_is_recorded_with_what_judged_it(tmp_path, monkeypatch):
    from app.broken import BrokenFiles
    from app.db import Item

    monkeypatch.setattr(mediainput, "FFMPEG_VERSION", "ffmpeg version 7.1.5")
    broken = BrokenFiles(tmp_path / "broken.json")
    item = Item(0, 0, 60_000, "201", "episode", "Fog Season", file_path="/media/Shows/A/movie.mkv")
    broken.record(item, mediainput.REFUSED, 5, problem="unsupported")
    broken.record(
        Item(0, 0, 60_000, "202", "episode", "Other", file_path="/x.mkv"), "can't open the file", 5
    )
    entries = {e["ratingKey"]: e for e in broken.entries()}
    assert (
        entries["201"]["judged"]
        == mediainput.judged()
        == f"{mediainput.ALLOW_VERSION}|ffmpeg version 7.1.5"
    )
    assert "judged" not in entries["202"], "only a refusal carries it"


def test_the_allow_lists_version_moves_with_it():
    # (A change to ALLOWED without a new ALLOW_VERSION would leave files refused under the old list unjudged: the
    # digest below changes with the list, and ALLOW_VERSION with it.)
    import hashlib

    digest = hashlib.sha256(",".join(mediainput.ALLOWED).encode()).hexdigest()[:12]
    assert (mediainput.ALLOW_VERSION, digest) == (1, "91fc55ddbe4e")


@needs_ffmpeg
async def test_enforced_a_station_takes_a_refused_file_off_the_air_as_unsupported(
    tmp_path, monkeypatch
):
    from ..fakeplex import FakePlex
    from ..test_e2e import record, start_server

    monkeypatch.setattr(mediainput, "ENFORCED", True)
    monkeypatch.setattr(jobs, "CHECK_NEW_STATIONS", False)
    d = tmp_path / "media"
    d.mkdir()
    listed = _concat(d, _video(d / "other.mp4"))
    fine = _with_sound(d / "fine.mkv", 6)
    plex = FakePlex()
    plex.add_show("100", "Show")
    plex.add_episode("201", "100", 1, 1, "Listed", str(listed), 5000)
    plex.add_episode("202", "100", 1, 2, "Fine", str(fine), 6000)
    base, app, _settings, srv, task = await start_server(tmp_path, plex)
    try:
        async with httpx.AsyncClient(headers=PAGE, base_url=base, timeout=30) as client:
            made = await client.post(
                "/api/channels",
                json={
                    "number": 5, "orderMode": "rotate", "introSeconds": 0, "upNextSeconds": 0,
                    "watermark": "off", "sources": [{"type": "show", "ratingKey": "100"}],
                },
            )  # fmt: skip
            assert made.status_code == 201, made.text
            data = await record(f"{base}/stream/5", 6)
    finally:
        srv.should_exit = True
        await task
    assert data, "the Station played the file that opens"
    entries = app.state.ctx.broken.entries()
    assert [(e["ratingKey"], e["problem"], e["reason"]) for e in entries] == [
        ("201", "unsupported", mediainput.REFUSED)
    ]


# A fixture for each vetted container: made here, then read under a Media read's options by ffprobe and by FFmpeg,
# its demuxer the one vetted. (On a build without a fixture's encoder, that one is skipped, and says so.)
FIXTURES = {
    "matroska,webm": [
        ("film.mkv", ["-c:v", "mpeg4"]),
        ("film.webm", ["-c:v", "libvpx", "-b:v", "200k"]),
    ],
    "mov,mp4,m4a,3gp,3g2,mj2": [
        ("film.mp4", ["-c:v", "mpeg4"]),
        ("film.mov", ["-c:v", "mpeg4"]),
        ("film.3gp", ["-c:v", "mpeg4", "-s", "176x144"]),
    ],
    "avi": [("film.avi", ["-c:v", "mpeg4"])],
    "mpegts": [("film.ts", ["-c:v", "mpeg2video"])],
    "mpeg": [
        ("film.vob", ["-c:v", "mpeg2video", "-f", "vob"]),
        ("film.mpg", ["-c:v", "mpeg1video", "-r", "25"]),
    ],
    "mpegvideo": [("film.m2v", ["-c:v", "mpeg2video", "-f", "mpeg2video"])],
    "asf": [("film.wmv", ["-c:v", "wmv2"])],
    "wtv": [("film.wtv", ["-c:v", "mpeg2video", "-f", "wtv"])],
    "flv": [("film.flv", ["-c:v", "flv"])],
    "ogg": [("film.ogv", ["-c:v", "libtheora"])],
    "rm": [("film.rm", ["-c:v", "rv10"])],
    "nut": [("film.nut", ["-c:v", "mpeg4"])],
    "mxf": [
        (
            "film.mxf",
            [
                "-c:v",
                "mpeg2video",
                "-pix_fmt",
                "yuv422p",
                "-b:v",
                "5M",
                "-s",
                "720x576",
                "-r",
                "25",
            ],
        )
    ],
    "dv": [
        ("film.dv", ["-c:v", "dvvideo", "-pix_fmt", "yuv411p", "-s", "720x480", "-r", "30000/1001"])
    ],
    "m4v": [("film.m4v", ["-c:v", "mpeg4", "-f", "m4v"])],
    "h264": [("film.264", ["-c:v", "libx264", "-f", "h264"])],
    "hevc": [("film.265", ["-c:v", "libx265", "-f", "hevc", "-x265-params", "log-level=error"])],
}
# (FFmpeg has no VC-1 encoder to make one: a raw VC-1 stream is vetted by its name alone.)
NO_FIXTURE = {"vc1"}


def test_every_vetted_container_has_a_fixture():
    assert set(FIXTURES) | NO_FIXTURE == set(mediainput.ALLOWED)
    assert not set(FIXTURES) & NO_FIXTURE


@needs_ffmpeg
@pytest.mark.parametrize(
    "name, file, codec",
    [(name, file, codec) for name, made in FIXTURES.items() for file, codec in made],
)
def test_a_real_file_in_each_vetted_container_is_read(tmp_path, name, file, codec):
    path = tmp_path / file
    made = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x96:r=25:d=1",
            *codec,
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if made.returncode != 0:
        pytest.skip(f"this FFmpeg can't make {file}: {made.stderr.strip()[-120:]}")
    probed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "csv=p=0",
         *mediainput.options(str(path)), str(path)],
        capture_output=True,
        text=True,
    )  # fmt: skip
    assert probed.returncode == 0, probed.stderr
    assert probed.stdout.strip().strip('"') == name
    played = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            *mediainput.options(str(path)),
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    assert played.returncode == 0, played.stderr

"""What FFmpeg may open for a Media read (the security suite's MED-FFMPEG-01, the apps
repository's docs/threat-models/security-suite-2.md).

A Media file's name says nothing of what's in it, and FFmpeg reads hundreds of
formats, some of which open other files or addresses by themselves: an ffconcat
list named movie.mkv plays the file beside it, an HLS list the addresses it
names. So a Media read takes only a vetted family of video containers (an
allow-list, failing closed: a new demuxer is never let in by default), only
the protocols its address needs, bounded memory and, over http, no redirect.
(mov's references are off by default, and a test pins that: the option is
mov's alone, and FFmpeg refuses it for any other file.)

Report-only until the release's soak shows no real video refused: a read is
given none of these options, and one whose container isn't on the list is
logged, once for each file, and read all the same.
"""

from __future__ import annotations

import asyncio
import logging
import re

from . import spawn

log = logging.getLogger(__name__)

# (Off until the soak's report shows no real video refused: then on, in the same release.)
ENFORCED = False

# The video containers a Media read may be, by the names FFmpeg gives its demuxers (mediaread's
# VIDEO_EXTENSIONS are their files' names). Widened only by what the soak shows, each with a fixture.
ALLOWED = (
    "matroska,webm",
    "mov,mp4,m4a,3gp,3g2,mj2",
    "avi",
    "mpegts",
    "mpeg",  # (program streams: .vob, .evo, .m2p, .mpg)
    "mpegvideo",
    "asf",
    "wtv",
    "flv",
    "ogg",
    "rm",
    "nut",
    "mxf",
    "dv",
    "m4v",
    "h264",  # (the raw video streams a recording can be)
    "hevc",
    "vc1",
)

# Never allowed, whatever the soak saw: what opens other files or addresses by itself,
# the picture readers, the device inputs and the outside libraries' wrappers.
NEVER = frozenset({
    "concat", "hls", "dash", "webm_dash_manifest", "imf", "vobsub", "sap", "sdp", "rtp", "rtsp",
    "dvdvideo", "ffmetadata",
    "image2", "image2pipe", "alias_pix", "brender_pix", "png_pipe", "jpeg_pipe", "webp_pipe",
    "alsa", "fbdev", "iec61883", "jack", "kmsgrab", "lavfi", "libcdio", "libdc1394", "openal",
    "oss", "pulse", "video4linux2,v4l2", "x11grab",
    "libgme", "libopenmpt", "vapoursynth", "avisynth",
})  # fmt: skip

# The one wording, everywhere, for a file a Media read refuses: "unsupported", never "broken" (an automatic
# replacement removes a broken file). Judged again when ALLOW_VERSION or FFmpeg's version moves (judged).
REFUSED = "This file isn't a video tapiOca can play"
# (One more each time ALLOWED changes: test_the_allow_lists_version_moves_with_it.)
ALLOW_VERSION = 1

MAX_PIXELS = 35_389_440  # (8K, 7680 x 4320, with room)
MAX_ALLOC = 1 << 30  # (one allocation: an 8K frame is about 100 MB)


def allowed(format_name: str) -> bool:
    """Whether the demuxer that read a file, as ffprobe names it, is a vetted one."""
    return format_name in ALLOWED


def options(source: str) -> list[str]:
    """FFmpeg's options for reading `source` as Media, before its input."""
    said = [
        "-format_whitelist", ",".join(ALLOWED),
        "-protocol_whitelist", _protocols(source),
        "-max_pixels", str(MAX_PIXELS),
        "-max_alloc", str(MAX_ALLOC),
    ]  # fmt: skip
    if source.startswith(("http://", "https://")):
        said += ["-max_redirects", "0"]
    return said


# tapiOca's own files FFmpeg reads (an Intro Bumper's picture it made, the sounds it ships): mp4 and m4a.
OWN_FORMATS = "mov,mp4,m4a,3gp,3g2,mj2"


def own(path: str) -> list[str]:
    """FFmpeg's input for one of tapiOca's own files: its whitelists, then `-i`."""
    return ["-format_whitelist", OWN_FORMATS, "-protocol_whitelist", "file", "-i", path]


# A subtitle file beside a program, read out into tapiOca's own .ass before it's drawn (subtitles.SIDECAR_SUFFIXES).
SUBTITLE_FORMATS = "srt,ass,webvtt"


def subtitle(path: str) -> list[str]:
    """FFmpeg's input for a subtitle file beside a program: its options once enforced, then `-i`."""
    whitelists = ["-format_whitelist", SUBTITLE_FORMATS, "-protocol_whitelist", "file"]
    return [*(whitelists if ENFORCED else []), "-i", path]


def read(source: str) -> list[str]:
    """FFmpeg's input for reading `source` as Media: its options once enforced, then `-i`."""
    return [*(options(source) if ENFORCED else []), "-i", source]


def _protocols(source: str) -> str:
    if source.startswith("https://"):
        return "https,tls,tcp"
    if source.startswith("http://"):
        return "http,tcp"
    return "file"


def refused(stderr: str) -> bool:
    """Whether FFmpeg's error says it refused the read for its container or protocol."""
    return "not on whitelist" in stderr


# What's wrong with the FFmpeg tapiOca runs, for a Media read's allow-list (check_at_start); until it's checked, that.
FFMPEG_PROBLEM: str | None = "FFmpeg hasn't been checked yet"
# Its version, as `ffmpeg -version`'s first line says it (check_at_start).
FFMPEG_VERSION = ""
NO_REDIRECTS = "its http can't be kept from following a redirect (it has no max_redirects)"
_CHECK_S = 20.0


# After its rule, each of `ffmpeg -demuxers`' rows: D, E (muxing) and, from FFmpeg 7.1, d (a device), then the name.
_RULE = re.compile(r"^ -+$", re.MULTILINE)
_ROW = re.compile(r" D[E ][d ]? (\S+)")


def _demuxers(listed: str) -> set[str]:
    """The demuxers' names `ffmpeg -demuxers` lists, as 6.1 lays them out or as 7.1 does."""
    _header, *rows = _RULE.split(listed, maxsplit=1)
    lines = rows[0].splitlines() if rows else []
    return {row[1] for line in lines if (row := _ROW.match(line))}


def judge(demuxers: str, http: str) -> str | None:
    """What's wrong with an FFmpeg for the allow-list, from `ffmpeg -demuxers` and `-h protocol=http`: a vetted
    demuxer missing, an unvetted one sharing part of a vetted one's name (FFmpeg's whitelist would let it in), or an
    http that follows redirects. None: nothing."""
    names = _demuxers(demuxers)
    if not names:
        return "its demuxers couldn't be listed"
    missing = [name for name in ALLOWED if name not in names]
    if missing:
        return f"it has no {', '.join(missing)}"
    parts = {part for name in ALLOWED for part in name.split(",")}
    alike = sorted(name for name in names - set(ALLOWED) if parts & set(name.split(",")))
    if alike:
        return f"its {', '.join(alike)} share a name with a vetted container"
    return None if "max_redirects" in http else NO_REDIRECTS


async def _printed(ffmpeg: str, *args: str) -> str:
    """What `ffmpeg args` prints, or "" if it can't be run in time."""
    try:
        proc = await spawn.start(
            ffmpeg, "-hide_banner", *args,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
    except OSError:
        return ""
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), _CHECK_S)
    except TimeoutError:
        return ""
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    return out.decode(errors="replace")


async def problem(ffmpeg: str) -> str | None:
    """What's wrong with the FFmpeg at `ffmpeg` for the allow-list (judge's), None for nothing."""
    return judge(await _printed(ffmpeg, "-demuxers"), await _printed(ffmpeg, "-h", "protocol=http"))


def closed() -> str | None:
    """Why no Media read may be made now, failing closed: enforced, with an FFmpeg that can't be checked. None:
    reads go on."""
    if ENFORCED and FFMPEG_PROBLEM:
        return f"tapiOca can't check its ffmpeg ({FFMPEG_PROBLEM})"
    return None


def judged() -> str:
    """What judges a Media read now: the allow-list's version and FFmpeg's, kept with each refusal."""
    return f"{ALLOW_VERSION}|{FFMPEG_VERSION}"


async def check_at_start(ffmpeg: str) -> None:
    """Checks the FFmpeg tapiOca runs, once as it starts, and says so. Report-only: nothing is refused."""
    global FFMPEG_PROBLEM, FFMPEG_VERSION
    FFMPEG_VERSION = (await _printed(ffmpeg, "-version")).partition("\n")[0].strip()
    FFMPEG_PROBLEM = await problem(ffmpeg)
    if FFMPEG_PROBLEM:
        log.warning(
            "Once enforced, every Media read would be refused: this FFmpeg can't be checked (%s)",
            FFMPEG_PROBLEM,
        )
    else:
        log.info("FFmpeg checked: a Media read opens only a vetted video container")


_said: set[str] = set()


def note(shown: str, format_name: str) -> None:
    """Report-only: logs, once for each file, a read whose container isn't vetted.
    `shown`: its source, redacted."""
    if allowed(format_name) or shown in _said:
        return
    if len(_said) > 10_000:
        _said.clear()
    _said.add(shown)
    log.warning(
        "Would not read %s: its container (%s) isn't one a Media file may be",
        shown,
        format_name or "unknown",
    )

"""Pictures for tapiOca's apps, made once and kept on disk (the plan's
"Pictures that load fast").

The memory cache (ondemand.PictureCache) stays in front. Behind it, every
picture made for an app is kept in ``data/cache/pictures``, so a restart or
an update never fetches and resizes every picture again:

- **Names:** each file is named by a hash of the source, the title's key,
  the kind, the width, the format and the encoder settings' version, never a
  file name or a title. A change of quality settings (ENCODER) makes new
  files; the old ones age out.
- **Size:** capped (2 GB to start, Settings.picture_cache_gb), the least
  recently viewed dropped first. Nothing is written while the disk has less
  than FREE_LEAST free, and a full disk or a failed write never fails a
  request: it's answered as if there were no disk cache.
- **Its own format:** STAMP, in the folder's ``FORMAT`` file. Another stamp
  (an older or newer tapiOca) empties the folder; nothing is ever read from a
  cache this version doesn't understand. It isn't in backups (backups.py
  copies the database and logos only).
- **Changed art never sticks:** each kept picture records the version of
  the picture it was made from (Plex's thumb or art timestamp, or a folder
  picture's modification time and size). A kept one whose version is no
  longer the one known now is made again; no request is made just to check.

Making: many requests for the same picture make it once (Maker.once), and a
screen's request goes ahead of anything drawn ahead (Maker.ahead_turn).
WebP is made by FFmpeg, in one step from the source picture, at a quality
measured to keep every color plane's SSIM at QUALITY_FLOOR or above against
a lossless resize (tests/test_pictures.py keeps it there); JPEG as before.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import shutil
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from . import ffmpeg as ff

log = logging.getLogger(__name__)

T = TypeVar("T")

# The widths pictures are made at (the next one up from what's asked for):
# posters, and wide pictures (backdrops and episodes' stills). 720 stays,
# so a full-width backdrop on a common phone (360 dp at 2x) doesn't jump to
# 1280; 3840 waits until a device draws at 4K. docs/internal-api.md lists
# them, and the apps keep a copy (shared/cases/artwork.json).
POSTER_WIDTHS = (160, 240, 320, 480, 720, 960, 1440)
WIDE_WIDTHS = (320, 640, 720, 1280, 1920)
KINDS = ("poster", "backdrop", "thumb")
# Station logos, when an app asks for a width: PNG always (they need their
# transparency), never made larger. Their addresses carry a version.
LOGO_WIDTHS = (80, 120, 160, 240, 320, 480)
FORMATS = ("jpeg", "webp")
TYPES = {"jpeg": "image/jpeg", "webp": "image/webp"}

# The encoder's settings: the smallest that keep every color plane at
# QUALITY_FLOOR at every width (measured on posters and backdrops with film
# grain, gradients and sharp edges: tests/test_pictures.py). libwebp below 85
# let some sizes' planes fall well under it (0.92 at 240 wide, 80). ENCODER
# names them: changing any of these changes it, so pictures are made again.
QUALITY_FLOOR = 0.97
JPEG_Q = 5  # (FFmpeg's -q:v: lower is better; 2 to 31)
WEBP_Q = 85  # (libwebp's -quality: higher is better; 0 to 100)
WEBP_EFFORT = 4  # (libwebp's -compression_level: 0 fastest, 6 smallest)
ENCODER = "1"

STAMP = "tapioca-pictures 1"  # the cache's own format
FOLDER = Path("cache") / "pictures"  # in the data folder
FREE_LEAST = 2 << 30  # nothing written with less free than this
USED_EVERY_S = 600.0  # a kept picture's last use is written at most this often
MAKE_S = 30.0  # the longest one picture takes to make
SOURCE_MOST = 20 << 20  # a source picture's bytes, at most


def wide(kind: str) -> bool:
    return kind != "poster"


def widths(kind: str) -> tuple[int, ...]:
    return WIDE_WIDTHS if wide(kind) else POSTER_WIDTHS


def width_for(kind: str, asked: int) -> int:
    """The width a picture of `kind` is made at: the next one up from what's
    asked for (the largest, for anything larger)."""
    sizes = widths(kind)
    return next((w for w in sizes if w >= asked), sizes[-1])


def logo_width(asked: int) -> int:
    return next((w for w in LOGO_WIDTHS if w >= asked), LOGO_WIDTHS[-1])


def height_for(kind: str, width: int) -> int:
    return width * 3 // 2 if kind == "poster" else width * 9 // 16


def name(source: str, key: str, kind: str, width: int, fmt: str) -> str:
    """A kept picture's file name: a hash, never a title or a file name."""
    said = f"{STAMP}|{ENCODER}|{source}|{key}|{kind}|{width}|{fmt}"
    return hashlib.sha256(said.encode()).hexdigest()[:40]


def etag(data: bytes) -> str:
    return f'"{hashlib.sha1(data).hexdigest()[:24]}"'


# Making a picture -------------------------------------------------------------------


def encoder_args(kind: str, width: int, fmt: str) -> list[str]:
    """FFmpeg's output settings for one picture."""
    if fmt == "webp":
        return ["-c:v", "libwebp", "-quality", str(WEBP_Q), "-compression_level", str(WEBP_EFFORT),
                "-f", "webp"]  # fmt: skip
    return ["-q:v", str(JPEG_Q), "-c:v", "mjpeg", "-f", "image2"]


async def encode(ffmpeg: str, data: bytes, kind: str, width: int, fmt: str) -> bytes | None:
    """`data` (a picture) made `width` wide at most, keeping its shape and
    never made larger, as `fmt`; None if FFmpeg can't (no encoder for it, or
    not a picture it can read)."""
    height = height_for(kind, width)
    try:
        proc = await asyncio.create_subprocess_exec(
            *ff.low_priority(nice=10, idle_io=False), ffmpeg, "-hide_banner", "-nostdin",
            "-loglevel", "error", *ff.UPLOADED_PICTURE, "-i", "pipe:0", "-frames:v", "1",
            "-vf", f"scale='min({width},iw)':'min({height},ih)':force_original_aspect_ratio=decrease",
            *encoder_args(kind, width, fmt), "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
    except OSError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), MAKE_S)
    except TimeoutError:
        return None
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
    return out if proc.returncode == 0 and out else None


async def logo(ffmpeg: str, data: bytes, width: int) -> bytes | None:
    """A Station's logo (PNG) made `width` wide at most, keeping its shape
    and its transparency; None if FFmpeg can't."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *ff.low_priority(nice=10, idle_io=False), ffmpeg, "-hide_banner", "-nostdin",
            "-loglevel", "error", *ff.UPLOADED_PICTURE, "-i", "pipe:0", "-frames:v", "1",
            "-vf", f"scale='min({width},iw)':-2:flags=lanczos,format=rgba", "-c:v", "png", "-f", "image2",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
    except OSError:
        return None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(data), MAKE_S)
    except TimeoutError:
        return None
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
    return out if proc.returncode == 0 and out else None


_webp: dict[str, bool] = {}


async def makes_webp(ffmpeg: str) -> bool:
    """Whether this FFmpeg can make WebP (libwebp), asked once."""
    if ffmpeg not in _webp:
        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg, "-hide_banner", "-nostdin", "-encoders",
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
            out, _ = await asyncio.wait_for(proc.communicate(), 10)
            _webp[ffmpeg] = proc.returncode == 0 and b" libwebp " in out
        except (OSError, TimeoutError):
            _webp[ffmpeg] = False
        if not _webp[ffmpeg]:
            log.warning("This FFmpeg can't make WebP pictures: tapiOca's apps get JPEG")
    return _webp[ffmpeg]


# The disk cache -----------------------------------------------------------------------


@dataclass(frozen=True)
class Kept:
    """A picture as kept: it, its type, its ETag, the version of the
    picture it was made from ("" if not known), and the library its title
    was in when it was made (for the access check after a restart)."""

    data: bytes
    content_type: str
    etag: str
    version: str = ""
    library: str = ""


class DiskCache:
    """Pictures kept in a folder, up to `most_bytes`, the least recently
    viewed going first. Every method is safe to call from a thread, and
    never raises for the disk: a problem is logged once and the picture is
    treated as not kept."""

    def __init__(self, folder: Path, most_bytes: int) -> None:
        self.folder = folder
        self.most_bytes = most_bytes
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._bytes = 0
        self._written_used: dict[str, float] = {}
        self._said: set[str] = set()

    @property
    def on(self) -> bool:
        return self.most_bytes > 0

    def _trouble(self, what: str, e: Exception) -> None:
        if what not in self._said:
            self._said.add(what)
            log.warning("The picture cache couldn't %s (%s): pictures are made as they're asked for", what, type(e).__name__)

    def open(self) -> None:
        """Ready to use: the folder made, emptied if its stamp isn't this
        version's, and its index opened."""
        if not self.on:
            return
        with self._lock:
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                stamp = self.folder / "FORMAT"
                found = stamp.read_text().strip() if stamp.is_file() else None
                if found != STAMP:
                    if found is not None:
                        log.info("The picture cache was made by another version of tapiOca: emptied")
                    for entry in self.folder.iterdir():
                        if entry.is_dir():
                            shutil.rmtree(entry, ignore_errors=True)
                        else:
                            entry.unlink(missing_ok=True)
                    stamp.write_text(STAMP + "\n")
                db = sqlite3.connect(self.folder / "index.db", check_same_thread=False, isolation_level=None)
                db.execute("PRAGMA journal_mode=WAL")
                db.execute(
                    "CREATE TABLE IF NOT EXISTS kept (name TEXT PRIMARY KEY, type TEXT, etag TEXT,"
                    " version TEXT, library TEXT, bytes INTEGER, used REAL)"
                )
                self._db = db
                self._bytes = db.execute("SELECT COALESCE(SUM(bytes), 0) FROM kept").fetchone()[0]
            except (OSError, sqlite3.Error) as e:
                self._db = None
                self._trouble("open its folder", e)

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                with contextlib.suppress(sqlite3.Error):
                    self._db.close()
                self._db = None

    def _path(self, name: str) -> Path:
        return self.folder / name[:2] / name

    def get(self, name: str) -> Kept | None:
        with self._lock:
            if self._db is None:
                return None
            try:
                row = self._db.execute(
                    "SELECT type, etag, version, library FROM kept WHERE name = ?", (name,)
                ).fetchone()
                if row is None:
                    return None
                try:
                    data = self._path(name).read_bytes()
                except FileNotFoundError:
                    self._forget(name)
                    return None
                now = time.time()
                if now - self._written_used.get(name, 0.0) > USED_EVERY_S:
                    self._written_used[name] = now
                    self._db.execute("UPDATE kept SET used = ? WHERE name = ?", (now, name))
                return Kept(data, row[0], row[1], row[2] or "", row[3] or "")
            except (OSError, sqlite3.Error) as e:
                self._trouble("read a picture", e)
                return None

    def put(self, name: str, kept: Kept) -> bool:
        """Keeps a picture: False if it isn't (too big, the disk nearly full,
        or a failed write), which changes nothing for the request."""
        with self._lock:
            if self._db is None or len(kept.data) > self.most_bytes // 8:
                return False
            try:
                if shutil.disk_usage(self.folder).free < FREE_LEAST:
                    return False
                path = self._path(name)
                path.parent.mkdir(exist_ok=True)
                part = path.with_name(f".{name}.{os.getpid()}.{threading.get_ident()}")
                try:
                    part.write_bytes(kept.data)
                    os.replace(part, path)
                finally:
                    part.unlink(missing_ok=True)
                old = self._db.execute("SELECT bytes FROM kept WHERE name = ?", (name,)).fetchone()
                self._db.execute(
                    "INSERT OR REPLACE INTO kept VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, kept.content_type, kept.etag, kept.version, kept.library, len(kept.data), time.time()),
                )
                self._bytes += len(kept.data) - (old[0] if old else 0)
                self._written_used[name] = time.time()
                self._evict()
                return True
            except (OSError, sqlite3.Error) as e:
                self._trouble("keep a picture", e)
                return False

    def drop(self, name: str) -> None:
        """No longer kept (its source's picture changed)."""
        with self._lock:
            if self._db is None:
                return
            try:
                self._forget(name)
            except (OSError, sqlite3.Error) as e:
                self._trouble("let go of a picture", e)

    def _forget(self, name: str) -> None:
        row = self._db.execute("SELECT bytes FROM kept WHERE name = ?", (name,)).fetchone()  # type: ignore[union-attr]
        if row is not None:
            self._db.execute("DELETE FROM kept WHERE name = ?", (name,))  # type: ignore[union-attr]
            self._bytes -= row[0]
        self._written_used.pop(name, None)
        with contextlib.suppress(OSError):
            self._path(name).unlink(missing_ok=True)

    def _evict(self) -> None:
        """The least recently viewed dropped until it's back under 90% of its cap."""
        if self._bytes <= self.most_bytes:
            return
        aim = self.most_bytes * 9 // 10
        for (gone,) in self._db.execute("SELECT name FROM kept ORDER BY used").fetchall():  # type: ignore[union-attr]
            if self._bytes <= aim:
                break
            self._forget(gone)

    @property
    def bytes_kept(self) -> int:
        return self._bytes


# Making once, what's on screen first -----------------------------------------------------


class Maker:
    """Each picture made once however many ask for it at once, with a
    screen's request ahead of anything drawn ahead."""

    def __init__(self) -> None:
        self._making: dict[str, asyncio.Future] = {}
        self._screens = 0  # (requests from a screen being made now)
        self._quiet = asyncio.Event()
        self._quiet.set()

    async def once(self, key: str, make: Callable[[], Awaitable[T]]) -> T:
        """What `make` makes, made once however many ask for `key` at once,
        and carried on to its end even when they stop waiting."""
        task = self._making.get(key)
        if task is None:
            task = self._making[key] = asyncio.ensure_future(make())

            def done(t: asyncio.Future) -> None:
                if self._making.get(key) is t:
                    del self._making[key]
                if not t.cancelled():
                    t.exception()  # (told to whoever's waiting; otherwise, no matter)

            task.add_done_callback(done)
        return await asyncio.shield(task)

    @contextlib.asynccontextmanager
    async def screen(self):
        """A screen's request: while any is being made, drawing ahead waits."""
        self._screens += 1
        self._quiet.clear()
        try:
            yield
        finally:
            self._screens -= 1
            if not self._screens:
                self._quiet.set()

    async def ahead_turn(self) -> None:
        """Drawing ahead's turn: once no screen's request is being made."""
        while self._screens:
            await self._quiet.wait()

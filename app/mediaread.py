"""Which file tapiOca reads itself for a path Plex reports (the security suite's
MED-01, the apps repository's docs/threat-models/security-suite-2.md).

Plex names each program's file, and tapiOca reads it straight from disk when it
can see it (sources.local_candidates), handing it to FFmpeg or to a player. So
whatever controls Plex's answers names what tapiOca reads. A place is taken
only when it's Media's:

1. It's under a root, as worked out: the media folder (MEDIA_DIR), a
   PATH_MAPPINGS target, or one of Plex's own library folders. Learned
   prefixes are never roots: they come from Plex's answers.
2. Where it really is, its links followed, isn't one of tapiOca's own: its
   data folder, the folders it makes in the temp folder, the cache or the
   app's own folder; nor /proc, /sys, /dev, /run or /etc. A place inside a
   root is Media's, wherever the root is (Media mounted inside the data
   folder still plays), and a link's target outside every root is read
   unless it's one of those (a library of links still plays).
3. Its real name is a video container's.
4. It isn't the database or one of its backups by device and inode (a hard
   link has another name).

A place refused is never "file not found": the next candidate is tried
(Plex's own stream, at last), and the log says why.

Report-only until the release's soak shows no real video refused: each
refusal is logged, once for each place, and nothing is refused.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .backups import BACKUP_DIR, DB_NAME
from .config import Settings

log = logging.getLogger(__name__)

# (Off until the soak's report shows no real video refused: then on, in the same release.)
ENFORCED = False

# A video container's extensions: the allow-list's family of containers (MED-FFMPEG-01), one table.
VIDEO_EXTENSIONS = frozenset({
    ".mkv", ".mk3d", ".webm",  # matroska,webm
    ".mp4", ".m4v", ".mov", ".3gp", ".3g2", ".mj2",  # mov,mp4,m4a,3gp,3g2,mj2 (and m4v)
    ".avi", ".divx",  # avi
    ".ts", ".m2ts", ".mts", ".tp", ".trp",  # mpegts
    ".mpg", ".mpeg", ".vob", ".evo", ".m2p",  # mpeg (program streams)
    ".m2v", ".mpv",  # mpegvideo
    ".wmv", ".asf", ".wtv",  # asf, wtv
    ".flv",  # flv
    ".ogv", ".ogm", ".ogg",  # ogg
    ".rm", ".rmvb",  # rm
    ".nut", ".mxf", ".dv",  # nut, mxf, dv
    ".264", ".h264", ".265", ".hevc", ".vc1",  # the raw streams a recording can be
})  # fmt: skip

# The system's own folders, never Media.
SYSTEM = ("/proc", "/sys", "/dev", "/run", "/etc")

# What tapiOca names the folders it makes in the temp folder (converting.py, gpu.py, hls.py).
OWN_TEMP_PREFIX = "stationplay-"

# The app's own folder: where its code is.
_APP = Path(__file__).resolve().parent.parent


def _under(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip("/") + "/")


@dataclass(frozen=True)
class Policy:
    """What may be read: the roots, and tapiOca's own places."""

    roots: tuple[str, ...]
    data_dir: str
    others: tuple[str, ...]  # the cache, the app's own folder, and the system's
    temp: str

    @classmethod
    def of(cls, settings: Settings, locations: Iterable[str]) -> Policy:
        """The roots from the media folder, PATH_MAPPINGS' targets and
        Plex's own library folders (`locations`, as Plex last listed them)."""
        named = [settings.media_dir, *(dst for _src, dst in settings.path_mappings), *locations]
        roots = tuple(dict.fromkeys(os.path.normpath(r) for r in named if r and r.startswith("/")))
        cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        others = (os.path.realpath(cache), str(_APP), *SYSTEM)
        temp = os.path.realpath(tempfile.gettempdir())
        return cls(roots, os.path.realpath(settings.data_dir), others, temp)

    def refusal(self, path: str) -> str | None:
        """Why the place `path` isn't Media's to read here, or None when it is."""
        if not any(_under(os.path.normpath(path), root) for root in self.roots):
            return "it isn't in the media folder, a mapped folder or one of Plex's library folders"
        real = os.path.realpath(path)
        if self._own(real):
            return "it's one of tapiOca's own files, or the system's"
        if os.path.splitext(real)[1].lower() not in VIDEO_EXTENSIONS:
            return "it isn't a video file"
        if self._same_file_as_own(real):
            return "it's the same file as tapiOca's database or a backup"
        return None

    def _own(self, real: str) -> bool:
        """Whether `real`, a place with its links followed, is tapiOca's own or
        the system's. One inside a root is Media's, wherever the root is."""
        if any(_under(real, os.path.realpath(root)) for root in self.roots):
            return False
        if _under(real, self.temp):
            return real[len(self.temp) :].lstrip("/").startswith(OWN_TEMP_PREFIX)
        return any(_under(real, folder) for folder in (self.data_dir, *self.others))

    def _same_file_as_own(self, real: str) -> bool:
        try:
            st = os.stat(real)
        except OSError:
            return False
        owned = [os.path.join(self.data_dir, DB_NAME + end) for end in ("", "-wal", "-shm")]
        backups = os.path.join(self.data_dir, BACKUP_DIR)
        if os.path.isdir(backups):
            owned += [os.path.join(backups, name) for name in os.listdir(backups)]
        for path in owned:
            try:
                own = os.stat(path)
            except OSError:
                continue
            if (own.st_dev, own.st_ino) == (st.st_dev, st.st_ino):
                return True
        return False


# What a program whose file was refused says: an outcome of its own, never "file not found" (which
# automatic replacement takes for missing), and never broken: it says nothing about the file itself.
NOT_OURS = "its file isn't tapiOca's to read here"


class Refused(Exception):
    """Each place Plex's file was found was refused (see Policy.refusal)."""


# The places a refusal was logged for (once each).
_said: set[str] = set()


def taken(policy: Policy, path: str) -> bool:
    """Whether `path`, a place that exists, is read. Each refusal is logged
    once; while report-only, it's read all the same."""
    why = policy.refusal(path)
    if why is None:
        return True
    if path not in _said:
        if len(_said) > 10_000:
            _said.clear()
        _said.add(path)
        log.warning("%s %s: %s", "Not reading" if ENFORCED else "Would not read", path, why)
    return not ENFORCED

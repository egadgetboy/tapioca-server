"""What an older release left that this one no longer uses, removed once
(1.43.0: the restore-fast-pictures handoff, part 6).

1.42's disk cache of pictures for the apps, `data/cache/pictures` (its
`FORMAT`, `index.db` with `-wal` and `-shm`, and files in two-letter
folders), and any `data/cache/.pictures-gone-*` an interrupted delete left
beside it. Nothing else in the data folder is touched, and nothing in the
database changes: 1.42's meta value `picture_cache_gb` is left, ignored.

- A `pictures` folder without 1.42's `FORMAT` or `index.db` isn't 1.42's:
  it's left as it is, and that's logged once.
- A `pictures` that's a link is removed as a link; its target is never
  touched. A `data/cache` that's a link (to another disk, say) is cleaned
  through it, the same way, and the link stays.
- Otherwise the folder is renamed aside in one quick step, then deleted
  without following links. If it can't be renamed (its own mount), what's
  inside is deleted in place and the folder kept. What another start has
  removed meanwhile counts as removed.
- It runs in a thread of its own at the lowest CPU priority and idle disk
  priority (`ionice -c 3`, where the system has it), DELAY_S after start,
  never holding up the start or a stream, and logs once, with no file names.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

DELAY_S = 30.0
GONE_PREFIX = ".pictures-gone-"
MARKS = ("FORMAT", "index.db")  # (what says a pictures folder is 1.42's)


def _size(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(root, name)).st_size
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
    return total


def _delete_tree(path: Path) -> bool:
    """Deletes a folder without following links; whether all of it went
    (what's gone already, another start's doing, counts as gone)."""
    failed = []

    def failing(_func, _path, exc) -> None:
        error = exc[1] if isinstance(exc, tuple) else exc
        if not isinstance(error, FileNotFoundError):
            failed.append(error)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=failing)
    else:
        shutil.rmtree(path, onerror=failing)
    return not failed and not os.path.lexists(path)


def _empty(path: Path) -> bool:
    """Deletes what's inside a folder, never following links, keeping it."""
    ok = True
    for entry in list(os.scandir(path)):
        child = Path(entry.path)
        try:
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                child.unlink()
            elif not _delete_tree(child):
                ok = False
        except FileNotFoundError:
            pass
        except OSError:
            ok = False
    return ok


def _is_1_42s(pictures: Path) -> bool:
    return any(os.path.lexists(pictures / mark) for mark in MARKS)


def old_picture_cache(data_dir: Path) -> None:
    """Removes 1.42's picture cache (see the module's notes)."""
    cache = Path(data_dir) / "cache"
    pictures = cache / "pictures"
    if not cache.is_dir():  # (none, or a link to nothing: nothing to do)
        return
    freed, ok, any_found, linked = 0, True, False, False
    aside_name = ""
    try:
        if os.path.islink(pictures):
            any_found = linked = True
            with contextlib.suppress(FileNotFoundError):
                pictures.unlink()
        elif pictures.is_dir() and not _is_1_42s(pictures) and os.path.lexists(pictures):
            # (Someone else's: left as it is, while what an interrupted delete left is still swept.
            # Gone meanwhile counts as removed: another start's.)
            log.warning("data/cache/pictures isn't 1.42's picture cache, so it was left as it is")
        elif pictures.is_dir():
            any_found = True
            freed += _size(pictures)
            aside_name = f"{GONE_PREFIX}{os.getpid()}-{time.monotonic_ns()}"
            try:
                os.rename(pictures, cache / aside_name)
            except FileNotFoundError:
                aside_name = ""  # (another start moved it first)
            except OSError:
                ok = _empty(pictures) and ok  # (its own mount: emptied in place)
        for entry in list(os.scandir(cache)):
            if entry.name.startswith(GONE_PREFIX):
                any_found = True
                gone = Path(entry.path)
                try:
                    if entry.is_symlink():
                        gone.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if gone.name != aside_name:
                    freed += _size(gone)  # (left by an earlier start)
                ok = _delete_tree(gone) and ok
        if not os.path.islink(cache):
            with contextlib.suppress(OSError):
                cache.rmdir()  # (only if it's empty; a linked one stays)
    except FileNotFoundError:
        pass  # (data/cache itself gone meanwhile: another start finished first)
    except OSError:
        ok = False
    if not any_found:
        return
    if linked and ok:
        log.warning(
            "data/cache/pictures was a link, so only the link was removed: what it pointed to "
            "(1.42's pictures, if it kept them there) was left as it is"
        )
    elif ok:
        log.info("tapiOca 1.42's picture cache was removed (%d MB freed)", freed // (1 << 20))
    else:
        log.warning(
            "1.42's picture cache couldn't all be removed: delete data/cache/pictures and any "
            "data/cache/.pictures-gone-* folders to free its space"
        )


def _idle_disk(thread_id: int) -> None:
    """This thread's disk access at idle priority (Linux keeps it per thread), where ionice is."""
    ionice = shutil.which("ionice")
    if ionice:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                [ionice, "-c", "3", "-p", str(thread_id)],
                check=False,
                capture_output=True,
                timeout=5,
            )


async def later(data_dir: Path) -> None:
    """old_picture_cache, DELAY_S after start, in a thread of its own at the
    lowest priority (its own thread, as a lowered priority can't be raised
    again)."""
    await asyncio.sleep(DELAY_S)
    loop = asyncio.get_running_loop()
    done: asyncio.Future = loop.create_future()

    def run() -> None:
        try:
            me = threading.get_native_id()
            with contextlib.suppress(OSError, AttributeError):
                os.setpriority(os.PRIO_PROCESS, me, 19)
            _idle_disk(me)
            old_picture_cache(data_dir)
        except Exception:
            log.exception("Removing 1.42's picture cache didn't work")
        finally:
            loop.call_soon_threadsafe(lambda: done.done() or done.set_result(None))

    threading.Thread(target=run, name="old-picture-cache", daemon=True).start()
    await done

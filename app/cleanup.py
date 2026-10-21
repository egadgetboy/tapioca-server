"""What an older release left that this one no longer uses, removed once
(1.43.0: the restore-fast-pictures handoff, part 6).

1.42's disk cache of pictures for the apps, `data/cache/pictures` (its
`FORMAT`, `index.db` with `-wal` and `-shm`, and files in two-letter
folders), and any `data/cache/.pictures-gone-*` an interrupted delete left
beside it. Nothing else in the data folder is touched, and nothing in the
database changes: 1.42's meta value `picture_cache_gb` is left, ignored.

- A symlink is removed as a link; its target is never touched.
- Otherwise the folder is renamed aside in one quick step, then deleted
  without following links. If it can't be renamed (its own mount), what's
  inside is deleted in place and the folder kept.
- It runs in the background at idle priority, DELAY_S after start, never
  holding up the start or a stream, and logs once, with no file names.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

DELAY_S = 30.0
GONE_PREFIX = ".pictures-gone-"


def _size(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(root, name)).st_size
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
    return total


def _delete_tree(path: Path) -> bool:
    """Deletes a folder without following links; whether all of it went."""
    failed = []
    shutil.rmtree(path, onerror=lambda *a: failed.append(a))
    return not failed and not path.exists()


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
        except OSError:
            ok = False
    return ok


def old_picture_cache(data_dir: Path) -> None:
    """Removes 1.42's picture cache (see the module's notes)."""
    cache = Path(data_dir) / "cache"
    pictures = cache / "pictures"
    if not os.path.lexists(cache):
        return
    freed, ok, any_found = 0, True, False
    aside_name = ""
    try:
        if os.path.islink(pictures):
            any_found = True
            pictures.unlink()
        elif pictures.is_dir():
            any_found = True
            freed += _size(pictures)
            aside_name = f"{GONE_PREFIX}{os.getpid()}-{time.monotonic_ns()}"
            aside = cache / aside_name
            try:
                os.rename(pictures, aside)
            except OSError:
                ok = _empty(pictures) and ok  # (its own mount: emptied in place)
        if cache.is_dir() and not cache.is_symlink():
            for entry in list(os.scandir(cache)):
                if entry.name.startswith(GONE_PREFIX):
                    any_found = True
                    gone = Path(entry.path)
                    if entry.is_symlink():
                        gone.unlink()
                    else:
                        if gone.name != aside_name:
                            freed += _size(gone)  # (left by an earlier start)
                        ok = _delete_tree(gone) and ok
            with contextlib.suppress(OSError):
                cache.rmdir()  # (only if it's empty)
    except OSError:
        ok = False
    if not any_found:
        return
    if ok:
        log.info("tapiOca 1.42's picture cache was removed (%d MB freed)", freed // (1 << 20))
    else:
        log.warning(
            "1.42's picture cache couldn't all be removed: delete data/cache/pictures to free its space"
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
            with contextlib.suppress(OSError, AttributeError):
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 19)
            old_picture_cache(data_dir)
        except Exception:
            log.exception("Removing 1.42's picture cache didn't work")
        finally:
            loop.call_soon_threadsafe(lambda: done.done() or done.set_result(None))

    threading.Thread(target=run, name="old-picture-cache", daemon=True).start()
    await done

"""The security suite's census (DL287, part A.1, the static half): every place
in tapiOca's code that asks something outside the process (an outbound
request), starts a program, or writes a file, found by reading the code,
never by hand. Each one found is declared below with what it is, so a new
one fails the suite until someone says what it is and it gets its checks:
nothing ships untested by omission.

The runtime half (every route) is in authz_matrix.py.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


@dataclass(frozen=True)
class Site:
    file: str  # (relative to app/)
    function: str  # (the innermost function it's in; "<module>" at the top)
    call: str  # (as written: "httpx.AsyncClient", "os.replace", ".write_text")

    def __str__(self) -> str:
        return f"app/{self.file}:{self.function} {self.call}"


# What reaches outside the process, by its full name once imports and
# aliases are followed (the security audit of 1.44.0: "import httpx as hx",
# "from httpx import AsyncClient", httpx.get and the rest all count).
_HTTPX_CLIENTS = {"httpx.AsyncClient", "httpx.Client"}
_EGRESS_NAMES = _HTTPX_CLIENTS | {
    *(f"httpx.{verb}" for verb in ("get", "post", "put", "patch", "delete", "head", "options", "request", "stream")),
    "httpx.AsyncHTTPTransport", "httpx.HTTPTransport",
    "urllib.request.urlopen", "urllib.request.build_opener", "urllib.request.OpenerDirector",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "socket.create_connection", "socket.getaddrinfo",
    "asyncio.open_connection", "asyncio.open_unix_connection",
    "requests.get", "requests.post", "requests.request", "requests.Session",
    "aiohttp.ClientSession", "aiohttp.request",
}  # fmt: skip
# And these, on whatever they're called on (a socket, an event loop).
_EGRESS_METHODS = {"connect", "connect_ex", "sock_connect", "create_connection", "create_datagram_endpoint", "getaddrinfo", "sendto"}
# (sqlite3.connect and the like aren't ways out.)
_NOT_EGRESS = {"sqlite3.connect"}
# A keyword that would send a client's requests somewhere the guard didn't choose.
_ROUTING = {"proxy", "proxies", "mounts"}
# What starts a program.
_SPAWN = {
    ("asyncio", "create_subprocess_exec"),
    ("asyncio", "create_subprocess_shell"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "call"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
    ("os", "system"),
    ("os", "popen"),
}
# What writes or moves a file (a Path's replace and rename take one argument; str.replace takes two).
_WRITE_ANY = {"write_text", "write_bytes", "mkstemp", "NamedTemporaryFile", "mkdtemp"}
_WRITE_OS = {
    ("os", "replace"),
    ("os", "rename"),
    ("os", "remove"),
    ("os", "unlink"),
    ("shutil", "copy"),
    ("shutil", "copy2"),
    ("shutil", "copyfile"),
    ("shutil", "copytree"),
    ("shutil", "move"),
    ("shutil", "rmtree"),
}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        inner = _dotted(node.value)
        return f"{inner}.{node.attr}" if inner else node.attr
    return ""


def _aliases(tree: ast.AST) -> dict[str, str]:
    """What each name a module imports stands for: "hx" for httpx, "AC" for httpx.AsyncClient."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _full_name(func: ast.AST, aliases: dict[str, str]) -> str:
    dotted = _dotted(func)
    head, _, rest = dotted.partition(".")
    if head in aliases:
        return aliases[head] + (f".{rest}" if rest else "")
    return dotted


def _egress_hit(func: ast.AST, aliases: dict[str, str]) -> str:
    full = _full_name(func, aliases)
    if full in _NOT_EGRESS:
        return ""
    if full in _EGRESS_NAMES:
        return full
    if isinstance(func, ast.Attribute) and func.attr in _EGRESS_METHODS:
        return f".{func.attr}"
    return ""


def _sites(kind: str) -> list[Site]:
    out: list[Site] = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _aliases(tree)
        owner: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    owner[id(inner)] = node.name  # (walk order: the innermost function wins)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else ""
            )
            base = _dotted(func.value) if isinstance(func, ast.Attribute) else ""
            where = owner.get(id(node), "<module>")
            rel = str(path.relative_to(APP))
            hit = ""
            if kind == "egress":
                hit = _egress_hit(func, aliases)
            elif kind == "spawn" and (base, name) in _SPAWN:
                hit = f"{base}.{name}"
            elif kind == "write":
                if (base, name) in _WRITE_OS:
                    hit = f"{base}.{name}"
                elif (
                    (name in _WRITE_ANY and base not in ("str",))
                    or (
                        name in ("replace", "rename", "unlink", "rmdir")
                        and base not in ("os", "dataclasses", "str")
                        and len(node.args) <= 1
                        and not node.keywords
                        and name != "replace"
                    )
                    or (
                        name == "replace"
                        and base not in ("os", "dataclasses")
                        and len(node.args) == 1
                        and not node.keywords
                    )
                ):
                    hit = f".{name}"
                elif (
                    name == "open"
                    and isinstance(func, ast.Name)
                    and len(node.args) > 1
                    and isinstance(node.args[1], ast.Constant)
                    and any(c in str(node.args[1].value) for c in "wax+")
                ):
                    hit = f"open({node.args[1].value!r})"
                elif (
                    name == "open"
                    and isinstance(func, ast.Attribute)
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and any(c in str(node.args[0].value) for c in "wax+")
                ):
                    hit = f".open({node.args[0].value!r})"
                elif name == "backup" and base not in ("",):
                    hit = f".{name}"
            if hit:
                out.append(Site(rel, where, hit))
    return sorted(set(out), key=str)


def egress_sites() -> list[Site]:
    return _sites("egress")


def spawn_sites() -> list[Site]:
    return _sites("spawn")


def write_sites() -> list[Site]:
    return _sites("write")


# ---------------------------------------------------------------------------
# What each one is (DL287). Provenance (the owner, October 21, DL287): an
# address an Admin typed into a setting may be on the home network; anything
# that comes from data must be public. "fixed" is an address in tapiOca's
# own code.

EGRESS = {
    "app/applibrary.py:proxy httpx.AsyncClient": "typed: Plex's address (a player's file or subtitle, from Plex)",
    "app/arr.py:_call httpx.AsyncClient": "typed: Sonarr's or Radarr's address",
    "app/notify.py:_post_once httpx.AsyncClient": "typed: an alert notification address",
    "app/plex.py:__init__ httpx.AsyncClient": "typed: Plex's address",
    "app/reach.py:_look httpx.AsyncClient": "typed: this tapiOca's own away address, checked from here",
    "app/releases.py:check httpx.AsyncClient": "fixed: GitHub's latest-release address",
    # (The guard itself: the one real transport, and the one lookup.)
    "app/safefetch.py:handle_async_request httpx.AsyncHTTPTransport": "guard: the vetted transport's own connections",
    "app/safefetch.py:_resolve socket.getaddrinfo": "guard: every name's lookup, on its own pool, within a time limit",
}

# Every program tapiOca starts: an argument list, never a shell (DEP-04,
# INJ-02, MED-01). "ffmpeg"/"ffprobe" are the image's own; "ionice" is the
# system's.
SPAWN = {
    "app/broadcaster.py:_run_ffmpeg asyncio.create_subprocess_exec": "ffmpeg: a Station's broadcast",
    "app/cleanup.py:_idle_disk subprocess.run": "ionice: the clean-up thread's disk priority",
    "app/converting.py:_start asyncio.create_subprocess_exec": "ffmpeg: a converted copy",
    "app/cuts.py:_read asyncio.create_subprocess_exec": "ffprobe: a file's keyframes",
    "app/ffmpeg.py:find_picture asyncio.create_subprocess_exec": "ffmpeg: a frame for a picture",
    "app/ffmpeg.py:probe asyncio.create_subprocess_exec": "ffprobe: what a file holds",
    "app/ffmpeg.py:run_to_end asyncio.create_subprocess_exec": "ffmpeg: a short job run to its end",
    "app/folderart.py:_run asyncio.create_subprocess_exec": "ffmpeg: a Media folder's art",
    "app/folderart.py:_scaled asyncio.create_subprocess_exec": "ffmpeg: a Media folder's art, resized",
    "app/folderscan.py:read_file asyncio.create_subprocess_exec": "ffprobe: a Media folder's file",
    "app/gpu.py:_run asyncio.create_subprocess_exec": "ffmpeg: the GPU's check at start",
    "app/hls.py:_run asyncio.create_subprocess_exec": "ffmpeg: a Station's HLS",
    "app/intro.py:colours asyncio.create_subprocess_exec": "ffmpeg: an intro card's colors",
    "app/logos.py:_ffmpeg asyncio.create_subprocess_exec": "ffmpeg: a logo",
    "app/main.py:render_icon asyncio.create_subprocess_exec": "ffmpeg: an app icon",
    "app/playback.py:busy_stream asyncio.create_subprocess_exec": "ffmpeg: the busy notice's stream",
    "app/scanner.py:_run asyncio.create_subprocess_exec": "ffprobe: the file check",
    "app/scanner.py:decode_through asyncio.create_subprocess_exec": "ffmpeg: the deep file check",
}

# Every place tapiOca writes, moves or deletes a file, by where: "data" is the
# data folder (settings.data_dir); "temp" is the system's temporary folder.
# Never the media folder, never a folder it serves its page or code from
# (FILE-03, FILE-04: tests/security/test_files.py checks it while running).
WRITE = {
    "app/alerts.py:_look_at_data .unlink": "data: the free-space probe",
    "app/alerts.py:_look_at_data .write_text": "data: the free-space probe",
    "app/api.py:backup .backup": "data: a backup's database copy",
    "app/backups.py:_put_in_place .unlink": "data: a restore's swap",
    "app/backups.py:_put_in_place os.replace": "data: a restore's swap",
    "app/backups.py:_write_zip os.replace": "data: a backup",
    "app/backups.py:apply_staged_restore shutil.rmtree": "data: a staged restore",
    "app/backups.py:before_update .unlink": "data: the copy before an update",
    "app/backups.py:before_update os.replace": "data: the copy before an update",
    "app/backups.py:discard_restore shutil.rmtree": "data: a staged restore",
    "app/backups.py:mark_ready .write_text": "data: a staged restore's mark",
    "app/backups.py:prune .unlink": "data: old backups",
    "app/backups.py:stage_restore .write_bytes": "data: a staged restore",
    "app/backups.py:stage_restore shutil.rmtree": "data: a staged restore",
    "app/broken.py:_write .write_text": "data: Broken files",
    "app/broken.py:_write os.replace": "data: Broken files",
    "app/bumpers.py:_keep .write_text": "data: a bumper",
    "app/bumpers.py:_keep os.replace": "data: a bumper",
    "app/cleanup.py:_delete_tree shutil.rmtree": "data: 1.42's picture folder",
    "app/cleanup.py:_empty .unlink": "data: 1.42's picture folder",
    "app/cleanup.py:old_picture_cache .rmdir": "data: 1.42's picture folder",
    "app/cleanup.py:old_picture_cache .unlink": "data: 1.42's picture folder",
    "app/cleanup.py:old_picture_cache os.rename": "data: 1.42's picture folder",
    "app/converting.py:_cut .open('wb')": "temp: a converted copy's pieces",
    "app/converting.py:_finished .replace": "temp: a converted copy's pieces",
    "app/converting.py:_tidy .unlink": "temp: a converted copy's pieces",
    "app/converting.py:new_folder .mkdtemp": "temp: a converted copy's folder",
    "app/converting.py:rest .unlink": "temp: a converted copy's pieces",
    "app/converting.py:stop shutil.rmtree": "temp: a converted copy's folder",
    "app/cuts.py:_write open('w')": "data: a file's keyframes",
    "app/cuts.py:_write os.replace": "data: a file's keyframes",
    "app/db.py:copy_database .backup": "data: a database copy",
    "app/devices.py:unlink .unlink": "no file: a device is unlinked in the database",
    "app/ffmpeg.py:write .write_text": "data: ffmpeg's subtitle-check sample",
    "app/folderart.py:_keep .unlink": "data: a Media folder's art",
    "app/folderart.py:_keep os.replace": "data: a Media folder's art",
    "app/gpu.py:detect .mkdtemp": "temp: the GPU's check",
    "app/gpu.py:detect shutil.rmtree": "temp: the GPU's check",
    "app/hls.py:__init__ .mkdtemp": "temp: a Station's HLS pieces",
    "app/infostation.py:_put .write_text": "data: INFO's pages",
    "app/infostation.py:_put os.replace": "data: INFO's pages",
    "app/logos.py:keep .write_bytes": "data: a logo",
    "app/main.py:banner_preview .mkdtemp": "temp: a banner's preview",
    "app/main.py:banner_preview shutil.rmtree": "temp: a banner's preview",
    "app/main.py:card_preview .mkdtemp": "temp: a card's preview",
    "app/main.py:card_preview shutil.rmtree": "temp: a card's preview",
    "app/main.py:data_dir_problem .unlink": "data: the start's write check",
    "app/main.py:data_dir_problem .write_text": "data: the start's write check",
    "app/main.py:load_device_id .write_text": "data: this server's ID",
    "app/subtitles.py:link os.replace": "data: a subtitle file's plainly named link",
    "app/subtitles.py:tidy .unlink": "data: a subtitle file's plainly named link",
}


def egress_guards() -> dict[str, tuple[str | None, object]]:
    """For each outbound client the census finds: the kind its transport is
    vetted as (safefetch.transport(safefetch.<KIND>, ...)), or None when it
    isn't made through safefetch; and its follow_redirects (None if unset)."""
    out: dict[str, tuple[str | None, object]] = {}
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    owner[id(inner)] = node.name
        aliases = _aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            hit = _egress_hit(node.func, aliases)
            if not hit:
                continue
            site = str(Site(str(path.relative_to(APP)), owner.get(id(node), "<module>"), hit))
            kinds = {k.arg: k.value for k in node.keywords}
            kind = None
            made = kinds.get("transport")
            if (
                isinstance(made, ast.Call)
                and _dotted(made.func) == "safefetch.transport"
                and made.args
            ):
                first = made.args[0]
                kind = first.attr.lower() if isinstance(first, ast.Attribute) else None
            redirects = kinds.get("follow_redirects")
            out[site] = (
                kind,
                redirects.value if isinstance(redirects, ast.Constant) else redirects,
            )
    return out


def unsafe_options() -> list[Site]:
    """Every call that could send a request where the guard didn't choose,
    or follow a redirect (the security audit of 1.44.0): a client given a
    proxy, proxies, mounts or trust_env=True, and any call with
    follow_redirects=True, such as a client's own .get or .send."""
    out: list[Site] = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _aliases(tree)
        owner: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    owner[id(inner)] = node.name
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            words = {k.arg: k.value for k in node.keywords if k.arg}
            why = ""
            follows = words.get("follow_redirects")
            if follows is not None and not (isinstance(follows, ast.Constant) and follows.value is False):
                why = "follow_redirects"
            elif _full_name(node.func, aliases) in _HTTPX_CLIENTS | {"httpx.AsyncHTTPTransport", "httpx.HTTPTransport"}:
                trust = words.get("trust_env")
                if _ROUTING & set(words):
                    why = sorted(_ROUTING & set(words))[0]
                elif trust is not None and not (isinstance(trust, ast.Constant) and trust.value is False):
                    why = "trust_env"
            if why:
                out.append(Site(str(path.relative_to(APP)), owner.get(id(node), "<module>"), why))
    return sorted(set(out), key=str)

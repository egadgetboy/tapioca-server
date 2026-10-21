"""tapiOca's own key (1.43.0): what lets its apps tell the real tapiOca from
anything else answering at its address (the apps repo's
docs/threat-models/server-proof.md, sections 1 and 2).

- One RSA-3072 key for each server, made once by the image's own `openssl`
  and kept forever in `<DATA_DIR>/server-key.pem` (PKCS#8, unencrypted,
  mode 0600). Never in the database, never in a backup.
- Made only when the file is missing (FileNotFoundError and nothing
  else), written once to a temporary file and linked into place, so two
  makers end with one key and a full disk leaves nothing half made. Never
  replaced when it's there but can't be used: tapiOca starts without a key,
  the proof answers 503, and an Admin alert says that cause's fix.
- Checked at each start: its mode, its shape (RSA, 3072 bits, e=65537) and
  one test signature. Its public numbers are kept from that start, and
  every signature is checked against them in plain Python before it's
  sent (only public numbers: safe in Python), so a fault, or a file
  swapped under a running server, never sends a bad signature.
- It signs only `tapioca/1 <purpose>\\n<body>`, for the purposes listed:
  this release, `server-proof`. It never decrypts and is never a TLS key.
- `openssl` runs for each signature, by absolute path, through `nice -n
  10` (playback's FFmpeg first), with no shell and an environment of PATH
  alone, the bytes on standard input and the signature on standard
  output, `-passin pass:` so an encrypted key fails closed, and a 2-second
  limit, after which it's stopped by its PID.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import errno
import hashlib
import logging
import os
import secrets
import signal
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

KEY_FILE = "server-key.pem"
OPENSSL = "/usr/bin/openssl"
NICE = "/usr/bin/nice"
PREFIX = "tapioca/1 "
PURPOSES = ("server-proof",)
# (Set aside for later releases, with tests that nothing signs them yet:
# Stand-ins, the play plan and Private at home's TLS key.)
SET_ASIDE = ("standins", "play-plan", "home-tls")
SIGN_LIMIT_S = 2.0
MAKE_LIMIT_S = 120.0
# The start's retries for a test signature that fails for a reason that
# isn't the key itself (a timeout on a busy boot), then every 5 minutes.
RETRIES_S = (5, 15, 45)
RETRY_EVERY_S = 300
FAILURES_FOR_ALERT = 3  # (signatures failing in a row, before the alert)

# The one key shape the apps take (§2): a 422-byte SubjectPublicKeyInfo.
SPKI_HEAD = bytes.fromhex("308201a2300d06092a864886f70d01010105000382018f003082018a0282018100")
SPKI_TAIL = bytes.fromhex("0203010001")
SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
SIGNATURE_BYTES = 384

# What each cause says to an Admin (FG-10). Only "not a key" says delete.
SAID = {
    "tools": (
        "tapiOca's image is missing a program it needs to prove who it is (OpenSSL or nice), "
        "so its apps can't connect. Use tapiOca's own image."
    ),
    "unreadable": (
        "tapiOca can't read its key, so its apps can't connect. Make server-key.pem in the data "
        "folder readable by the user tapiOca runs as, then restart tapiOca."
    ),
    "not-a-key": (
        "tapiOca's key file isn't a key it can use, so its apps can't connect. Delete "
        "server-key.pem from the data folder and restart tapiOca. Then make a code under Access → "
        "Reconnect apps and enter it on each app that asks."
    ),
    "changed": (
        "tapiOca's key file changed while it was running, so its apps can't connect. If you "
        "restored or replaced it on purpose, restart tapiOca, then make a code under Access → "
        "Reconnect apps and enter it on each app that asks. If not, put the old file back."
    ),
    "unsaved": (
        "tapiOca couldn't save its key, so its apps can't connect. Make room in the data folder, "
        "then restart tapiOca."
    ),
    "retrying": ("tapiOca couldn't prove who it is to its apps just now. It keeps trying."),
    "fault": (
        "tapiOca couldn't prove who it is to its apps just now. If this keeps happening, restart "
        "tapiOca."
    ),
}

spawn = asyncio.create_subprocess_exec


def read_file(path: Path) -> bytes:
    return path.read_bytes()


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def flush_folder(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def environment() -> dict[str, str]:
    """openssl's environment: PATH alone (no OPENSSL_CONF, no OPENSSL_*)."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}


def signed_bytes(purpose: str, body: bytes) -> bytes:
    if purpose not in PURPOSES:
        raise ValueError(f"tapiOca's key doesn't sign {purpose!r}")
    return (PREFIX + purpose + "\n").encode("ascii") + body


def numbers(spki: bytes) -> int:
    """The modulus of a key of the one shape; ValueError otherwise."""
    if len(spki) != 422 or spki[:33] != SPKI_HEAD or spki[-5:] != SPKI_TAIL or not spki[33] & 0x80:
        raise ValueError("not the one key shape")
    return int.from_bytes(spki[33:417], "big")


def checks(modulus: int, data: bytes, signature: bytes) -> bool:
    """Whether `signature` is RSA PKCS#1 v1.5 with SHA-256 over `data` by
    the key whose modulus this is (e=65537): its public numbers only."""
    if len(signature) != SIGNATURE_BYTES:
        return False
    s = int.from_bytes(signature, "big")
    if s >= modulus:
        return False
    digest = SHA256_INFO + hashlib.sha256(data).digest()
    want = b"\x00\x01" + b"\xff" * (SIGNATURE_BYTES - 3 - len(digest)) + b"\x00" + digest
    return pow(s, 65537, modulus).to_bytes(SIGNATURE_BYTES, "big") == want


class Unusable(Exception):
    """The key can't be used, for `cause` (a key of SAID)."""

    def __init__(self, cause: str) -> None:
        super().__init__(cause)
        self.cause = cause


class NotReady(Exception):
    """There's no key to sign with (yet, or at all)."""


class SignFailed(Exception):
    """A signature didn't come back, or didn't check: `cause` is "fault",
    "tools" or "changed"."""

    def __init__(self, cause: str) -> None:
        super().__init__(cause)
        self.cause = cause


class ServerKey:
    """The server's key. `alert(sentence)` raises the Admin alert for a
    cause (None clears it). `.state` is "making" until the start's check
    ends, then "ready" or "unusable"."""

    def __init__(self, data_dir: Path, alert: Callable[[str | None], None]) -> None:
        self.folder = Path(data_dir)
        self.path = self.folder / KEY_FILE
        self.alert = alert
        self.state = "making"
        self.cause = ""
        self.public_text = ""
        self._spki = b""
        self._modulus = 0
        self._failures = 0

    # The start ---------------------------------------------------------------

    async def start(self) -> None:
        """Loads the key (or makes it, when there's none), and checks it;
        tried again at 5, 15 and 45 seconds, then every 5 minutes, while it
        can't be used."""
        tries = 0
        while True:
            try:
                await self._load()
            except Unusable as e:
                self.state, self.cause = "unusable", e.cause
                log.warning("tapiOca's key can't be used yet (%s)", e.cause)
                if e.cause not in ("self-test", "mismatch"):
                    self.alert(SAID[e.cause])
                elif tries >= len(RETRIES_S):
                    # (After the three retries: a key whose signatures keep
                    # failing its own numbers is no key; anything else, it
                    # keeps trying.)
                    self.alert(SAID["not-a-key" if e.cause == "mismatch" else "retrying"])
            except Exception:
                log.exception("Checking tapiOca's key didn't work")
                self.state, self.cause = "unusable", "fault"
                if tries >= len(RETRIES_S):
                    self.alert(SAID["retrying"])
            else:
                self.state, self.cause = "ready", ""
                self.alert(None)
                log.info("tapiOca's key is ready")
                return
            await asyncio.sleep(RETRIES_S[tries] if tries < len(RETRIES_S) else RETRY_EVERY_S)
            tries += 1

    async def _load(self) -> None:
        if not (os.access(NICE, os.X_OK) and os.access(OPENSSL, os.X_OK)):
            raise Unusable("tools")
        try:
            data = await asyncio.to_thread(read_file, self.path)
        except FileNotFoundError:
            data = await self._make()
        except OSError as e:
            log.warning("tapiOca can't read %s (%s)", KEY_FILE, e.strerror or e)
            raise Unusable("unreadable") from None
        self._mode()
        first = data.split(b"\n", 1)[0].strip()
        if first != b"-----BEGIN PRIVATE KEY-----":
            raise Unusable("not-a-key")
        spki = await self._public()
        try:
            modulus = numbers(spki)
        except ValueError:
            raise Unusable("not-a-key") from None
        self._spki, self._modulus = spki, modulus
        self.public_text = base64.b64encode(spki).decode("ascii")
        body = b'{"selfTest":true}'
        try:
            signature = await self._run_sign(signed_bytes("server-proof", body))
        except SignFailed as e:
            if e.cause == "tools":
                raise Unusable("tools") from None
            raise Unusable("self-test") from None
        if not checks(modulus, signed_bytes("server-proof", body), signature):
            raise Unusable("mismatch")

    def _mode(self) -> None:
        try:
            mode = self.path.stat().st_mode & 0o777
            if mode & 0o077:
                self.path.chmod(0o600)
                log.info("Made %s readable by tapiOca alone again", KEY_FILE)
        except OSError as e:
            log.warning(
                "Couldn't make %s readable by tapiOca alone (%s): its folder may not allow it",
                KEY_FILE,
                e.strerror or e,
            )

    async def _public(self) -> bytes:
        try:
            proc = await spawn(
                OPENSSL, "pkey", "-in", str(self.path), "-passin", "pass:", "-pubout", "-outform",
                "DER", stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=environment(),
            )  # fmt: skip
        except FileNotFoundError:
            raise Unusable("tools") from None
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            raise Unusable("not-a-key")
        return out

    async def _make(self) -> bytes:
        """A new key, written once: a temporary file linked into place."""
        log.info("Making tapiOca's key (this can take a few seconds)")
        try:
            proc = await spawn(
                OPENSSL, "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072",
                "-pkeyopt", "rsa_keygen_pubexp:65537", stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=environment(),
            )  # fmt: skip
        except FileNotFoundError:
            raise Unusable("tools") from None
        try:
            pem, _ = await asyncio.wait_for(proc.communicate(), MAKE_LIMIT_S)
        except TimeoutError:
            self._stop(proc)
            raise Unusable("self-test") from None
        if proc.returncode != 0 or not pem.startswith(b"-----BEGIN PRIVATE KEY-----"):
            raise Unusable("tools" if proc.returncode in (125, 126, 127) else "self-test")
        return await asyncio.to_thread(self._place, pem)

    def _place(self, pem: bytes) -> bytes:
        self.folder.mkdir(parents=True, exist_ok=True)
        temp = self.folder / f".{KEY_FILE}.{secrets.token_hex(6)}.new"
        try:
            self._write_new(temp, pem)
        except OSError as e:
            with contextlib.suppress(OSError):
                temp.unlink()
            log.warning("Couldn't save tapiOca's key (%s)", e.strerror or e)
            raise Unusable("unsaved") from None
        try:
            os.link(temp, self.path)
        except FileExistsError:
            # (Another process made one first: that's the key, never replaced.)
            temp.unlink()
            return read_file(self.path)
        except OSError as e:
            temp.unlink()
            if e.errno not in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV):
                raise Unusable("unsaved") from None
            # (A mount with no hard links: written in place, once.)
            try:
                self._write_new(self.path, pem)
            except FileExistsError:
                return read_file(self.path)
            except OSError:
                with contextlib.suppress(OSError):
                    self.path.unlink()
                raise Unusable("unsaved") from None
        else:
            temp.unlink()
        try:
            flush_folder(self.folder)
        except OSError as e:
            log.warning("Couldn't flush the data folder after saving the key (%s)", e.strerror or e)
        log.info("tapiOca's key is made")
        return pem

    @staticmethod
    def _write_new(path: Path, data: bytes) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)

    # Signing -----------------------------------------------------------------

    async def sign(self, purpose: str, body: bytes) -> bytes:
        """The signature over `tapioca/1 <purpose>\\n<body>`, checked before
        it's given. ValueError for a purpose it doesn't sign; NotReady with
        no key; SignFailed when it didn't come, or didn't check."""
        data = signed_bytes(purpose, body)
        if self.state != "ready":
            raise NotReady()
        try:
            signature = await self._run_sign(data)
        except SignFailed as e:
            self._failed(e.cause)
            raise
        if not checks(self._modulus, data, signature):
            changed = await self._changed()
            self._failed("changed" if changed else "fault")
            raise SignFailed("changed" if changed else "fault")
        self._failures = 0
        return signature

    def _failed(self, cause: str) -> None:
        if cause == "changed":
            self.alert(SAID["changed"])
            return
        self._failures += 1
        if self._failures >= FAILURES_FOR_ALERT:
            self.alert(SAID["tools" if cause == "tools" else "fault"])

    async def _changed(self) -> bool:
        """Whether the key file's public key isn't the start's any more."""
        try:
            return await self._public() != self._spki
        except Unusable:
            return True

    async def _run_sign(self, data: bytes) -> bytes:
        try:
            proc = await spawn(
                NICE, "-n", "10", OPENSSL, "dgst", "-sha256", "-sign", str(self.path), "-passin",
                "pass:", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=environment(),
            )  # fmt: skip
        except FileNotFoundError:
            raise SignFailed("tools") from None
        except OSError as e:
            log.warning("Couldn't start openssl to sign (%s)", e.strerror or e)
            raise SignFailed("fault") from None
        try:
            out, _ = await asyncio.wait_for(proc.communicate(data), SIGN_LIMIT_S)
        except TimeoutError:
            self._stop(proc)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), 1)
            log.warning("openssl took over %s seconds to sign, and was stopped", SIGN_LIMIT_S)
            raise SignFailed("fault") from None
        if proc.returncode in (125, 126, 127):
            raise SignFailed("tools")
        if proc.returncode != 0:
            raise SignFailed("fault")
        return out

    @staticmethod
    def _stop(proc) -> None:
        """Stops a process by its PID (only one that has a PID and is still
        running)."""
        pid = getattr(proc, "pid", None)
        if not pid or getattr(proc, "returncode", None) is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)

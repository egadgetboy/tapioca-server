"""Access -> Reconnect apps (1.43.0): a one-time code an Admin makes, so an
app whose server's key changed (a restore onto a new computer, the key
file deleted) can trust the new key (the apps repo's
docs/threat-models/server-proof.md, section 6).

- 12 characters of the linking codes' alphabet (links.ALPHABET: 32
  letters and digits with no 0, 1, I or O, so 60 bits), shown as
  ABCD-EFGH-JKMN. It works for 10 minutes, for any number of devices; End
  it ends it early, and a new one ends the old. At most 5 are made in 10
  minutes.
- Kept in memory only: never logged, never in the database, and a restart
  ends it. Only the Admin who made it sees it again.
- A proof asked with `reconnect: true` always gets `reconnectSalt` (32
  fresh random bytes) and `reconnect`: while a code is active,
  HMAC-SHA256(code, "tapioca/1 reconnect\\n" + salt + "\\n" + nonce + "\\n" +
  key), the salt and key as the answer's base64; otherwise 32 random bytes.
  The two look the same either way. The app works the MAC out from the
  code typed and never sends the code.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from collections import deque

from . import links

LENGTH = 12
LASTS_S = 10 * 60
MADE_MOST = 5  # (codes made in LASTS_S)

clock = time.monotonic


class TooMany(Exception):
    """Five codes were made in the last 10 minutes."""


def shown(code: str) -> str:
    return "-".join(code[i : i + 4] for i in range(0, LENGTH, 4))


class Reconnect:
    def __init__(self) -> None:
        self._code = ""
        self._ends = 0.0
        self._by: int | None = None
        self._made: deque[float] = deque()

    def make(self, by: int | None) -> tuple[str, float]:
        """A new code (ending any other), as shown, and the seconds it has."""
        now = clock()
        while self._made and now - self._made[0] >= LASTS_S:
            self._made.popleft()
        if len(self._made) >= MADE_MOST:
            raise TooMany()
        self._made.append(now)
        self._code = "".join(secrets.choice(links.ALPHABET) for _ in range(LENGTH))
        self._ends, self._by = now + LASTS_S, by
        return shown(self._code), LASTS_S

    def end(self) -> None:
        self._code, self._ends, self._by = "", 0.0, None

    def active(self) -> str:
        if self._code and clock() >= self._ends:
            self.end()
        return self._code

    def status(self, who: int | None) -> dict:
        """What the page shows: whether one is active and for how long; the
        code only to the Admin who made it."""
        code = self.active()
        if not code:
            return {"active": False}
        said: dict = {"active": True, "seconds": max(0, round(self._ends - clock()))}
        if who is not None and who == self._by:
            said["code"] = shown(code)
        return said

    def fields(self, nonce: str, key_text: str) -> dict[str, str]:
        """The two fields every reconnect proof carries."""
        salt = base64.b64encode(os.urandom(32)).decode("ascii")
        code = self.active()
        if code:
            message = f"tapioca/1 reconnect\n{salt}\n{nonce}\n{key_text}".encode("ascii")
            mac = hmac.new(code.encode("ascii"), message, hashlib.sha256).digest()
        else:
            mac = os.urandom(32)
        return {"reconnectSalt": salt, "reconnect": base64.b64encode(mac).decode("ascii")}

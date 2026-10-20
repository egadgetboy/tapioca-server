# Pictures for the apps: every path to a picture, and its access check

From 1.42.0 (`app/applibrary.py`, `picture`; `app/pictures.py`). A picture is
served only after the same check a title's own page gets. Nothing kept (in
memory, on disk or drawn ahead) is ever served without it.

| Path | Where the picture comes from | Shared check | Limits check (a viewer with limits) |
|---|---|---|---|
| Kept in memory | `app_pictures` | `cat.check(key, kept library)`: the library known now wins; the kept one only while none is known | `must_see` with the title asked of the library (`cat.entry`), every time |
| Kept on disk, after a restart | `picture_disk`, then memory | As above: a library unshared since is refused (404) | As above |
| Made now | `make_picture` (Plex's resize, WebP, a Media folder of tapiOca's own) | Checked before making; making asks `cat.entry`, which refuses what isn't shared | Checked before making |
| A changed one kept until its replacement is made | The kept one, sent only when the new one can't be made just now (503) | Checked first, as above | Checked first, as above |
| Drawn ahead | Made and kept, never sent | Not sent to anyone, so no check; a later request is checked as above | As above |
| A Station's logo with `w` | `/channel-icon/{n}.png`, `/hls/k/{key}/{n}/logo.png` | As without `w`: the tuner's logos are open to the home network, and the app's own address checks its key | Stations someone may not see aren't listed to them; their logos aren't private |

What a kept library can't do: vouch for a title in a library that's no
longer shared (the shared libraries are checked every time), or for a title
someone may not see (limits are judged from the title itself). Plex's rating
keys belong to one library, and a Media folder of tapiOca's own gives its
titles keys of their own, so a title can't move to another library under the
same key. A different Plex at the same address can show the old server's
picture for a key both have until its next list says the picture's version:
the picture of a title of the same key, never one the viewer may not see.

Nothing kept is named by a title or a file: names are hashes of the source,
the key, the kind, the width, the format and the encoder's version; the
index holds those names, types, ETags, hashed versions and library IDs.

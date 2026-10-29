# Sign out always takes you off the list: threat model and every path

Class D (sign-in, a device's list of people, stored data), for tapiOca
1.44.3, a security patch with nothing new on screen. Written before any
code, and audited three times before it (no P0 or P1 left open). This is the
server's half of the record; the apps need no change, since each already
sends its remove with the sign-in it holds and counts a 2xx done.

## 1. The problem

A person on a shared device presses Sign out. Their app sends
`POST /api/internal/picker/remove` with the device's key and the person's
sign-in. Before 1.44.3 the remove wasn't one of the Gate's open routes, so
for a sign-in tapiOca no longer took, the Gate answered 401 "Sign in to
tapiOca" before the handler ran, and no one was removed. The apps let a
remove's 401 go and show Who's Tuning In?, with the person still on it.

A device's sign-in stops being taken for many reasons, which the app hears
of only at its next request:

- the person's password changed, on any device (every sign-in they have ends);
- their role changed;
- a new PIN, a PIN removed, or an Admin choosing Full sign-in (the sign-ins
  the old PIN made);
- a device's sign-in unused for a day (or 30 days since last seen);
- the person's 21st sign-in ending their oldest;
- another person signing in on the device (one sign-in per device);
- an Admin ending it, a trusted network forgotten, old ones pruned;
- a restored backup, or the reset-access file;
- a changed password's own answer lost, late or cut off, so the app's remove
  goes with the old sign-in.

So a careful person's path failed: change the password on a phone, walk to
the TV, press Sign out. They stayed on Who's Tuning In?, and with no PIN,
anyone at that device could pick them: picking needs only the device's key,
so the new password didn't help. **A Medium** (a shared device; no data
leaves it).

## 2. The design

**The newest sign-in tapiOca gave a person on a device, and the one a
changed password renewed it from, still count for one thing after they
end: taking that person off that device's list, while they're on it.**
Nothing else.

**What's kept:** a table, `device_sign_ins`, with one row per person per
linked device: the hash of their newest sign-in there (as `sessions` keeps
it), the hash it was renewed from when a changed password made it on that
device (else none), and when it was made. Its key is (device, person), with
foreign keys to `linked_devices` and `users`, `ON DELETE CASCADE`. It's
written in `Database.add_session`'s transaction, the only writer of
`sessions`, whenever the sign-in has a device, so the row is always the
newest. "Renewed from" lasts until the new sign-in's first use five minutes
or more after it was made (the first time tapiOca notes it seen): no honest
app sends the old one by then, since each stores the new sign-in before it
uses it.

**The Gate:** the remove joins the Gate's open routes, beside the picker's,
where the device's key says which device. Everything that runs before the
Gate's decision still runs for it (HTTPS from outside, the body limit, the
page-origin check). The handler decides, in this order:

1. **The device** (`this_device`, as before): 400 with signing in off; 401
   for no key or an unknown one; 403 for a trusted network's device away
   from that network.
2. **The token:** the Bearer header only, never a browser's cookie. An API
   token gets exactly the Gate's answer for it, which the Gate keeps for an
   open route instead of throwing it away: 401 for an unknown one, 403 for a
   known one. None: 401 "Sign in to tapiOca".
3. **A live sign-in:** the person off this device's list, the sign-in sent
   ended, and now, in the same transaction, every sign-in of theirs on this
   device ended and their row forgotten.
4. **Otherwise** one Database method, in one transaction under the
   database's lock: the row for this device whose newest hash, or "renewed
   from" hash, is the token's; its person on this device's list anywhere,
   at home or away (the one roster decision, `devices.on_picker`, given the
   person and how they're on it, read under the method's lock). Found: the
   person off the list, every sign-in of theirs there ended, the row
   forgotten, `{"ok": true}`, and the access log's line.
5. **Otherwise** 401 "Sign in to tapiOca".

**Only the remove reads the table** (a census test: it appears in `app/`
only in `db.py`).

**Backups never hold it:** `copy_database` empties it with `sessions`, so
the nightly backups, the page's downloads and a before-restore copy never
say who signed in where. A later update's before-update copy keeps it, as it
keeps sign-ins. A backup 1.44.2 makes of an updated database does hold its
rows, and the rebuild below clears them when it's restored.

**The access log** says "Pat took themselves off Living Room TV", with
"(their sign-in there had ended)" when it had. No token or hash is written.

**Filled, and rebuilt when it can't be trusted.** One pure predicate
(`device_sign_ins_fill`) decides, and both `changes_needed` and `_upgrade`
call it, so the backup and the rebuild always agree. It fills the table
afresh from `sessions` (each person's newest sign-in on each linked device,
joined with `linked_devices` and `users`) whenever:

- the table is new, or its fill's mark is missing (a start stopped before
  the fill finished);
- an older version ran since: `version_started` parses below 1.44.3 (a named
  constant, never `__version__`), or doesn't parse; empty says nothing (a
  bare open, or a database last run before 1.34.0);
- a device's sign-in has no row whose newest hash is it: other code signed
  someone in there (a version before 1.34.0, or an unreleased build).

Its mark is written by a plain statement after the rows, in the fill's own
transaction. A second start changes nothing.

## 3. What must hold

1. An ended sign-in authenticates nothing but its own person's remove from
   its own device, while they're on its list. Every other route, with that
   token, answers as before (the Gate's 401).
2. Only the device that held it, and only its newest (or the one a changed
   password renewed it from). An older sign-in of the person's on this
   device, another device's, a browser's, an API token, or a token tapiOca
   never gave: refused.
3. The remove only takes away: it never signs anyone in or returns a
   sign-in.
4. It never relaxes a network's binding: a trusted network's device away
   from it is refused by `this_device` (403), as before.
5. No secret kept or written: hashes as `sessions` keeps them; never in a
   backup 1.44.3 makes; never in a log line.
6. Nothing grows: one row per person per device.
7. The update is safe: backed up first; filled once, and rebuilt whenever
   it can't be trusted; 1.44.2 opens the updated database and ignores the
   table.
8. No error hidden: a database error on the remove isn't caught. It's
   logged and answers the bare 500, which every app retries, never a 401
   and never a 500 with a sentence, which they'd take as final.
9. The apps don't change.

## 4. Every path

"Removed": off this device's list, every sign-in of theirs on this device
ended, their row forgotten, `{"ok": true}`.

| # | The remove's sign-in | Before 1.44.3 | 1.44.3 |
| --- | --- | --- | --- |
| P1 | live, this device's | removed | removed |
| P1b | live, another device's (the phone's), with this device's key | off this device's list, the phone's sign-in ended | as before, and every sign-in of theirs on this device ended |
| P2 | the newest, ended by a password change anywhere | 401, still listed | removed |
| P3 | the newest, ended by a role change | 401 | removed |
| P4 | the newest, ended by a new PIN, a PIN removed, or Full sign-in | 401 | removed |
| P5 | the newest, unused for a day | 401 | removed |
| P6 | the newest, ended as the person's 21st sign-in came | 401 | removed |
| P7 | the newest, ended by an Admin, a forgotten network, or pruned | 401 | removed |
| P8 | the newest, ended because someone else signed in on this device | 401 | removed |
| P9 | the one a changed password renewed from, its answer lost | 401; the new one left live, held by no one | removed, the new one ended too |
| P10, P11 | the one renewed from, after Sign out's time ran out, or a network change canceled the password's answer | 401 | removed |
| P11b | the newest, ended, of someone listed only at home, sent from away | 401 | removed (the list checked anywhere) |
| P12 | an older sign-in of theirs on this device, or the one renewed from once the new one has been seen | 401 | 401 |
| P13 | an ended sign-in of another linked device | 401 | 401 |
| P14 | a browser's cookie with this device's key | its person removed | 401 (Bearer only) |
| P14b | a browser's sign-in as a Bearer token | 401 | 401 |
| P15 | a known API token, with this device's key | 403 | 403, the Gate's own decision |
| P15b | an unknown API token, with this device's key | 401 | 401 |
| P15c | an API token without a key | 401 or 403 | 401 (the key is asked first) |
| P16 | a token tapiOca never gave, or none | 401 | 401 |
| P17 | one gone from `sessions` before the update | 401 | 401 |
| P18 | the person already off this device's list | 401 | 401 |
| P19 | the person deleted | 401 | 401 (cascade) |
| P20 | the device unlinked | 401 | 401 (cascade) |
| P21 | a trusted network's device, away from that network | 401 | 403, the device's own answer, asked first; still listed |
| P22 | the device's key wrong or missing | 401 | 401 |
| P23 | signing in off on the server | 400 | 400 |
| P24 | after going back to 1.44.2 and forward again: an old row's token | — | 401: rebuilt at the start |
| P24b | after going back and forward: a sign-in 1.44.2 made, ended since | — | removed, if it was still in `sessions` at the rebuild; else 401 |
| P25 | the newest, after a restored backup | 401 | 401 |
| R1 | two removes at once, for the same person | — | one removes; the other finds nothing (one transaction) |
| R2 | a remove racing a pick of the same person | — | as before with a live remove: the person can end up signed in on the device but off its list until they sign out |
| R3 | a remove while a changed password is being checked | — | removed; the password then makes a sign-in on this device for someone off its list, held by no one |

The same token anywhere else (each of P2 to P11): the Gate's 401, as before.

## 5. The update and going back

- **Up:** `changes_needed` lists the new table and its index, so the
  database is copied first; `_upgrade` makes and fills the table once.
- **Back to 1.44.2:** it doesn't read the table, and opens the database as
  it is; its sign-ins write no row and its removes forget none. Or put the
  before-update copy in place, as the notes' Rolling back says.
- **Forward again:** `version_started` names 1.44.2, so the table is
  backed up and rebuilt from `sessions` before anything reads it.
- **`tools/upgrade_check.py --from v1.44.2`:** after the update, the linked
  device's app sign-in has its row; a sign-in a password changed on another
  device ended still takes its person off; and with 1.44.2 started on the
  database as it is, a sign-in made there and left unused for a day, 1.44.3
  started again rebuilds: the sign-in from before is refused (P24), and the
  one 1.44.2 made takes its person off (P24b).

## 6. The security suite

- **A new class, "device":** the remove leaves "watcher". With no key,
  every vantage gets 401; with the device's key, no sign-in or a made-up
  one, 401; an API token, 403; another device's ended sign-in, 401; an
  older sign-in of the person's, 401; this device's own newest ended
  sign-in, 200, once.
- **The open routes pinned:** a test of the Gate's open list, each member
  with its reason, and a structural check: every route classed watcher,
  user or admin is outside it, and every device route inside it (a
  handler's own 401 would otherwise pass a watcher's checks).
- **The census:** where `device_sign_ins` may appear.
- **The live harness** (`tools/attack_check.py`): a password changed on
  another device; the ended sign-in refused on the apps' other routes, with
  another device's key, as an API token or a made-up one; then taking its
  person off its own device, once.
- **The manifest** (`docs/security/manifest-1.44.3.md`).

## 7. Known limits

Each is the behavior before 1.44.3, unchanged, with nothing new on screen:

- **A sign-in gone from `sessions` when the table is filled** (P17, P24b),
  **or after a restored backup** (P25): its remove gets a 401 once; the
  person signs in once more to sign out.
- **A start stopped between the schema and the fill** is repaired at the
  next start (the mark is missing); one stopped after a rebuild and before
  the version is noted rebuilds again, harmlessly, with a second copy.
- **A remove racing a pick** (R2) and **a remove during a changed
  password's check** (R3), as in §4.
- **A trusted network's device, away from that network** (P21): the person
  comes off when they sign out on that network.
- **The TV asked first:** if the device asks tapiOca anything before Sign
  out, it hears the 401 and goes back to Who's Tuning In? with no goodbye;
  the person stays listed until they pick themselves and sign out. That's
  the design (a locked viewer goes back there), and outside what this
  release promises.
- **Two installs with one key** (only by copying the key): one install's
  Sign out ends the other's sign-in for the same person.

## 8. The ten gates

- **FG-01 Product contract.** Sign out takes the person off the device's
  list, as it says; nothing new on screen; no new route.
- **FG-02 Identity and ownership.** A row belongs to the device and person
  its sign-in was made for; only the remove reads it.
- **FG-03 Data and migration.** One table and index, backed up before,
  filled once and rebuilt whenever it can't be trusted, cascaded with
  devices and people, never in a backup 1.44.3 makes.
- **FG-04 Auth and privacy.** §3's rules 1 to 5; one narrow new way in,
  stated: an ended sign-in with the device's key reaches one write, its own
  person's removal from that device.
- **FG-05 Failures and recovery.** Every path is a row (§4); a database
  error answers the bare 500 and is logged.
- **FG-06 Integration contracts.** `docs/internal-api.md` says it; the apps'
  contract is unchanged.
- **FG-07 Performance and scale.** One indexed lookup on a remove that
  isn't signed in; one row written per device sign-in; one indexed update at
  a renewed sign-in's first "seen"; one query at each start; one row per
  person per device.
- **FG-08 Platform feasibility.** Python and SQLite as before; no
  dependency.
- **FG-09 Verification.** `tests/test_signout_ends.py` (every path, the
  races, the predicate as a table, the fill and rebuild, backups, the
  census, the bare 500), the security suite, `upgrade_check`, the soak.
- **FG-10 Operations.** The access log's line; no playback touched.

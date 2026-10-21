# Security

## Which versions get fixes

Only the newest release. tapiOca is in beta, so a fix comes as a new release, not as a change to an older one. Keep tapiOca up to date (README: [Updating](README.md#updating)).

## Reporting a problem

Please report a security problem privately, never in a public issue:

1. Open tapiOca's page on GitHub: <https://github.com/egadgetboy/tapioca-server>.
2. Choose the **Security** tab, then **Report a vulnerability**.
3. Say what you found, which version, and the steps that show it.

Only tapiOca's maintainer sees the report.

If you don't see **Report a vulnerability**, open an issue that says only "I've found a security problem," with no details. The maintainer will answer there with a private way to send it.

## What happens next

- You'll get a reply within 7 days.
- Once the problem is confirmed, the fix comes in the next release, as soon as it's ready and tested. Its release notes say what was fixed.
- You'll be credited in the notes if you'd like to be.

Please give the fix time to ship before you tell anyone else about the problem.

## What's in scope

tapiOca itself: the server, its page and its API, and tapiOca's own apps. Problems in Plex, Jellyfin, FFmpeg or Debian belong with those projects.

## How tapiOca is tested

Every release runs tapiOca's security suite before it's published (`python -m tools.security_suite`): every address tapiOca serves, from every kind of visitor; sign-in tokens; every connection tapiOca makes to another machine; file paths; and known ways of chaining small problems together. A release with a serious finding isn't published. Each finding becomes a test that stays, so it can't come back.

## Signs that a tapiOca server was broken into

Things to look for if you think your server was compromised:

- In the **Logs** tab: sign-ins you don't recognize, Admins you didn't add, or alert addresses, Sonarr or Radarr addresses you didn't type.
- In the **Access** tab: devices, apps or API tokens you don't recognize.
- In the data folder: files you didn't expect, outside `backups`, `cache` and the folders tapiOca made. tapiOca never writes programs or scripts there.
- Processes in tapiOca's container other than tapiOca itself and the `ffmpeg` and `ffprobe` it starts.
- High CPU while nothing is playing or converting.

If you find any: stop tapiOca, restore a backup from before the problem, change every Admin password, remove every linked device and API token, and change your Plex password. Then update to the newest release.


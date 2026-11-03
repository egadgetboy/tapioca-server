# Backups, updating and rolling back

## Backups

tapiOca backs itself up about 15 minutes after it first starts, then every night at about 3 AM, and keeps the newest 7 in `data/backups`. A backup holds your Stations and schedules, every setting, the Broken files list, the tuner's identity (so Plex still knows it), your logos, people and their passwords (as hashes), and viewing stats. It leaves out Intro Bumper videos, which stay in `data/bumpers`. Your Plex token is in tapiOca's app settings, not its data folder.

On the **Setup** tab, under **Backups**:

- **Download a backup** makes one now and downloads it (it also counts toward the 7 kept).
- **Restore a backup…** replaces everything above with a backup's copy.
- **The list** shows each backup, with **Download**.

> **Important:** Keep backup files private. A backup holds Sonarr's and Radarr's API keys, your alert web addresses (a webhook address is a secret) and password hashes. Only sign-ins and devices are left out.

**Restoring.** Choose **Restore a backup…**, pick the `.zip`, and confirm. tapiOca checks that it's a genuine tapiOca backup, saves what you have as a "before restore" backup, restarts, and puts the backup in place. Anyone watching is disconnected, and everyone signs in again as the people in the backup. A backup with no people turns sign-in off, so tapiOca asks first.

> **Important:** Keep the container's restart setting (`restart: unless-stopped`). A restore restarts tapiOca, and Docker must start it again.


### Knowing when a new version is out

tapiOca never updates itself. With **Tell me when a new tapiOca is out** ticked, under **New versions** on the **Setup** tab, it asks GitHub every 4 hours whether a newer version is out, sending only its version (GitHub sees your internet address, as any website does). It's off until an Admin answers, in the setup's last step or here. **Check now** looks right away. tapiOca 1.44.2 and 1.44.3 can't find newer versions (they ask GitHub by the number of a repository that's gone): update them by hand, as below.

While a newer version is out, Admins see a banner: "tapiOca 1.45.0 is available," with the steps for your install, **What's new**, **Back up now**, **All the steps** and **Not now** (which hides it for that version, in that browser). A "tapiOca 1.45.0 is out" pill stays in the header.

## Updating

Back up first (**Back up now**, or **Download a backup**), then:

| Install | To update |
| --- | --- |
| TrueNAS SCALE | In **Apps**, open **stationplay**, and choose **Update** if it's offered. If not, run `sudo docker pull ghcr.io/egadgetboy/tapioca-server:latest` in **System → Shell**, then **Edit** the app and **Save**. (Not confirmed yet.) |
| Docker Compose, Docker Desktop | In the compose file's folder, run `docker compose up -d --pull always`. |
| Unraid | On the **Docker** tab, **Check for Updates**, then **apply update** on **stationplay**. |
| Synology | Over SSH, in tapiOca's folder, run `sudo docker compose up -d --pull always` (on older systems, `sudo docker-compose pull`, then `sudo docker-compose up -d`). (Not confirmed yet.) |
| docker run | `docker pull ghcr.io/egadgetboy/tapioca-server:latest`, `docker rm -f stationplay`, then your `docker run` command. |

Your data folder, and so your Stations, settings, logos, videos and lists, carries over. Existing Stations keep their settings. The page reloads with the new version, and the setup may open once with new questions.

**A database copy first.** Before an update changes the database, tapiOca copies it to `data/backups/before-<version>-<date>.db`, and keeps the newest 3. If it can't (a full disk, say), it changes nothing and stops: make room, then start it again. 1.44.3 added one table, so updating to it or later from an earlier version makes this copy. 1.44.4 changes nothing in the database.

**Staying on one version.** Change the end of `image:` from `:latest` to `:1.44` (fixes for 1.44 only) or `:1.44.4` (exactly that). Change it back to `:latest` to follow every release. Images exist from 1.34.0 on.

**From before 1.34.0,** when tapiOca built itself, switch once: back up, delete the `build:` block from your file, set `image:` to `ghcr.io/egadgetboy/tapioca-server:latest`, add `TAPIOCA_INSTALL` for your install, and start it again. Your data carries over.

## Rolling back

1. **Stop tapiOca** (in TrueNAS's **Apps**, with `docker compose stop`, `docker stop stationplay`, or on Unraid's **Docker** tab).
2. **Put back the database copy,** if the update made one. In the data folder:

   ```
   sudo cp backups/before-1.44.3-20261101-153000.db stationplay.db
   sudo rm -f stationplay.db-wal stationplay.db-shm
   ```

   (With your copy's name. In PowerShell, use `Copy-Item` and `Remove-Item`.)
3. **Ask for the previous image,** such as `ghcr.io/egadgetboy/tapioca-server:1.44.2`, in `image:` (or Unraid's **Repository**), and start it.

> **Important:** The copy made before an update holds everything, sign-ins included. Putting it back brings back sign-ins ended since the update (Sign outs included), old passwords and PINs, and people removed since. Check the **Access** tab afterward. Going back to 1.44.2 also brings back the Sign out problem 1.44.3 fixed (see People, sign-in and Viewing Levels), and going back to 1.44.2 or 1.44.3 brings back an update check that can't find newer versions.

Everyone stays signed in, and anything changed since the update is lost. **From 1.44.4 to 1.44.3, or from 1.44.3 to 1.44.2,** skip step 2: the older one runs on this database as it is, and nothing is lost. Each release is signed, with `SHA256SUMS` beside it (the README's "Checking a release's signature" has the commands).

# Installing tapiOca

tapiOca comes as a ready-made Docker image, `ghcr.io/egadgetboy/tapioca-server`, for x86-64 and ARM64. Each version's image is the exact one that passed its tests. You need one file that tells Docker how to run it:

| File | For |
| --- | --- |
| `tapioca-server.yaml` | TrueNAS SCALE |
| `docker-compose.yml` | Docker Compose, Synology, Docker Desktop and everything else |
| `unraid/stationplay.xml` | Unraid's **Docker** tab (in the repository's `unraid` folder) |

Download the first two from the latest release on GitHub (`github.com/egadgetboy/tapioca-server/releases/latest`), under **Assets**. Both ask for `:latest`, the newest release. Docker downloads it when you install, and again only when you update, so tapiOca never needs the internet to start. Each file sets `TAPIOCA_INSTALL`, which tells tapiOca's page how your kind of install updates.

A few names stay `stationplay`, tapiOca's earlier name: the container, the app's name on TrueNAS and Synology, the Unraid template, the data folder in the examples, and the database, `stationplay.db`. Use them as shown.

> **Note:** Each system's steps follow that system's own documented way, and not every one has been confirmed on it yet. If a step doesn't match what you see, open an issue on GitHub.

### Before you start

1. **Where your media lives** on the Docker host, such as `/mnt/tank/media`.
2. **The user tapiOca runs as,** as `UID:GID`, such as `1000:1000`. It must be able to read your media and write to tapiOca's data folder. `ls -ln /path/to/media` shows the owner's numbers in the third and fourth columns.
3. **With Plex: its address,** such as `http://192.168.1.10:32400`. Use the server's network IP, never `localhost`.
4. **With Plex: your Plex token.** In Plex Web, open any movie or episode and choose **⋯ → Get Info → View XML**. The new page's address ends with `X-Plex-Token=…`: that value is your token.

**No Plex?** Delete the `PLEX_URL` and `PLEX_TOKEN` lines (on Unraid, clear both), then add a Media folder on tapiOca's page after it starts.

> **Important:** Keep your Plex token private: it gives full access to your Plex server. tapiOca never shows it on its page or in its logs.

## TrueNAS SCALE

This needs TrueNAS SCALE 24.10 (Electric Eel) or later.

1. **Make the data folder.** In **System → Shell**, run (with your pool's name for `tank`; paths are case-sensitive):

   ```
   sudo mkdir -p /mnt/tank/apps/stationplay/data
   sudo chown -R 1000:1000 /mnt/tank/apps/stationplay/data
   ```

2. **Install the app.** Go to **Apps → Discover Apps → ⋮ → Install via YAML**. Name it `stationplay`, and paste the contents of `tapioca-server.yaml`.
3. **Change every line marked `<- CHANGE`:** the two folders (only the part before `:/data` or `:/media`), `PLEX_URL` and `PLEX_TOKEN` (or delete both), `TZ` (such as `America/Chicago`), and `user:` if your media belongs to another user. TrueNAS's apps user is `568:568`: if you use it, `chown` the data folder to it too. Leave `MEDIA_DIR` as `/media` and `TAPIOCA_INSTALL` as `truenas`.
4. **Check the GPU lines.** The Intel and AMD lines are on in this file. If the server has no Intel or AMD graphics, delete them, or the app won't start.
5. **Save.** TrueNAS downloads the image and starts tapiOca.
6. **Open** `http://<your-nas-ip>:3310`. The first-time setup starts.

## Docker Compose (Linux, Proxmox, Raspberry Pi)

1. Make a folder, fetch the compose file, and make the data folder:

   ```
   mkdir -p ~/stationplay && cd ~/stationplay
   curl -fLO https://github.com/egadgetboy/tapioca-server/releases/latest/download/docker-compose.yml
   mkdir -p data && sudo chown -R 1000:1000 data      # use your UID:GID
   ```

2. Edit `docker-compose.yml`, changing every line marked `<- CHANGE`. Leave `TAPIOCA_INSTALL` as `compose`. For a GPU, uncomment its lines.
3. Run `docker compose up -d`, then open `http://<server-ip>:3310`.

- **Proxmox:** run Docker in a virtual machine or LXC container, with your media mounted inside it. For an Intel or AMD GPU in LXC, pass `/dev/dri` through first.
- **Raspberry Pi:** use a 64-bit OS. Its GPU can't be used, so start with the 480p picture size.

## Synology

This needs DSM 7.2 or later, with **Container Manager**.

1. In **Control Panel → Terminal & SNMP**, turn on SSH.
2. In **File Station**, make `/volume1/docker/stationplay` with a `data` folder inside, and upload `docker-compose.yml` there.
3. Over SSH, find your IDs with `id` (such as `uid=1026 gid=100`), then run `sudo chown -R 1026:100 data` in that folder.
4. In `docker-compose.yml`, set `user: "1026:100"` and `TAPIOCA_INSTALL: "synology"`, and change the other `<- CHANGE` lines. Media is usually under `/volume1/`.
5. In **Container Manager**, open **Project → Create**, name it `stationplay`, choose that folder, and finish. (Or run `sudo docker compose up -d` there over SSH.)

tapiOca updates over SSH. On older systems without `docker compose`, use `docker-compose`, with a hyphen; to update there, run `sudo docker-compose pull`, then `sudo docker-compose up -d`. Intel models with built-in graphics can use the GPU.

## Unraid

1. In the terminal, make the data folder, owned by Unraid's `99:100`, and add the template:

   ```
   mkdir -p /mnt/user/appdata/stationplay/data
   chown -R 99:100 /mnt/user/appdata/stationplay/data
   curl -fL -o /boot/config/plugins/dockerMan/templates-user/my-stationplay.xml \
     https://raw.githubusercontent.com/egadgetboy/tapioca-server/main/unraid/stationplay.xml
   ```

2. On the **Docker** tab, choose **Add Container**, and pick **stationplay** under **Template**.
3. Fill in your time zone, your media folder (such as `/mnt/user/media`), and Plex's address and token (or clear both). Leave `TAPIOCA_INSTALL` as `unraid`.
4. Choose **Apply**.

For an Intel GPU, turn on **Advanced View** and set **GPU** to `/dev/dri`. If the **Video encoding** line on tapiOca's **Setup** tab names a group, add `--group-add <that number>` to **Extra Parameters**. To use the compose file instead, install the **Compose Manager** plugin, follow the Docker Compose steps with `99:100`, and set `TAPIOCA_INSTALL` to `compose`.

## Windows and macOS

tapiOca runs in **Docker Desktop**, and the computer must stay on and awake.

1. Install and start Docker Desktop.
2. Make a folder, such as `C:\tapioca`, with a `data` folder inside, and put `docker-compose.yml` there.
3. In it, delete the `user:` line, set `TAPIOCA_INSTALL` to `"docker-desktop"`, set your media folder with forward slashes (such as `D:/Media:/media:ro`), and change the other `<- CHANGE` lines.
4. In a terminal, in that folder, run `docker compose up -d`.

Allow port 3310 through the firewall if asked. Only an NVIDIA GPU on Windows (through WSL 2) can be used. If Plex runs on Windows, tapiOca can't read its `D:\…` paths, and streams those files from Plex instead. Docker Desktop hides each device's address, so trusted networks can't work there.

## docker run

Make a folder with a `data` folder inside, then run, with your own settings:

```
docker run -d --name stationplay --restart unless-stopped --init \
  --user 1000:1000 -p 3310:3310 -p 3311:3311 \
  -e TAPIOCA_INSTALL=docker-run \
  -e PLEX_URL=http://192.168.1.10:32400 -e PLEX_TOKEN=paste-your-plex-token-here \
  -e TZ=America/Chicago -e PORT=3310 -e PUBLIC_PORT=3311 \
  -e MEDIA_DIR=/media -e HW_ACCEL=auto \
  -v "$PWD/data:/data" -v /path/to/your/media:/media:ro \
  --security-opt no-new-privileges:true --cap-drop ALL \
  --log-opt max-size=10m --log-opt max-file=3 \
  ghcr.io/egadgetboy/tapioca-server:latest
```

Save the command: you'll run it again each time you update. Without Plex, remove its two lines. Without the public port, remove `-p 3311:3311` and `-e PUBLIC_PORT=3311`. For Intel or AMD, add `--device /dev/dri:/dev/dri --group-add <group>`; for NVIDIA, `--gpus all`.

> **Important:** Keep the restart setting (`--restart unless-stopped`, or `restart: unless-stopped`). Restoring a backup restarts tapiOca, and Docker must start it again.

## GPU encoding

A GPU makes tapiOca much lighter on your server, and lets more Stations play at once, 1080p included. tapiOca uses Intel and AMD graphics through VA-API (including Quick Sync) and NVIDIA through NVENC. At startup it test-encodes a short clip, and uses the first GPU that passes, NVIDIA first. Otherwise it uses the processor. The **Video encoding** line on the **Setup** tab says which, and why.

- **Intel or AMD:** the container needs `/dev/dri` and its group, under `devices:` and `group_add:`. Find the group with `ls -ln /dev/dri` (the group of `renderD128`). It's usually `107` on TrueNAS. If it's wrong, the **Video encoding** line names the right one.
- **NVIDIA:** install the NVIDIA driver and Container Toolkit (on TrueNAS, **Apps → Configure → Settings → Install NVIDIA Drivers**), then uncomment the `deploy:` block, or add `--gpus all`.
- **Choosing:** `HW_ACCEL` is `auto`, `nvidia`, `intel`, `amd` or `cpu`. With several GPUs, `HW_DEVICE` picks one.

**Safeguards.** A program or copy that fails on the GPU carries on from the same point on the processor. After 3 programs in a row fail on the GPU but play on the processor, tapiOca stops using it until it restarts. Stalls never count against the GPU, because a slow disk causes them too.

### How tapiOca reads Plex's files

tapiOca asks Plex where each file is, then reads it straight from disk. Mount your media at `/media`, and tapiOca matches the end of each Plex path to a file there (at least the file name and its folder). The **Media files** line on the **Setup** tab shows whether it works. Where it can't see a file, it streams it from Plex, which adds load to Plex. For unusual layouts, set `PATH_MAPPINGS`, such as `"/data/media:/media"` (several pairs separated by `;`).

### The two ports

- **3310** (`PORT`), the home port: the page at home, Plex's tuner, the guides, the playlist and the streams. Home network only.
- **3311** (`PUBLIC_PORT`), the public port: the page and apps from the internet, through a reverse proxy or tunnel. Remove it if you don't need it.

> **Important:** Never forward port 3310 on your router, or point a tunnel or reverse proxy at it. Its tuner and streams never ask for a password.

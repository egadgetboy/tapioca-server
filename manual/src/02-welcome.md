# Welcome to tapiOca

tapiOca is a media server you run at home and own. It turns your own movies and shows into live, always-on Stations with a real guide, and plays them on demand, as Media, in tapiOca's apps. There's no subscription, no cloud account and no ads. The server is free and open source, and runs in Docker on your own hardware.

### What it does

- **Your own live Stations.** Pick shows and movies, and a Station plays them around the clock, in episode order or shuffled, with a guide two days ahead. Make Stations one at a time, from a filter that keeps itself up to date, from Plex collections, or dozens at once.
- **Station extras.** Marathons, movie nights and time-of-day blocks; commercials and trailers from your own folders; Station ID cards, an Intro Bumper and an Up Next Banner; a logo, name or clock in the corner; nearly 1,000 original logos; and even loudness.
- **A bad file never stops the show.** A program that fails is tried again, then a stand-in fills its time. tapiOca checks files before they air and lists what's wrong. It can ask Sonarr or Radarr to replace a file.
- **Media in tapiOca's apps.** People browse, search and resume your shows and movies, at the best picture and sound each device can play.
- **With or without Plex.** tapiOca reads your folders itself, with details from NFO files, tags and names. Use it alone, beside Plex, or for what isn't in Plex.
- **Family limits in tapiOca's apps.** Everyone signs in as themselves. Viewing Levels set what each person can see. A shared TV opens on **Who's tuning in?**, with a PIN for each person.
- **Away from home,** through a VPN or your own reverse proxy with HTTPS.
- **Works with Plex and Jellyfin.** Your Stations also show up in other apps at home, as a tuner and a guide.

### tapiOca and Plex

Plex is optional. With your own Plex Media Server, tapiOca takes your shows and movies from it: details, artwork, and intro and credits markers. It reads the files straight from disk. Your Stations can also appear in Plex's **Live TV** guide, with tapiOca as a network tuner, which needs Plex Pass.

> **Note:** Plex's terms license Plex Media Server for personal use, on hardware and storage you own. Use tapiOca with your Plex server as those terms allow. Product names are the property of their owners.

### Private by design

- **Yours, at home.** No cloud account, and nothing to sign up for. People sign in to your own server.
- **Nothing sent to the developer.** tapiOca connects only to addresses an Admin typed in and, if an Admin says yes, to GitHub, to see whether a new version is out.
- **What Admins see.** Admins can see what each person watches, and their stats, to fix problems and choose what to add. The privacy notice says so.
- **Open, and never locked.** The server is free, unlimited and open source.

### What you need

- **Your own movies and shows,** in folders tapiOca reads itself, in your own Plex Media Server, or both. Watching your Stations in Plex needs Plex Pass.
- **A computer that runs Docker** on your home network: a NAS (TrueNAS SCALE, Synology, Unraid), a Linux server or virtual machine, a Raspberry Pi 4 or 5 with a 64-bit OS, or a Windows or Mac computer with Docker Desktop. x86-64 and ARM64 both work.
- **Access to your media folder** from that computer.
- **Enough processing power.** Each Station being watched is converted in real time. A modern 4-core processor can usually run several 720p Stations at once. A GPU (Intel Quick Sync, AMD or NVIDIA) handles many more. A Raspberry Pi or a Mac can't use its GPU, so plan on one or two Stations at smaller sizes there.

> **Tip:** Start with one Station. Once it plays well, run **Test this server** on the **Setup** tab to see how many your hardware can play at once.

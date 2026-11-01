# Watching in other apps

Your Stations work in other apps on your home network: as a tuner and guide for Plex, and as a playlist and guide for Jellyfin, Emby, Kodi and others. Everyone watching a Station shares one stream.

| For | Addresses |
| --- | --- |
| Plex (as an HDHomeRun tuner) | Tuner `http://<server-ip>:3310`, guide `http://<server-ip>:3310/xmltv.xml` |
| Jellyfin, Emby, Kodi and others | Playlist `http://<server-ip>:3310/stations.m3u`, guide `http://<server-ip>:3310/guide.xml` |
| Any HLS player | `http://<server-ip>:3310/hls/<station number>/index.m3u8` |

**Tuner integration**, at the top of the **Setup** tab, shows these with **Copy** buttons, and three status lines: **Media files** (whether Plex's files are read from disk), **Video encoding** (GPU or processor, and why) and **Guide updates** (whether tapiOca can ask Plex to refresh its guide). Opened from the internet, it shows the address Plex uses for tapiOca's tuner, or `http://<your NAS>:3310` until Plex has one.

> **Important:** These addresses work at home only, and never ask for a password. Never forward port 3310. Plex users away from home still watch through Plex, which relays the stream.

[[screenshot: The Setup tab's Tuner integration panel, with its addresses and status lines]]

### In Plex

1. In Plex, open **Settings → Live TV & DVR → Set Up Plex DVR**.
2. Choose **Don't see your HDHomeRun device? Enter its network address manually**, and enter the tuner address. Plex doesn't find tapiOca by itself.
3. When Plex asks for guide data, choose **Have an XMLTV guide on your server? Click here to use it**, and enter the guide address for Plex.
4. Continue. Plex matches your Stations (it calls them channels), and they appear under **Live TV**. <!-- wording-ok -->

tapiOca then asks Plex to refresh its guide whenever a Station changes. If **Guide updates** says it can't, use **Settings → Live TV & DVR →** your tuner **→ Refresh Guide**. After you make a new Station, choose **Scan for channels** there. A Plex Home or managed user needs **Allow Live TV and DVR access** to see Stations. Plex won't add a tuner with an empty guide: the INFO Station fills it until you make one. <!-- wording-ok -->

### In Jellyfin, Emby and Kodi

- **Jellyfin:** in the dashboard, open **Live TV**. Choose **+** next to **Tuner Devices**, then **M3U Tuner**, with the playlist address. Then **+** next to **TV Guide Data Providers**, then **XMLTV**, with the guide address. Leave Jellyfin's limit on simultaneous streams at no limit: tapiOca enforces its own.
- **Emby** (needs Emby Premiere): in **Live TV**, add a TV source, **M3U Tuner**, with the playlist address. Then add a guide data provider, **XMLTV**, with the guide address.
- **Kodi:** install the PVR Simple Client add-on (**Add-ons → Install from repository → PVR clients**). In its settings, set the playlist location to remote and **M3U play list URL** to the playlist address (it tells Kodi where the guide is). Restart Kodi. Your Stations appear under **TV**.
- **Other apps,** such as Channels DVR and VLC, take the playlist address.

These apps download the guide on their own schedule, about once a day. After you change a Station, refresh the guide in the app (in Jellyfin, **Dashboard → Scheduled Tasks → Refresh Guide**).

**HLS** shares the Station's one stream, so it never takes a second tuner. It runs only while a player asks for it, and stops 30 seconds after the last one stops.

### What other apps don't get

Other apps on the tuner get your Stations, and nothing else. Media on demand, Viewing Levels, **Who's tuning in?**, languages that follow each person, and problem reports work only between tapiOca's server and its apps. Other apps don't say who's watching, so they show every Station and program. See Tuner access and Blocking Stations for Plex users.

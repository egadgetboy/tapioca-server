# Stats, logs and alerts

## The Stats tab

Everyone can open **Stats**. Choose **Today** (since midnight), **7 days** (the default), **30 days** or **All**. It shows totals; for each Station its **Viewings**, hours **Watched**, **Average**, **Last watched** and **Most watched** title; the most watched shows and movies; and **When people watch**, by time of day.

A viewing counts once it lasts a minute. Viewings are counted per stream, so several people watching one Station together in Plex can count as one. Stats are kept for 400 days, and a Station's go with it.

**Admins also see:**

- **Server** (marked **Live**, every 5 seconds, with 10-minute charts): **Processor** and **Memory** (tapiOca's and the machine's, or the **Container's limit**), **Sending** and **Receiving**, the **GPU** in use, and the data folder's **Storage**.
- **Watching now:** **Who**, what, the **App and device**, at home or away, **Since** when, and **How** it's sent (**As it is**, **Repackaged** or **Converted**, its size and bitrate).
- **Top people:** who watched most, and what. In the apps, viewing counts for whoever is signed in. For Plex, tapiOca asks Plex every 30 seconds who's watching each Station, and marks Plex users **Plex**. Other apps aren't counted per person.
- **Top Media:** the titles played most in Media.

[[screenshot: The Stats tab, with the Server tiles, Watching now and the Station table]]

## The Logs tab

The **Logs** tab shows the latest 200 entries, newest at the bottom. **Search the log** finds words through everything it keeps (its newest 500 lines, and with **Access** ticked, the newest 2,000 sign-ins and changes). **Warnings** and **Errors** filter it. **Access** shows the access log. **Copy** copies what's shown. The activity log starts again when tapiOca restarts. Its lines also go to the container's output (`docker logs stationplay`), which Docker keeps until it rotates it: the install files keep 3 files of 10 MB each.

The log names each Station ("station 2, Cartoon Classics") and says what plays and how: a program's file, picture and sound, and how the Station makes it ("made 720p at 3.5 Mbps on the Intel/AMD GPU"); who started what in Media, and whether it plays as it is, repackaged or converted, and why; steps down in quality; and who stopped what, and when.

**Problems in the apps,** at the top, lists what the apps report as they play: a Station that doesn't start or stops, Media that doesn't play, playing that can't keep up, the app closing, or the app not reaching tapiOca (told once it's back). Choose **Today**, **7 days** or **30 days**. Each problem shows how often, on how many devices, for whom, and on what kinds of device. **One kind of device** points to that device or its app. **What it means**, **What the app said** and **What led up to it** explain each one. Problems are kept for 30 days. **Clear** removes them.

[[screenshot: The Logs tab, with Problems in the apps above the log]]

## Alerts

tapiOca alerts Admins, in a pill in the page's header and in the apps, when:

- Plex can't be reached, won't accept the token, or refuses tapiOca's pictures;
- the data folder has less than 2 GB free, or can't be written to;
- a Station keeps failing to start (3 times in 10 minutes), or backups fail twice in a row;
- tapiOca's clock is more than 2 minutes off from Plex's;
- the apps can't reach tapiOca from outside;
- the **Broken files** tab needs an Admin (at most once an hour), or clip folders need ratings;
- an Admin's PIN was entered wrong 5 times; or
- a door is left open (see Home, away and your network).

An alert starts only once a problem persists, and clears once things stay right, so alerts don't flicker. Each start and fix is logged. Alerts survive restarts, and a fix while tapiOca was stopped is still reported, once.

### Alert notifications

To get alerts on your phone or in a chat:

1. On the **Logs** tab, open **Alert notifications**.
2. Tick **Send each alert to the addresses below when it starts and when it's fixed**.
3. Enter a **Web address**, and choose its format: **ntfy or plain text** (the default), **JSON (Gotify, Home Assistant and others)**, **Discord** or **Slack** (Mattermost and Rocket.Chat take Slack's too).
4. **Add an address** for more, up to 3.
5. Choose **Send a test**, then **Save**.

JSON sends `{"title": "tapiOca", "message": "...", "kind": "...", "state": "started"}` (or `"fixed"`). A Discord or Slack webhook always gets its own format, and never pings anyone. One address failing doesn't hold up the others. tapiOca waits 5 seconds, tries once more, and follows no redirects. Only Admins see the addresses.

> **Important:** An alert can name a person, a title and a Station, and give your Plex server's home address and your away-from-home address. Send alerts only to services you trust.

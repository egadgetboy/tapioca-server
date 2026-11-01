# tapiOca's own apps

tapiOca's apps connect straight to your server, so people can watch your Stations and Media without Plex Pass or any other app. They're in beta, in private testing: tapiOca for Android (phones, foldables, tablets, Google TV and Android TV), for iPhone and iPad, and for Roku. This chapter covers the server's side. The manual for tapiOca's apps covers each app.

> **Note:** Media on demand, Viewing Levels, **Who's tuning in?**, languages that follow each person, and problem reports work only between tapiOca's server and its apps. That's on purpose: they're built together.

### Which server the apps need

The apps need tapiOca 1.22.0 or newer, and browse fastest with 1.43.0 or newer. An app on an older server says so. Newer servers add: PINs (1.28.0); languages and Admin alerts (1.29.0); converted copies (1.29.1); reporting a problem (1.30.0); automatic subtitles (1.34.0); trusted networks (1.36.0); **Shuffle all**, **Shuffle unwatched** and jumping through a Media folder (1.37.0); invite codes and Admin passwords on **Who's tuning in?** (1.38.0); "Restricted program" (1.39.0); limits checked while a title plays (1.40.0); and faster Media folders (1.43.0). Use the newest server for every feature.

### Connecting an app

Add the first Admin before you connect the apps. Until there's an Admin, the server lets anyone at home use them without signing in, and they all share one Resume row.

1. **Find the server.** At home, an app can look for tapiOca on your network, or you enter the address you use for tapiOca's page at home, such as `http://192.168.1.20:3310`.
2. **Sign in:** with a code on a TV (entered with **Link an app** on tapiOca's page), with a name and password, with an invite code, or with nothing at all on a trusted network.
3. **Choose a PIN,** or none, when the app asks.

Each signed-in app appears under **Signed-in apps** on the **Access** tab. Apps set up at home remember the away-from-home address, and switch to it when home doesn't answer.

## Media in tapiOca's apps

On the **Access** tab, open **Media in tapiOca's apps** (also in the setup). Tick the Media folders the apps can show, choose **When playing can't keep up** for **At home:** and **Away from home:**, and set **Even sound for a show's episodes**. Then choose **Save**.

[[screenshot: The Access tab's Media in tapiOca's apps panel]]

- **The best picture and sound.** A file plays as it is whenever the device can play it, 4K, HDR, Dolby Vision and Dolby Atmos included.
- **Copies only when needed.** Otherwise tapiOca makes a copy as it plays. A **repackaged** copy keeps the picture and converts only the sound, which costs almost nothing. A **converted** copy makes the picture again, at up to 1080p in standard color: at most 3 at once, or 6 with a GPU. Copies also draw in subtitles a device can't show, and make smaller pictures for slow connections.
- **One listing per title,** whatever its versions. Each device plays the best one it can. A movie in several files plays as one.
- **When playing can't keep up,** after the buffer, a short test finds out why, and the app **Stop, and offer a smaller version** (at home, to start) or does **Switch to a smaller version on its own** (away, to start).
- **Each person's own place:** their Resume row, resume points and watched list.
- **Even sound for a show's episodes** (on to start) plays episodes at −24 LUFS, as on Stations. Movies aren't changed. The cost: Dolby Atmos or DTS sent on to a receiver comes as ordinary 5.1 or stereo. Turn it off to keep each episode's sound as it is.
- **Languages.** Each person chooses sound and subtitles in the app's Options, and the choice follows them to every device. Subtitles start **Automatic**: shown when the sound isn't in their language. They can also choose for one title, or a whole show with **Sticky Audio & Subtitles**. Stations use `AUDIO_LANGUAGE` instead.
- **Night mode** on devices that can't change the sound themselves (Apple's player, a Roku) is made on the server, only for those watching that way.

## How many can watch at once

Each device watching in the apps gets its own copy of the stream, over your network at home and over your upload away. So these limits are about your network, not your processor. On the **Access** tab, open **How many can watch at once in tapiOca's apps**:

- **Devices watching at once:** every device, at home and away, Media included.
- **Away from home, at most:** how many of those can be away, so your upload doesn't run out.

Leave a box empty for no limit (the default), then **Save**. A device already watching can always change Stations. One beyond a limit is told an Admin has limited tapiOca, and to try again later. Plex and other apps aren't counted here.

**What tapiOca recommends** comes from connection tests that time tapiOca's own data (never an outside service), using the fastest recent test with 30% headroom. **Use the recommended numbers** fills them in. **Test the connection** runs a test from your browser, counted as at home or away by where the page is opened. To test away from home, run it from a phone on mobile data, in an app's Options. **Recent connection tests** lists the latest.


The apps' problems show on the **Logs** tab, and people's reports on the **Broken files** tab. Admins see tapiOca's alerts in the apps too.

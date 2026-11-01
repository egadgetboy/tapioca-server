# Keeping Stations on the air

A bad file should never take a Station down. tapiOca retries, fills the time with a stand-in, checks files before they air, and lists what's wrong for you.

### Safeguards

| When | What tapiOca does |
| --- | --- |
| A program won't open, or stops partway | Tries again from where it stopped, twice. |
| It still won't play | Lists it on the Broken files list, and a stand-in joins at the same point and ends when it would have, so the guide stays right. A stand-in is another episode of the same show, then a program of the same kind, then anything long enough. |
| Opening a file is slow (a sleeping drive) | Keeps the stream alive with a few seconds of black. |
| A file stalls (no video for 8 seconds) | Resumes or replaces it. Stalls are blamed on storage: a file is listed only if it stalls in two separate viewings. |
| The corner logo, banner or subtitles fail | Plays the program again with nothing drawn over it before blaming the file. |
| Plex or the media share can't be reached | Skips those programs for now, without listing them. |
| Nothing on the Station can fill the time | Shows a "We'll be right back" card, then continues. |
| Nothing could play for two programs in a row | Shows "This station is off the air. Please report it.", keeps trying, and comes back by itself. |
| The Station's stream fails | Restarts it at once, so viewers see at most a brief pause. After 3 failures in 5 minutes, the off-air card shows for 2 minutes. |

## The Broken files tab

Files that can't play properly go on one list for Stations and Media alike, stored in `data/broken-files.json`. Each entry shows what's wrong, when it was found, how many times it failed, the file's path, the Stations that have it, and whether it's in Media.

- **On Stations,** every entry is skipped until it's cleared, and a stand-in plays instead.
- **In Media,** a broken file doesn't play (another version does, if there is one). A damaged one still plays.
- **Versions** of a program are separate files, each with its own entry.

| Label | Meaning |
| --- | --- |
| **Missing** | Gone from disk or from Plex, while a Station or Media still has it. |
| **Broken** | Won't play. |
| **Damaged** | Plays, but the picture or sound breaks up. |
| **Unsupported** | Plays, but can't be shown correctly on Stations (Dolby Vision profile 5). |

The tab has three parts. **Needs you** holds people's reports, and files tapiOca found that wait for your choice; the tab's count is these. **Being replaced** is what Sonarr or Radarr is fetching now. **Found by tapiOca** is the rest: files you're handling, files nothing plays now, and Unsupported files. At the top, **Check the list again** goes through the list now, and **Download list** saves it as a file.

[[screenshot: The Broken files tab, with the file checks panel, Needs you and an entry's buttons]]

**Clearing an entry yourself:**

- **Retry** means "the file is fine. Put this program back on the air." The checks then leave that file alone. (An Unsupported file then plays with the wrong colors.)
- **Removed a show on purpose?** Take it off the Stations its entry lists, and its **Missing** entry clears within half an hour.
- **Deleting an entry** from `broken-files.json` also works (tapiOca notices within 15 seconds), but doesn't tell the checks to leave the file alone.

**Entries that clear themselves:** when Plex has the program again under a new ID, or a missing file is no longer on any Station or in Media (checked every half hour); when a new file for the program passes its quick check; and, for files a quick check took off the air, when they pass again overnight. Deep-scan and playback problems stay until the file changes.

## File checks

tapiOca checks files at the lowest priority, to find problems before anyone tunes in, and steps aside while anyone is watching. Each file is checked once for Stations and Media together. In order:

1. **Programs airing soon** (in the next 3 hours) that are due a check.
2. **A file someone just had trouble with:** tapiOca decodes the minute around where it happened, then quick-checks the file. Only what tapiOca finds lists it, so a network hiccup changes nothing.
3. **New arrivals,** quick-checked within minutes: the file must open, and its picture and sound must decode at five points.
4. **Weekly,** every program on a Station is quick-checked again.
5. **The overnight deep scan** decodes files in full, Stations' programs first, then Media's (Resume rows and next episodes first). It stops the moment anyone starts watching. Each file is scanned once, and again only if it changes.

**Deep scan every night from**, on the **Broken files** tab, sets its start and end times (1:00 AM to 6:00 AM to start), then **Save**. Untick it to turn the deep scan off. **Check files** on a Station card quick-checks all its programs now. The panel at the top of the tab shows how far the checks have gotten.

| Result | What it means |
| --- | --- |
| **Broken** | Won't open, has no picture, stops decoding, ends early (more than 10 seconds or 2% short), or can't be read on two different nights. |
| **Damaged** | The picture breaks up, the sound drops out (20 ms or more lost within a second), or the file skips; no sound, or nothing, for 30 seconds or more; no sound track or silence throughout (for programs from 1930 on); an all-black picture; sound that stops before the picture; or a file that runs well past its stated length. |
| **Fine** | Warnings no one would see or hear, anything in the first 2 seconds or last 5, pauses under 30 seconds, a still picture over sound, a black opening, or a file slightly short. |

Each entry says what was found and where, such as "the picture breaks up around 12:31 and 48:02". Times are approximate.

## Replacing files with Sonarr and Radarr

tapiOca doesn't need them. But if you use **Sonarr** (TV) or **Radarr** (movies), version 3 or later, tapiOca can ask them to replace files on the list that a Station or Media plays.

1. On the **Broken files** tab, open **Replacing files with Sonarr and Radarr**.
2. Tick **Use Sonarr for episodes** (or **Use Radarr for movies**).
3. Enter its address, such as `http://192.168.1.10:8989`, and its **API key** (in the app under **Settings → General**).
4. Choose **Test**, then **Save**. (An address on your home network asks first.)
5. Choose **Files to replace** (**Broken or damaged**, **Missing** or **Both**) and **When to replace** (**Only when I ask** or **Automatically**).

With **Only when I ask**, choose **Replace with Sonarr** (or **Radarr**) on an entry. With **Automatically**, every entry is replaced, unless you choose **I'll handle it** on it. API keys are stored in tapiOca's database and backups, and never shown again.

**What happens.** For a broken or damaged file, the app first **blocklists** the release it came from, then deletes the file and searches for another. This happens only if the app's file is exactly the one tapiOca found, and the app has a record of fetching it. For a missing file, the app rescans and searches. Each gets up to 3 searches, 8 hours apart. tapiOca checks each new file, and puts the program back on the air once it passes. It only asks about what the app is monitoring: unmonitor something there to leave it alone.

**The same problem twice** may be part of the program itself, such as an old film's transitions. tapiOca stops and marks the entry **Needs your review**. Watch it there: choose **Retry** if it's fine, or **Try another file**.

Each entry shows **Replacing**, **Downloading**, **Downloaded**, **Gave up** (3 searches found nothing; **Try again** starts over), **Can't replace**, **Needs your review** or **You're handling it**. The **Logs** tab records every step. Unsupported files aren't replaced this way: you're the best judge of the right version.

## People's reports

People can report a problem from tapiOca's apps, from a title's page, the player's menu, or a Station's player. They pick it from a list: **Picture** (No picture; The picture breaks up or freezes; Poor picture quality), **Sound** (No sound; The sound cuts out; The sound is out of sync; Wrong language), **Subtitles** (Subtitles are missing or wrong), **The program** (It won't play; It stops before the end; Wrong episode or movie) and **Details** (Wrong title, details or artwork).

Reports go under **Needs you**, with who sent it, from what device, where in the program, and how it was playing.

- **What tapiOca can check** (no picture, breaking up, no sound, cutting out, stopping early, not playing): it checks the file at once. If it finds the problem, the file is listed. If not, the report says so, for you to **Dismiss**.
- **What only a person can judge** (sync, language, wrong episode, picture quality, subtitles): it waits for you, with what tapiOca can tell about the file. Choose **Replace with Sonarr** (or **Radarr**), **Find a better copy** (an upgrade, keeping the file meanwhile) or **Dismiss**.
- **Wrong title, details or artwork:** fix it in Plex (**Fix Match** or **Edit**), then **Dismiss**.

A report never takes anything off the air by itself. Each person can send one report a day about each program, and 10 a day in all. Turn reporting off for someone with **Can report problems**, on the **Access** tab or under **Reports from tapiOca's apps** here. Reports are kept 90 days after they're handled.

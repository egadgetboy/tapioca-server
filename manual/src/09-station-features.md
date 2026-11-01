# Station features

Each feature is set in a Station's editor, in the group named here. The Settings reference lists every choice and default.

## Logos

tapiOca comes with 984 original logos, drawn for it. None copies a real network's or show's name, symbol or lettering. They're grouped as made-up networks and stations, styles (Classic TV, TV shows, Cartoons & anime, Teens, Kids & family), genres (three designs for each of Plex's 37), themes (decades, holidays, seasons, times of day, moods, on-air signs), and letters and numbers in a modern and a retro style.

- **Choose…** opens the logo picker, with search and categories. It opens on **Suggested** logos when the Station's name or filter suggests a genre. Faded logos are already used.
- **Surprise me** picks one at random. **Station number** shows the number instead.
- **Upload your own…** takes a PNG, JPEG, WebP, GIF or BMP image up to 10 MB, made into a 512×512 PNG (square images look best). Your logos are listed under **Your logos**, up to 500. An Admin can delete an unused one with its **×**.
- **Use the logo from Plex** takes the title artwork Plex has for the first show. A new Station with one show or movie is named after it, and gets its Plex logo by itself.

[[screenshot: The logo picker, with Suggested logos and the category chips]]

## In the corner (On screen)

Shows the Station's **Logo**, its **Name** or a **Clock** in a corner during programs, never during commercials, trailers or cards. Set its **Size**, **Transparency**, **Corner** (or click a corner of the preview), the **Clock**'s format, the logo's **Look** (**In color** or **All white**), and **When** (**Always**, or **At the start**: the first 30 seconds of each program, and of whatever's on when someone tunes in).

**Burn-in protection.** So a still picture can't mark an OLED or plasma TV, what's in the corner steps every 4 minutes to the next of 9 places, all within 6 pixels. Every Station does it.

### Up Next Banner (On screen)

Three minutes before each show or movie ends, a banner shows the Station's logo, **Up next** and the next program, for **3 sec**, **5 sec** or **10 sec** (or **Off**), at a **Size** you choose. **Preview** plays it. It takes the corner logo's place while it's up, and skips programs under 3 minutes.

### Station ID card (Between programs)

After each program and its commercials, a card shows the Station's logo, name and number, and what's up next, for **3 sec**, **5 sec** or **10 sec**, with one of 15 original jingles (**Jingle** **On** or **Off**). **Preview** shows it. The card's time is part of each program's time in the guide.

## Commercials and trailers (Between programs)

**Commercials & trailers** plays **None**, **1**, **2** or **3** clips after each program: commercials after episodes, trailers after movies. They're part of each program's time in the guide, each plays about as often as the others, and all play at an even loudness.

1. Make a folder named `commercials` at the top of your TV shows' Media folder, and `trailers` at the top of your movies' (Linux names are case-sensitive). Subfolders are fine.
2. Put clips from 3 seconds to 10 minutes long in them.
3. Put a `.plexignore` file containing `*` in each, so Plex doesn't add the clips:

   ```
   echo '*' > /mnt/tank/media/tv/commercials/.plexignore
   echo '*' > /mnt/tank/media/movies/trailers/.plexignore
   ```

- **By decade.** Clips in a folder named for a decade (`commercials/1960s` or `commercials/60s`) play only after programs from that decade.
- **Under Viewing Levels.** On a Station someone with limits can see, a clip plays only if its folder is rated (see Viewing Levels and limits).
- **Finding them.** tapiOca looks at startup and every hour, or now with **Check again** in the editor. A clip that fails is left out until it changes, and listed under **Commercials and trailers that didn't play** on the **Broken files** tab.

## Intro Bumper (When someone tunes in)

When a Station's stream starts, an Intro Bumper can play before the program:

- **Built-in card:** the Station's logo arriving, "You're tuning in to", its name, a one-line **Description** (up to 140 characters) and what's on, for 3 to 15 seconds, with the sound of an old TV dial (**Sound** **On** or **Off**). **Preview** shows it.
- **Your video:** **Upload a video…** up to 30 seconds long and 500 MB (MP4, MOV, MKV, WebM and similar). tapiOca makes a copy at the right size and loudness. Videos are kept in `data/bumpers` (not in backups), up to 50, and only Admins can **Delete** one.
- **Off.**

Someone joining while others already watch joins in progress, without a bumper.


### Viewers join (When someone tunes in)

- **In progress:** like real TV. Tune in at 10:20 to a show that began at 10:00, and you join 20 minutes in. The show's sound fades in under the bumper.
- **From the beginning:** the program on now starts from its beginning, and the Station runs that far behind the guide while anyone is watching. A program that began more than 2 hours ago is joined in progress.

### Subtitles (On screen)

Draws subtitles into the picture: **Off**, **Forced only** (lines meant to be read, such as foreign dialogue) or **Always**. They're in the `AUDIO_LANGUAGE` language (English unless set), from the file or a file beside it (`Movie (1999).en.srt`, `Movie (1999).en.forced.srt`). Viewers can't turn them off. A program's first airing may play without them while they're prepared.

## Specials

Under **Specials**, three kinds of event take over a Station now and then. Each starts at the program break nearest its time, and the Station then picks up where it left off. A block wins over a Feature Presentation, and both over a marathon. A special more than 15 minutes late is skipped, and the **Logs** tab says so.

- **Marathons:** three episodes of one show in a row, at **Random times** (1 to 4 a week) or **Set times** (days and a time), playing **Next in order** or from a **Random starting point**. The Station needs at least 5 shows with 3 or more episodes each.
- **Feature Presentation:** a movie night on days and at a time you choose, after a 10-second card (**Preview the card**). **Movies from** is the Station's own movies, a movie Media folder or a movie collection, so a TV Station can have movie nights too. Every movie plays once before any repeats.
- **Blocks:** up to 4, such as Saturday Morning Cartoons. **Add a block**, then set its **Block name**, **Block days**, **Start time** and **End time** (30 minutes to 12 hours, past midnight is fine) and **Choose shows…**. A block ends at the program break nearest its end time, and picks up where it left off next time.

Saving is refused, with the reason, if specials clash or have nothing to play. The card shows when each is next.

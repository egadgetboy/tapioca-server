# How Stations play

### One format for each Station

Each Station is one continuous stream, as on broadcast TV. Everything on it is converted as it plays to the Station's format: H.264 at the Station's picture size, 29.97 frames a second, in standard color (SDR), with stereo sound. So a 4K movie, an old DVD copy and a commercial follow one another without a glitch, in any app.

| **Picture** | Size | Video per viewer | Work for the server |
| --- | --- | --- | --- |
| **480p** | 854×480 | 1.5 Mbps | About half of 720p |
| **720p** (standard) | 1280×720 | 3.5 Mbps | Light enough for most servers |
| **1080p** | 1920×1080 | 6 Mbps | About twice 720p; a GPU helps |

Sound adds 192 kbps. A new size takes effect the next time the Station starts, after everyone stops watching it.

- **4K and HDR.** Stations play at up to 1080p in standard color, on purpose: 4K HDR would need a GPU fast enough to convert everything live, and about 20 Mbps a viewer. So 4K is scaled down, and HDR (HDR10, HDR10+, HLG and most Dolby Vision) is converted to standard color the way a TV would.
- **Dolby Vision profile 5** files can't be shown correctly by anything but a Dolby Vision player, so Stations don't play them. They're listed as **Unsupported** on the **Broken files** tab.
- **Movies in several files** play back to back as one program. If one part is missing or won't play, it's listed ("part 2 of 3"), and a stand-in plays the rest of its time.

## Tuners

The **Tuners** number (1 to 20, under **Picture and tuners** on the **Setup** tab; 4 to start) sets how many different Stations can play at once, across Plex and every other app.

- **One tuner per Station.** Everyone watching a Station shares one stream, however many watch.
- **When every tuner is busy,** someone tuning in to another Station sees an **All tuners in use** card for 30 seconds, listing what's on. Up to 3 people at a time see it.
- **Plex** is told there are more tuners than there are, so it lets tapiOca show that card. If you raise the number and Plex still won't play more, restart Plex.
- **Flipping back is instant.** A Station keeps running for 20 seconds after its last viewer leaves, and gives up its tuner if someone else needs it.

**Test this server** makes a few seconds of video at each size (up to a minute, at low priority) and says roughly how many Stations your server can play at once. A button such as **Use 4 tuners for 720p** fills in its suggestion, which leaves 30% headroom; then choose **Save**. 4K and HDR programs take more work, so treat it as a guide. The page warns you if you set more.


## Schedules

Programs play back to back at their real lengths, never stretched to fill a time slot.

- **Episode order:** one episode of each show in turn, each show in order, like classic reruns. Shows go alphabetically, and a movie counts as a one-episode show. Then the run starts again.
- **Shuffle:** every program once a pass, each pass shuffled again, so a show airs at different times each day. No show plays more than twice in a row, unless one show makes up almost all of the Station: then it sometimes plays three or more times in a row, and the card says so. Add more shows to avoid that.

The schedule is worked out the same way every time, from when you saved the Station, so the guide stays right and a restart never changes what's on.

## Updates to Stations

New episodes join Stations by themselves, and removed ones leave. Every hour, tapiOca prepares an update from what changed, and the card shows **Update ready**. An update never cuts a program short. It starts at a program break:

- **With Plex,** after Plex next downloads the guide (tapiOca asks it to), usually within the hour.
- **Without Plex,** once the guide other apps downloaded runs out, up to 2 days. If no app downloads it, at the next program break.

In **Shuffle**, new programs are spread through the pass, so 23 new episodes of one show don't become a marathon.

**Updates that need your review.** On a Station with 10 or more programs, an update that would remove more than half isn't applied by itself: it's more likely a drive offline than something you meant. The same goes when a Media folder suddenly reports nothing, or Plex loses most of the intro and credits markers. The card says "N programs gone — needs your review". Choose **Update now** if it's right.

**Shows Plex adds again** under a new ID are found again by title, and keep their places. If it can't tell which show is meant, the Station keeps what it had, and the **Logs** tab names the show to choose again. Specials (season 0) are left out of Stations.

## Skipping intros and credits

With **Intros & credits** set to **Skip them**, each program airs without its opening titles and end credits, from the same markers as Plex's own **Skip Intro** and **Skip Credits**.

- **Cold opens still play,** and a scene after mid-program credits still plays.
- **No markers, no skipping.** Programs without markers play in full, including those from Media folders tapiOca reads itself.
- **Exact guide times,** without the skipped parts.
- **Only sensible markers:** an intro must start in the first half and be under 5 minutes; credits must start in the second half; at least a minute must be left.
- **Clean cuts.** tapiOca moves each skip to a change of shot or a moment of black near the marker, so a few seconds of titles may show (never more than 6 at each end). A skip only ever gets shorter.

Plex must find the markers first: under **Settings → Library**, set **Generate intro video markers** and **Generate credits video markers** to run as a scheduled task and when media is added (a Plex Pass feature). <!-- wording-ok -->

### Sound and picture shape

**Even sound.** TV episodes play at the same loudness (−24 LUFS, the US broadcast standard). Movies keep their original sound.

**4:3 shows.** **Black bars** keeps the original shape. **Stretch** widens the picture to fill the screen. **Zoom** fills it and trims the top and bottom. Widescreen programs are never changed. With **Stretch** or **Zoom**, black bars built into the picture are removed first.

**The guide** covers the next 2 days, in Plex, in tapiOca's apps, and under **Guide** on each card.

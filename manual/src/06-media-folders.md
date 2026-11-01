# Media and Media folders

Everything tapiOca plays comes from **Media folders**, each holding shows or movies. A Media folder is either one of Plex's, or one tapiOca reads itself from folders in its media folder (`MEDIA_DIR`, `/media` in the container). Both work the same way for Stations, filters, smart Stations and Media in the apps.

### The Media folders panel

On the **Setup** tab, **Media folders** lists every Media folder, Plex's and tapiOca's own.

- **The switch** keeps a Media folder out of tapiOca's apps when it's off. Stations can still use it. It saves at once.
- **Media folders tapiOca reads itself** also show their folders, when they were last read (such as "Read 5 minutes ago", or "Reading 120 of 800 files"), and **Read again**, **Edit** and **Remove**.
- **Notes** say when a folder can't be read now, or is also in one of Plex's Media folders (its titles then appear twice).

[[screenshot: The Setup tab's Media folders panel, with a Plex Media folder and one tapiOca reads itself]]

### Adding a Media folder tapiOca reads itself

1. On the **Setup** tab, choose **Add a Media folder**.
2. Give it a **Name**, such as "Home Movies".
3. Under **It holds**, choose **Shows** or **Movies**.
4. Open a folder in the list, then choose **Add this folder**. Add as many as you like, but not one inside another.
5. Choose **Add**. tapiOca reads it right away.

To use tapiOca without Plex, leave out `PLEX_URL` and `PLEX_TOKEN` when you install.

### Laying out its folders

Lay out folders as Sonarr, Radarr, Plex, Jellyfin and Emby do:

- **Shows:** `TV/Show (2010)/Season 01/Show (2010) - S01E02 - Title.mkv`. Also `1x02`; `S01E02E03` (two episodes in one file); `Specials` or `Season 00`; and dates for daily shows (`Show - 2024-03-15 - Title.mkv`).
- **Movies:** `Movies/Movie (1999)/Movie (1999).mkv`. Other files in a movie's folder are its versions (`Movie (1999) - 4K.mkv`). `cd1` and `cd2`, `part1` and `part2`, or `disc1` and `disc2` are parts of one movie.
- **IDs in names,** such as `{tmdb-12345}` or `{tvdb-67890}`, are kept.
- **Left out:** hidden files; extras folders (Extras, Featurettes, Behind The Scenes, Deleted Scenes, Interviews, Trailers, Shorts, Other); samples; a NAS's own folders (`@eaDir`, `#recycle`); copied discs (`BDMV`, `VIDEO_TS`); and links that lead outside the media folder.

### Where its details come from

For each detail, the first of these that has it: **NFO files** beside the videos (titles, years, plots, genres, ratings, studios, cast and crew, collections); **tags inside the files**; then **folder and file names**. tapiOca looks nothing up online and never guesses. A title from a name drops its release details: `Coastline.2010.Special.1080p.WEB-DL.x264-GRP.mkv` is "Coastline 2010 Special".

- **Ratings** come from the NFO files (`<mpaa>`, such as `PG-13`). A title with no rating is unrated, so Viewing Levels that hide unrated titles hide it.
- **Pictures** come from beside the videos (`poster.jpg`, `folder.jpg`, `fanart.jpg`, `clearlogo.png`, `season01-poster.jpg`, an episode's `-thumb.jpg`), then from covers inside the files.
- **Not yet:** skipping intros and credits, and pictures for titles with none beside them or inside them.

tapiOca's apps never get a file's name or a folder's path.

### Reading it again

tapiOca reads new and changed files soon after it starts, every 6 hours, when you choose **Read again**, and when Sonarr or Radarr brings a replacement it asked for. It reads at the lowest priority, and never while anyone is watching.

- **Renamed, moved or replaced files** keep their place on Stations, and what people watched of them.
- **A folder that can't be reached** keeps its programs, listed as missing until it's back. They're never taken off your Stations for it.
- **A name that isn't UTF-8,** as on some older NAS shares, is skipped, and the **Logs** tab says so. Rename it.

### Media folders from Plex

With `PLEX_URL` and `PLEX_TOKEN` set, Plex's TV and movie Media folders appear by themselves, with Plex's details, artwork, ratings, and intro and credits markers. For Plex's titles, tapiOca never reads anything from file names. While Plex isn't answering, Media folders tapiOca reads itself still play.

### Sharing Media with the apps

Every Media folder of shows and movies, including ones added later, is shared with the apps until an Admin saves a choice: under **Media in tapiOca's apps** on the **Access** tab, in the setup, or with the switches here. A choice is kept, even none. Viewing Levels still decide what each person sees, and Stations, Plex and other apps aren't affected.

A tapiOca updated from before 1.34.1 that never saved a choice shares nothing until an Admin chooses. The setup asks once, with every Media folder ticked.

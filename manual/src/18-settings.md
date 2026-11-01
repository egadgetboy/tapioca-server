# Settings reference

Every setting in tapiOca 1.44.3, grouped as the screen groups them.

### The YAML or compose file

Environment variables, set when you install. Restart tapiOca after changing one.

| Setting | What it does | Choices | Default |
| --- | --- | --- | --- |
| `PLEX_URL` | Plex's address. Leave out for no Plex. | An address | None |
| `PLEX_TOKEN` | Your Plex token. | Text | None |
| `TAPIOCA_INSTALL` | How your install updates, for the page's steps. | `truenas`, `compose`, `unraid`, `synology`, `docker-desktop`, `docker-run` | None |
| `TZ` | Time zone for the clock, specials, checks, backups, stats and logs. | Such as `America/Chicago` | `UTC` |
| `MEDIA_DIR` | Where your media is inside the container. | A folder | `/media` |
| `PATH_MAPPINGS` | Plex's paths, for unusual layouts. | `plex/path:local/path;…` | None |
| `HW_ACCEL` | The encoder. | `auto`, `nvidia`, `intel`, `amd`, `cpu` | `auto` |
| `HW_DEVICE` | Which GPU, with several. | A render node, or an NVIDIA number | Automatic |
| `PORT` | The home port. | A port | `3310` |
| `PUBLIC_PORT` | The public port. Must differ from `PORT`. | A port | Off |
| `AUDIO_LANGUAGE` | Stations' sound and subtitle language. | A language code | `eng` |
| `FRIENDLY_NAME` | The tuner's name in Plex. | Text | `tapiOca` |
| `BASE_URL` | Only if Plex reaches tapiOca at another address than your browser. | An address | Automatic |
| `IDLE_GRACE_SECONDS` | How long a Station runs after its last viewer leaves. | Seconds | `20` |
| `AUDIO_BITRATE_KBPS` | Stations' sound bitrate. | kbps | `192` |
| `DATA_DIR` | The data folder inside the container. Leave it. | A folder | `/data` |
| `FFMPEG_PATH`, `FFPROBE_PATH` | A custom ffmpeg build. | A program | `ffmpeg`, `ffprobe` |

`TUNER_COUNT` and `VIDEO_HEIGHT`, from before 1.14, are read once if set, then ignored.

### Setup tab

| Setting | What it does | Choices | Default |
| --- | --- | --- | --- |
| **Picture for new stations** | New Stations' picture size. | **480p**, **720p**, **1080p** | **720p** |
| **Tuners** | Stations that can play at once. | 1 to 20 | 4 |
| A Media folder's switch | Whether the apps show it. | On, off | On |
| **Name** (Add a Media folder) | Its name. | Up to 60 characters | Empty |
| **It holds** | What it holds. | **Shows**, **Movies** | **Shows** |
| **Its folders** | The folders it reads. | One or more, none inside another | None |
| **Tell me when a new tapiOca is out** | The update check. | On, off | Off until answered |

### The Station editor

The setup's **New station settings** step sets what new Stations start with for **Subtitles**, **Commercials & trailers**, **Station ID card**, **Intro Bumper** (its **Length**), **Up Next Banner**, **In the corner** and **Corner**. The defaults below apply until you change them there.


| Setting | What it does | Choices | Default |
| --- | --- | --- | --- |
| **Number** | Its number (99 is INFO's). | 1 to 9999 | The next free one |
| **Name** | Its name. | Up to 60 characters | "Station" and its number |
| **Logo** | Its logo. | Built-in, your own, Plex's, **Station number** | Its number's (1 to 50), or an unused one |
| **What's on this station** | What it plays. | **Pick shows & movies**, **Use a filter** | **Pick shows & movies** |
| **Picture** (How it plays) | Its picture size. | **480p**, **720p**, **1080p** | The new-Station size |
| **Order** | How programs follow. | **Episode order**, **Shuffle** | **Shuffle** |
| **4:3 shows** | How 4:3 fills the screen. | **Black bars**, **Stretch**, **Zoom** | **Black bars** |
| **Intros & credits** | Skip Plex's markers. | **Play them**, **Skip them** | **Play them** |
| **Marathons** (Specials) | 3 episodes in a row. | **Off**, **Random times** (1 to 4 a week), **Set times** | **Off** (2 a week; Saturday, 8:00 PM) |
| Which episodes | Where marathons start. | **Next in order**, **Random starting point** | **Next in order** |
| **Feature Presentation** | A movie night. | **Off**, **On**, with days and a time | **Off** (Friday, 8:00 PM) |
| **Movies from** | Its movies. | This Station's, a Media folder, a collection | This Station's movies |
| **Blocks** | Time-of-day blocks. | Up to 4: name (40 characters), days, 30 minutes to 12 hours, shows | None |
| **Commercials & trailers** (Between programs) | Clips after each program. | **None**, **1**, **2**, **3** | **None** |
| **Station ID card** | A card after each program. | **Off**, **3 sec**, **5 sec**, **10 sec** | **Off** |
| **Jingle** | The card's jingle. | **On**, **Off** | **On** |
| **In the corner** (On screen) | During programs. | **Nothing**, **Logo**, **Name**, **Clock** | **Logo** |
| **Size** | Its size. | **Small**, **Medium**, **Large** | **Large** |
| **Transparency** | How see-through. | **High**, **Medium**, **Low** | **Medium** |
| **Corner** | Which corner. | **Top left**, **Top right**, **Bottom left**, **Bottom right** | **Bottom left** |
| **Clock** | The clock's format. | **12-hour**, **24-hour** | **12-hour** |
| **Look** | The logo's color. | **In color**, **All white** | **In color** |
| **When** | When it shows. | **Always**, **At the start** | **Always** |
| **Up Next Banner** | How long it shows. | **Off**, **3 sec**, **5 sec**, **10 sec** | **10 sec** |
| **Size** (banner) | Its size. | **Small**, **Medium**, **Large** | **Large** |
| **Subtitles** | Drawn into the picture. | **Off**, **Forced only**, **Always** | **Off** |
| **Viewers join** (When someone tunes in) | Where they join. | **In progress**, **From the beginning** | **In progress** |
| **Intro Bumper** | What plays first. | **Off**, **Built-in card**, **Your video** | **Built-in card** |
| **Length** | The card's length. | **3 sec**, **5 sec**, **10 sec**, **15 sec** | **10 sec** |
| **Sound** | The card's dial sound. | **On**, **Off** | **On** |
| **Description** | The card's line. | Up to 140 characters | Empty |
| **Video** | Your video. | Up to 30 seconds, 500 MB | None |

### Access tab

| Setting | What it does | Choices | Default |
| --- | --- | --- | --- |
| **Name** (Add a user) | Their name. | Up to 40 characters, unique | None |
| **Password** | Their password. | At least 8 characters (optional for a User) | None |
| **PIN (optional)** | Asked when they pick themselves. | 4 digits | None |
| **Role** | What they can do. | **User**, **Admin** | **User** (the first is an Admin) |
| **Viewing Level** | What they can see. | Any level | **New people start on**'s |
| **Stations they can make** | A User's Stations. | **None (watches only)**, 1, 3, 5, 10, 25, **Any number** | 3 |
| **Can change their own password**, **Can change their own PIN**, **Can report problems** | A User's permissions. | On, off | On |
| **How you sign in** (Your account) | An Admin's sign-in. | **Full**, **Light** | **Full** |
| **Trusted networks** | Skip signing in. | Up to 50, giving **Who's tuning in?** or **Signed in as** a person | None |
| **Trusted proxies** | Believed about visitors. | Up to 10 home addresses | None |
| **Names for tapiOca at home** | Home names. | Up to 10 | None |
| **New people start on** | New Users' level. | Any level | **Unrestricted** |
| **Movies up to**, **TV up to** | A level's ratings. | A rating, **No limit** | As each level |
| **Unrated titles** | A level's unrated titles. | **Shown**, **Hidden** | **Hidden** (but **Unrestricted**) |
| **Media folders** (a level) | What a level sees. | **All**, or some | **All** |
| **Genres**, **Tags**, **Collections**, **Studios** | Names a level hides. | Any names | None |
| **Commercials and trailers** | Clip folders' ratings. | TV or movie ratings | **Not rated** |
| **Tuner access** | Who uses the tuner. | **Any device on my home network**, **Only these devices** (up to 50) | **Any device on my home network** |
| **Stop Plex users from watching stations blocked for them** | Plex blocking. | On, off | Off |
| **Let tapiOca's apps watch away from home** | The apps away. | On, off | Off |
| **The address apps reach tapiOca at from outside** | Their address. | Up to 200 characters | Empty |
| **Media away from home** | Media's quality away. | **Original**, **Up to…** 1 to 200 Mbps | **Original** |
| **Devices watching at once** | The apps' limit. | A number, or empty | No limit |
| **Away from home, at most** | The apps' limit away. | A number, or empty | No limit |
| Media folders (Media in tapiOca's apps) | Shown in the apps. | Tick each | Every one |
| **When playing can't keep up**, **At home:** | Media stalling at home. | **Stop, and offer a smaller version**, **Switch to a smaller version on its own** | **Stop, and offer a smaller version** |
| **When playing can't keep up**, **Away from home:** | Media stalling away. | The same | **Switch to a smaller version on its own** |
| **Even sound for a show's episodes** | Even loudness in Media. | On, off | On |
| **Accept API tokens from the internet** | Tokens on the public port. | On, off | Off |

### Logs, Broken files and the footer

| Setting | What it does | Choices | Default |
| --- | --- | --- | --- |
| **Send each alert to the addresses below when it starts and when it's fixed** | Alert notifications. | On, off, up to 3 **Web address** entries | Off |
| Format | Each address's format. | **ntfy or plain text**, **JSON (Gotify, Home Assistant and others)**, **Discord**, **Slack** | **ntfy or plain text** |
| **Deep scan every night from** | The overnight scan. | On, off, with times | On, 1:00 AM to 6:00 AM |
| **Use Sonarr for episodes**, **Use Radarr for movies** | File replacing. | On, off, with an address and **API key** | Off |
| **Files to replace** | Which entries. | **Broken or damaged**, **Missing**, **Both** | **Both** |
| **When to replace** | Ask first or not. | **Only when I ask**, **Automatically** | **Only when I ask** |
| **Appearance** (footer) | Light or dark, in one browser. | **Automatic**, **Light**, **Dark** | **Automatic** |

### The data folder

`stationplay.db` (the database), `broken-files.json` (the Broken files list), `device.json` (the tuner's ID in Plex), `cuts.json` (where skips end), `backups/`, `logos/` and `bumpers/`. An empty `reset-access` file, then a restart, removes every person.

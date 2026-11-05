# First-time setup

The first time someone opens tapiOca's page, the setup opens, titled **Welcome to tapiOca**. It asks a few questions and checks that everything works. Use **Next** and **Back**, or the steps down the side. Each answer is saved when you move to another step. **Skip setup** keeps everything else as it is.

> **Important:** On a new server, skipping the setup leaves no Admin. Until there is one, anyone at home can use tapiOca's page and apps and change anything. Add an Admin in step 4, or on the **Access** tab.

[[screenshot: The setup's first step, Checking your server, with its list of checks]]

### The ten steps

1. **Checking your server.** tapiOca checks the server itself, never waiting on Plex: that it can read your media folder (`MEDIA_DIR`, and any folder `PATH_MAPPINGS` names) and a video in it, how it encodes video, whether its clock matches your browser's, and its backups. If nothing is at `MEDIA_DIR`, it says where your media seems to be, and what to set `MEDIA_DIR` to. Each check shows **Working**, **Needs a look**, **Not working**, **Good to know** or **Not checked yet**, and says what to do. After changing tapiOca's app settings, restart it, then choose **Check again**.
2. **How stations play.** The **Picture for new stations** and the number of **Tuners**, with **Test this server** to help you choose.
3. **New station settings.** What each new Station starts with: **Subtitles**, **Commercials & trailers**, **Station ID card**, **Intro Bumper**, the Up Next Banner, and what goes **In the corner**. Stations you already have don't change. This step is the only place to change these defaults.
4. **Who can use tapiOca.** Enter your **Name** and a **Password** to become the first Admin, and you're signed in right away. To let your home's devices skip signing in, tick **Devices on my home network skip signing in**. It offers the network tapiOca sees you on, such as `192.168.1.0/24`. Its devices then open on **Who's tuning in?** in tapiOca's apps. (A tapiOca updated with signing in off offers **Anyone on my network** or **Only people who sign in**.)
5. **Who sees what.** The Viewing Level **New people start on** (**Unrestricted** until you choose another), and each person's level.
6. **Watching away from home.** Whether tapiOca's apps can watch away from home, the address they use, and whether tapiOca can reach it.
7. **Media in tapiOca's apps.** Which Media folders the apps can browse and play (every one, to start), and **Even sound for a show's episodes**.
8. **Checking files.** When the overnight deep scan runs, or whether it runs.
9. **Tuner.** **Will you watch your stations in other apps?** Tick **Plex**, **Jellyfin**, **Emby**, **Kodi**, **Another app**, or **Only tapiOca's own apps** on its own. Each app ticked shows its steps and addresses, with **Copy** buttons. This only changes what the step shows: every app can still use the tuner. For Plex, three checks show whether tapiOca can reach Plex (and whether the server's owner has Plex Pass), whether it finds the files Plex lists, and whether Plex has tapiOca as a DVR yet. **Check again** runs them again.
10. **All set.** Your settings, anything that still needs a look, and **Tell me when a new tapiOca is out**. The box is never ticked for you: unticked is No.

> **Important:** Never trust a guest network in step 4. Anyone on a trusted network can use tapiOca's apps without a password.

> **Tip:** If Plex says "There was a problem fetching channel mappings," reload Plex's page and start again. Plex renames the tuner partway through, so it may still know tapiOca's tuner from before. <!-- wording-ok -->

[[screenshot: The setup's Tuner step, with Plex and Jellyfin ticked and their addresses below]]

### Running it again

Choose **Run First-Time Setup Q&A Again** on the **Setup** tab or the identically named button at the bottom of the page. Your current answers are filled in. When an update brings a new question for an Admin, the setup opens once by itself, titled **What's new in tapiOca**, with just that question.

### The INFO station

A new tapiOca starts with Station 99, **INFO**. Plex won't add a tuner whose guide is empty, so INFO lets you add tapiOca to Plex before you make a Station. Once you have one of your own, INFO is for tapiOca's apps only: Plex and other apps leave it out.

- **What it shows:** a film of teal pearls flying through tapiOca's ring, to a light tune, with the time and date, tapiOca's web address, and a panel that changes every 15 seconds: **What's new in tapiOca**, **tapiOca's apps, in beta**, **By the numbers** (counts of your Stations and shared Media, never titles) and **A tip for tapiOca's apps**.
- **For everyone** who can watch your Stations in the apps, whatever their Viewing Level. It never shows your server's addresses or how it's doing.
- **Always playing.** Its film comes with tapiOca, needs no Plex or internet, is never checked or listed as broken, and drifts slightly, so nothing burns in. The guide shows it as 4-hour listings.
- **Always 99.** You can rename it and change its settings, but not its number. It plays only its own film.

To remove it, delete it on the **Stations** tab. To bring it back, choose **Add the INFO station** under **The INFO station** on the **Setup** tab (another Station on 99 must move first).

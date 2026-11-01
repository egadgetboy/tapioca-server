# Troubleshooting

Start with the **Logs** tab: search it, or tick **Warnings** or **Errors**, and **Copy** what it says. `docker logs stationplay` has more, back to Docker's last rotation (3 files of 10 MB each, as installed). A good bug report, as an issue on GitHub, says what you expected, what happened, and what the log showed.

### Installing and starting

| Symptom | Cause | Fix |
| --- | --- | --- |
| It keeps restarting, and can't write to `/data`. | The data folder isn't owned by tapiOca's user. | Run the `chown` command the message shows, with your folder, then restart. |
| It won't start, and mentions `/dev/dri`. | GPU lines, but no Intel or AMD graphics. | Remove the `devices:` and `group_add:` lines. |
| Port 3310 or 3311 "is already allocated". | Another app uses it. | Change the port line's first number (`"3320:3310"`), and use it everywhere. |
| The page still shows the old version after updating. | Docker didn't fetch or use the new image. | Check that `image:` ends in `:latest`, then pull it yourself and start again (see Updating). |
| "No matching manifest" for your system. | The image is 64-bit only. | Use an x86-64 or ARM64 machine, and a 64-bit OS on a Pi. |
| **Nothing to play yet**, or "Plex didn't accept the token in PLEX_TOKEN". | No Media folder, or Plex isn't set up. | Add a Media folder, or fix `PLEX_URL` and `PLEX_TOKEN`. Use Plex's network IP, not `localhost`. |
| The first check finds nothing at `MEDIA_DIR`. | The media folder isn't mounted there. | Fix the media `volumes` line, or set `MEDIA_DIR` as the check says, restart, and **Check again**. |

### Plex

| Symptom | Cause | Fix |
| --- | --- | --- |
| Plex isn't connected. | Its address, Plex itself, or the token. | Check `PLEX_URL` (not the example), that Plex runs, and `PLEX_TOKEN`. The setup's **Tuner** step says which. |
| Plex can't find the tuner. | tapiOca doesn't answer Plex's search. | Enter the tuner address yourself. |
| Plex says no tuners are available. | Plex hasn't read the new number. | Restart Plex after raising **Tuners**. |
| The guide shows the wrong program. | Plex has an older guide. | **Refresh Guide** in Plex's tuner settings, wait a minute, and reload. |
| "Device not found". | Plex knows the tuner by an old ID. | Compare the log's tuner ID with `DeviceID` at `http://<server-ip>:3310/discover.json`. Put Plex's ID in `data/device.json` as `{"deviceId": "1A2B3C4D"}`, owned by tapiOca's user, and restart. |
| A managed user can't see the Stations. | Their Live TV access is too narrow. | Set it to **Allow Live TV and DVR access**. |
| Skipping intros skips nothing. | Plex hasn't marked any yet. | Turn on Plex's marker settings (see How Stations play). |

### Playing

| Symptom | Cause | Fix |
| --- | --- | --- |
| "This station is off the air. Please report it." | Nothing on it could play, or its stream kept failing. | The log says why: usually Plex or the share is down, or every program is broken. |
| A stream stops, or "is falling behind real time". | The server can't convert fast enough, or the viewer left. | Use a smaller picture, fewer tuners, or a GPU. Run **Test this server**. |
| HDR looks washed out. | ffmpeg can't convert HDR. | Use tapiOca's own image. |
| Subtitles don't show. | None in `AUDIO_LANGUAGE`, or not forced ones. | Add subtitles in that language. The first airing may play without them. |
| No commercials or trailers. | Folders not found, or not rated. | Name them exactly `commercials` and `trailers`, at the top of a Media folder, inside `/media`. Rate them for people with limits. |
| A special doesn't happen. | A more important one overlapped, or it was too late. | The card shows when the next is, and the log says why. |
| Up Next Banners never show, and the log names the data folder. | `DATA_DIR` has characters ffmpeg can't handle. | Remove `DATA_DIR`. |
| A Station stopped following Plex. | An update removing over half its programs waits. | Choose **Update now** if it's right. |

### Files, GPU and access

| Symptom | Cause | Fix |
| --- | --- | --- |
| Many files listed at once. | Plex lost them, or a share was down. | Check the **Media files** line, fix the cause, then **Retry**. |
| **Damaged**, but it plays fine for you. | Something you can't see. | **Retry**: the checks then leave it alone. |
| A file or folder is skipped in a Media folder. | Its name isn't UTF-8. | Rename it, then **Read again**. |
| The GPU isn't used. | The group number, or `/dev/dri` not passed in. | The **Video encoding** line says why. `docker exec stationplay vainfo` shows what the driver sees. |
| The GPU "was turned off after 3 programs in a row failed on it". | tapiOca set it aside. | Restart tapiOca. If it keeps happening, check the driver. |
| Locked out of the page. | No Admin can sign in. | Use `reset-access` (see People and sign-in). |
| A trusted device still asks to sign in. | A non-home name, a proxy, or Docker hiding addresses. | The **Access** tab says why. Open tapiOca by a home address or name. |
| **Away from home** is **Down**. | The apps can't reach tapiOca. | Read the status. Point the proxy at 3311 and list it under **Trusted proxies**. |
| **Away from home** is **Can't check**. | Your router doesn't loop back. | Test from mobile data, or add a DNS host override. |
| "Stopping playback needs Plex Pass…" or "Plex won't say who's watching…". | No Plex Pass, or a token that can't see sessions. | Use Plex Pass, and the server owner's token. |

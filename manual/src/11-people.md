# People, sign-in and Viewing Levels

Everyone who uses tapiOca's page or apps signs in as themselves: someone an Admin added on the **Access** tab. Signing in doesn't change who can watch in Plex, Jellyfin, Emby or Kodi: each app decides that itself.

### Roles

| Role | Can do |
| --- | --- |
| **Admin** | Everything: every Station, and the **Setup**, **Access**, **Logs** and **Broken files** tabs. |
| **User** | Watch what their Viewing Level allows, see **Stats**, make a few Stations (3 to start) and change only their own, and add logos and Intro Bumper videos. On a Viewing Level with limits, they only watch. |

The first person added is always an Admin, and there's always at least one. Until there's an Admin, the page and apps are open to anyone at home, and closed to the internet.

> **Important:** Skipping the first-time setup on a new server leaves no Admin, so anyone at home can change anything. Add one right away.

### Adding a person

1. On the **Access** tab, under **Add a user**, enter a **Name** (up to 40 characters, unlike anyone else's).
2. Enter a **Password**, optional for a User.
3. Optionally, a 4-digit **PIN (optional)**.
4. Choose a **Role**, and for a User, a **Viewing Level** and **Stations they can make**.
5. Choose **Add**.

[[screenshot: The Access tab's list of people, with each person's buttons, and the Add a user form]]

Each row shows the person's **Name**, **Role**, **Viewing Level**, **Stations they make** and **Last signed in** (when, and from what address). Beside each:

- **What they see:** Stations and titles for this person (see Viewing Levels and limits).
- **Rename:** they keep everything, and sign in with the new name.
- **Devices:** the devices they're on, their PIN, and **Make an invite code**.
- **New password** (or **Add a password**): signs them out everywhere else.
- **Set PIN** (or **Change PIN**), and **Remove**.

Three permissions under each person start on: **Can change their own password**, **Can change their own PIN** and **Can report problems**. Admins always can. A new role ends all of that person's sign-ins, but the one making the change.

### Passwords and limits

- **Passwords** need at least 8 characters, with no rules about symbols or capitals. tapiOca's developer chose this, and it's less than NIST's guidelines (SP 800-63B) ask for, 15 characters. A longer one is safer: a few words together work well. tapiOca turns away common passwords (checked on the server against a list it keeps), repeats and runs, and ones built from the person's name or tapiOca's. Every password box has **Show**.
- **Passwords and PINs are stored only as salted hashes.**
- **A sign-in lasts 30 days** after it was last used. The page signs you out after an hour without activity.
- **Wrong passwords:** after 5 from one address in 15 minutes, that address waits.
- **Wrong PINs:** after 5, that person waits 15 minutes, on every device. After 10 on one browser, it needs a password.
- **No password.** A User may have none, such as a "Kids" user who only picks themselves on the TV. They get on a device with an invite code.

## Full or Light sign-in

Each Admin chooses, under **How you sign in** in **Your account**:

- **Full** (the default): your password every time you sign in for Admin tasks.
- **Light:** your password once on each browser or device, then your PIN there, at home. It needs a PIN.

Through tapiOca's internet address, the page never takes a PIN. A PIN's sign-in can't change passwords or PINs, add people, make API tokens or invite codes, or link an app. Choosing **Full**, or a new PIN, ends the sign-ins the old PIN made. A User's PIN never signs in on the page.

## Linked devices and Who's tuning in?

The first time someone signs in on a device, such as the living room TV, it's **linked**: from then on it opens on **Who's tuning in?**, and whoever is watching picks themselves.

- **Who's on the list:** only people who signed in on that device themselves, with their password, an invite code, or **Link an app**. They're on it at home and away. Someone with no password and no PIN is on it only at home.
- **PINs.** A person with a PIN gives it when they pick themselves. The app asks for a PIN, or none, the first time they sign in. An Admin can give their password instead, and gets Admin tasks from a PIN only in Light sign-in, at home.
- **Taking yourself off.** **Sign out** in an app takes you off that device's list, and ends your sign-ins there, even if your sign-in there had already ended. One exception: if the app went back to **Who's tuning in?** by itself before you pressed **Sign out**, you're still listed. Pick yourself, then **Sign out**, or have an Admin **Unlink** the device.
- **A sign-in from Who's tuning in?** lasts a day from when it was last used, so a shared device returns to the list.

> **Important:** On a shared device, anyone can pick anyone who has no PIN. Give everyone without limits a PIN on devices that people with limits use.

**Invite codes.** Choose **Devices** beside a person, then **Make an invite code**. On the device, choose **Sign in** on **Who's tuning in?**, and enter their name and the code. A code works once, for 7 days.

**Signed-in apps** lists each app, as whom, and when it was last used: **Sign out** ends one at once, and one unused for 30 days ends by itself. **Linked devices** lists each shared device and who's on it: **Unlink** signs it out.

### The access log and lockouts

On the **Logs** tab, tick **Access** to see sign-ins, failed sign-ins, sign-outs and changes to who can sign in. The newest 2,000 entries are kept across restarts.

**Locked out?** Create an empty file named `reset-access` in tapiOca's data folder (`sudo touch data/reset-access`), and restart tapiOca. Every person, every trusted network that signs in a person, and every trusted proxy is removed, and sign-in turns off. The file is deleted. Add an Admin again right away.

## Viewing Levels and limits

Each person has a **Viewing Level** that sets what they can see in tapiOca's apps and on its page. Admins always see everything. The server decides every limit, and the apps show only what it tells them.

### Viewing Levels

On the **Access** tab, open **Viewing Levels**. Choose each person's level beside their name, or as you add them.

| Level | Movies up to | TV up to | Unrated titles |
| --- | --- | --- | --- |
| **Unrestricted** (can't be changed) | No limit | No limit | Shown |
| **Teen** | PG-13 | TV-14 | Hidden |
| **Kid** | PG | TV-PG | Hidden |
| **Young Child** | G | TV-G | Hidden |

**New people start on** is the level new Users get: **Unrestricted** until you choose another.

To change a level, choose **Edit** beside it (or **Add a level** for your own, such as "Grandparents"), set these, then **Save**:

- **Name**, **Movies up to**, **TV up to**, and **Unrated titles** (**Shown** or **Hidden**).
- **Media folders:** all, or only some. A show in two Media folders is then seen only through the one the level includes.
- **Genres**, **Tags**, **Collections** and **Studios:** type a name and choose **Add** to hide anything with it, whatever its rating. Plex's names are offered as you type. Tags are what Plex calls labels.

Ratings are read as ages, for the US and other countries alike. An episode counts as its show, or its own rating if that's stricter. A title with no rating, or one tapiOca doesn't know, is unrated. To give one person ratings of their own, give them a level of their own.

[[screenshot: The Viewing Levels panel, with the four built-in levels and Also hides]]

### What they see

Choose **What they see** next to someone's name. For Kit, **What Kit sees** has three parts:

- **Stations:** for each, **As Kid says** (their level), **Allowed** or **Blocked**, with why each is shown or hidden.
- **Also hidden for Kit:** genres, tags, collections and studios, and titles you find by typing, hidden whatever their level shows.
- **Allowed for Kit:** titles their level would hide, shown anyway, if they're in a Media folder the level includes.

### How limits work on Stations

Everyone watching a Station sees the same stream, so:

- **A Station is shown** to someone only if everything on it is within their level. Allow or block it under **What they see** to change that.
- **"Restricted program."** On any Station, a program someone may not watch is blocked for them while it airs, and their guide shows "Restricted program". Their Station comes back by itself afterward, and everyone else watches on.
- **Limits are checked while a title plays,** so a change stops it within seconds.
- **Nothing hidden shows** anywhere for them: not in Media, search, **More like this**, cast pages, the Resume row or the guide.
- **People with limits only watch:** they can't make Stations.

Until tapiOca knows a Station's ratings, or a title's genres and tags, it's hidden from anyone it might not suit.

### Commercials and trailers

On a Station someone with limits can see, a clip plays only if its folder is rated at or below the Station's highest-rated program. Under **Commercials and trailers**, below the levels, rate **Commercials** (TV ratings), **Trailers** (movie ratings) and each decade's folder, then choose **Save ratings**. Until then, those Stations skip unrated clips, and an alert says how many.

### What tapiOca enforces, and what it can't

Viewing Levels work in tapiOca's apps and on its page, for someone signed in as themselves. They don't cover:

- **Plex, Jellyfin and anything else on the tuner,** or a Station's stream address played at home (such as in VLC). They don't say who's watching, so they show everything. See Tuner access, and Blocking Stations for Plex users.
- **Devices without PINs,** where anyone can pick anyone.
- **Someone who knows another's password.**
- **A rating or genre Plex has wrong,** or what's inside a program beyond its rating, genres and tags.

> **Tip:** Use your devices' own controls too, such as Apple's Screen Time or Google's Family Link.

The access log records each change to a level, a person's choices and the clip ratings.

### Blocking Stations for Plex users

Plex shows every Station to everyone with Live TV on your server. With Plex Pass on the server owner's account, tapiOca can stop a Plex user's playback instead.

1. On the **Access** tab, open **Block stations for some Plex users**.
2. Open each Plex user and tick the Stations they can't watch.
3. Tick **Stop Plex users from watching stations blocked for them**, and choose **Save**.

When a blocked user tunes in, Plex stops it within seconds and shows "This station isn't available on your Plex account." The panel lists **Recently stopped**. This covers Plex apps only (you, Plex Home users and friends you've shared Live TV with), needs a Plex user for each person, and needs sign-in on in tapiOca. If two Stations air the same program at once and Plex gives no Station number, tapiOca can't tell them apart, and stops neither.

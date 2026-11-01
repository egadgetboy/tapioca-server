# Security and the API

### The two ports

**Keep port 3310 on your home network.** Its tuner, guides and streams never ask for a password, because Plex can't sign in to a tuner. If it's reached from the internet anyway, tapiOca treats those connections as from the internet, and alerts Admins.

**The public port** (`PUBLIC_PORT`, 3311) is for the page and apps from the internet, behind a reverse proxy with HTTPS or a tunnel. There:

- **No Plex addresses:** the tuner, guides, streams and playlist don't exist.
- **Sign-in is always required.** Visitors who haven't signed in see only the sign-in page, tapiOca's name and version, its notices and privacy notice, and what the apps need to connect. Until signing in is on, it says only "This tapiOca client can't reach the server. Please check back later."
- **Wrong passwords are limited:** 5 in 15 minutes for each address, and 100 for the whole internet.
- **Apps need HTTPS,** and API tokens are refused unless an Admin allows them.

### Built-in protections

- **Plex.** The page never sees your Plex token, and can't send its own requests to Plex. tapiOca plays only Plex's own file addresses.
- **Uploads.** Logos must be images and Intro Bumpers videos, each made into a clean copy. Limits: 500 logos, 50 videos, and 2 GB left free on the data folder's disk.
- **The page** runs only its own scripts, can't be embedded in another site, and refuses changes from other sites (each change carries a header only tapiOca's page sends).
- **Backups** restore only if they're genuine tapiOca backups.
- **Outside connections** go only to addresses you typed and, if you said yes, GitHub. Other addresses must be on the internet. None follows a redirect.
- **Sign-ins.** Passwords and PINs are kept as salted hashes, API tokens as fingerprints. An app's stream addresses end with its sign-in.
- **Tested every release.** Each release passes tapiOca's security tests before it's published: every address, from every kind of visitor, and its sign-ins, outside connections and file paths.

### If your server is reachable from the internet

- **Update promptly.** Only the newest release gets fixes.
- **Keep Plex up to date** too.
- **At your reverse proxy,** remove any `X-Forwarded-For`, `X-Real-IP` or `Forwarded` a visitor sends, limit sign-in attempts if it can, and never cache signed-in answers (tapiOca marks them `no-store`). List it under **Trusted proxies**.
- **Use long passwords** for Admins.
- **Never forward** your NAS's admin ports, or 3310.

**Signs of a break-in:** sign-ins, Admins, addresses, devices, apps or API tokens you don't recognize on the **Logs** and **Access** tabs; unexpected files in the data folder (tapiOca never writes programs there); processes in the container other than tapiOca, `ffmpeg` and `ffprobe`; or high processor use while nothing plays. If you find any, stop tapiOca, restore a backup from before, change every Admin password, remove every linked device and API token, change your Plex password, and update.

**Reporting a security problem.** Report it privately, never in a public issue: on tapiOca's GitHub page (`github.com/egadgetboy/tapioca-server`), choose **Security**, then **Report a vulnerability**. You'll get a reply within 7 days.

### tapiOca's API

*Optional.* Your own scripts, home automation and other players can use tapiOca's API, under `/api/v1`: the server, its Stations with what's on now and next, the guide, each Station's HLS stream, and how tapiOca is doing. An Admin token can also update a Station, check its files, refresh Plex's guide and make a backup. Version 1 only grows: a breaking change would come as a new version, with version 1 kept at least 6 months after. The reference is `docs/api.md` in the repository, with an OpenAPI spec at `/api/v1/openapi.json`. The apps' own addresses, under `/api/internal`, aren't part of it.

**API tokens.** With sign-in off, the API needs no token at home. Otherwise:

1. On the **Access** tab, open **API tokens**.
2. Enter **What it's for**, such as "Home Assistant", choose a **Scope** (**Viewer (reads only)** or **Admin**) and when it **Expires** (**In 30 days**, **In 90 days**, **In a year** or **Never**; 90 days to start).
3. Choose **Make token**, then **Copy**. It's shown once.

Scripts send it as `Authorization: Bearer <token>`. A token works only with the API, never does more than its Admin can now, and stops when it expires, is revoked (**Revoke**), or its Admin is removed. **Accept API tokens from the internet** (off to start) lets tokens work through the public port, over HTTPS.

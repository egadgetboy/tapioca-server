# Home, away and your network

tapiOca treats every connection as either at home or from the internet. Several panels on the **Access** tab decide what each may do.

### At home or from the internet

Anything reaching the public port (3311) is from the internet, even from inside your home. A connection to the home port (3310) is at home only when it comes from a home or VPN address (such as 192.168.x.x, 10.x.x.x, 172.16.x.x to 172.31.x.x, or Tailscale's 100.64.x.x), doesn't ask for tapiOca by an internet address, and no proxy says it's from the internet. Anything else is treated as from the internet, and gets only what the public port gives.

**Home names.** Trusted networks also need tapiOca asked for by a home name: an address, a single word (such as `nas`), a name ending in `.local`, `.lan`, `.home`, `.home.arpa`, `.internal`, `.localdomain` or `.ts.net`, `BASE_URL`'s name, or one listed under **Names for tapiOca at home**. This also stops another web page from pointing a name of its own at tapiOca and using your browser to change it (DNS rebinding).

## Trusted networks

Devices on a trusted network skip signing in. Nothing is trusted until an Admin adds it.

1. On the **Access** tab, open **Trusted networks**. It says where you are, such as "You're at 192.168.1.44, on Home Wi-Fi."
2. Enter a **Network, or one device's IP address** (such as `192.168.1.0/24`, `192.168.1.44` or your VPN's `10.8.0.0/24`), or choose **Add the network you're on**.
3. Give it a **Name (optional)**, such as "Home Wi-Fi", and choose what **Its devices** get:
   - **Who's tuning in?** (the default): in tapiOca's apps, the device is linked without signing in, and opens on **Who's tuning in?** Its list starts empty: each person chooses **Sign in** there once.
   - **Signed in as** a person (such as **Signed in as Ada**): the device is signed in as that person, for watching, in the apps and on the page. For an Admin, only one device's address: reserve it in your router.
4. Choose **Add**.

> **Important:** Never add a guest network. Anyone on a trusted network can use tapiOca's apps without a password.

- **Home addresses only,** up to 50. A network wider than 256 addresses asks first. The narrower of two overlapping entries wins.
- **Only there.** What a trusted network signs in works only on that network, never away from home. Changing or removing the network ends it.
- **For watching.** A trusted network's sign-in can't change passwords or PINs, add people, make tokens or invite codes, or link an app. An Admin gives their password for Admin tasks.
- **Only when tapiOca can be sure:** signing in on, a home name, and tapiOca able to see where connections come from. Nothing is ever trusted through Docker's own address.


## Trusted proxies

List your reverse proxy or tunnel under **Trusted proxies**, by its **Proxy's IP address** on your home network, then **Add**. List up to 10 (or `127.0.0.1` for a tunnel in tapiOca's own container).

- **Only a listed proxy is believed** about its visitors, in `X-Real-IP`, `X-Forwarded-For` and `Forwarded`, which must all name the same visitor. Headers from anything else are ignored, and Admins get an alert.
- **HTTPS.** tapiOca believes a request came over HTTPS only from a listed proxy, so the apps from the internet need their proxy listed.
- **Trust this proxy.** When tapiOca's away-from-home check comes through a proxy that isn't listed, it offers **Trust this proxy**, which checks again and lists just that address.
- **A proxy in another container on the same server** reaches tapiOca from Docker's own address (such as `172.17.0.1`). List it so wrong passwords count by each visitor, but nothing is trusted through it. For trusted networks through it, give the proxy its own address on a Docker network shared with tapiOca.

### Names for tapiOca at home

If you open tapiOca at home by a name such as `tapioca.example.com` (split DNS), list it under **Names for tapiOca at home** (up to 10), so trusted networks work by it. Your away-from-home address's name can't be one.

### Doors left open

When tapiOca can't be sure a connection is from home, it treats it as from the internet, and alerts Admins (never with an address or a name):

| Left open | What tapiOca does |
| --- | --- |
| The home port forwarded on the router | Treats it as from the internet. Close the forward. |
| A reverse proxy or tunnel pointed at 3310 | Treats its visitors as from the internet. Point it at 3311. |
| An internet name on 3310 | Never trusts it. If it's a home name, list it under **Names for tapiOca at home**. |
| Forwarding headers from a device that isn't listed | Ignores them. If it's your proxy, list it. |
| Docker hiding every device's address | Turns trusted networks off. |
| Signing in left off | Open at home only. Nothing from the internet gets in. |
| An internet address asking for the tuner | Never gives it the tuner. |

**When Docker hides addresses.** Some Docker setups pass every connection through Docker's own address, as Docker Desktop always does. When that happens, trusted networks turn off, and the **Access** tab says why. The fix: host networking (`network_mode: host`, in place of the `ports:` lines), or `"userland-proxy": false` in Docker's `daemon.json`, then restart Docker and tapiOca. On Docker Desktop there's no fix: every device signs in. When only some connections are hidden, open tapiOca by its IPv4 address.

## Tuner access

The **tuner** is what Plex, Jellyfin and other apps use: the HDHomeRun tuner, the guide, the list of Stations and their streams. None of these apps can sign in. It's on the home port only. Under **Tuner access** on the **Access** tab, choose who can use it:

- **Any device on my home network** (the default).
- **Only these devices:** enter a **Device's IP address, or a network** and a **Name (optional)**, then **Add** (home addresses, up to 50). **Plex server only** lists just Plex's address, after showing you which it is.

**Recent tuner connections** shows each device that used the tuner in the last 7 days, what it asked for, and whether it was **Refused**. **Allow** lists one. Plex in Docker often comes from the Docker network's address, so use **Plex server only** or **Allow** rather than typing the server's address. Any device can call itself Plex: check the address first.

> **Note:** An IP address isn't a password. Tuner access keeps out devices that find the tuner by mistake, not someone at home who means to get in. tapiOca's own apps, signed in, never need listing. Turn sign-in on first, so no one else can change this.

## Away from home

**Often you don't need a way in.** Plex users away from home watch through Plex, which relays the stream. Only tapiOca's page and apps need a way in from outside.

> **Important:** Never open port 3310 to the internet. Its tuner and streams never ask for a password. Every way in below keeps it closed.

| Way in | Good for | Open to the internet | Cost |
| --- | --- | --- | --- |
| **Tailscale** (a VPN) | The page and apps on your own devices | Nothing | Free for personal use |
| **WireGuard on your router** (a VPN) | The same | One port, for the VPN | Free |
| **A reverse proxy with HTTPS** | The apps anywhere, for anyone you've added, with no VPN; also the page | Port 443, to the proxy | A domain name, about $10 to $15 a year |
| **A Cloudflare Tunnel** | The page only | Nothing | Free |

A VPN is the most private, and tapiOca treats a device on it as at home. A reverse proxy suits people who won't install a VPN. A Roku can't run a VPN, so it needs the reverse proxy.

### Turning on the apps away from home

1. At home, add the first Admin, with a long password, if you haven't.
2. On the **Access** tab, open **tapiOca's apps away from home**, and tick **Let tapiOca's apps watch away from home** (off to start).
3. Under **The address apps reach tapiOca at from outside**, enter your reverse proxy's `https://` address with no port (such as `https://tv.example.com`), or your VPN address with its port (such as `http://nas.your-tailnet.ts.net:3310`).
4. Choose **Media away from home:** **Original** (the default, as at home), or **Up to…** 1 to 200 Mbps, which converts larger files down to fit, at most 1080p.
5. Choose **Save**. The status below should show **Ready**.

Each Station watched away from home uses your upload: about 1.7 Mbps at 480p, 3.7 at 720p and 6.2 at 1080p. The panel shows your upload as the apps measured it from outside. Without `PUBLIC_PORT`, apps reach tapiOca from outside only through a VPN.

[[screenshot: The tapiOca's apps away from home panel, with an https address and the Ready status]]

**The reach check.** While it's on, tapiOca calls its own address as an app away would: at startup, when you save, every 5 minutes, and with **Check now**. **Ready** means it works. Anything else says the problem in one sentence, such as a proxy pointed at 3310, no HTTPS, a name that isn't found, a bad certificate, or a redirect. **Away from home** in the header shows **Up**, **Down**, **Checking** or **Can't check**. One failure never makes it **Down**.

**When your router answers from home.** Many routers don't let devices at home reach the home's own internet address (NAT loopback, or hairpinning). Apps away still work, but tapiOca's check from home can't, so it shows **Can't check**, or **Up** when an app came in from outside in the last 15 minutes. To be sure, open your address on a phone using mobile data. To fix it, add a DNS host override in your router (such as Unbound's, in OPNsense or pfSense) pointing your address's name at the proxy's home address.

### Tailscale

1. Install Tailscale on the server (on TrueNAS, **Apps → Discover Apps → Tailscale**; on Unraid, its plugin; on Synology, **Package Center**), sign in, and turn on **MagicDNS**.
2. Install it on each device that should reach tapiOca, on the same account.
3. Use the server's Tailscale name with port 3310, such as `http://nas.your-tailnet.ts.net:3310`, for the page and as the apps' outside address.

### WireGuard on your router

Turn on your router's built-in WireGuard server, and add each phone or tablet in the WireGuard app. While connected, use tapiOca's home address as if you were home.

### A reverse proxy with HTTPS

The proxy (such as Caddy or Nginx Proxy Manager) takes HTTPS from the internet and passes it to tapiOca's **public port**, 3311, never 3310. You need a domain name pointing at your home (with dynamic DNS if your address changes), port 443 forwarded to the proxy, and a certificate.

**Caddy** (the whole `Caddyfile`):

```
tv.example.com {
    reverse_proxy 192.168.1.20:3311 {
        header_up X-Real-IP {remote_host}
    }
}
```

**Nginx Proxy Manager** (or NPMplus): a proxy host for `tv.example.com`, forwarding to `192.168.1.20`, port `3311`, with a Let's Encrypt certificate and **Force SSL** on its **SSL** tab.

Then, at home, list the proxy under **Trusted proxies**, and turn on the apps away from home with its `https://` address. The proxy must pass each visitor's address in `X-Real-IP` or `X-Forwarded-For`, replacing any a visitor sends.

On the public port, apps connect only over HTTPS; each app's stream addresses are its own and end with its sign-in; and API tokens are refused unless an Admin allows them.

### A Cloudflare Tunnel (the page only)

A tunnel reaches the page without opening a port. It's not for the apps: Cloudflare's free plan isn't meant for video.

1. At home, add the first Admin, with a long password. Keep `PUBLIC_PORT` and its port line.
2. In Cloudflare **Zero Trust**, add a public hostname to your tunnel with the service `http://<your-server-ip>:3311`. Never 3310.
3. List the address `cloudflared` reaches tapiOca from under **Trusted proxies** (`127.0.0.1` if it runs in tapiOca's own container).
4. **Strongly recommended:** in Zero Trust **Access**, add the hostname as a self-hosted application allowing only your people's email addresses, so Cloudflare asks for an email code first.

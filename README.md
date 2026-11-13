# EaveLuxOS
### The Intelligent Lighting Control Platform

By **Christopher A. Tankelewicz (ThinkTank4n6)** · MIT License · version 3.13.1

EaveLuxOS currently works with **Trimlight Edge** permanent-lighting controllers.
Its scheduling, mapping and design tools are built to grow to other brands.
*(Formerly "LumaOS" and "Trimlight Scheduler". Updating keeps all your settings.)*

**New here? Read [MANUAL.md](MANUAL.md)**, the full step-by-step guide.

A free, point-and-click control app for **Trimlight Edge** permanent holiday
lights. It runs on any always-on computer in your home, such as a mini PC, a
spare laptop or a Mac mini. You use it from that computer's browser or from
your phone.

*EaveLuxOS is an independent community project. It is not made, endorsed or
supported by Trimlight. Trimlight and Trimlight Edge are trademarks of their
owner and are used here only to say which hardware EaveLuxOS works with.*

## What it does better than the Trimlight Edge app

- **Uses true sunrise and sunset times.** They are calculated for your exact
  location every day, and you can add offsets like "15 minutes after sunset"
  or use dusk and dawn.
- **Gets daylight saving time right.** By default it follows your time zone's
  official rules. You can also hold daylight time or standard time all year.
- **Sorts out overlapping schedules with clear priorities.** Holidays beat your
  everyday lights, and you decide the rest.
- **Can react to weather.** For example, it can switch to a snowfall pattern
  when it's snowing (US National Weather Service, no account needed).
- **Rotates patterns.** It can switch among any number of patterns every few
  minutes.
- **Has a security flash.** Bright lights on demand, from a button, Home
  Assistant or a webhook, and then the lights go back to normal.
- **Gamma-corrected colors (optional):** LED colors look like the colors you
  pick instead of pale and washed out, with a side-by-side converter and a
  test on the house.
- **A bulb painter:** paint single bulbs, ranges, zones or every Nth bulb,
  in one repeat of the pattern or across the whole house, with a live count
  of the controller's 30 color slots.
- **Includes a pattern designer with a live animated preview.** You can also
  save designs into the Trimlight app's own library.
- **Lets you share patterns with other owners.** Export and import pattern
  files; your credentials are never included.
- **House map:**
  - A bulb finder that lights any bulb or range.
  - Photos of the front, both sides, the back and a shed (or any side you
    add), with pinned landmarks.
  - **Automatic roofline detection** from each photo, which you then adjust
    point by point, plus hand-traced ridges and "wire only" stretches.
  - A **flat diagram** of every side, with landmarks and bulb numbers, that
    you can download as an SVG.
  - Named zones you can paint in one step.
- **Accounts with roles:** Administrators, Editors (patterns, schedules, house
  map, light controls) and Viewers (look only).
- **A different pattern each night,** in any order you choose.
- **Playlists:** rotate patterns with their own time each (Christmas 10
  minutes, Snowfall 5, Warm white 15), or a different one each night.
- **Whites by color temperature,** from 2200 K candlelight to 6500 K daylight,
  for architectural lighting.
- **Recreate any built-in effect with your own colors.**
- **A community library** of patterns shared by other owners.
- **Home Assistant and Apple Home:** a ready-made Home Assistant package, and
  webhooks for motion sensors and automations.
- **Music shows that don't get cut off.** Start a show (or plan show nights)
  and this app leaves the lights to the controller's music mode instead of
  switching them back to the schedule mid-song.
- **Optional safety net:** copies the next nights into the controller's own
  timers, so the lights still run if the computer is off. It backs up the
  controller first, verifies every write, and never touches your own timers.
- **Stores everything in a local SQLite database,** with version history and
  one-click restore. Nothing has to live on the controller.
- **A guided hardware test** (`python3 main.py hwtest`) checks what only your
  real controller can answer, and writes a report.
- **Keeps your controller's clock correct.** It sends the correct time to the
  controller every day.

## What you need

1. **A Trimlight Edge controller** that is already set up in the Trimlight Edge app.
2. **A Trimlight API Client ID and Client Secret.** Trimlight issues these on
   request: sign in with your Trimlight account at
   https://trimlight.ledhue.com/trimlight/v1/api-credentials/apply
   and choose **Get API credentials** (see the manual, section 2). If that
   doesn't work for you, contact Trimlight support and ask for API access.
3. **A computer that stays on** (Windows, Mac or Linux) with
   **Python 3.11 or newer** (only if you run from source; the ready-made
   downloads under **Install** include Python). You can get Python from https://www.python.org/downloads/.
   On Windows, tick **"Add python.exe to PATH"** during installation.

## Install

### Easiest: download the installer (no Python needed)

Open this project's **Releases** page on GitHub and download the file for your
computer.

**Windows:** `EaveLuxOS-Windows.zip`
- Unzip it into a folder you'll keep and double-click `EaveLuxOS.exe`.
- If Windows says "Windows protected your PC", click **More info › Run
  anyway** (the app isn't code-signed).
- Settings are kept in `%LOCALAPPDATA%\EaveLuxOS` (for example
  `C:\Users\you\AppData\Local\EaveLuxOS`), the same folder for every version,
  so updating is just unzipping the new version and starting it.

**Mac (Apple silicon, M1 and newer):** `EaveLuxOS-macOS.dmg`
- Open it and drag **EaveLuxOS** into **Applications**.
- The first time, macOS blocks it because it isn't notarized by Apple. Open
  **System Settings › Privacy & Security**, scroll down, and click **Open
  Anyway** next to EaveLuxOS. On older macOS versions, right-click the app
  and choose **Open**.
- It runs in the background with no Dock icon; your browser opens to it. To
  stop it, use **Settings › Quit the app**.
- Settings are kept in `~/Library/Application Support/EaveLuxOS`.

**Linux PC (Ubuntu, Debian, Mint):** `eaveluxos_<version>_amd64.deb`
- Install with `sudo apt install ./eaveluxos_<version>_amd64.deb`, then start
  **EaveLuxOS** from the app menu, or run `eaveluxos` in a terminal.
- For other distributions, use `EaveLuxOS-Linux-x86_64.tar.gz`: unpack it and
  run `./eaveluxos`.

**Raspberry Pi (64-bit Raspberry Pi OS, Pi 3/4/5):** `eaveluxos_<version>_arm64.deb`
- Install with `sudo apt install ./eaveluxos_<version>_arm64.deb`.
- A Pi usually runs without a screen. Start it with `eaveluxos run`, then open
  `http://<pi-address>:8787` from your phone. Under **Settings › Start
  automatically**, make it start with the Pi, then run
  `sudo loginctl enable-linger $USER` once so it starts without anyone
  logging in.
- 32-bit Raspberry Pi OS: run from source instead (below). Python 3.11 is
  already installed on current Pi OS.

On Linux and the Pi, settings are kept in `~/.local/share/eaveluxos`.

**Commands such as the hardware test:**
- Windows: `EaveLuxOS-cli.exe hwtest`
- Mac: `/Applications/EaveLuxOS.app/Contents/MacOS/EaveLuxOS hwtest`
- Linux and Pi: `eaveluxos hwtest`

### From source (Python 3.11 or newer)

1. Download and unzip this folder anywhere, for example in Documents.
2. Double-click the launcher for your system:
   - **Windows:** `Start EaveLuxOS.bat`
   - **Mac:** `Start EaveLuxOS.command` (the first time, right-click
     it and choose Open)
   - **Linux:** `start-eaveluxos.sh`
3. Your browser opens to the setup assistant. Enter your Client ID and Secret,
   choose your controller, set your location, and create your Administrator
   account for signing in from your phone.
4. In the **Trimlight Edge app**, set the controller to **Manual** and turn off
   its timers, so the two schedules don't fight.
5. Under **Settings › Start automatically**, turn on starting the app with the
   computer.

### On your phone

Open the address shown under **Settings › Phones and other computers**, for
example `http://192.168.1.20:8787`, while you're on your home Wi-Fi. Then sign
in with your account. In Safari, choose **Share › Add to Home Screen** to
get an app icon.

## The tabs

| Tab | What it's for |
|---|---|
| **Home** | Shows what's on now and today's sunrise, sunset and lights-on bar. It has one-tap patterns, brightness and speed, the security flash, and the week ahead. |
| **Patterns** | Your patterns, the patterns saved in the Trimlight app, and all 180 built-in effects. You can try any of them on your lights. |
| **Create** | The pattern designer: pick colors, set bulbs per color, or paint single bulbs, ranges and every Nth bulb, choose an animation, preview it, and save. |
| **Schedule** | Rules (sun-based or set times, date ranges, days, rotation, brightness, priority), plus weather rules, the security flash, and importing timers from the Trimlight app. |
| **Music** | Music shows: steps aside while the controller's own music mode (started in the Trimlight app) makes the lights dance, for a set time or on planned show nights. |
| **Lights** | A card for each controller on the account (online, on/off, bulbs); tap one to manage it. Bulbs per port (Simple mode) or exact bulb ranges, including mirrored ports (Advanced mode). Also the LED chip type, color order, color test and controller name. |
| **Date & Time** | Location, time zone, daylight saving mode, today's sun times and the controller clock. |
| **House map** | Bulb finder, photos of each side, automatic roofline detection, landmarks, zones and the flat diagram. |
| **Manual** | This guide (MANUAL.md) inside the app, with a search box and clickable contents. |
| **Settings** | Your Trimlight account, your account and password, accounts for other people, start automatically, webhooks, and backup and sharing. |

The bottom of every screen, including the sign-in page, shows the version,
the copyright notice and a link to the MIT License.

## Several schedules a day

A day can have several rules at different times, like the Trimlight Edge
app's timers: for example **6:00 AM → sunrise** and **sunset → 11:00 PM**.
Each runs in its own time; priorities only decide where rules overlap. A
rule never runs longer than 20 hours, so a 6:00 AM → sunrise rule skips the
days when the sun is already up by then.

## How overlapping rules are decided

The scheduler checks these from highest to lowest:

1. **Security flash.** It runs for a set time and then steps aside.
2. **Something you turned on or off by hand.** It lasts until the next
   scheduled change.
3. **A weather rule.** These apply only while a scheduled rule has the lights
   on, and only if the weather rule's priority is higher than that rule's.
4. **The scheduled rule with the highest priority.** Holiday rules (with
   dates) default to 200 and everyday rules to 100. Weather defaults to 150, so
   snow replaces your everyday lights but not Christmas.

## Privacy and security

- Your Trimlight secret is stored only on the app's computer, in the
  owner-only database `data/eaveluxos.db`, **encrypted with AES-256-GCM**. The
  key is `data/secret.key` (or the `EAVELUXOS_SECRET_KEY` environment variable,
  to keep it off the data disk). It is never shown in the app again and never
  sent to phones. Encryption needs the `cryptography` package; the installers
  include it and the launchers install it.
- Everyone signs in with their own **account**: **Administrator** (everything),
  **Editor** (patterns, schedules, house map and light controls, but not
  accounts, the Trimlight connection, location or other household settings)
  or **Viewer** (look only). The server enforces this on every request, and at
  least one active Administrator always remains.
- Passwords are stored as salted **scrypt** hashes. Passwords saved by older
  versions are upgraded the next time you sign in. The single app password of
  older versions becomes the password of the Administrator account **admin**.
- The computer running the app can always use it. Other devices must sign in.
  Before any account exists, they need the 6-digit setup code shown in the
  app's window or log. A request that came through a reverse proxy or tunnel
  on the app computer (Caddy, Tailscale Serve, cloudflared) is treated as
  another device, never as this computer, because those add an
  `X-Forwarded-For` header. **nginx doesn't add it by default**: add
  `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` to its
  `location` block. A proxy or port forward that adds no such header (nginx
  without that line, `ssh -L`, `socat`, a TCP-only tunnel) looks exactly like a
  browser on this computer, so turn on **Settings › Require signing in on this
  computer too** before using one.
- Sign-ins are short: they end after **8 hours without use** (an Administrator
  can choose 1 hour to 7 days) and always **7 days** after signing in.
  Changing your password signs you out on every other device; changing or
  disabling an account signs that account out everywhere.
- Changing accounts, the Trimlight account, webhooks, the port,
  start-automatically or the "require signing in on this computer" option
  from a phone asks for your password again.
- For encryption on your Wi-Fi, run `python3 main.py make-cert` once and
  restart the app (or use your own certificate; see the manual).
- Keep the app on your home network. **Don't port-forward it.** For access away
  from home, use a VPN into your network.
- Webhooks are off until you turn them on, and they need their own token.

## Run it in a container (Docker)

For a home server or NAS that already runs Docker:

```sh
cp env.example .env        # optional: BIND_ADDRESS, HOST_PORT, EAVELUXOS_ALLOWED_HOSTS
docker compose up -d --build
docker compose logs eaveluxos   # the 6-digit setup code for the first sign-in
```

The container runs as an unprivileged user (uid 10001), never as root, with
a read-only file system except its data volume, all Linux capabilities
dropped and `no-new-privileges`. By default it only listens on the server
itself (`127.0.0.1:8787`); set `BIND_ADDRESS` in `.env` to the server's LAN
address to use it from phones. Nobody counts as "this computer" in a
container, so everyone signs in, starting with the setup code from the log.

## Where your data is kept

- **Windows:** always `%LOCALAPPDATA%\EaveLuxOS`, whichever version or copy
  of the app you run (from source or the `.exe`). The first time 3.7 or newer
  starts, it copies your settings there from the earlier version's `data`
  folder (the newest one it finds next to it or in a sibling version folder,
  such as `Downloads\eaveluxos-3.6.0\eaveluxos\data`); the old folder is left
  as it was. "Start automatically" is also switched to the copy you run.
  For a USB stick, put an empty `portable.txt` next to `main.py` or
  `EaveLuxOS.exe` to keep data in `data` next to the app instead.
- **Mac app:** `~/Library/Application Support/EaveLuxOS`.
- **Linux and Raspberry Pi packages:** `~/.local/share/eaveluxos`; from source,
  `data` next to `main.py`.
- **Container:** the `eaveluxos-data` volume.

**Settings › Setup and about** shows the folder in use.

## Home Assistant example

Turn on webhooks in Settings and copy the token. Then add this to your
configuration:

```yaml
rest_command:
  lights_security_flash:
    url: "http://APP-COMPUTER-IP:8787/api/hook/flash"
    method: POST
    headers:
      X-Token: !secret trimlight_webhook_token
```

Available actions:
- `flash` (optional `{"minutes": 10}`)
- `stop_flash`
- `on` (`{"effect": "pattern_name"}`)
- `off`
- `resume`
- `levels` (`{"brightness": 0-255}`)

## Troubleshooting

- **"Trimlight didn't accept these":** check the Client ID and Secret. They are
  case-sensitive.
- **The lights didn't change:** look at the Home tab under Controllers and
  activity. Make sure the controller shows as online in the Trimlight app.
- **Times are off by an hour:** on the Date & Time tab, check the time zone and
  make sure daylight saving is set to Automatic. Also check that the computer's
  own clock is correct.
- **On Linux, it doesn't start until someone logs in:** run
  `loginctl enable-linger $USER` once.
- **The log** is in `data/eaveluxos.log`.

## Building executables and releases

Executables are built by GitHub Actions. Push a version tag and the workflow
in `.github/workflows/release.yml` runs the tests, builds Windows, macOS and
Linux executables with PyInstaller, and attaches them to a new release:

```
git tag v3.2.1
git push origin v3.2.1
```

To build one yourself for the computer you're on:

```
python -m pip install pyinstaller pillow tzdata
python packaging/build.py
```

The result is in `dist/`. `.gitignore` keeps the private `data` folder (your
credentials, password hash, photos and backups) out of the repository; never
remove that rule.

## Notes for developers

Run the tests from the app folder with `python3 -m unittest -v` (stdlib only,
no network: a fake Trimlight cloud in `tests/` checks request signatures).


This app uses only the Python standard library, with no installs except
`tzdata` on Windows, and it has no build step. Run `python3 main.py run --open`.
Settings live in `data/settings.json`; `python3 main.py check` validates them.

It's built on Trimlight's published V2 API documentation, which is dated 2022.
Two behaviors are based on reasonable readings of that documentation and are
worth confirming on your firmware:
- A port set to Off is sent as start 0 / end 0.
- Designer patterns saved to the Trimlight library are sent with category 1
  (custom).

Older installs that used `config.toml` and `.env` are imported automatically on
first start.

## License

MIT License. Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6).
See [LICENSE](LICENSE). Trimlight and Trimlight Edge are trademarks of their
owner; this project is independent and not endorsed by Trimlight.

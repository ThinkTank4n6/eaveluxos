# Changelog

## 3.9.0: music shows

- **New Music tab.** Trimlight's controller makes the lights dance to music
  on its own, but its music mode can only be switched on in the Trimlight
  app over home Wi-Fi; Trimlight's cloud has no music controls. Until now this
  app would notice the change and put the schedule back mid-song. **Start a
  music show** (for a set time or until stopped) and this app sends nothing to
  the controller (no patterns, checks or timer copies) until the show ends,
  then sends the scheduled pattern in full.
- **Show nights:** planned shows with dates, days and sunset or clock times,
  like schedule rules. Stopping one ends it for that night only.
- A security flash still interrupts a show. Choosing a pattern or Return to
  schedule ends it. Brightness and speed are left to the Trimlight app during
  a show.
- Home and the status pill say *Music show* while one runs.
- Webhook and Home Assistant actions `music` and `stop_music`.
- Manual section 16, Music shows: how to start the controller's music mode,
  and wiring a computer to the controller's aux input. Later sections are
  renumbered.
- `tools/music-capture/`: a guide and a report tool for recording how the
  Trimlight app switches music mode on over the home network (research for a
  later version). The tool reads pcap and pcapng captures and needs nothing but
  Python.
- 22 new tests (190 total).

## 3.8.1: security and reliability fixes

- **Security: a request hidden in the body of another request is no longer
  run.** Through a reverse proxy that reuses its connection (Caddy does by
  default), an outside request could carry a second request that the app
  took as coming from this computer, with full Administrator rights. Every
  request body is now read in full, and once a connection has carried a
  proxied request, nothing else on it counts as this computer.
- **Daylight saving: the night clocks fall back no longer turns the lights on
  a second time.** A rule ending between 1:00 and 2:00 that night switched
  off, then on again an hour later. Schedules now compare real moments, not
  clock readings, and a security flash lasts its real length across the change.
- **Weather never holds up the lights.** A slow National Weather Service
  could stall scheduled changes, buttons and the Home screen for up to a minute.
- **Never two schedulers:** a copy started while another was still starting
  no longer moves to the next port and runs alongside it, and moving to a new
  port waits for the old scheduler to stop and stops a new copy that fails.
- **Safety net:** a timer copy changed or cleared in the Trimlight app is
  noticed at the next check (about 5 minutes), and the app drives the lights
  itself until it has copied it again. A copy that fails halfway is taken back
  instead of left half old, half new.
- **Import:** Replace everything keeps your house map and safety-net
  settings (exports don't include them). Add to mine keeps imported rules on
  their own pattern when a pattern with the same name already exists here.
- **Database:** a full disk, a locked file or a folder that can't be written
  no longer gets the database set aside as damaged and settings restored from
  the last good copy; the app reports the problem and changes nothing.
- **Sign-in:** behind a proxy, failed sign-ins are counted per visitor instead
  of for everyone at once (IPv6 per /64). "Require signing in on this
  computer" stays on if the encryption key is lost.
- Status reads no longer change anything; `reset-password` for a new account
  no longer signs everyone else out; a full disk while writing the recovery
  copy no longer stops a save from taking effect; bad numbers in an address
  give a clear error instead of "Something went wrong".
- "Snow Showers" counts as snow only, not rain. The Lights tab reads several
  controllers at once.
- README and manual: what a reverse proxy must send (nginx needs one extra
  line), and when to require signing in on this computer.
- Housekeeping: one version number for the app (`eaveluxos/version.py`), so the
  Trimlight and weather requests stop reporting "3.1"; the deprecated
  `document.execCommand` copy fallback and the `apple-mobile-web-app-capable`-only
  tag are replaced; two messages no longer point to a command and a file that
  don't exist any more.
- 24 new tests (168 total).

## 3.8.0: gamma-corrected colors

- **Color correction (gamma)** on the Lights tab. Colors picked on a screen
  often look pale on LEDs; with correction on, each color channel is sent as
  `255 × (value ÷ 255) ^ gamma` (gamma 1.0–3.5, 2.2 by default), so the house
  looks closer to the screen. A channel that's on never drops to 0. Off by
  default; Administrators only.
- **Converter:** pick a color to see it as picked and as sent (hex and RGB),
  and show either one on the house for 15 minutes.
- Applies to your own patterns everywhere they're used (schedule, Try, safety
  net, saving to the Trimlight app). Built-in effects, saved-pattern
  references and patterns imported from the Trimlight app are sent unchanged.
  Swatches and previews always show the colors as designed.
- **Exact colors** in Create skips correction for one pattern. Patterns
  imported from the Trimlight app get it automatically.
- 10 new tests (144 total), including one that checks the browser converter
  gives the same numbers as the server.

## 3.7.2: editable zones

- **House map zones can be edited:** each zone has an **Edit** button to fix
  its name or first and last bulb (for example after a counting mistake),
  with **Light these bulbs** to check it on the house before saving, and
  **Use the finder's range** to take the bulb finder's selection.
- **Release notes appear once.** The four build machines used to attach their
  files to the release one by one, each adding its own "Full Changelog" line.
  Now one final job attaches everything, and only when all four builds
  succeeded.
- 2 new tests (134 total).

## 3.7.1: controller backups on Windows

- **Fix:** controller backups made in quick succession could overwrite each
  other on Windows, whose clock can report the same microsecond twice. Each
  backup now gets a name of its own (found by GitHub's new Windows test run).
- 1 new test (132 total).

## 3.7.0: one data folder on Windows

- **Windows keeps all data in `%LOCALAPPDATA%\EaveLuxOS`**, for every version
  and every copy of the app (source or `.exe`). Updating is just unzip and
  start; no more copying the `data` folder, and no more starting from scratch
  when you forget.
- **First start brings your settings over** from the earlier version's
  `data` folder: its own, or the most recently used one in a sibling version
  folder (for example `Downloads\eaveluxos-3.6.0\eaveluxos\data`). Only
  folders next to an EaveLuxOS program count. The database is copied with
  SQLite's backup (safe even mid-write), `secret.key`, photos and backups as
  files. The old folder is never changed, and it only happens once.
- **Start automatically follows the copy you run** on Windows, so an update
  doesn't keep starting the old version at login.
- **Portable mode:** an empty `portable.txt` next to the app keeps data in
  `data` next to it (USB sticks).
- Mac, Linux and container installs are unchanged.
- 10 new tests (131 total).

## 3.6.1: Windows fixes

Found by running the tests on Windows.

- **Damaged database recovery works on Windows.** A connection to the damaged
  file stayed open, so Windows refused to move the file aside and the app
  couldn't start. It's now closed first.
- **Text files are always read and written as UTF-8.** Windows otherwise
  uses its own code page, which fails on characters such as "–" or "✓" (for
  example in the hardware test report).
- **The Linux .tar.gz keeps the program executable** even if it's packaged on
  Windows.
- `.gitattributes` keeps the Mac and Linux launchers' line endings correct when
  the project is committed from Windows.
- Tests run on Windows: permission-bit checks only on Mac and Linux, the HTTPS
  test uses the app's own `make-cert` instead of `openssl`, and GitHub now runs
  the tests on Windows as well as Linux.

## 3.6.0: several schedules a day

- **Morning and evening schedules on the same day**, like the Trimlight Edge
  app's timers (for example 6:00 AM → sunrise and sunset → 11:00 PM). The
  scheduler already switched between them, but the app showed only one
  window per day, warned that the morning rule "never runs", and the safety
  net copied only one window per day to the controller. Now Home (This week),
  Schedule (Coming up), the rule check and the safety net all use every
  stretch of the day.
- Where rules overlap, the lower-priority one now also shows (and is copied to
  the controller) for the time the higher one leaves free, e.g. everyday
  lights from sunset until a New Year's Eve rule starts at 8:00 PM.
- **Fix:** a rule whose off time comes before its on time never runs longer
  than 20 hours. Before, "6:00 AM → sunrise" ran from 6:00 AM until the next
  day's sunrise (about 23 hours) on summer days when sunrise is before 6:00.
- **Add a morning schedule** button on the Schedule tab.
- 6 new tests (121 total).

## 3.5.1: getting API credentials

- Manual section 2 now has step-by-step **How to obtain API credentials**,
  using Trimlight's self-service page
  (https://trimlight.ledhue.com/trimlight/v1/api-credentials/apply): sign in
  with your Trimlight account email and password, or an emailed code, then
  **Get API credentials**. Contacting Trimlight support is the fallback.
- The setup assistant, Settings › Trimlight account and the README link to
  that page.

## 3.5.0: bulb painter

- **Paint bulbs** in Create: paint single bulbs (click; Shift-click for
  everything between), ranges, House map zones, or every Nth bulb with a
  chosen width, within one repeat of the sequence or across the whole house.
  Undo, fill, zone off, any color, landmarks marked on the strip, and the
  animated preview follows along.
- The painted pattern is turned back into the controller's color runs (at
  most 30 runs of up to 90 bulbs), with a live slot count; past 30 the app
  explains why and won't apply it.
- Approach adapted from Trimlight Home Studio (MIT License; see LICENSE).
- 2 new tests (114 total).

## 3.4.1: Manual button and license footer

- **Manual** in the ribbon: the full manual inside the app, with clickable
  contents and a "Find in the manual" box. It's readable on every computer and
  phone, and ships inside the installers and the container image.
- **Footer on every screen** (including sign-in): the version, "Copyright (c)
  2026 Christopher A. Tankelewicz (ThinkTank4n6)" and a link to the MIT
  License text.
- A small Markdown renderer (`static/markdown.js`) that escapes all text and
  allows only safe links.
- 5 new tests (112 total).

## 3.4.0: accounts, rooflines, container

- **Fix: changing a password now signs out every other device.** Before, a
  lost phone that was signed in stayed signed in after the owner changed the
  app password.
- **Accounts and roles:** each person signs in with a user name and password
  as an **Administrator**, **Editor** or **Viewer**, enforced by the server on
  every request. At least one active Administrator always remains (the app
  refuses to demote, disable or delete the last one). The old app password
  becomes the password of the Administrator account `admin`, and signed-in
  devices stay signed in as it. New `main.py users`; `reset-password NAME`.
- **Short sign-ins:** 8 hours without use by default (Administrators can pick
  1 hour to 7 days), and never more than 7 days after signing in. Any change
  to an account signs it out everywhere.
- **House map rooflines:** front, right, back, left and shed views; automatic
  roofline detection from each photo (in the browser), point-by-point
  adjustment with mouse, touch or keyboard, ridges, wire-only stretches, and
  a flat diagram of every side with landmarks, downloadable as SVG. Adapted
  from Trimlight Home Studio (MIT License; see LICENSE).
- **Container:** `Dockerfile` and `compose.yaml` that run as an unprivileged
  user (uid 10001) with a read-only file system, no capabilities and
  `no-new-privileges`, listening on 127.0.0.1 unless `BIND_ADDRESS` is set.
  `EAVELUXOS_DATA_DIR` and `EAVELUXOS_ALLOWED_HOSTS` are new settings.
- 16 new tests (107 total).

## 3.3.0: security hardening

- **Reverse proxies and tunnels:** a request that reaches the app through
  Caddy, nginx, Tailscale Serve, cloudflared or another proxy on the app
  computer is no longer treated as "this computer". Before, such requests came
  from 127.0.0.1 and were signed in automatically, without a password.
- **Passwords:** scrypt (memory-hard) replaces PBKDF2. Older hashes still work
  and are upgraded at the next sign-in. Wrong current passwords on the
  password screen now count toward the sign-in limit.
- **Encrypted secrets:** values in the secrets table (Trimlight Client ID and
  Secret, password hash, webhook token) are encrypted with AES-256-GCM, bound
  to their row. Existing values are encrypted at the first start. Key in
  `data/secret.key` or `EAVELUXOS_SECRET_KEY`. Without the `cryptography`
  package the app keeps working unencrypted and shows a warning.
- **Sign-ins** last 30 days after last use (was 180 days, fixed). Existing
  sign-ins are shortened.
- **Password again for security changes from phones:** Trimlight account,
  webhooks, port, start automatically, and the local-password option
  (confirmed for 5 minutes per sign-in).
- **HTTPS made easy:** `main.py make-cert` makes a self-signed certificate.
  The sign-in page warns when the connection isn't encrypted.
- 14 new tests (91 total).

## 3.2.2: Mac .dmg, Linux .deb, Raspberry Pi

- **Mac:** `EaveLuxOS-macOS.dmg` with a real **EaveLuxOS.app** to drag to
  Applications.
  - It runs as a background app with no Dock icon.
  - It's re-signed ad hoc after setting its version (Apple-silicon Macs
    require a valid signature).
  - Settings are kept in `~/Library/Application Support/EaveLuxOS`, never
    inside the app bundle.
- **Linux:** `eaveluxos_<ver>_amd64.deb` installs to `/opt/eaveluxos`, with a
  menu entry, icon and `eaveluxos` command. `EaveLuxOS-Linux-x86_64.tar.gz`
  is the portable version.
- **Raspberry Pi:** `eaveluxos_<ver>_arm64.deb` and a `.tar.gz` for 64-bit
  Raspberry Pi OS, built on GitHub's arm64 runner.
- **Older systems:** Linux builds run on Ubuntu 22.04, so they also work on
  Raspberry Pi OS and other systems with older system libraries.
- The `.deb` was installed, run and removed in testing. 3 new tests
  (77 total).

## 3.2.1: executables and GitHub

- **Standalone executables:** Windows, macOS and Linux builds that need no
  Python, made with PyInstaller (`packaging/build.py`).
  - Double-clicking starts the app and opens the browser.
  - Data is kept next to the executable, with the per-user folder as a
    fallback.
  - Start-at-login and port changes launch the executable itself.
  - Windows gets a no-console `EaveLuxOS.exe` plus `EaveLuxOS-cli.exe` for
    commands.
- **GitHub Actions:**
  - Tests run on every push.
  - Pushing a `v*` tag tests, builds all three executables and publishes a
    release.
- **`.gitignore` keeps the private `data` folder** (credentials, password
  hash, photos, backups) out of the repository. A test confirms it with git.
- 2 new tests (74 total).

## 3.2.0: EaveLuxOS

- **New name: EaveLuxOS, the Intelligent Lighting Control Platform.** LumaOS
  was dropped because "LUMA" and "LUMA-NET" are registered trademarks for
  lighting products and lighting-control software.
- **New logo:** a lavender bulb under a roofline on a navy tile. The app icon
  is the symbol only; the header uses a slightly bolder version so the lines
  stay crisp at small sizes.
- **Renamed:**
  - launchers: `Start EaveLuxOS.bat`, `Start EaveLuxOS.command`,
    `start-eaveluxos.sh`
  - code package: `eaveluxos/`
  - database and log: `eaveluxos.db`, `eaveluxos.log`
  - start-at-login entries
- **LumaOS and Trimlight Scheduler installs carry over by themselves:**
  - The database is renamed (from `lumaos.db` or `trimlight.db`).
  - The per-user data folder is renamed.
  - Start-at-login entries under either earlier name are replaced.
  - Signed-in phones stay signed in.
  - Service files from either earlier name are still recognized.

## 3.1.0: LumaOS

- **New name: LumaOS, the Intelligent Lighting Control Platform** (formerly
  "Trimlight Scheduler"). The product name no longer uses another company's
  trademark; Trimlight is mentioned only to say which hardware LumaOS works
  with.
- **Renamed:**
  - launchers: `Start LumaOS.bat`, `Start LumaOS.command`, `start-lumaos.sh`
  - code package: `lumaos/`
  - database and log: `lumaos.db`, `lumaos.log`
  - start-at-login entries, and the name on phones' home screens
- **Existing installs carry over by themselves:**
  - `trimlight.db` is renamed on first start.
  - The per-user data folder is renamed.
  - An old start-at-login entry is replaced with the LumaOS one.
  - Signed-in phones stay signed in, because the token moves to the new
    storage key.
- **New logo:** a lavender bulb on a navy tile (`icon.svg`, plus PNG
  home-screen icons for iPhone and Android, and `logo-mark.svg` in the
  header). The app icon shows the symbol only, so it stays legible at
  home-screen size.
- 2 new tests (71 total).

## 3.0.0: SQLite storage, version history, hardware test

- **Settings, patterns, schedule, map, credentials and sign-ins now live in
  one SQLite database,** `data/lumaos.db` (standard library; nothing to
  install).
  - Every save is a single transaction, so a crash or power cut can't leave
    half a file.
  - The revision check runs inside the transaction, so the app and
    command-line tools can't overwrite each other's changes.
  - The file is private to your account (chmod 600; ACL on Windows).
  - A plain-text recovery copy is kept. A damaged database is set aside and
    rebuilt from it, with a warning.
- **Automatic import of older installs:** the first start imports 2.x JSON
  files (or 1.x config.toml / .env). The old files are kept, renamed
  `….migrated-….json`.
- **Version history:** every save is kept (last 100). Settings › Version
  history restores the patterns, schedule and house map from any save, and
  the restore is itself saved, so you can switch back.
- **No more hand-editing:** `python3 main.py allow-host NAME` replaces editing
  the settings file for allowed host names.
- **`python3 main.py backup FILE`** copies the whole database safely while the
  app runs.
- **`python3 main.py hwtest`:** a guided test on your real controller.
  - It checks the clock, bulb numbering, 90 vs 60 bulbs per color, saving to
    the Trimlight library, port off, the controller's own timer (the safety
    net) and the command rate.
  - It backs up first, asks before every change, always cleans up (even on
    Ctrl+C), and writes a shareable report.
- Found while testing: the hardware test's cleanup steps shared a variable
  (Python late binding), so one test pattern would have been left on the
  controller. Fixed, with a regression test.
- 69 tests.

## 2.4.0: open-issues sweep

1. **No more lost settings from a typo.** A settings file that can't be read
   (usually from a hand edit) used to start the app on factory defaults, and
   the next save overwrote everything. Now the last good copy is restored,
   the edited file is kept as `settings.damaged-….json`, and the app names the
   line with the error.
2. **Safety net:** normal nights now run from the controller's own timer, so
   the lights go off on time even if the computer dies mid-evening. After a
   manual change, weather or a flash, the app keeps control for the rest of
   that night. It never switches the controller to Timer mode mid-window,
   because that behavior isn't confirmed on hardware.
3. **Startup failures are visible.** Windows shows a message box. A read-only
   app folder now falls back to the per-user data folder instead of failing.
4. **Windows file privacy:** the secrets and sessions files get an access list
   allowing only this user and SYSTEM, since chmod has no effect on Windows.
5. **Webhook tokens are refused in the URL.** Send them in the `X-Token`
   header or a JSON `"token"` field. Webhooks also accept only the six
   documented actions.
6. **Automatic 60-bulb fallback:** if the cloud refuses more than 60 bulbs per
   color slot, long runs are split (same look) and the limit is remembered.
7. **Safety-net syncs wait** if a scheduled change is less than 3 minutes
   away, so they can't delay it.
8. **Optional password on the app computer itself**, plus
   `python3 main.py reset-password` for recovery.
9. **Optional HTTPS:** put your own `cert.pem` and `key.pem` (for example from
   mkcert) in `data/tls`. TLS handshakes run per connection, so a stalled
   client can't block others.
10. **The day bar's cache** is keyed by a settings generation counter instead
    of `id()`, which Python can reuse.

14 new tests (63 total).

## 2.3.2: third code review (browser security and new features)

Security
- **Sign-in no longer uses a cookie.** Browsers send cookies to every port on
  the same host, so a phone's session token was also sent to other web apps
  on the same computer. The token now lives in the browser's per-origin
  storage (scheme, host and port) and travels in an `X-Session` header. The old
  cookie is cleared at sign-in. Phones sign in once after updating.
- **A signed-in phone can no longer change server or network settings**
  (allowed hosts, web host or port) through the settings document. The port
  has its own checked endpoint; allowed hosts are editable only in the file.
- **Stricter browser policy:**
  - CSP now adds `object-src 'none'`, `base-uri 'none'` and
    `form-action 'self'`.
  - New `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy:
    same-origin` headers stop other sites from opening the app's pages or
    embedding its images and data.
  - New `Permissions-Policy` header.
  - Photos load through the authenticated API.

Bugs
- **Previews expire.** The bulb finder (10 minutes after the last change),
  pattern tries and color tests (15 minutes) return to the schedule by
  themselves. Before, a forgotten highlight replaced the lights until the
  window ended.
- **Nightly rotation counts only the nights a rule runs,** so "Fri and Sat"
  rules keep their order.
- **Safety net records ownership after each write.** A network failure
  part-way through a sync no longer leaves timer entries the app forgets it
  made.
- **The safety net keeps the controller's original state.** The backup from
  before the app ever wrote is now kept permanently. Backup names are
  unique, and failed removals are retried every 30 minutes instead of every
  few seconds, so retries no longer churn through backups.
- **Moving ports works from desktop terminals.** "Restart on new port" no
  longer exits when the app was started from a Linux desktop terminal, where
  `INVOCATION_ID` is set. Only the app's own service entries count as
  supervised.
- **Manual changes right after startup are kept.** A change made in the app's
  first seconds is no longer dropped by the first schedule check.
- The rule check is cached per settings change and day, and the length of
  house-side names is validated.
- 5 new regression tests (49 total).

## 2.3.1: choose the port

- **Settings › App address:** change the web port. The app checks the port
  is free, starts a copy on it, waits until that copy answers, then closes
  the old one. The schedule pauses only for those seconds, and if the new
  copy fails, everything stays as it was.
- **Busy ports are handled at startup:** if another program already uses the
  saved port (for example 8787), the app moves to the next free port,
  remembers it, logs why, and opens the browser there. Before, it failed
  silently when started in the background.
- **Windows:** the port is now claimed exclusively. Windows otherwise lets two
  programs bind the same port, with both receiving garbled traffic.
- `python3 main.py port NUMBER` for computers without a screen.

## 2.3.0: house map, zones, nightly patterns, safety net

- **House map tab:**
  - A bulb finder that lights one bulb or a range, with everything else dark.
    It steps by 1, 5, 10 or 25 and can update the house as you move.
  - Photos of each side of the house, with pins you place on them.
  - Named landmarks and named zones.
  - Photos stay on the app computer and are never exported.
- **Paint by zone** in Create: color whole sections in one step. A counter
  shows how many of the 30 color slots are used.
- **A different pattern each night:** rules can cycle their patterns nightly,
  starting from the first night of the date range.
- **Rule check:** a rule that another rule always beats now shows "Never runs
  in the next year", with the reason and the fix.
- **Safety net (optional):**
  - Copies the next 3 to 14 nights into the controller's own calendar timers,
    so the lights still run if the computer or internet is down.
  - Backs up the controller before every change and only touches its own
    "Auto" timers and patterns.
  - Reads every write back and removes them on any mismatch.
  - Warns about Trimlight app timers that would also run.
  - Between windows, the controller rests in Timer mode only while a verified
    copy covers today.
- 11 new automated tests (44 total), including rollback when the controller
  reads back differently, a full pattern library, and never touching the
  user's own timers.

## 2.2.0: checked against Trimlight's user guide

- **Zone off (✕):** the designer now has the Trimlight app's X. Those bulbs
  stay dark and are skipped by any movement (the API's `disable` flag).
  Patterns imported from the Trimlight app keep their X slots. Before this,
  they became black, which moves with the animation.
- **Up to 90 bulbs per color**, matching the guide (was 60).
- **Designer tips from the guide:** a warning when Comet or Wave has a color of
  5 or fewer bulbs (they won't run), and a tip for slowing a fast chase.
- **Wording matches the Trimlight app:** "Sequencing spacing" and "Reverse
  direction".
- **Lights tab:** warns before changing color order away from RGB or the chip
  away from UCS1903, the guide's standard settings.
- **Manual:**
  - New prerequisites: home Wi-Fi with the green "Network Connected" light;
    blue-light mode isn't reachable.
  - The Manual/Timer/Off modes explained, the Front Peak zoning example, and
    the controller troubleshooting steps.
  - What stays in the Trimlight app (music, groups, voice, firmware) and what
    a factory reset means.

## 2.1.0: code review release

Security
- Blocks DNS-rebinding attacks. Requests must name this computer, an IP
  address or a host the user listed; any other site trying to reach the app
  through the browser is refused.
- The setup code only works while setup is unfinished. Afterward, other
  devices need the app password.
- Signed-out devices no longer see setup details.
- Request bodies with a negative, malformed or oversized length are refused
  and the connection is closed. Before this, one bad request could hang a
  server thread or desynchronize a keep-alive connection.

Reliability
- Every 5 minutes the app reads the controllers back. If one was changed
  outside the app (power blip, Trimlight app), it's restored after two
  matching readings.
- The status page no longer waits on slow cloud calls, because commands and
  status use separate locks.
- Weather is checked on its own thread, so a slow weather service can't delay
  scheduled changes.
- Only one copy can run the scheduler. Launching twice opens the running copy,
  and the scheduler starts only after the app holds its port.

Correctness
- Settings carry a revision number. A save based on stale settings, for
  example from a second phone, is refused instead of silently overwriting
  newer changes.
- Settings are fully validated even before setup is finished.
- A chosen controller time is now kept as an offset. Before, the next status
  refresh replaced it within a minute.
- Forecasts that only say "chance of …" no longer trigger weather rules, and
  weather observations over 2 hours old are ignored.
- Start-automatically entries now handle folders with spaces (Linux) and
  special characters (macOS).
- Upcoming times, log times and clock messages show the house's time zone,
  not the viewing device's.
- Fixed a timer leak on the Date & Time screen.

Project
- MIT License. Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6).
- Added MANUAL.md, a step-by-step user manual.
- Added an automated test suite (31 tests) with a fake Trimlight cloud.

## 2.0.0
- Full point-and-click app with setup assistant, seven tabs, pattern designer,
  ports and bulbs setup, daylight saving modes, phone access and sharing.

## 1.x
- Command-line scheduler with sunrise/sunset, DST handling, weather rules,
  priorities, rotation and security flash.

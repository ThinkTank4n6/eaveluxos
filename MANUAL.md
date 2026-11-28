# EaveLuxOS: User Manual
### The Intelligent Lighting Control Platform

Version 4.28.2 · © 2026 Christopher A. Tankelewicz (ThinkTank4n6) · MIT License

> [!TIP]
> **Quick start: you probably don't need Python.**
> 1. Download the ready-made app for your computer from the project's GitHub
>    **Releases** page (https://github.com/ThinkTank4n6/eaveluxos/releases/latest).
>    It already includes Python and everything else (section 4).
> 2. Have your Trimlight **Client ID** and **Client Secret** ready (section 2).
> 3. Follow the setup assistant (section 5).
> 4. Put the app on your phones and tablets (section 8).
>
> Python (section 3) is only needed to run EaveLuxOS from its source code,
> for example on 32-bit Raspberry Pi OS. Where this manual shows a command as
> `python3 main.py …`, use `EaveLuxOS-cli.exe …` on Windows and
> `eaveluxos …` on Linux or a Pi.

EaveLuxOS is a free, community-made lighting control platform. Today it runs
**Trimlight Edge** permanent lights. It runs on a computer that stays on at
home (Windows, Mac, Linux or a Raspberry Pi), and you use it from that
computer's browser or from your phones and tablets.

This manual takes you from nothing installed to a working schedule, then
explains every screen. You never need to type commands.

- **In the app:** the **Manual** button (**?** on a phone) at the top of every
  screen opens this manual, with a search box.
- **Version tags:** a small number after a heading, like **4.22**, is the
  version that added it.
- **Colored boxes:** green **Tip** boxes save you time; red **Important** boxes
  keep your lights and settings safe.
- **The bottom of every screen** shows the app's version, the copyright notice
  and a link to the MIT License.

It complements Trimlight's own **Trimlight Select EDGE Wi-Fi V2 User's Guide**.
That guide covers the hardware, pairing and the Trimlight Edge app; you can
find it and Trimlight's videos at **trimlight.com/edge**. Where this manual
refers to "Trimlight's guide", that's the document it means.

*EaveLuxOS is not made, sold, endorsed or supported by Trimlight. Trimlight
and Trimlight Edge are trademarks of their owner and appear here only to say
which hardware EaveLuxOS works with. EaveLuxOS was previously called
"LumaOS", and before that "Trimlight Scheduler"; updating keeps all your
settings.*

---

## Contents

**Start here:** [What's new](#whats-new) · [Where things are](#where-things-are)

1. [What you need](#1-what-you-need)
2. [Get your Trimlight API credentials](#2-get-your-trimlight-api-credentials)
3. [Install Python (source code only)](#3-install-python-source-code-only)
4. [Download and start the app](#4-download-and-start-the-app)
5. [The setup assistant](#5-the-setup-assistant)
6. [Prepare the Trimlight Edge app](#6-prepare-the-trimlight-edge-app)
7. [Make it start automatically](#7-make-it-start-automatically)
   - [Starting it again after Quit](#starting-it-again-after-quit-4222)
8. [Phones and tablets: iPhone, iPad, Android](#8-phones-and-tablets-iphone-ipad-android)
   - [Set up a phone, step by step](#the-quick-way-set-up-a-phone-4182)
9. [Home](#9-home)
10. [Patterns](#10-patterns)
    - [Lightning and Snowflake](#lightning-and-snowflake-422)
11. [Create a pattern](#11-create-a-pattern)
    - [Animations](#animations-423)
    - [Studio: layers, gradients and shows](#studio-layers-gradients-and-shows-420)
12. [House](#12-house)
13. [Schedule](#13-schedule)
    - [Birthdays and anniversaries](#birthdays-and-anniversaries-418)
    - [Game-time lights](#game-time-lights)
    - [Fades between patterns](#fades-between-patterns-419)
14. [Alerts](#14-alerts)
    - [Who's home: arriving and leaving](#whos-home-arriving-and-leaving-418)
    - [The weather on the lights](#the-weather-on-the-lights-419)
    - [Security flash](#security-flash)
    - [Phone alerts](#phone-alerts)
    - [Webhooks and Home Assistant](#webhooks-and-home-assistant)
15. [Music shows](#15-music-shows)
16. [Backup timer (safety net)](#16-backup-timer-safety-net)
17. [Setup › Lights & controller](#17-setup--lights--controller)
    - [Local mode (home network)](#local-mode-home-network)
18. [Setup › Location & time](#18-setup--location--time)
19. [Setup › Accounts & access, and App](#19-setup--accounts--access-and-app)
20. [Share patterns with other owners](#20-share-patterns-with-other-owners)
21. [Update, move or uninstall](#21-update-move-or-uninstall)
22. [Test with your controller](#22-test-with-your-controller)
23. [Troubleshooting](#23-troubleshooting)
24. [Questions and answers](#24-questions-and-answers)
25. [License](#25-license)

---

## What's new

**4.28 to 4.22: games on the calendar, control from anywhere, power-cut alerts, community sharing, game-time lights, college game days, animations, Lightning and Snowflake**
- **Games on the calendar** (4.28): Schedule › Coming up shows your teams'
  games, with start times, for game-time lights and for score celebrations.
  Every team now gets game time (15 minutes before to 15 after) unless you
  chose all evening: see [Game-time lights](#game-time-lights).
- **Control from anywhere** (4.27): **Setup › Accounts & access › Away from
  home** walks you through Tailscale, step by step, then shows the address
  and a QR code for your phone. Nothing opens on your router (section 19).
- **"EaveLuxOS was off" alerts** (4.27): after a power cut or restart, your
  phone hears how long the app was off. Controller-offline alerts now come
  after 10 minutes, and **Sent lately** lists what was sent, to check against
  your phone (section 14, *Phone alerts*).
- **No more needless re-sends** (4.28.2): the lights aren't sent again about
  7 minutes after every change, when Trimlight's cloud catches up (section
  16, *After a restart or a power cut*).
- **Lightning and Snowflake** on any pattern saved on your controller, the
  same two effects as the Trimlight Edge app's Pattern Library: see
  [Lightning and Snowflake](#lightning-and-snowflake-422).
- **Start EaveLuxOS from its icon** (4.22.2): after **Quit**, the desktop icon
  your browser made shows a **Start EaveLuxOS** button. See
  [Starting it again after Quit](#starting-it-again-after-quit-4222).
- **Macs come back after a restart** (4.22.1): the app tells you if it's
  running from Downloads or the disk image, where it can't start by itself.
- **All 23 Trimlight animations** (4.23): Full strobe, Twinkle, Firework,
  Inside out, Dissolve and Juggle are new, and Stars and Breath now use the
  Trimlight app's names, Twinkle fade and Fade:
  [Animations](#animations-423).
- **Share to the community library** (4.26): one button writes the file and
  opens GitHub ready to propose it: [The community library](#the-community-library).
- **Game-time lights** (4.25): team colors only while the game is on, from
  a little before the start to a little after the final score:
  [Game-time lights](#game-time-lights).
- **College sports and the WNBA on game day** (4.24): NCAA football, men's
  and women's basketball and hockey, with a team picker in each team's own
  colors: [Game-time lights](#game-time-lights).
- **Badges for Lightning and Snowflake** (4.22.5) on Patterns › In the
  Trimlight app and My patterns.
- **The right one of two look-alike patterns** (4.22.3): when two saved
  patterns look the same but only one has Lightning or Snowflake, the app
  shows the one you meant.

**4.21: game day, sharing and energy**
- **Lights for a win** and a celebration length for each team:
  [Game-time lights](#game-time-lights).
- **Share Studio shows and automations** as codes, and add them from the
  Community list: [Share Studio shows and automations](#share-studio-shows-and-automations-421).
- **Energy estimate:** about how many watts, kilowatt-hours and dollars your
  schedule uses (**Setup › App › Lights usage**, section 19).
- **Start the controllers together**, so two or more controllers' patterns
  move in step: [Start the controllers together](#start-the-controllers-together-421).
- **On and Off always work** (4.21.1), even when the app thinks the lights
  are already that way (section 9).

**4.20: Studio**
- Layers, gradients and timed shows with fades between looks:
  [Studio](#studio-layers-gradients-and-shows-420).

**4.19: fades and weather looks**
- **Fades between patterns** instead of a sudden switch:
  [Fades between patterns](#fades-between-patterns-419).
- **Weather looks** (rain, snow, storm, wind, fog) and **temperature colors**:
  [The weather on the lights](#the-weather-on-the-lights-419).

**4.18: people and dates**
- **Who's home:** lights that welcome you when you arrive and change when the
  last person leaves: [Who's home](#whos-home-arriving-and-leaving-418).
- **Birthdays and anniversaries** with their own patterns:
  [Birthdays and anniversaries](#birthdays-and-anniversaries-418).
- **Templates** for common automations (motion lights, welcome home, doorbell):
  [Templates and motion lights](#templates-and-motion-lights-418).
- **Siri, Alexa and Google:** [Siri, Alexa and Google](#siri-alexa-and-google-418).
- **Set up a phone, step by step**, from a code on the app computer:
  [Set up a phone](#the-quick-way-set-up-a-phone-4182).

Every change, version by version, is in **CHANGELOG.md** in the download.

---

## Where things are

The app has seven tabs. On a phone they're along the **bottom** of the
screen (they step aside while you type, so they never cover the keyboard).

| Tab | What's there |
|---|---|
| **Home** | What the lights are doing and why, **On** and **Off**, favorites, brightness and speed, tonight and the week ahead, who's home, each controller, and Activity. |
| **Patterns** | **My patterns** (with folders), **In the Trimlight app**, **Built-in** effects and **Community**. **New pattern** opens the designer; **Studio** builds layered looks and timed shows. |
| **Schedule** | **Every night:** rules, night curves and fades. **Special days:** holidays, birthdays and anniversaries, game-time lights and away mode. **Who wins tonight** shows how a night is decided. |
| **Alerts** | Automations (When · If · Then) and templates, who's home, weather rules and weather looks, severe weather alerts, the security flash, webhooks, Home Assistant, Siri, Alexa and Google. |
| **Music** | Music shows (the controller's music mode), music from this computer, music zones and mood follow. |
| **House** | The house map: photos, rooflines, camera calibration, landmarks, zones, the bulb finder, bulb numbering, house view and scenes. |
| **Setup** | **Lights & controller** (ports, the backup timer, start the controllers together), **Color correction**, **Local mode** (including **Lightning and Snowflake**), **Pattern backups**, **Controller health**, **Location & time**, **Accounts & access** and **App** (set up a phone, lights usage and energy, updates, start automatically). |

Getting around:

- **Search features**, at the top of every page: type a few letters of what
  you're after ("backup", "eagles", "ports", "snowflake") and choose a result,
  or press **Enter** for the first. The app opens that page and panel and
  outlines it for a moment. Press **/** to jump to the search box from
  anywhere; **Esc** clears it.
- Panels that fold show a one-line summary, such as "Holidays · next:
  Thanksgiving, Thu, Nov 26". Tap one to open it; the app remembers which
  ones you keep open.
- The browser's **Back** button returns to the tab you were on before.
- The **Manual** is the **?** button at the top.
- Old names and bookmarks still work: the backup timer was called the
  **safety net**, **Bulb numbering** was **Address space**, and `#settings`,
  `#lights`, `#time` and `#create` open the right place.

---

## 1. What you need

| Item | Details |
|---|---|
| Trimlight Edge controller | Already installed and **connected to your home Wi-Fi**, not just to its own "Trimlight" network. On the controller, the light labeled **Network Connected** should be **green**. |
| A Trimlight account with the controller paired to it | Done in the Trimlight Edge app: **Sign up**, then **+ › Add device** (Trimlight's guide, "Creating an Account" and "Pairing to a local WIFI Network"). |
| Trimlight API Client ID and Client Secret | A pair of codes from Trimlight (see step 2). |
| A computer that stays on | Windows 10 or 11, macOS, or Linux. A small mini PC is ideal. It must be on for the schedule to run. |
| Python | **Usually not needed.** The ready-made app from GitHub's Releases page includes it (section 4). Only for running from the source code: Python 3.11 or newer (section 3). |
| Home Wi-Fi | The computer and your phone should be on the same home network. |

The computer does **not** need to be near the lights. It controls them
through Trimlight's cloud service, the same way the Trimlight app does when
you're away from home.

> [!IMPORTANT]
> In blue-light mode ("Wifi Broadcasting"), the controller only
> talks to a phone connected to its own Trimlight network and never reaches
> the internet. **This app can't control a controller in blue-light mode.**
> Trimlight notes that the controller needs a strong 2.4 GHz Wi-Fi signal. If
> yours is weak, use a 2.4 GHz extender, or separate the 2.4 and 5 GHz bands on
> a dual-band router, as Trimlight's guide describes.

## 2. Get your Trimlight API credentials

The app talks to Trimlight's official API, which needs a **Client ID** and a
**Client Secret**. You can get them yourself from Trimlight's API credentials
page, using the same account you sign in to the Trimlight Edge app with.

### How to obtain API credentials

1. Open Trimlight's API credentials page:
   https://trimlight.ledhue.com/trimlight/v1/api-credentials/apply
2. Under **Verification method**, choose one:
   - **Password:** enter your Trimlight account **email** and **password**.
   - **Email code:** enter your Trimlight account **email**, then the code
     Trimlight emails to you.
3. Click **Get API credentials**.
4. Copy the **Client ID** and **Client Secret** exactly as shown. Upper and
   lower case matter; don't include spaces before or after.
5. Keep the two codes somewhere safe, like a password manager. Treat the
   Client Secret like a password: anyone who has it can control your lights.

You'll paste them into the setup assistant (section 5), or later under
**Setup › Accounts & access › Trimlight account**.

If the page doesn't accept your account or doesn't give you credentials,
contact Trimlight support and ask for **API access (Client ID and Client
Secret) for your Trimlight Edge controller**.

## 3. Install Python (source code only)

**Using the ready-made app from the Releases page (section 4)? Skip this
section:** it already includes Python. This is only for running EaveLuxOS
from its source code (`eaveluxos.zip`).

### Windows

1. Go to **python.org/downloads** and click **Download Python 3.x** (3.11 or
   newer).
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"**,
   then click **Install Now**.
3. When it finishes, click **Close**.

### Mac

1. Go to **python.org/downloads** and download the macOS installer.
2. Open it and follow the steps.
3. When it finishes, the installer opens a folder. Double-click **Install
   Certificates.command** in that folder.

### Linux (Ubuntu, Debian, Raspberry Pi OS and similar)

Most recent systems already include Python 3.11 or newer. If yours doesn't,
install it with your system's software installer (the package is `python3`).

## 4. Download and start the app

There are two ways to get EaveLuxOS. Most people want **the ready-made
app**: nothing else to install. The source code is for computers without a
ready-made app, or for changing the code.

### The ready-made app (recommended)

**Step 1. Download it.** On the computer that will run your lights, open
either of these:

- **GitHub** (always the newest release):
  https://github.com/ThinkTank4n6/eaveluxos/releases/latest. Scroll down
  to **Assets**.
- **ThinkTankForensics.com**: https://thinktankforensics.com/home.html,
  under **Home projects**. It links to the same files.

Download the file for your computer:

| Computer | File to download |
|---|---|
| Windows 10 or 11 | `EaveLuxOS-Windows.zip` |
| Mac with Apple silicon (M1 and newer) | `EaveLuxOS-macOS.dmg` |
| Mac with Intel | `EaveLuxOS-macOS-Intel.dmg` |
| Linux PC | `eaveluxos_…_amd64.deb`, or `EaveLuxOS-Linux-x86_64.tar.gz` |
| Raspberry Pi (64-bit Raspberry Pi OS) | `eaveluxos_…_arm64.deb` |

Not sure which Mac you have? Apple menu › **About This Mac**: it says
**Intel** on an Intel Mac, and **Apple M1** (M2, M3…) otherwise.

**Step 2. Install and start it.**

| Computer | What to do |
|---|---|
| Windows | Right-click the zip › **Extract All…** into a folder you'll keep, such as `Documents\EaveLuxOS` (not Downloads, and not inside the zip). Double-click **EaveLuxOS.exe**. If Windows says "Windows protected your PC", click **More info › Run anyway** (only the first time). |
| Mac | Open the .dmg and drag **EaveLuxOS** into **Applications**. Open it from Applications. If macOS blocks it, open **System Settings › Privacy & Security**, scroll down and click **Open Anyway**. |
| Linux PC | Run `sudo apt install ./eaveluxos_…_amd64.deb`, then start **EaveLuxOS** from the app menu. For the .tar.gz: unpack it and run `./eaveluxos`. |
| Raspberry Pi | Run `sudo apt install ./eaveluxos_…_arm64.deb`, then `eaveluxos run`. |

> [!IMPORTANT]
> **Mac: always run it from Applications**, not from **Downloads** or from
> the open .dmg window. Otherwise macOS runs a temporary copy that's gone
> after a restart, and the app can't start on its own. The app notices this
> (since 4.22.1): Home and **Setup › App** tell you to move it, and **Start
> automatically** won't turn on until it runs from Applications. To fix it:
> drag it into Applications, eject the .dmg, open it from Applications and
> turn **Start automatically** on there.

**Step 3. The setup assistant opens.** Your browser opens to
**http://localhost:8787** (or **https://** once HTTPS is on, section 8). Go
to section 5.

**Optional: check the download.** To be sure the file is complete and
unchanged, compare its fingerprint with its line in **SHA256SUMS.txt** (also
under Assets on GitHub). The long number must match exactly.

- Windows (Command Prompt):
  ```
  certutil -hashfile %USERPROFILE%\Downloads\EaveLuxOS-Windows.zip SHA256
  ```
- Mac or Linux (Terminal), with your file's name:
  ```
  shasum -a 256 EaveLuxOS-macOS.dmg
  ```

**Later versions install themselves** from **Setup › App › Update**
(section 21), so you don't download them again. Your settings are kept apart
from the program (see **Where your data is kept** below), so they stay when
you update or go back to an older version.

### From the source code (needs Python)

Use this only if there's no ready-made app for your computer, or you want to
change the code. Install Python first (section 3).

**Step 1. Download and unzip.** Download **eaveluxos.zip** and unzip it
somewhere permanent, such as your **Documents** folder (not Downloads, and
not inside the zip).

**Step 2. Start it.** Open the **eaveluxos** folder and double-click the
launcher for your computer:

| Computer | Double-click | Good to know |
|---|---|---|
| Windows | **Start EaveLuxOS.bat** | The first time, it may install a small time-zone package (needs internet). The app then runs in the background, without a window. |
| Mac | **Start EaveLuxOS.command** | The first time, macOS may block it: right-click the file › **Open** › **Open**. Keep the Terminal window open while the app runs. |
| Linux | **start-eaveluxos.sh** | If asked, choose **Run in Terminal**. Keep the window open. |

**Step 3. The setup assistant opens.** Your browser opens to
**http://localhost:8787**. If it doesn't, open the browser yourself and go to
that address. Then go to section 5.

> [!TIP]
> Starting it twice is safe: the second start only opens the browser to the
> copy that's already running. If it doesn't start at all, Windows shows a
> message box that explains why.

#### If the Mac won't start it

**"Could not be executed because you do not have appropriate access
privileges."** The file lost its permission to run, which happens when the
folder was copied from another computer, a USB stick or a re-made zip. Fix
it once, in **Terminal** (Applications › Utilities):

1. Type `chmod +x ` (with a space at the end), drag **Start
   EaveLuxOS.command** into the window and press **Return**.
2. If it still won't run, type `xattr -c ` (with a space), drag the file in
   again and press **Return**.
3. Double-click it again. The first time: right-click › **Open** › **Open**.

If the folder is on a USB stick, a network drive or an opened disk image,
copy it to **Documents** first: macOS may not run anything from there.

To start it without the file: in Terminal, type `cd ` (with a space), drag
the **eaveluxos** folder in and press **Return**, then run:

```
python3 main.py run --open
```

**Setup › App › Start automatically** then starts it at each login.

**"Failed building wheel for cryptography"** (or "failed to build
installable wheels … cryptography"). An older **pip**, often on an Intel
Mac, can't find the ready-made encryption package and tries to build it.
Type these two lines in Terminal. Type them rather than paste them: text
pasted from an email or chat can carry special spaces, and pip then answers
"no such option".

```
python3 -m pip install --upgrade pip
python3 -m pip install --user --only-binary :all: cryptography
```

Since 4.10.1, **Start EaveLuxOS.command** does this by itself. If it still
fails, that Mac's Python or macOS is too old for the package: install the
current Python from python.org (and run **Install Certificates.command** in
its folder), or use the Mac app instead. EaveLuxOS runs without the package,
but until it's installed, the Trimlight secret is saved unencrypted on that
computer (the app warns you) and the secure phone connection waits.

None of this applies to the Mac apps (`EaveLuxOS-macOS.dmg` and
`EaveLuxOS-macOS-Intel.dmg`).

### Where your data is kept

Your settings, patterns and photos are kept apart from the program, so a new
version (or an older one) finds them:

| Computer | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\EaveLuxOS` (for example `C:\Users\you\AppData\Local\EaveLuxOS`) |
| Mac | `~/Library/Application Support/EaveLuxOS` |
| Linux | the `data` folder next to `main.py`, or `~/.local/share/eaveluxos` if that can't be written |

**Setup › App › Setup and about** shows the folder in use.

## 5. The setup assistant

The assistant has six short steps. Run it on the computer where you installed
the app.

1. **Welcome.** Click **Get started**.
2. **Your Trimlight account.** Paste your **Client ID** and **Client Secret**,
   then click **Test and continue**.
   - If you see "Trimlight didn't accept these", check for extra spaces and
     make sure upper and lower case are exactly right.
   - The secret is saved only on this computer and is never shown again.
3. **Controllers.** Tick the controllers this app should run (usually just
   one), then click **Continue**.
4. **Location.** Type your town in the search box, click **Search**, and pick
   your town from the list. This fills in your latitude, longitude and time
   zone.
   - If the search can't find your town, enter latitude and longitude yourself.
     In Google Maps, right-click your house and the coordinates appear at the
     top of the menu. In the Americas, longitude is negative.
   - Leave **Daylight saving time** on **Automatic** unless you have a reason
     not to (see section 18).
   - Click **Save and continue**.
5. **Phone access.** Create your **Administrator account**: a user name
   (`admin` unless you change it) and a password of at least 8 characters.
   Phones and other computers use it to sign in. You can skip this if you'll
   only ever use the app on this computer, and add accounts for other people
   later (section 19).
6. **Done.** Click **Go to Home**.

You start with sample patterns and a sample schedule. The schedule turns the
lights on every night from 15 minutes after sunset until 11 PM, plus holiday
seasons. Change or delete these on the Schedule tab.

## 6. Prepare the Trimlight Edge app

The app and the Trimlight Edge app shouldn't both be scheduling the lights.

1. Open the **Trimlight Edge** app on your phone.
2. Go to the controller's **Settings** and set the mode switch to **MANUAL**.
   Trimlight's guide explains the three positions: **Off** ignores all timers
   and keeps the lights off; **Manual** is direct control; **Timer** makes the
   controller follow its own timers. EaveLuxOS uses Manual and Off
   itself, so the controller's Timer mode isn't needed.
3. Open the **timer (clock) tab**. Turn off both **daily timers** and delete or
   disable any **calendar events**. Use **Schedule › Import from Trimlight app**
   first (section 13) if you want to keep them.

You can keep using the Trimlight Edge app to design patterns. EaveLuxOS
can use them (see section 10).

> [!NOTE]
> Every 5 minutes EaveLuxOS checks that the lights
> are doing what the schedule says: on, off or Timer mode, and the pattern
> showing. If someone turns them off or picks another pattern in the Trimlight
> app, or the controller restarts after a power blip, the scheduler restores
> them within about 10 minutes. To override the schedule, use **Turn on** or
> **Turn off** in this app instead. (If a controller doesn't report a pattern
> back exactly as it was sent, the app notes that under Home ›
> **Activity** and checks only on and off for the rest of
> that pattern's run.)

## 7. Make it start automatically

### Starting it again after Quit (4.22.2)

The EaveLuxOS icon your browser put on the desktop or taskbar (**Open in
app**, or **Install**) and any bookmark only *show* the app; the EaveLuxOS
program is what runs the lights. When the program isn't running (after
**Quit**, say), that window says **Can't reach EaveLuxOS** and shows a
**Start EaveLuxOS** button:

1. Click **Start EaveLuxOS**. The browser asks whether to open EaveLuxOS;
   tick **Always allow** (or similar) and choose **Open**.
2. Wait a few seconds. The page opens the app by itself once the program
   answers; no need to press **Try again**.

The page also shows where the program is (for example
`C:\Users\you\EaveLuxOS\EaveLuxOS.exe`), in case the button does nothing.
Then open that file yourself. The button is set up for your user account
each time the program starts, so it works once EaveLuxOS 4.22.2 or newer has
run on this computer, and it follows the program if you move it. It only
ever starts EaveLuxOS; nothing on a web page can send it anything else. On a
Mac it works for the app in Applications (not when run from the source
code).

To have it running without any of this, turn on **Start automatically**:

1. Go to **Setup › App**.
2. Under **Start automatically**, tick **Start this app when the computer
   starts**.

On Linux, it starts when you log in. To make it start at power-on without
anyone logging in, see section 23.

On a Mac it also starts when you log in. If the Mac waits at the login
screen after a restart (FileVault always does), the lights follow the
schedule once someone logs in; turn on automatic login in **System Settings ›
Users & Groups** if you want it to start by itself. The app must run from the
**Applications** folder (section 4); otherwise this panel says so and won't
turn on.

A sleeping computer can't follow the schedule. On Windows and on a Mac
(4.7.2), **Keep this computer awake while the app runs** (same panel, on by
default, 4.4.4) stops the computer from going to sleep on its own while the
app is running: the screen can still turn off, and the power button and
**Sleep** still work (on a Mac laptop, so does closing the lid). Quitting the
app lets it sleep again. On a Mac it works the way the built-in `caffeinate
-i` command does; `pmset -g assertions` in Terminal lists it as
*EaveLuxOS: following the lights' schedule*. On Linux, turn off sleep in the
computer's power settings. On Windows it doesn't hurt to do that too:

```
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

## 8. Phones and tablets: iPhone, iPad, Android

EaveLuxOS runs on the app computer; phones and tablets open it in their
browser and can install it on the home screen like an app. Nothing comes
from an app store.

### The quick way: Set up a phone (4.18.2)

On the app computer, open **Setup › App › On your phone** and click **Set up
a phone or tablet, step by step**. It shows a code: point the phone's camera
at it (the phone on your home Wi-Fi). The phone opens a page that takes it
through everything below, in order:

1. **Trust the app's certificate** (only with HTTPS): **Download the
   certificate**, then the two or three taps for an iPhone, iPad or Android
   phone, shown for the device you're holding. The page shows the
   certificate's fingerprint; it's the same as the one on the computer's
   page. (With HTTPS on, this one page and the certificate are the only
   things the app sends without encryption: the phone needs them before it
   can trust anything. The certificate is public; its key never leaves the
   app computer.)
2. **Open the secure address** and sign in.
3. **Put EaveLuxOS on the home screen**: an **Install** button where the
   browser offers one, otherwise the steps for this device.
4. **Who's home** (optional): choose who this phone belongs to; **I'm home**
   and **I'm away**, and the Shortcuts recipe with that name filled in.

The page finds mkcert's root certificate by itself (the computer's mkcert
folder, `$CAROOT`, or a copy of **rootCA.pem** in EaveLuxOS's `tls` folder),
and only if it's the one that signed the app's certificate. The **How**
button on a phone's "Put EaveLuxOS on your home screen" bar opens the same
page. The rest of this section is the same, step by step by hand.

### 1. Find the address

On the app computer, open **Setup › Accounts & access** and look under
**Phones and other computers** for an address such as
`http://192.168.1.20:8787` (or `https://…` once HTTPS is on). Give the app
computer a **reserved IP address** (a DHCP reservation) in your router, so
the address never changes.

Every phone and tablet must be on your **home Wi-Fi** (not a guest network,
and not mobile data) to reach it. You sign in with your EaveLuxOS user name
and password (section 5; more accounts in section 19).

### 2. HTTPS with mkcert (recommended)

Without HTTPS the app works, but the password crosses your Wi-Fi
unencrypted, the browser doesn't keep the app's files, and Android adds a
plain shortcut instead of an installed app. **mkcert** is a free tool that
makes a certificate your own devices trust, with no warnings. Do this once,
on the app computer.

**Install mkcert**

- **Windows:** in Command Prompt, `winget install FiloSottile.mkcert`. (Or
  download `mkcert-…-windows-amd64.exe` from
  https://github.com/FiloSottile/mkcert/releases, rename it `mkcert.exe` and
  put it in a folder of your own; run it from there.) Close and reopen
  Command Prompt afterward.
- **Mac:** with Homebrew (https://brew.sh), in Terminal: `brew install mkcert`
  (and `brew install nss` if you use Firefox).
- **Linux or a Pi:** `sudo apt install mkcert libnss3-tools`.

**Make the certificate.** Replace `192.168.1.20` with the app computer's
address from step 1. On **Windows**, in Command Prompt:

```
mkcert -install
mkdir "%LOCALAPPDATA%\EaveLuxOS\tls"
cd /d "%LOCALAPPDATA%\EaveLuxOS\tls"
mkcert -cert-file cert.pem -key-file key.pem 192.168.1.20 localhost 127.0.0.1
```

`mkcert -install` asks once whether to trust the new certificate authority:
click **Yes**. On a **Mac**, in Terminal:

```
mkcert -install
mkdir -p ~/Library/Application\ Support/EaveLuxOS/tls
cd ~/Library/Application\ Support/EaveLuxOS/tls
mkcert -cert-file cert.pem -key-file key.pem 192.168.1.20 localhost 127.0.0.1
```

On **Linux or a Pi**, the same in the app's data folder's `tls` folder
(**Setup › App › Setup and about** shows the data folder).

**Restart EaveLuxOS** (**Quit** at the top, then start it again). Its address
now starts with **https://**, the browser shows a padlock, and old
`http://` bookmarks forward to `https://` by themselves.

**The root certificate for your phones.** Run `mkcert -CAROOT`: it names a
folder holding two files. Only **rootCA.pem** goes to your phones and
tablets (steps 3 and 4). **Never copy `rootCA-key.pem` anywhere:** with it,
anyone could make certificates your devices trust. If your router gives the
app computer a new address, run the last `mkcert -cert-file …` line again
with the new address and restart.

No mkcert? `python3 main.py make-cert` (installed apps: `EaveLuxOS-cli.exe
make-cert` on Windows, `eaveluxos make-cert` on Linux) makes a self-signed
certificate instead. Each browser then warns once, and phones won't install
the app fully; mkcert is better.

### 3. iPhone and iPad

**Trust the certificate (once, with HTTPS):**

1. Send **rootCA.pem** to the iPhone or iPad: AirDrop it from a Mac, or email
   it to yourself and tap the attachment in the Mail app. It says
   **Profile Downloaded**.
2. Open the **Settings** app: **General**, then **VPN & Device
   Management**. Tap the **mkcert** profile and **Install** (enter the
   device passcode), then **Install** again.
3. Still in the **Settings** app: **General**, **About**, then **Certificate
   Trust Settings** at the bottom. Turn on the switch for the **mkcert**
   certificate and tap **Continue**.

**Install the app:**

1. Open **Safari** and go to the address from step 1 (with `https://`).
2. Sign in.
3. Tap the **Share** button (on an iPhone at the bottom, on an iPad at the
   top right; in newer iOS, the **⋯** button first), then **Add to Home
   Screen**. Leave **Open as Web App** on if it's shown, and tap **Add**.

The EaveLuxOS icon opens straight into Quick (below). **Setup › App › On
your phone** shows the same steps and whether this device has it.

**If the address times out on one device** while it works on another:
the router or firewall may be holding back a device it hasn't seen before
(Firewalla, eero and others can quarantine new devices), and an iPhone or
iPad uses a different **Private Wi-Fi Address** for each network. In the
**Settings** app: **Wi-Fi**, tap **ⓘ** next to your network and set
**Private Wi-Fi Address** to **Fixed** (or off), then allow the device in
the router's app.

### 4. Android phones and tablets

**Trust the certificate (once, with HTTPS):**

1. Copy **rootCA.pem** to the phone or tablet (email it to yourself, or put
   it in Google Drive) and download it. If the phone won't offer it as a
   certificate, rename it **rootCA.crt**.
2. Open the **Settings** app and search for **CA certificate**. It's under
   **Security & privacy** (Pixel: *More security & privacy*, *Encryption &
   credentials*, *Install a certificate*; Samsung: *Security and privacy*,
   *More security settings*, *Install from device storage*).
3. Tap **CA certificate**, then **Install anyway**, and pick the file.

**Install the app:**

1. Open **Chrome** and go to the address from step 1 (with `https://`).
   (Firefox for Android doesn't use certificates you add; Samsung Internet
   does.)
2. Sign in.
3. Tap **Install** on the bar EaveLuxOS shows, or the **⋮** menu, then
   **Install app** (on some versions **Add to Home screen**, then
   **Install**).

Tablets work the same way as phones; the app uses the larger screen by
itself. Press and hold the icon for **Lights on**, **Lights off**, **Back to
the schedule** and **Security flash** (below).

### The app on your home screen (4.14)

EaveLuxOS installs from the browser like an app, with no app store:

- The icon opens **Quick**: big buttons for what you reach for most (see
  below), with a brightness slider while the lights are on.
  **Everything else (Home)** goes to the full app.
- **Press and hold the icon** (Android; on iPhone, the app's own buttons)
  for **Lights on**, **Lights off**, **Back to the schedule** and **Security
  flash**, straight from the home screen. The same addresses opened as an
  ordinary link (an email, another web page) ask before doing anything.
- On an **https://** address (and on the app computer itself), the app's
  own files are kept on the phone: it opens at once, and when you're away
  from home Wi-Fi it says **Can't reach EaveLuxOS** with a **Try again**
  button instead of a browser error. Nothing about your lights, settings or
  accounts is kept on the phone; that always comes fresh from the app
  computer. Each new version replaces the kept files by itself.
- On a plain **http://** address the app works the same, but the browser
  doesn't keep its files, and Android Chrome adds a home-screen shortcut
  rather than an installed app. For the full app, use HTTPS with a
  certificate the phone trusts (mkcert, step 2 above).

**Quick buttons.** Until you choose them, Quick shows Lights on, Lights off,
Back to the schedule, your Home favorites and up to three scenes. **Edit**
(on Quick) chooses up to 12 buttons, in order, for everyone in the
household: On, Off, Back to the schedule, Security flash, any pattern or
scene, or an automation (it runs that automation's **Then** at once). The
button for what's showing has an outline. **Quick buttons** on Home opens
Quick in any browser.

**Why not an app store app?** An installed EaveLuxOS is the same app you use
in the browser, always the version on your app computer, with nothing to
update on the phone. A store app would need Apple's and Google's developer
accounts and reviews, and would still have to reach the app computer on
your home network to do anything.

A phone stays signed in until it goes **8 hours without being used**, and
never longer than **7 days** (an Administrator can change the first number
under **Setup › Accounts & access**). The sign-in is stored for this
app's exact address, including the port, so other web apps on the same
computer never see it. If you change the app's port (section 19), or update
from a version before 2.3.2, each phone signs in once more.

> [!NOTE]
> **HTTPS:** see step 2 above. With HTTPS on, an old `http://` address or
> bookmark forwards to `https://` by itself (4.16.5).

> [!NOTE]
> **Away from home:** The app is reached on your home network only, which is
> deliberate. Never "port forward" it on your router. For remote access, use
> Tailscale (**Setup › Accounts & access › Away from home** walks you through
> it, section 19) or your router's own VPN.
>
> **If you put a reverse proxy in front of the app** (Caddy, nginx, Tailscale
> Serve, cloudflared), the app tells outside requests apart from this computer
> by the `X-Forwarded-For` header the proxy adds. Caddy, Tailscale Serve and
> cloudflared add it on their own. nginx needs
> `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` in its
> `location` block. Anything that forwards without adding that header (`ssh -L`,
> `socat`, a TCP-only tunnel) can't be told apart from a browser on this
> computer, so first turn on **Setup › Accounts & access › Require signing in on this computer
> too**.

## 9. Home

Home shows what the lights are doing now and lets you take over quickly.

**On every screen,** the top right shows what the lights are doing (*Lights
on*, *Lights off* or *Music show*) next to these buttons. On a phone they show
as icons only: a light bulb, a power symbol, the theme, a question mark and a
door, and the tabs are along the bottom of the screen.

- **On** turns the lights on with tonight's scheduled pattern: the one
  showing now, or the next one on the schedule. With nothing scheduled in the
  coming week, it uses the last pattern you turned on by hand, or Warm white.
- **Off** turns the lights off.
- Both last until the next scheduled change, like **Turn on** and **Turn off**
  below. The one that matches what the app wants right now is dimmed, but
  still works (see **On and Off at the top always work**, below). Viewers
  don't see them.
- **Theme (auto, light or dark):** the look of the app's screens, not the
  lights. Tap to switch. **Auto** follows the
  phone's or computer's own setting; **Light** and **Dark** stay that way. The
  choice is kept on each phone or computer separately.
- **Manual** (**?**) opens this manual.
- **Quit** stops the app, after asking first. It's shown only on the computer
  the app runs on (see **Quit the app** in section 19).

- **The headline** says whether the lights are on and why. For example, "Every
  night: Warm white until 11:00 PM" or "Christmas, set by hand".
- **Tonight** (under the headline): what the schedule does in the next 24
  hours, with sunset, when the lights come on, a switch to another rule, and
  when they go off, plus a countdown to the next one ("Lights on in 2 h 5
  min"). Away mode and game days are included.
- **The day bar** runs from midnight to midnight:
  - Dark is night, light blue is daytime, and the in-between shades are dawn
    and dusk.
  - **Amber** shows when the lights are scheduled on.
  - The thin line is now.
- **Turn on:** tap any pattern to show it right away. It stays on until the
  next scheduled change. **Favorites** (patterns you starred on the Patterns
  tab, up to 6) show as big buttons; the rest are under **All patterns**.
- **Turn off:** turns the lights off until the next scheduled change.
- **Return to schedule** appears after a manual change. Tap it to go back to
  the schedule immediately. The Schedule tab's **Run the schedule** button
  (section 13) is always there and also ends a security flash and resends the
  lights.
- **Security flash:** see section 14, *Security flash*.
- **Brightness and speed:** these change whatever is showing now, until the
  next scheduled change.
- **This week:** each day's on and off times and which rule runs. A note
  appears on the day daylight saving time changes.
- **Controllers** (4.5): a card for each controller, as the Trimlight app's
  first screen lists them: its name, **Online** or **Offline**, on or off,
  its firmware, and its address on your home network, such as
  `192.168.1.50`, with whether it's **answering** there. Trimlight's cloud
  doesn't report the address, so it's the one entered in **Setup › Lights &
  controller › Local mode**; until then, Administrators see a link there.
  The app checks every 5 minutes by opening and closing a connection to each
  controller (nothing is sent). **Not answering** usually means the router
  gave the controller a new address: the Trimlight app shows the current
  one when it opens. Reserve it in the router so it stays the same.
  With two or more controllers on the account (4.7.1), the ones this app
  runs are marked **Active** with a green edge, and the others are grayed out
  with **Not run by this app** and come last. To run one too, tick it under
  **Setup › Lights & controller › Controlled by this app**.
  Each Active card (4.8) says what that controller shows now and gives it
  its own **On**, **Off** and **Show a pattern…**. That choice is for that
  controller only and lasts until its schedule changes (its rule starts or
  ends); **Back to schedule** ends it sooner. The **On** and **Off** at the
  top of the page still mean all of them, and end any one controller's own
  choice. When the controllers show different things, the headline lists
  each one.
- **On and Off at the top always work (4.21.1).** The one matching what
  EaveLuxOS wants right now is dimmed, but you can still press it: the lights
  can be on while the app says "Lights off" (turned on with the Trimlight
  app, by the controller's own timer, or when power comes back), and
  **Off** then turns them off. Every press is sent to every controller again,
  the on/off itself and not just the pattern. **Off** also ends a flash that's
  running (security, a score, an automation) instead of waiting for it.
- **Activity:** a log of everything the app did.

## 10. Patterns

The buttons at the top switch between three lists.

**My patterns** are the ones schedules can use. On each card:
- **Turn on** shows the pattern now.
- **Edit** opens it in Create, or for built-in effects lets you change speed,
  brightness and length.
- **Delete** removes it. A pattern that a rule uses can't be deleted until
  you change that rule.
- **The star** pins it to Home as a big one-tap button (up to 6). Tap it again
  to unpin.
- **Folder** (4.9.1) puts it in a folder, such as *Christmas* or *Fourth of
  July*: type a new name or pick one you've used. Leave it empty for none.

**Order** lists them **A to Z** (the usual), **Newest first** or **Oldest
first**. Once a pattern has a folder, buttons above the list show **All**,
each folder, and **No folder**, each with how many it holds. This browser
remembers the order and folder you chose. Folders only sort the list; they
change nothing on the lights, and a pattern saved again in Create keeps its
folder.

**In the Trimlight app** lists the patterns saved in your Trimlight Edge app,
read from your controller.
- With two or more controllers (4.7.1), **Controller** at the top chooses
  whose patterns to list, including ones this app doesn't run. Each
  controller keeps its own patterns, so the lists can differ.
- For Administrators, a controller with an address under **Setup › Lights &
  controller › Local mode** is read over your home network, so the list is
  what it holds right now. Otherwise, or if it doesn't answer, the list is
  what Trimlight's cloud last heard from it. The note above the list says
  which.
- **Try** shows one on the lights, on the controllers this app runs (the
  note says so when that isn't the one listed).
- **Add to my patterns** copies it here so your schedule can use it.
  Colors, bulb counts and the gaps of bulbs left off carry over exactly; a
  built-in effect keeps its effect, speed and brightness. If you already
  have a pattern with that name, it's added with the controller's name after
  it, for example *Christmas (Front)*.

**Built-in (180)** lists all of Trimlight's built-in effects. Search by color,
for example "red green", or filter by family (Wave, Snake, Stars, Fire and so
on).
- **Try** shows one on the lights.
- **Add** saves it to My patterns, after asking for speed, brightness and
  pattern length.
- **Recreate with my colors** opens it in Create as a new pattern with the
  same colors and the closest animation (a Wave stays a Wave, a Meteor becomes
  a Comet, Fire becomes Twinkle fade), ready for you to change the colors. Built-in
  effects' colors are fixed in the controller, so this is a copy that moves a
  little differently from the original, not an edit of it.

### Lightning and Snowflake (4.22)

The Trimlight Edge app's **Pattern Library** can add one of two effects to a
pattern saved on the controller. EaveLuxOS sets them too, over your home
network:

| Effect | What it adds |
|---|---|
| **Lightning** | Sudden bright flashes over the pattern, like a storm. |
| **Snowflake** | White sparkles falling over the pattern, like snow. |
| **None** | The pattern exactly as designed. |

**Add one**

1. Open **Setup › Local mode** (Administrators). The controller's address
   must be set there (section 17).
2. Under **On the controller now**, find the pattern. Each one has an
   **Effect** choice next to **Delete**.
3. Choose **Lightning**, **Snowflake** or **None**. The app backs the
   controller up, sends the change, and reads the controller back to check
   it. A message says when it's done.

**See it on the lights**

The effect belongs to that saved pattern, so it plays whenever the
controller shows that pattern **by its number**:

- from the Trimlight Edge app or the controller's own timers;
- from EaveLuxOS (the schedule, a press on Home, an automation), when Local
  mode's **Send on/off and saved patterns over the home network** is on and
  your pattern is that saved pattern or an exact copy of it (**Patterns › In
  the Trimlight app › Add to my patterns**, without changing its colors,
  speed or brightness).

A copy you change (another brightness, say) is shown live instead, and live
patterns don't carry the effect.

**Which patterns have one (4.22.5)**

A badge shows it: **⚡ Lightning** or **❄️ Snowflake**.

- **Patterns › In the Trimlight app**: on each saved pattern that has one.
- **Patterns › My patterns**: on each of your patterns that the controller
  shows by a saved pattern's number, so the effect plays with it. A copy
  you've changed has no badge, because it's shown live.

Badges need the controller's address in Setup › Local mode. If Local mode's
**Send on/off and saved patterns over the home network** is off, the My
patterns badge's tip says the effect plays only when the pattern is shown
over the home network.

> [!TIP]
> To have a pattern both ways, save it twice in the Trimlight Edge app (for
> example *Candy cane* and *Candy cane storm*) and add Lightning to one. When
> two saved patterns look exactly alike, EaveLuxOS shows the one whose name
> matches your pattern's name (4.22.3); if neither name matches, the one
> without an effect.

**Good to know**

- One effect per pattern. Choosing another replaces it.
- Deleting a pattern in Local mode takes its effect off first, then deletes
  it, so a pattern saved later under the same number doesn't flash or snow
  by surprise.
- If the controller still lists an effect for a number with no pattern (a
  pattern deleted in the Trimlight app, or before 4.22.4), Local mode says
  which numbers, and EaveLuxOS saves new patterns under other numbers first.
- The **Effect** choice appears only when the controller reports its effects
  list the way it did on a real controller in November 2026. If it doesn't
  (another firmware, say), nothing is sent, and Local mode says
  **Lightning and Snowflake aren't available for this controller yet**, with
  the reason (4.22.6). Set the effect in the Trimlight Edge app meanwhile.
  To help add that controller, press **Copy details** and send what it
  copies to the EaveLuxOS project. It holds only the controller's timers,
  effects and clock, no pattern names; the same line is in the log
  (section 23).
- If the reason is **no clock at the end**, open the Trimlight Edge app once
  on your home Wi-Fi (it sets the controller's time), then **Read again**.
- Controllers with newer firmware (4.17.79, November 2026) report their
  effects a little differently; EaveLuxOS reads both kinds (4.23.1). That
  firmware still offers just Lightning and Snowflake. If a later one adds an
  effect EaveLuxOS doesn't know yet, it shows as **Another effect (set in the
  Trimlight app)**, with a ✨ badge, and is never changed unless you choose
  Lightning, Snowflake or None for that pattern.

## 11. Create a pattern

With two or more controllers of different lengths (4.9.1), **Bulbs of**
above the preview chooses whose bulbs the preview and **Paint bulbs** count,
for example *Front (106 bulbs)* or *Deck (96 bulbs)*. Your patterns are
shared by all controllers, and a pattern repeats along any controller's
lights, so it works on each; this only changes what you see while making it.

### Describe it in words

At the top of **Create** (Patterns › New pattern), type what you'd like, for example "cyberpunk rainy
night", "1980s retro arcade" or "slow candy cane twinkle", and tap **Make it**
(or press Enter). The colors, motion, speed and brightness are filled in for
you to adjust, preview and save. **Try another** gives a different take on
the same words.

- **Built in (the standard way):** a dictionary of holidays, seasons, moods,
  places and eras, color words ("purple and gold", and all 141 web color
  names such as "crimson and forest green"), motion words ("twinkle",
  "chase", "breathe", "comet", "wave", "strobe", "fade") and speed words
  ("slow", "fast"). It runs on this computer, free, and sends nothing
  anywhere. Words it doesn't know still give a pattern, the same one every
  time.
- **With AI (optional):** add an Anthropic API key in **Setup › App › AI pattern
  ideas**, and **Use AI** appears. The description you type (nothing else) is
  sent to Anthropic's Claude, which answers with colors and a motion. Each idea
  costs a fraction of a cent on your Anthropic account. The answer is checked
  like any pattern (up to 8 colors, the controller's own motions) before you
  see it. Saving or removing the key asks for the app password again. To
  keep the cost in check, Use AI allows 6 ideas a minute and 100 a day (Try
  another, built in, has no limit). If Use AI says the model wasn't found
  (Anthropic retires older models), enter a newer model name under the key
  in **Setup › App › AI pattern ideas**; leave it empty for the default.

### Design it yourself

This works like the color circles in the Trimlight app.

1. On the **Patterns** tab, tap **New pattern** (or **Edit** on one of your
   patterns). This opens **Create**; **‹ Patterns** at the top goes back.
2. Type a **Name**, for example "Candy cane".
3. Under **Colors in order**, each circle is one color, and its number is how
   many bulbs that color covers, from 1 to 90. There can be up to 30 circles,
   just like the 30 sequence slots in the Trimlight app. The sequence repeats
   along the whole roofline.
   - Tap a circle to select it.
   - Tap a color in the palette to change it, or use the rainbow circle to pick
     any color.
   - **By name or code:** type a color's name (**crimson**, **forest green**,
     **deep sky blue**; suggestions appear as you type) or its code from an
     RGB chart: **FF1493**, **#FF1493**, **255 20 147** or **FF 14 93**. Tap
     **Set** (or press Enter).
   - **Paste a list** in the same box, such as "crimson, forest green, gold" or
     rows copied from a chart, and choose **Use them as the pattern** or **Add
     after** the selected color. A chart row that gives one color three ways
     (name, hex and decimal) counts once.
   - **Named colors…** lists the 141 standard web color names (the RGB chart
     shared in Trimlight groups), grouped by color, with a search box.
   - **Whites** sets a white by color temperature, like light bulbs on a box:
     **Candlelight** (2200 K), **Warm white** (2700 K), **Soft white** (3000 K),
     **Neutral white** (4000 K), **Cool white** (5000 K) and **Daylight**
     (6500 K), or any value in between with the **Warm–Cool** slider. Use the
     same white on every circle for an even architectural look. Trimlight
     bulbs have no separate white chip, so these whites are mixed from red,
     green and blue; if whites look too blue or too pink on your house, adjust
     **Setup › Color correction**. Whites are in **Paint bulbs** too.
   - Use **−** and **+** to change how many bulbs the color covers (1 to 90).
   - Use **Move left** and **Move right** to reorder, and **Remove** to delete
     the selected color.
   - Tap **+** at the end to add another color (up to 30).
   - **Black** is a dark color. In a moving pattern, the dark gaps move along
     with the colors.
   - **✕ (Zone off)** works like the X in the Trimlight app. Those bulbs stay
     dark and are **skipped by every movement**. Use it to keep lights over a
     bedroom window dark, or to leave out part of the roofline (see the
     example below).
4. Choose an **Animation** and set **Speed** and **Brightness**. The list is
   the Trimlight Edge app's, in its order (see **Animations** below).
5. Watch the **Preview**. It's drawn with your real number of bulbs, and the
   animation is a close approximation of the controller's.
6. Tap **Try on my lights** to see it on the house. A preview lasts 15
   minutes, then the schedule takes over again.
7. Tap **Save pattern**. Tick **Also save it on the controller** first if you
   want it in the Trimlight Edge app's list too. Since 4.3 this goes over your
   home network (see **Local mode** in section 17), so the controller's address
   must be set there.

### Animations (4.23)

The same 23 animations as the Trimlight Edge app, in its order:

| Animation | What it does |
|---|---|
| Static | Stays still. |
| Chase forward, backward, middle to out, out to middle | The colors move along the roofline. |
| Twinkle fade | Bulbs twinkle and fade (called **Stars** before 4.23). |
| Fade | The whole pattern fades in and out (called **Breath** before 4.23). |
| Comet forward, backward, middle to out, out to middle | Comets with tails run along. |
| Wave forward, backward, middle to out, out to middle | Waves of brightness roll along. |
| Strobe | Flashes. |
| Solid fade | The whole roofline fades from one color to the next. |
| Full strobe | Every bulb flashes on and off together. |
| Twinkle | Bulbs glow up and out on their own. |
| Firework | Bursts of color spread from random spots. |
| Inside out | Colors grow from the middle outward. |
| Dissolve | Bulbs change to the next color one by one. |
| Juggle | Dots of color bounce back and forth at different speeds. |

The previews are close approximations; **Try on my lights** shows the real
thing.

> [!NOTE]
> The last six (Full strobe to Juggle) came with newer Trimlight Edge apps,
> and Trimlight's cloud doesn't list them. EaveLuxOS shows them over your home
> network (Setup › Local mode). If it ever has to use the cloud instead, it
> shows the closest older animation (Juggle as Chase forward, for example)
> until the home network answers again. Patterns saved on the controller keep
> their own animation, whichever it is.

When **color correction** is on (see
[Setup › Lights & controller](#17-setup--lights--controller)), the lights get adjusted
colors so they look like the preview. Tick **Exact colors** to send this
pattern's colors unchanged, for example colors you already tuned by eye on the
house.

To change a pattern later, open **Patterns › My patterns** and tap **Edit**.

### Named colors on LED lights

The RGB charts shared online show colors as a **screen** shows them. LED
lights mix colored light, so many named colors look different on a house.
**Named colors…** notes how each one looks on lights, and **Only colors that
show well on lights** hides the rest:

| Note | Colors like | What you'll see |
|---|---|---|
| Great on lights | Red, Crimson, Orange Red, Gold, Lime, Deep Sky Blue, Blue, Dark Violet, Magenta, Deep Pink | Close to the chart |
| Softer on lights | Salmon, Light Coral, Sky Blue, Orchid, Khaki | A light, whitish version of the color |
| Pale: looks almost white | Pink, Lavender blush, Peach Puff, Tan, Plum, Pale Green | Nearly white |
| Looks white | The whole White group (Snow, Ivory, Linen, Beige…), Lavender | White; you can't tell them apart on a roofline |
| Looks like dim white | The Gray group (Silver, Gray, Slate Gray…) | A dimmer white |
| Looks like dim … | Navy, Maroon, Dark Green, Teal, Indigo | A dimmer version of the color (the brightness slider does the same) |
| Looks orange / red / yellow | Chocolate, Sienna, Peru, Goldenrod, Brown | Lights can't make brown: brown is dark orange next to brighter colors |

The selected color shows its name in Create (or the nearest name, like
"#E0A060 · near Sandy Brown"), with a note when it won't look like the chart.
Hold the pointer over any color strip in the app to see its colors' names.

### Paint single bulbs, ranges or every Nth bulb

For detail the color circles can't give you, tap **Paint bulbs** in **Create**.
The circles become a strip with one dot per bulb (numbers every 10).

1. Choose what you're painting:
   - **One repeat:** one copy of your sequence, which then repeats along the
     roofline. Set **Bulbs in one repeat** to make it longer or shorter.
   - **Whole house:** every bulb from 1 to your total (House › Bulb
     numbering), painted once with no repeat. Landmarks from the House tab show
     as small orange marks under their bulbs.
2. Pick a **paint color**, ✕ (zone off: dark, skipped by movement) or any
   color with the rainbow button.
3. Paint:
   - **One bulb:** click it. **Shift-click** another bulb to paint everything
     in between.
   - **A range:** enter **First bulb** and **Last bulb** (or, for the whole
     house, pick a zone), then **Paint range**.
   - **Every Nth bulb:** set **Every N bulbs** and **Width**, then **Paint
     every**. It works within First–Last: every 4 with width 2 from bulb 1
     paints 1–2, 5–6, 9–10 and so on.
   - **Fill everything** paints every bulb; **Undo** steps back.
4. Watch the **color slots** count. The controller stores up to 30 runs (a
   run is a stretch of one color, up to 90 bulbs), so lots of separate single
   bulbs can run out. Past 30 the app explains why and won't apply it; use
   fewer separate bulbs, or paint one repeat instead of the whole house.
5. Tap **Use this pattern**, check the preview, then **Save pattern**.

### Combine patterns by zone

(4.7.) Show a different one of your patterns along each zone, for example
**Christmas** on the garage, **Thanksgiving** on the main roof and
**American Flag** on the porch, as one pattern.

1. Save your zones on the House tab first (section 12).
2. In **Create**, tap **Combine patterns by zone**.
3. Choose a pattern for each zone, or leave a zone as **the rest**. Choose
   what **Everything else** shows: off (dark) or a color.
4. Choose the **Motion**: **Still** (each zone stays in place; looks best) or
   **Moving** with a motion. A controller has one motion for all its bulbs,
   so a moving pattern carries each zone's colors into the next zone.
5. The strip shows the result. Tap **Combine**, then **Preview on house** or
   **Try on my lights**, name it and tap **Save pattern**.

A controller shows at most 30 color blocks. When the zones together would
need more, the busiest zone's colors are made longer until it fits (for
example 6 bulbs of each color instead of 3); the note under the strip says
which zones and how much. A zone's pattern that is dimmer than the brightest
one chosen is darkened to keep its look, since a controller has one
brightness. Only patterns of your own colors can be combined: built-in
effects and patterns saved only on the controller can't be laid along a
zone. The combined pattern is an ordinary pattern and doesn't follow later
changes to the zones or the patterns: combine again to update it.

With zones for one controller (4.10, section 12), each zone shows its
pattern along its own controller's bulbs, and a zone for every controller
shows on each. When you choose a pattern for a zone that is one
controller's, give it a **Name**: the strip shows each controller's part,
and **Combine** saves a pattern for each controller (in the **Zone parts**
folder) and a **Split by controller** pattern with that name that shows
them together. Use that one in schedules. A controller with no zone chosen
is off in it.

### Paint by zone

If you've saved zones on the House tab (section 12), you can color whole
sections at once:

1. In **Create**, tap **Paint by zone**.
2. Choose a color for each zone, such as Garage roof = Red and Main roof =
   White. Leave a zone as "Leave as the rest" to skip it. The percentage next
   to it sets that zone's **brightness** against the others, for example the
   second story at 35% and the garage at 100%.
3. Choose **Everything else**: ✕ Zone off (dark, never moves), Black, or a
   color.
4. Tap **Paint**, check the preview, name the pattern and tap **Save pattern**.

A controller has one brightness for the whole pattern, so a dimmer zone is
made by darkening its color. That works best for still patterns: a moving
pattern carries the dimmer color along with it. The percentages look right
with **Color correction** on (section 17). With it off, a dimmed zone looks
brighter than its number: 50% looks closer to 75%.

**Preview on house** (next to Paint bulbs) shows the design animating on your
house photo (section 12, House view).

The counter above the circles shows how many of the controller's **30 color
slots** the pattern uses. Each slot holds up to 90 bulbs, so a long zone may
take several slots. If your controller turns out to accept only 60 bulbs per
slot (Trimlight's own documents disagree), the app splits longer runs
automatically. The lights look exactly the same.

### Example: keep one gable dark

This is the "Isolated Front Peak" example from Trimlight's guide:

| Circle | Color | Bulbs | Result |
|---|---|---|---|
| 1 | Red | 26 | Bulbs 1–26 red |
| 2 | Green | 22 | Bulbs 27–48 green |
| 3 | ✕ Zone off | 18 | Bulbs 49–66 stay dark, even while the pattern moves |
| 4 | Blue | 25 | Bulbs 67–91 blue |

The sequence then repeats for the rest of the lights. Bulb numbers follow the
port setup on Setup › Lights & controller (section 17), so get that right first.

### Tips from Trimlight's guide

- **Comet and Wave** only run when each color covers **more than 5 bulbs**. The
  designer warns you when a color is set to 5 or fewer.
- **Chase** is very fast with 1 bulb per color. Slow it down with larger counts
  or black spaces between the colors. For example, 1 red followed by 7 black
  sends a single red light running along the roofline.
- **For a pulse**, fill several circles with a large count (up to 90) of one
  color, and add one circle of a second color that will travel through it.

### Studio: layers, gradients and shows (4.20)

**Patterns › Studio** is the advanced editor. You build a **show**: looks in
order (keyframes on a timeline), each for some minutes, fading from one to
the next. Approved, the looks become your patterns and the show can go on
the schedule.

**Describe it.** Type the whole show, for example *warm white for 30
minutes, then fade to candy cane twinkle, then deep blue for 2 hours*, and
tap **Lay it out**. Each part (split at *then*, `;` or `->`) becomes a
keyframe made by the built-in designer; *for 30 minutes* or *for 2 hours*
is its length (10 minutes if you don't say), and *fade* or *over 5 seconds*
sets the fade between them. The line under the box says what it found.

**The timeline** shows every keyframe in proportion to its minutes. For each
keyframe: its minutes, **↑** to move it earlier, **Copy**, ✕, and **Layers**
to change its look. **Add a look (layers)** starts a new one, and **Add one
of your patterns** copies one of yours in. **Fade between** sets the fade
(none, 2, 3, 5 or 8 seconds). Your work in progress is kept in this browser
until you approve it or tap **Start over**.

**Layers.** A look is a base and up to 4 layers on top:

- **Base**: one color, or a **gradient** through up to 6 colors (**there
  and back** mirrors it), over the **bulbs in one repeat** (2 to 300).
- **Accent**: a color every N bulbs, 1 or more bulbs wide (sparkles of
  white every 8 bulbs over a gradient, say).
- **Band**: a color over a stretch of bulbs.
- **Motion**, speed and brightness, as in Create.

The strip under them is exactly what one repeat of the lights will show.
The controller takes at most 30 colors, so a long gradient's in-between
shades are merged (the closest neighbors first); layers keep their colors.

**Play on the lights** plays the show once, quickly (3 to 20 seconds a look;
the real minutes are for the schedule), with its fades, then the last look
stays for 10 minutes. Next to the button it says which look is showing.
**Stop**, or any button anywhere in the app, ends it, and a button pressed
during a fade wins over the next look.

**Approve and save** adds the looks to your patterns (named after the show;
none of yours is replaced) and, with **Put it on the schedule** ticked, a
rule *Studio: (name)* that plays them in turn, each for its minutes, every
night between the times you give (sunset to 11 PM to start). If fades were
off, the show's fade turns them on (Schedule › Fades between patterns).

## 12. House

The House tab helps you find where each bulb is, label your house, and
name sections of roofline.

### Elevations and their versions (4.12)

Each side of the house is an **elevation**: **Front elevation**, **Right
side elevation**, **Rear elevation**, **Left side elevation** and **Shed**
are always there. **Add an elevation** adds another (a second side
elevation on an L-shaped house, a garage, a deck) and asks which kind it
is. **Rename** changes its name and kind; an elevation you added can be
deleted.

**Versions.** One elevation can have more than one photo and layout, for
example a daylight photo for tracing and a night photo with the lights on,
or before and after adding a run of lights:

1. Choose the elevation, then **Add a version** and name it (for example
   *Night*). Leave **Start from this version's rooflines, bulbs and pins**
   ticked when the photo is taken from the same spot; the traced lines,
   their bulb numbers and the pins come along.
2. Upload the version's photo. Each version keeps its own photo, rooflines
   and pins.
3. The **★** version is the one the whole-house view and the flat diagram
   show. **Show this version in the whole house** makes the one you're
   looking at the ★ one.

**Delete this version** removes its photo, rooflines and pins (the
landmarks stay, without their pins).

**Export this elevation** saves a file (`….elevation.json`) with all its
versions: their photos, rooflines, bulb numbers and pins. **Import an
elevation** adds one from such a file as a new elevation, for example on
another computer running EaveLuxOS, or to restore it. Unlike pattern files,
this file **does contain your photos**, so share it only with people you'd
show them to.

### Two or more controllers (4.10)

Each controller numbers its own bulbs from 1. With two or more, the House tab
has a **Controller** choice at the top, next to the bulb count of each:

- **All controllers** works as before: the finder lights a bulb number on
  every controller at once, and the house counts one set of numbers.
- Choose one, and the finder, **Light these bulbs** on a zone and scene
  previews light only that controller, along its own bulbs (for example
  106 on the Front, 96 on the Deck). The other controllers keep showing what
  they were. **Return to schedule** ends it for all.
- Under the elevation buttons, **This elevation's lights** gives an elevation to
  one controller. Choosing that elevation then chooses its controller.
- A zone or landmark saved while a controller is chosen is that
  controller's; the list says whose. One zone name can be used once for each
  controller.
- **Paint by zone** in Create lists the zones for the controller **Bulbs of**
  counts, and the zones for every controller. **Combine patterns by zone**
  makes one pattern for each controller (section 6).

A weather or webhook alert set to light a zone lights those bulb numbers on
every controller, as before.

### Find a bulb

1. Open the **House** tab. The **Bulb finder** shows bulb **1** of your address
   space. That's the total number of bulbs, taken from the controller's ports
   (section 17).
2. Tap **Show on house**. That one bulb lights up and everything else goes
   dark.
3. Step with **‹** and **›**. **Move by** sets the step size (1, 5, 10 or 25).
   You can also type a number in **Go to bulb**.
4. Tick **Update the house as I move** to light each new bulb automatically
   as you step.
5. When you're done, tap **Return to schedule**. If you forget, the schedule
   comes back by itself 10 minutes after your last change in the finder.

> Bulb numbers are pattern addresses. If two ports overlap (a mirrored run,
> such as Port 2 = 84–138 and Port 3 = 100–138), one number lights in two
> places on the house.

**A range:** tick **Select a range** and enter the first and last bulb. The
arrows then move the whole range.

### Photos and pins

1. Pick a side (**Front**, **Right side**, **Back**, **Left side**, or **Add a
   side** for a shed or garage).
2. Tap **Upload photo**. A photo taken at night from the street, with the
   lights on, works best. The app shrinks it before saving.
3. Find a bulb with the finder, tap **Pin bulb N on this photo**, tap the spot
   on the photo, and give it a name, such as "Front gable peak".
4. Tap a pin later to jump the finder to that bulb.

Photos stay on the app computer, in the `data/photos` folder. They're never
included in exported pattern files.

### Landmarks

Landmarks are named bulbs, such as corners and peaks. Find the bulb, type a
name and tap **Save bulb N**. A pin on a photo also creates a landmark. Tap
**Show** to light a landmark.

### Zones

Zones are named sections, such as "Garage roof = bulbs 84–138". Tick
**Select a range**, set the first and last bulb, type a name and tap
**Save**. You can then paint zones in Create (section 11).

To fix a zone (for example if a bulb count was off), tap **Edit** next to it.
Change the name or the first and last bulb; **Use the finder's range** copies
the bulb finder's current selection. Tap **Save zone**. **Show** lights a zone
and ✕ deletes it. Patterns you already painted with a zone keep their colors;
paint them again to use the new bulbs.

**Line a zone up with the house (4.12).** In **Edit**:

1. Tap **Light these bulbs**. The zone's **first bulb is green** and its
   **last is red**, so you can see on the house exactly where it starts and
   ends.
2. If they're off, use **First −1 / +1**, **Last −1 / +1**, or **Whole zone
   −1 / +1** (moves both ends, for example after a bulb was added upstream).
   While the zone is lit, the house follows each change.
3. The picture under the buttons shows the zone on each elevation photo it
   reaches (green start, red end), from the bulbs you placed.
4. **Runs the other way** is for a zone whose pattern should start at its
   last bulb, such as a run wired from the far end. **Combine patterns by
   zone** then lays that zone's pattern from its last bulb back; the green
   and red ends swap to show it.

### Bulb numbering

The app normally uses the controller's port layout. Under **Use a different
total**, you can set your own number instead, for example if the controller
hasn't answered yet.

### Rooflines: automatic detection and tracing

Each side (**Front**, **Right side**, **Back**, **Left side** and **Shed**,
plus any side you add) can have its roofline traced on its photo. A daylight
photo taken straight on, with the whole roof in view, works best.

1. Choose the side and upload its photo.
2. Tap **Auto-detect roofline**. The app looks for the strongest edge between
   the roof and the sky and draws it as a line of points. This happens in
   your browser; the photo isn't sent anywhere. If trees, wires or the ground
   confuse it, set **Search from %** and **to %** to the part of the photo
   where the roof is (the rest is shaded) and try again.
3. Adjust the suggestion: drag points, or select one and use the arrow keys
   (hold Shift for bigger steps). Tap the photo to add a point after the
   selected one (or at the end). **Delete point** removes the selected one.
4. Tap a stretch between two points to mark it **wire only**: wire with no
   bulbs on it, such as a jumper across a gap. It turns gray and dotted.
5. Choose **Roof edge / eave** or **Ridge**, then **Save section**.

**Trace by hand** starts an empty section, for ridges, dormers and edges the
detection can't see. A side can have up to 40 sections of up to 100 points.
Tap a saved line (or **Adjust**) to change it; ✕ deletes it. Replacing a
photo removes that side's sections, since they were drawn on the old photo.

### Bulbs on each line

To preview patterns on a photo or build scenes (below), each traced roof edge
needs to know its bulbs:

1. Under the photo, tap **Bulbs** next to a section.
2. Enter the bulb at its **first point** and at its **last point**. Use the
   bulb finder to check the two ends. If they count down (for example 84 to
   40), enter them that way.

The bulbs are spread evenly along the line, skipping wire-only stretches.
Adjusting the line keeps its bulb numbers; **Clear** removes them.

### Calibrate with the camera (4.16)

Instead of tracing lines and numbering them by hand, let a phone's camera
find every bulb:

1. **At night**, stand where the whole elevation is in view, and prop the
   phone up (a tripod, a car roof, a fence post). It must not move for about
   a minute.
2. Open EaveLuxOS on the phone at its **https://** address (the camera only
   works on a secure page: section 8, HTTPS with mkcert). On the app computer
   itself, `http://localhost` with a webcam works too.
3. With two or more controllers, choose the **Controller** at the top of the
   House tab: each numbers its own bulbs.
4. Choose the elevation, tap **Calibrate with the camera**, then **Start**.
   The lights show about 16 black-and-white frames, a second or two each
   (for 106 bulbs; a few more for more bulbs). Each frame lights half of the
   bulbs in a different arrangement, so together they spell out every
   bulb's number; the camera reads them. Nothing goes anywhere: it's worked
   out in the phone's browser.
5. The result shows each bulb found on the photo, with a line through each
   run. **Save as a new version** makes it a version of the elevation
   (**Calibrated**), with the camera's own photo, a line for each run, and
   every bulb found pinned where it was seen; bulbs it missed are spread
   evenly between. **Show it in the whole house** makes it the ★ version.
6. The lights go back to what they showed before (a choice made by hand
   stays).

Tips: darker is better; keep car headlights and flashlights out of view
during the minute it runs; if many bulbs are missed, check the whole
elevation is in the picture, or set **Wait for each frame** to **4 seconds**
(for a slow connection to Trimlight's cloud). Two ports with the same bulb
numbers (a mirrored run) show up in both places, as two lines. Lights of
another controller in view, even moving ones, are ignored.

This needs a controller that repeats a short pattern along its lights, as
Trimlight controllers do with patterns shorter than the lights; if one
doesn't, the result says so.

### Place bulbs: each bulb where it really is (4.12)

Bulbs are spread evenly along each line, which is close on a straight run
but off where the spacing changes (a corner, a gap, a wider stretch). To
fix it:

1. In **House view**, tap **Place bulbs**. Every bulb is a dot.
2. **Drag a dot** to where that bulb really sits on the photo. It's
   **pinned** there (green), and the bulbs between it and the next pin (or
   the end of the line) spread out evenly again. A few pins usually fix a
   whole run.
3. Tap a dot to select it. **Light bulb N on the house** lights that one
   bulb, so you can check it against the real one. With a bulb selected,
   the arrow keys nudge it (Shift moves it farther).
4. **Unpin it** puts a bulb back to even spacing; **Unpin all on this
   photo** does that for every bulb on the photo.

Pins are used everywhere bulbs are placed: the preview, scenes and the
whole-house view. Adjusting a line keeps its pins; changing its **Bulbs**
numbers drops pins outside the new range.

### House view: preview a pattern on your house

**House view**, under the photo, shows the side with each bulb where it sits.

- **Preview a pattern** animates any pattern made of colors on the photo.
  **Night** darkens the photo so the lights glow. **Preview on house** in
  Create brings a design there before you save it.
- The animation is the app's approximation of the controller's motions, the
  same one Create's preview uses, so speed and smoothness are close, not exact.
  Built-in effects and patterns saved only in the Trimlight app can't be
  previewed, because their colors aren't known here.

### Scenes: light just the bulbs you choose

A scene is architectural lighting, for example 3 warm-white bulbs above each
window and at each peak with the rest of the roofline dark.

1. In **House view**, tap **Build a scene**.
2. Choose **Tap lights** (1 to 9 bulbs) and tap a bulb on the photo: that bulb
   and the ones around it light. Tap again to turn them off.
3. **Landmarks named…** lights every landmark whose name contains the words,
   for example "window", with the same number of bulbs around each. Or type
   **bulb numbers**, such as `10-12, 40`, and tap **Light these** (the way to
   build a scene with a keyboard).
4. **Add a group** for a different color or brightness, such as a dimmer white
   over the garage. Groups can use up to 14 colors.
5. Name it, tap **Show on lights** to check, and **Save as a pattern**.

Every other bulb is set to ✕ (dark). A scene is an ordinary pattern, so rules,
Home and Turn on use it like any other. **Edit a saved scene** (or Edit on the
Patterns tab) opens it here again.

Each lit spot and each dark gap uses one of the controller's 30 color slots
(two for a dark stretch over 90 bulbs, or over 60 on a controller that only
takes 60 per slot), so a scene has room for about 12 to 14 separate lit
spots. The counter shows how many it uses on your controller; spots that touch
share a slot. The group buttons count the bulbs each group really lights (a
later group wins a bulb two groups share). Dimmed groups follow the same rule
as dimmed zones above.

A scene covers exactly the bulbs your lights had when it was saved. If the
number changes (ports or the House tab total), the scene and the Patterns tab
say so: open it and save it again. Bulbs numbered past the last bulb are
flagged under the photo and left out of House view.

### The whole house at once (4.12)

**Whole house: every elevation at once**, at the top of the House tab,
shows each elevation (its ★ version) side by side, with its bulbs lit and
moving:

- **One pattern** shows the same pattern everywhere. A **Split by
  controller** pattern shows each controller's own part on its elevations.
- **Tonight's schedule** shows what the schedule plans from noon to noon,
  each controller with its own pattern. Drag the time, tap **Now**, or
  **Play** (ten minutes a second). The bars show when each controller is
  on and with what. Weather, scores, alerts, automations and choices by
  hand can't be known ahead, so they aren't shown.
- **A pattern for each zone** lets you choose a pattern for each zone and
  see them together, each zone moving its own. **Make it a pattern** opens
  **Combine patterns by zone** with those choices. (A controller moves one
  pattern with one motion, so the saved pattern moves as one.)
- **Night** darkens the photos.

An elevation shows the bulbs of the controller under **This elevation's
lights**; without one, the first controller's. Elevations without placed
bulbs aren't shown.

**Show flat diagram** unfolds every side into one picture: roof edges in
green, ridges in purple, wire-only stretches in gray, and your landmarks with
their bulb numbers. **Download SVG** saves it as a file you can print or open
in a drawing program. Traced lines follow your photos, so the diagram isn't
to scale.

## 13. Schedule

A **rule** says when the lights turn on and off, and which pattern shows.

The Schedule tab has two parts: **Every night** (your rules, and **Coming up**,
what runs each night) and **Special days** (holidays, game-time lights and away
mode, each folded to one line until you open it). Weather, severe weather
alerts and the security flash are on the **Alerts** tab; the backup timer is
in **Setup › Lights & controller**.

### Pause the schedule (4.16.6)

**Pause the schedule** (in the **Right now** box) stops everything this app
does by itself (scheduled on and off, weather rules, holidays, game days,
automations) until you tap **Resume the schedule**. The lights stay exactly
as they are, whatever set them. On, Off and patterns chosen by hand still
work, and so does the security flash. **Run the schedule** resumes too. The
top of the page says **Schedule paused** meanwhile.

### Run the schedule

The **Right now** box at the top of the Schedule tab says what the lights are
doing: following the schedule, or something set by hand. Tap **Run the
schedule** to hand the lights back to your schedule right away. It's the
same idea as leaving manual mode in the Trimlight Edge app so its timer runs
again. It:

- ends anything set by hand: a pattern you chose, **Off**, brightness or
  speed changes, a music show started with the Music button, and a security
  flash;
- sends what the schedule says right now to the controller again, in full.
  Use it after changing the lights in the **Trimlight Edge app**, because this
  app can't see changes made there.

Show nights you set up on the Music tab are part of the schedule, so they keep
running. Without the button, anything set by hand still ends by itself at the
next scheduled change.

### Add a rule

1. Open the **Schedule** tab and tap **Add a rule**.
2. **Name:** for example "Christmas season".
3. **When in the year:**
   - **All year**, or
   - **Only between** two dates, for example Nov 27 and Jan 6. A range can
     cross New Year.
4. **Days of the week:** untick days to skip them, for example weekends only.
5. **Turn on at** and **Turn off at.** Pick one of:
   - **Sunset** or **Sunrise**, with optional minutes, for example **15**
     for 15 minutes after, or **−30** for 30 minutes before.
   - **Dusk:** about 30 minutes after sunset, when it really looks dark.
   - **Dawn:** about 30 minutes before sunrise.
   - **A set time**, for example 11:00 PM.

   If the off time is earlier than the on time, it means the next morning.
   For example, on at Sunset and off at Sunrise keeps the lights on all night,
   using the next morning's real sunrise. A rule never runs longer than 20
   hours, so a 6:00 AM → Sunrise rule simply skips the days when the sun is
   already up by 6:00 AM.
6. **Pattern:** choose one. To use several, tap **Add a pattern to rotate**
   and add more. Then choose:
   - **Switch every … minutes** (the same time for each), or
   - **Its own time for each pattern:** a playlist. A minutes box appears next
     to each pattern, for example Christmas 10, Snowfall 5, Warm white 15. They
     play in order, then start again. (In a settings file: `rotate_each = [10,
     5, 15]`, one number per pattern.) Or
   - **A different one each night, in this order.** The first night of the
     rule's date range gets the first pattern, the next night the second, and
     so on, repeating.
7. **Use its own brightness** (optional): for example, dim late-night lights.
8. **When rules overlap, this one is:**
   - **Holiday (200):** beats everyday rules. This is automatic for rules with
     dates.
   - **Everyday (100):** the normal choice for all-year rules.
   - **Low (90):** only runs when nothing else is on.
   - **Custom:** any number. Higher wins.
9. Tap **Save**.

**Coming up** on the right shows what will run, two ways:
- **Month** (what it opens to): a calendar. Each rule has its own color, so
  seasons, game nights and gaps stand out. Use **‹ ›** to change month (up to
  two years ahead) and tap a day for its exact times.
- **List:** the next three weeks, with on and off times. Daylight saving
  changes are marked.

If a rule shows **"Never runs in the next year"**, another rule wins on every
one of its nights, usually one with the same priority that is listed first.
The note names that rule and how to fix it, usually by raising this rule's
priority.

### Night curve: warmer and dimmer as the night goes on

A rule can change its whites and brightness through the night, for example
crisp 5000 K white at dusk, warm 2700 K from 9 PM, and a 15% glow after
midnight.

1. In the rule, tick **Night curve**.
2. Each row is a point: a time (21:00, 00:00, sunset or sunset + 30), a white
   (or the pattern's own colors) and a brightness. **Dusk to midnight glow**
   fills in the example above. Use 2 to 6 points.
3. Save.

Between points the lights change a little at every 10-minute mark (9:00,
9:10, ...), so a point at 9:00 PM is reached at 9:00 PM. Each change sends
the pattern again, which starts its motion over, so a **moving** pattern
changes every 30 minutes instead (9:00, 9:30, ...); a still one every 10. Times earlier than
the rule's start count as the next morning ("00:00" is midnight that night);
a point a little before the start (such as "sunset" for a rule starting at
sunset + 30) counts as the start.

- **Whites** (colors with little color in them) take the curve's white;
  other colors keep their color and only dim. Brightness works for every
  kind of pattern.
- A brightness you set by hand (Home's slider) wins until the next scheduled
  change.
- When a **weather** pattern takes over (snow, for example), it dims with the
  curve but keeps its own whites, so snow white stays snow white.
- A curve needs this app to change the lights, so those nights aren't handed
  to the controller's own timer. The **backup timer** copies the curve's
  opening look, so the lights still come on and go off on time if this
  computer is off.
- Home says where the curve is, for example "Night curve: 2700 K, 43%
  brightness".

### Several schedules a day

Like the Trimlight Edge app's timers, a day can have more than one rule, as
long as their times don't overlap. Each one runs in its own time. For
example:

- **Evening:** all year, Sunset → 11:00 PM.
- **Morning:** all year, 6:00 AM → Sunrise.

**Add a morning schedule** on the Schedule tab fills in the second one for
you (6:00 AM → Sunrise, with your everyday pattern); change anything before
tapping **Save**. Both show in **Coming up** and in **This week** on Home,
and the backup timer copies both to the controller.

In winter the morning rule runs from 6:00 AM until it gets light. Around
the summer, when the sun is up before 6:00 AM, it doesn't run at all.

Priority only matters where rules overlap. There, the higher priority wins
and the other rule runs in the time that's left: for example, an
everyday Sunset → 11:00 PM rule and a New Year's Eve 8:00 PM → 12:30 AM
holiday rule give everyday lights from sunset to 8:00 PM, then the holiday
pattern.

### Examples

| Goal | Settings |
|---|---|
| Every night | All year, every day, Sunset + 15 → 11:00 PM, Warm white, Everyday |
| Christmas season | Nov 27 – Jan 6, Sunset + 10 → 12:30 AM, Christmas and Candy cane rotating every 15 min, Holiday |
| All night on Christmas Eve and Day | Dec 24 – Dec 25, Sunset → Sunrise, Christmas, Holiday |
| Game days | All year, Sunday only, Dusk → 11:00 PM, team colors, custom priority 150 |
| A different look every night in December | Dec 1 – Dec 31, Sunset → 11:00 PM, five Christmas patterns, "A different one each night" |
| A holiday playlist | Dec 1 – Dec 31, Sunset → 11:00 PM, Christmas, Snowfall and Candy cane, "Its own time for each pattern": 10, 5 and 5 minutes |
| Dim accent until morning | All year, 11:00 PM → Sunrise, Warm white, own brightness 25%, Low |
| Morning lights on dark mornings | All year, weekdays, 6:00 AM → Sunrise, Warm white, Everyday (alongside an evening rule) |

### Bring over timers from the Trimlight app

Tap **Import from Trimlight app**, tick the timers you want, and tap
**Import**. They come across with their fixed clock times; edit them
afterward to switch to sunset-based times. The patterns they use are added
to My patterns automatically.

### Away mode

Going away? Choose the day you're **Back on** and how much to **Move times by**
(10 to 60 minutes), then tap **Turn on away mode**. Each night the lights then
come on and go off a little earlier or later than usual, so the house looks
lived in rather than on a timer.

- Every rule moves by the same amount on a given night, and the same night
  always moves by the same amount, so restarting the app never changes
  tonight's times.
- The Month calendar and Home show the real, shifted times, and the safety
  net copies them to the controller too.
- It ends by itself after the day you're back, or tap **Turn off (I'm back)**.

### Holidays that find their own dates

Instead of a dated rule for every holiday (and changing Thanksgiving's date
every year), pick holidays on the **Schedule** tab under **Holidays**. The app
works out each one's date every year, loads its playlist that morning and runs
it from the time you choose.

1. Tick **Use holiday lights**.
2. Choose a holiday in **Add a holiday…** and tap **Add**. It comes with one
   or two themed patterns (Harvest for Thanksgiving, Easter pastels, Diwali
   lamps and so on), added to your patterns for you to change.
3. Choose up to three patterns. With more than one, they take turns, each for
   **Each shows** minutes.
4. Change **On** and **Off** if you like (sunset to 11:00 PM to start;
   New Year's Eve runs to 12:30 AM).
5. **Days before** and **Days after** make it a season: Halloween with 6 days
   before is Halloween week; Christmas Day with 20 before and 12 after is a
   Christmas season.

| Kind | Holidays | How the date is found |
|---|---|---|
| Fixed | New Year's Day and Eve, Valentine's, St. Patrick's, Juneteenth, July 4, Halloween, Veterans Day, Christmas Eve and Day, Kwanzaa (7 nights) | The same date every year |
| By rule | MLK Day, Presidents' Day, Mother's Day, Memorial Day, Father's Day, Labor Day, Columbus / Indigenous Peoples' Day, Thanksgiving | "Fourth Thursday of November", "last Monday of May"… |
| From Easter | Mardi Gras, Good Friday, Easter | Calculated for any year |
| Hebrew calendar | Rosh Hashanah (2 nights), Hanukkah (8 nights) | Calculated exactly for any year; they begin at sundown, so the lights start the evening before |
| By the moon | Lunar New Year, Holi, Diwali, Eid al-Fitr, Eid al-Adha | Published dates built in through 2035 |

- **Moved dates.** Diwali and Holi are sometimes kept a day apart from India's
  date, and the two Eids depend on the new moon being seen, so they can be a
  day off where you live. **Move …’s date to** fixes it for that year.
- After 2035, the moon-set holidays need a newer EaveLuxOS (the panel says so
  ahead of time); the others never run out.
- **That morning** (from 6 AM), the event log and Home say "Today is
  Thanksgiving: tonight's lights are Harvest / Harvest glow, from 4:38 PM".
- **Priority.** Holidays (210) beat seasonal rules (a Christmas season at
  200) and the everyday schedule; a game night (250) beats a holiday. If a
  holiday turns off before the season rule does, the season runs the rest of
  the night.
- The Month calendar shows holiday nights, and the **backup timer** copies them
  to the controller like any rule.
- Turn **Use holiday lights** off to pause them without losing your picks.

#### Another country's public holidays

Under **Another country's public holidays**, choose a country (or **Other**
and its two-letter code) and a pattern. The official public holidays (for
example Canada Day and Boxing Day for Canada) come from the free
**Nager.Date** service, fetched from the app computer once a week and kept,
so the lights still run if it can't be reached. Only the country code is
sent. These share one pattern and rank just below the holidays you picked
(205). A newly chosen country is checked right away (and again within hours
if the service can't be reached); **Check now** works once a minute. Holidays kept only in one state or province aren't included.

### Birthdays and anniversaries (4.18)

**Schedule › Birthdays & anniversaries** keeps your own dates and shows
their lights every year without setting them up again.

1. Tap **Add a date**. Type a name (for example *Chris*, or *Our wedding*),
   choose whether it's a birthday, an anniversary or another date, and pick
   the month and day.
2. Optionally type the year: the list then says *turns 47* or *25th
   anniversary*, and nothing shows in the years before it.
3. Choose the patterns (up to 6, shown in turn for the minutes you choose;
   **↑** moves one earlier, **Preview** shows it on the lights for 15
   minutes), the times (like rules: sunset, sunset + 30, 18:00) and, if you
   like, up to 7 days before and after.

The list shows **Today** on the date itself and **Lights tonight** on the
days around it.

A date ranks 220: above holidays (210), so a birthday on Christmas gets its
own lights, and below game days (250). Home says *Today is Chris's
birthday* that morning, like a holiday (on the days around it, *Tonight: the
lights for Chris's birthday (in 2 days)*), and **Who wins tonight** lists it as
a birthday or anniversary. February 29 shows on February 28 in other years.
The tick box turns a date off without deleting it. Your dates stay on this
computer: they are never in a shared or exported settings file (an
encrypted backup keeps them).

### Game-time lights

Your team's colors while they play, instead of the usual pattern: from 15
minutes before each game until 15 minutes after it ends, set automatically
from ESPN's start times (4.28). Before 4.25 this was called **Game-day
lights**, and it lit the whole evening of every game day; that's still a
choice for each team.

> [!TIP]
> Videos: **Game-time lights** and **Celebrate scores** walk through each
> one, about a minute each.

1. Under **Game-time lights**, choose a team in **Add a team…** and tap
   **Add**. The Eagles, Phillies, 76ers and Flyers come with a team-color
   pattern made for you. For any other team, choose **Another team…**, pick
   the league, start typing the team's name and choose it from the list
   (4.24). It gets a pattern in its own colors, from ESPN. If the list can't
   be loaded, type ESPN's short team code instead (the letters in the team's
   address on espn.com, for example `nyg` for the Giants) or, for a college,
   its team number (the number in its espn.com address, for example `213`
   for Penn State).
2. Choose when, with **Lights on**:
   - **During the game** (every team unless you choose otherwise, 4.28):
     from a little before the start
     (**From**: 15 minutes before, to start) until a little after the final
     score (**until**: 15 minutes after the end). A day game lights up only
     once it's dark, and only if it's still on; tick **Day games too** to
     light it in daylight as well.
   - **All evening**: the **On** and **Off** times (sunset to 11:00 PM to
     start), every game day, as before 4.25. Since 4.28, teams added before
     4.25 use **During the game** too, unless you chose **All evening**.
3. Change the **Pattern** if you like.
4. Check that **Use game-time lights** is ticked (adding your first team
   ticks it, and only it). Nothing is checked while it's off (the panel says
   so). Within a minute the panel lists the next games, with their start
   times.

**Under Coming up (4.28).** Schedule › Coming up shows each game of a team
you follow, with game-time lights or score celebrations on: the Month view
marks the day with the sport (🏈, 🏒, 🏀, ⚾) and the start time; tap the
day, or use List, for "8:15 PM Eagles game · game-time lights · celebrate
scores". With game-time lights on, the lights' own times show as well, as
"Eagles game time (8:00 PM)", in a color of their own.

| League | In the list as |
|---|---|
| NFL, MLB, NBA, NHL, WNBA (4.24) | the pro leagues |
| College football (4.24) | NCAA football (FBS and FCS) |
| College basketball (4.24) | NCAA men's basketball, NCAA women's basketball |
| College ice hockey (4.24) | NCAA men's hockey, NCAA women's hockey |

**How it knows when the game is on (4.25).** The start time comes from
ESPN's schedule. The end comes from ESPN's live scoreboard, followed during
the game whether or not score celebrations are on: the lights end the
chosen minutes after the final score. If the score can't be followed (ESPN
can't be reached), they end when the longest game of that sport usually
would (4 hours for the NFL and MLB, 4¼ for college football, 3 for the NBA,
2¾ for the WNBA and college basketball, 3¼ for hockey). A game whose start
time ESPN hasn't set yet gets no lights until it has one. In an MLB
doubleheader, the lights start with the first game and end with the first
final score.

**When it talks to ESPN.** Game dates come from ESPN's public schedule: about
a minute after the app starts or game-time lights are turned on (or a team is
added), then every 6 hours, and right away after you change the time zone.
**Check now** asks at once. Each time it asks for the regular season and the
playoffs by name (not the preseason). Live scores are a separate, much more
frequent check, only on game days (see Score celebrations below). It's free
and needs no account, but isn't an official service, so it could change.

- Postponed and canceled games light up nothing.
- A game starting after midnight (a late West Coast game) counts for the
  evening before; one whose time ESPN hasn't set yet, for ESPN's own date.
- If ESPN can't be reached, or answers with no games at all, the dates
  already known are kept (the panel says so), and with none your normal
  schedule simply runs. A game night wins
over seasonal rules (priority 250), so an Eagles game in December shows Eagles
colors. Turn **Use game-time lights** off to pause it without losing the teams.

#### Score celebrations

Score celebrations have their **own switch** (since 4.3.5), separate from
**Use game-time lights**: use either one, both, or neither.

1. Tick **Celebrate scores** at the top of the panel.
2. Under each team you want, tick **Celebrate this team's scores**.

When that team scores during a game, the lights flash its team colors
(moving fast) for a few seconds, then go back to whatever was on: the game
game's colors, or your normal schedule when game-time lights are off. The
team still needs to be on the list (for its colors and its schedule); its On
and Off times only matter for game-time lights. Settings from before 4.3.5,
when one switch ran both, keep working as they were.

- **Celebrate for** sets the length (10 to 60 seconds; 15 to start).
- **Only while the lights are on** (on to start) skips daytime games, so the
  lights don't come on at 1 PM for a touchdown. A celebration never
  interrupts a music show, a security flash or a **weather alert** that's
  showing (a High Wind Warning, say). A skipped celebration is listed under
  **Activity** on Home with the reason, such as "Flyers scored! skipped: the
  High Wind Warning alert is showing." To let celebrations through, use
  **Home › Dismiss weather alert** (section 14).
- If the team can't be found on ESPN's scoreboard on a game day, the panel
  says so: check the team code. For an MLB doubleheader, the game being played
  is followed. A game that runs past midnight is followed until it ends (until
  4 AM at the latest), and a score ESPN takes back after a review and then
  restores isn't celebrated twice.
- What counts as a score: NFL and college football field goals and
  touchdowns (not the extra point), every MLB run and every NHL or college
  hockey goal, and NBA, WNBA and college basketball 3-pointers (ordinary
  baskets are too frequent).
- College scoreboards on ESPN show only ranked games unless asked for a
  division, so EaveLuxOS asks for Division I (football: FBS, then FCS if the
  team isn't there). Smaller divisions may not be listed live.
- The panel shows the live score during the game.

#### A sound when they score (4.9)

A team with celebrations on can also play a sound, such as a goal horn or a
fight song, through the speakers of the computer EaveLuxOS runs on.

1. Under the team, **Sound when they score** › choose an **MP3** or **WAV**
   file you have (up to 15 MB). It's kept in this app's data folder on that
   computer, not in the settings, so a settings backup or share doesn't
   carry it.
2. **Start at** (seconds into the file) and **Play for** (1 to 30 seconds;
   20 to start) choose the part that plays.
3. **Listen here** plays that part in the browser you're using. **Play on the
   app computer** plays it through that computer's speakers, to check the
   volume.

**Play the sound** turns it off and on without losing the file; **Remove
sound** deletes the file. The sound plays with the light celebration, so
**Only while the lights are on** applies to it too. A second score while
it's playing starts it again. EaveLuxOS doesn't come with any team's sounds,
and it can't take them from Spotify or a website: use a file you have.

On Windows it plays through Windows' own media player, on a Mac through
`afplay`. On Linux it needs `paplay`, `aplay`, `mpg123` or `ffplay`; without
one, the lights celebrate without sound.

Live scores come from ESPN's public scoreboard, asked only on your team's game
days: every 20 seconds during the game, less often before it, and not at all
afterward. ESPN's feed runs some seconds behind live TV, and each change
passes through Trimlight's cloud, so **the lights celebrate shortly after you
see the score on TV**, not at the same moment. Starting the app in the middle
of a game doesn't celebrate the score so far, and a final score is never
celebrated.

**Lights for a win (4.21).** For each team, **When they win, show** a
pattern for 15 minutes to 4 hours after a game they win; then the schedule
takes over again (and the lights still turn off at the schedule's next
change). It works without score celebrations. **Only while the lights are
on** applies to it too. If the winning goal's celebration is still flashing
at the final horn, the win lights come right after it; a weather warning, a
music show, a paused schedule or the security flash keeps them off.

**A team's own celebration length (4.21).** With celebrations on, each
team can have **Its own celebration length** (10 seconds to 2 minutes);
otherwise it uses the length for every team. **Make it an automation**
keeps it.

### How overlapping rules are decided

From highest to lowest:

1. **A flash**: the security flash, an alert from a webhook, or a score
   celebration.
2. **A severe weather alert** (section 14), while the lights are on, or at
   any time if it's set to turn them on. Never during a music show.
3. **A music show** (section 15).
4. **Something you turned on or off by hand** (until the next scheduled change).
5. **A weather rule** (section 14).
6. **The scheduled rule with the highest priority.** Game days are 250,
   dated rules 200 and everyday rules 100 unless you change them. If two have
   the same priority, the one listed first wins. This only decides
   overlapping time: rules at different times of day (morning and evening)
   each run.

With two or more controllers, each controller goes down this list on its
own (4.8). A rule with **Controllers** set to some of them (below) only
counts for those, and a choice made on one controller's Home card only for
that one.

### A schedule for each controller

With two or more controllers, a rule has **Controllers** (4.8): untick the
ones it isn't for. All ticked (the usual) means every controller, including
one added later. Each controller follows the rules that are for it, by the
usual priorities, so for example:

- **Everyday**, sunset to 11:00 PM, all controllers, and **Deck early**,
  sunset to 9:00 PM, Deck only, priority 200: the Front runs to 11:00, and
  the Deck switches to *Deck early*'s pattern and goes off at 9:00.
- Two rules at the same time, one for the Deck and one for the Front, each
  with its own pattern and brightness.

In the rule list, a rule for some controllers says so (*Front only*).
**Coming up** on the Schedule tab has a controller choice: **All
controllers** lists each controller's nights, naming whose they are when
they differ; choosing one shows that controller's own month. Home's week
does the same.

How it's sent: when the controllers follow different rules, each one's
pattern goes out together the way **Split by controller** does, and a
controller whose own pattern didn't change isn't sent anything (its motion
doesn't restart, and it gets no extra commands). On those nights the app
runs both controllers itself rather than handing the night to the
controllers' own timers, as for a night curve. The backup timer copies each
controller's own nights to it.

### Fades between patterns (4.19)

**Schedule › Fades between patterns** blends the lights from the old colors
to the new ones when the schedule changes the pattern, instead of a jump:
a rotation, a holiday taking over at its time, a weather rule starting, a
night-curve step to warmer whites, and in and out when the schedule turns
the lights on and off.

1. Choose **2, 3, 5 or 8 seconds** (or **Off**).
2. **Try it** fades from what's showing to the pattern you choose, which
   then shows for 15 minutes (as other Try buttons do).

Good to know:

- Fades go over the home network (**Setup › Local mode**, with commands on):
  a fade is a few still frames shown live, as the Trimlight app shows a
  pattern while you edit it. Nothing is saved on the controller, and the
  cloud never gets a fade; without the home network the change is simply
  sent at once.
- Only your own patterns fade. A built-in effect or a pattern saved on the
  controller has colors only the controller knows, so it changes at once.
- A pattern you choose, **Lights off**, a flash, a restore after a power cut
  and the first change after EaveLuxOS starts are never faded. A button
  pressed during a fade ends it at once.
- With several controllers, they fade one after another (a controller takes
  one command at a time), sharing the fade's length (at least a second each).
- The same colors sent again (for example a moving pattern's night-curve
  step) don't fade, so their motion isn't stopped.

### Who wins tonight (4.15)

**Schedule › Who wins tonight** lays out a night (noon to noon; pick any
date) for each controller: each stretch of time, the pattern it shows, the
rule, holiday or game day it comes from with its priority, what it beats and
why (lower priority, or the same priority but listed later), and which
weather rules could take over if their weather comes. Warnings point out
what's likely to surprise you: two things with the same priority at the
same time (the one listed first wins), a rule that never shows that night,
and weather that could replace a pattern. Automations that run at a time
that night, and ones that wait for an event (a score, a webhook), are listed
too; they come on top when they run.

## 14. Alerts

Everything on the **Alerts** tab: what changes the lights when something
happens (automations, who's home, the weather), the security flash, messages
to your phone, and webhooks for Home Assistant and other systems.

### Automations (When · If · Then)

An automation (4.11) says: **when** something happens, **if** everything you
list is true, **then** the lights do what you say, and afterward go back to
what they were showing. For example: *when the Flyers score, if it's dark,
flash orange and black for 20 seconds.*

1. On the **Alerts** tab, open **Automations** and tap **Add an automation**.
2. Give it a name.
3. **When** (what starts it), one of:
   - **A team scores**, **A game starts** or **A game ends** (a win, a loss
     or either). The team must be listed under **Schedule › Game-day
     lights**; **Any team** works too. The scoreboard follows the team even
     if its own score celebration is off.
   - **A weather warning starts** (any, or one whose name contains words
     you type, such as *tornado*). Needs **Severe weather alerts** on.
   - **A webhook event**, by name (see below).
   - **A time of day**, or **sunrise** or **sunset** with an offset
     (*sunset-30m*). It runs once a day.
   - **The schedule turns the lights on** (or **off**).
4. **If** (optional; all of them must be true):
   - **It's dark** (sunset to sunrise), **between** two times, **before** or
     **after** a time.
   - **On these days** of the week; **between two dates** (month-day, such
     as 12-01 to 01-06; it can wrap past New Year's).
   - **The lights are on** (or **off**); **a rule is running**; **a pattern
     is showing**.
   - For game events only: the team is **home** or **away**, **winning** or
     **losing**.
5. **Then** (up to four, done in order):
   - **Flash, then go back**: a pattern, a color, or a color on one zone,
     for 5 to 600 seconds. Afterward the lights go back to what they were
     showing.
   - **Show a pattern** for some minutes, or until the schedule changes.
   - **Turn off** for some minutes.
   - **Play a team's sound** (its score celebration sound, under Game-day
     lights).

   Each light action is for **all controllers** or one of them. A flash on
   one controller goes back to that controller's own choice afterward.
6. **Priority**, **Cooldown** and **Beats a manual choice**:
   - When two automations start together, the higher priority goes first,
     and a lower one that wants the same lights is skipped. While one is
     flashing, a lower-priority one doesn't cut in.
   - **Cooldown**: after it runs, it waits this many seconds before it can
     run again (30 by default), so a flurry of goals is one flash.
   - By default an automation leaves alone lights you set by hand (On, Off
     or a pattern chosen on Home). Tick **Beats a manual choice** to let it
     run anyway; a flash still goes back to your choice afterward.
7. **Save**. The sentence under the form says what it will do.

Each automation in the list has:

- **Try it now**: does the **Then** part right away, whatever the **If**
  says, so you can see it. It doesn't start the cooldown.
- **Check it now**: shows each condition with ✓ or ✗ as of now.
- The tick box turns it off without deleting it.
- **Lately** lists what automations did or why they were skipped
  ("skipped: not it's dark"). The same lines are in Activity.

Safety rules that always apply:

- A severe **weather warning** stays on top: while one is showing, an
  automation that changes the lights is skipped (one that only plays a
  sound still runs).
- A **music show** isn't interrupted unless **Beats a manual choice** is on.
- Automations use the same paths as the app's buttons, with the same
  limits; nothing is written to the Trimlight cloud's patterns or timers.

**Webhook events.** A camera, doorbell or Home Assistant can start an
automation by name:

```
POST /api/hook/event
{"name": "doorbell"}
```

with the webhook address and token from **Alerts › Webhooks** (*Webhooks and
Home Assistant*, below).
Names are 1 to 40 letters, numbers, spaces, - or _, and upper and lower case
are the same. The answer lists what each automation did.

**Make it an automation.** Under **Schedule › Game-time lights**, each team
with a score celebration has **Make it an automation**. It creates the same
celebration as an automation (when the team scores, if the lights are on
(unless the celebration was set to flash in daylight too),
flash its pattern for the same seconds, and play its sound if it has one),
and turns the old celebration off so it doesn't flash twice. Then add
conditions, such as **It's dark**, or change it. Score celebrations you
don't convert keep working as before.

### Who's home: arriving and leaving (4.18)

Automations can start when someone comes home or leaves, and can check
whether anyone is home. EaveLuxOS doesn't track phones: each phone tells it,
with a webhook, when its owner arrives or leaves. Only *home* or *away* and
the time are kept (in `presence.json`); no location is sent or stored.

1. Under **Alerts › Who's home**, add the people who live here (up to 12).
2. Turn on webhooks (*Webhooks and Home Assistant*, below) and set up each
   phone:
   - **iPhone, Shortcuts:** **Automation › New Automation › Wi-Fi**, choose
     your home network, **When Joining** and **Run Immediately**. (Not
     **Arrive**: it runs down the street, before the phone is back on your
     Wi-Fi, so it can't reach the app.) Add **Get Contents of URL** with
     `https://APP-COMPUTER-ADDRESS:8787/api/hook/presence`; under **Show
     More**: Method **POST**, header **X-Token** with the webhook token
     (the panel has a **Copy token** button), Request Body **JSON** with
     `person` (the name as on the list) and `state` = `home`. Make a second
     automation with **Leave** (your home, **Run Immediately**) and
     `state` = `away`.
   - **Home Assistant** (iPhone or Android, with the companion app): a
     `rest_command` and an automation on the person's state; the panel shows
     both, ready to copy.
3. **Mark home** / **Mark away** on the panel sets someone by hand (and runs
   the automations, like the phone would). So do **I'm home** / **I'm away**
   on the phone's **Set up this phone** page.

Home shows who's home under the state line (*Who's home: Chris · away:
Ann*), for Editors and Administrators.

**A phone at the edge of the Wi-Fi** can go home, away, home within a
minute. After someone's change, the next one within **2 minutes** (set it
on the panel, 0 to 30; 0 never ignores) is only noted: Who's home stays
right and Home › Activity says "arrived home again within 2 min: noted, no
automations", but no automation runs, so the welcome flash doesn't repeat.
Marking someone by hand is never ignored.

When you leave, the phone is no longer on your home Wi-Fi, so it can only
reach the app over a VPN (section 19, *Away from home*). Without one, use
Home Assistant for leaving: it runs at home.

In the automation builder:

- **When › Someone arrives home**: anyone or one person; tick **only when
  nobody else was home** for the first one back.
- **When › Someone leaves home**: anyone or one person; tick **only when
  nobody is left home** for the last one out.
- **If › Someone is home** / **Nobody is home**.

"Nobody is home" and "everyone has left" count only once every person's
phone has said so: someone the app hasn't heard from yet may well be home.
A phone saying the same thing twice runs nothing.

With seven automations or more, the list is in groups by what starts them:
People, Games, Weather, Cameras, sensors and buttons (webhooks), Times and
the schedule.

### Templates and motion lights (4.18)

**Start from a template** (next to **Add an automation**) fills in a
ready-made automation to change and save:

| Template | When | If | Then |
|---|---|---|---|
| Motion lights | webhook event `motion` | it's dark | white in the first zone for 60 s |
| Welcome home | the first one arrives | it's dark | a warm flash for 2 minutes |
| Motion while nobody's home | webhook event `motion` | nobody is home, it's dark | red for 30 s (highest priority, beats a manual choice) |
| Doorbell | webhook event `doorbell` | | blue for 20 s |
| Everyone left | the last one leaves | 11 PM to sunrise | off for 8 hours |

A camera (Frigate, Blue Iris, UniFi Protect through Home Assistant) or a
motion sensor sends `POST /api/hook/event` with `{"name": "motion"}`. Use a
name per camera (`motion-driveway`, `motion-porch`) and an automation per
name to light a different zone for each; the cooldown keeps a busy camera
from flashing again and again. A paused schedule (section 13) runs no
automations that change the lights.

### Weather rules

Weather rules change the pattern based on current conditions, using the US
National Weather Service. They work in the United States only, and no
account is needed.

1. On the **Alerts** tab, open **Weather** and tick **On**.
2. Tap **Add a weather rule**.
3. Tick conditions:
   - **Snow** (also flurries, sleet and freezing rain)
   - **Rain**
   - **Thunderstorm**
   - **Fog**
   - **Windy**
   - **Cloudy**
   - **Clear**
   - **Freezing** (32°F or below)

   You can also set **Colder than** or **Warmer than** temperatures.
4. Choose the pattern, for example Snowfall.
5. Leave **Priority** at **150** so it replaces everyday lights but not
   holidays. Use **250** if it should replace holidays too.

Important points:

- Weather never turns the lights **on** by itself. It only changes the pattern
  while a rule already has them on.
- **Check with** chooses current conditions, the next-hour forecast, or either.
  Forecasts that only say "chance of" are ignored.
- If the weather service can't be reached for 2 hours, weather rules pause
  and your normal schedule continues.

### The weather on the lights (4.19)

**Add the weather looks** (Alerts › Weather, Administrators) adds ready-made
patterns and weather rules in one step, and turns weather rules on. Nothing
of yours is changed; a look whose name you already use is left out. Change
or delete them like your own.

| Weather | Look |
|---|---|
| Rain | blue drops falling (Comet) |
| Snow | white and ice-blue twinkles (Twinkle fade) |
| Thunderstorm | dark blue with white lightning flashes (Strobe) |
| Windy | teal and white waves, fast |
| Fog | soft grays breathing, dimmed |
| Any (the temperature) | **Temperature colors**: deep blue when it's freezing, cyan, green when it's mild, yellow, orange, red when it's hot |

The looks rank 150: above the everyday schedule, below holidays. Temperature
colors rank 140, so rain still shows rain. The color changes every 5 °F, not
with every reading; with fades on, it blends to the next. **Show the
temperature as a color instead of a pattern** in any weather rule does the
same with your own conditions or temperatures (for example only below
32 °F).

The controller's own **Lightning** and **Snowflake** effects (in the
Trimlight app's Pattern Library) aren't used yet: how they're set is still
being worked out from captures. These looks are EaveLuxOS's own patterns.

### Severe weather alerts

When the National Weather Service issues a **warning** for your location
(a tornado or winter storm warning, for example), the lights change to an
alert pattern until the warning ends. No account is needed; US only.

1. On the **Alerts** tab, open **Severe weather alerts** and tick **On**.
2. Tick the kinds of warnings: Tornado, Severe thunderstorm, Winter storm
   (blizzard or ice), Flash flood, Hurricane or tropical storm, Extreme heat or
   cold, High wind. Tornado and severe thunderstorm are ticked to start.
3. Choose the **Pattern**: **Severe weather (amber)** is ready-made, or use
   one of your own.
4. Tick **Turn the lights on for a warning** if the alert should also show in
   daytime or when the schedule has the lights off. Otherwise it only changes
   the pattern while the lights are on.

Points to know:

- Only warnings count, not watches or advisories, which are far more
  frequent.
- Warnings are checked every 5 minutes. When a warning ends (or is
  canceled), the lights go back to normal by themselves.
- **Home › Dismiss weather alert** puts the lights back for that warning, and
  it stays dismissed while the Weather Service updates or extends it (even
  after a restart). Turning the lights on or off by hand does the same. Once
  the warning is over, the next one shows again.
- If the weather service can't be reached for 2 hours, alerts stop applying,
  so a lost connection can't leave the amber lights on.
- An alert never interrupts a music show. A security flash or a webhook alert
  still wins over it while it runs.

### Security flash

The security flash is bright lights on demand for a few minutes. After that,
everything returns to normal, including turning the lights back off in
daylight.

1. On the **Alerts** tab, open **Security flash** and choose a pattern
   (Security white is included) and the minutes. Changes save as you make
   them.
2. Start it from **Home › Security flash**, or from a motion sensor through
   Home Assistant (*Webhooks and Home Assistant*, below).

Starting it again while it's running restarts the timer. **Stop flash** ends it.

Webhooks can also flash **other patterns, for a set number of seconds, on
part of the house** (*Webhooks and Home Assistant*, below), for example
green over the front porch when a package is detected. **Stop flash** ends those too.

### Phone alerts

Administrators can get a message on their phone when something needs
them:

- the lights can't be reached to turn on or off (after 10 minutes);
- a controller is offline (after 10 minutes), and again when it's back;
- Trimlight can't read a controller (code 12006);
- **EaveLuxOS was off** (4.27): the computer lost power, was shut down or
  restarted without **Quit**, for 5 minutes or more. While the computer is
  off nothing can be sent, so this one comes when it runs again, with the
  times it was off ("from about 8:41 PM to 10:24 PM"). It's also listed
  under **Activity** on Home. A **Quit** isn't reported;
- a new version is out.

To set it up:

1. Install the free **ntfy** app (App Store or Google Play). No account is
   needed.
2. In ntfy, tap **+** and subscribe to the topic shown in EaveLuxOS (tap
   **Copy**).
3. Tap **Send a test**, then tick **Send alerts** and the alerts you want.

Alerts only go out when something is wrong, so on a good week you get none.
**Sent lately** lists the last 20 messages, with ✓ when the ntfy server took
them (or why it didn't). **A ✓ but nothing on your phone?** Open the ntfy
app and look in the topic:

- **The message is in the topic, but no banner came:** on an iPhone, open
  the **Settings** app, then **Notifications**, then **ntfy**, and turn on **Allow Notifications**
  and **Banners**; check that a Focus mode isn't hiding it.
- **The message isn't in the topic:** in ntfy, delete the subscription and
  add the topic again (copy it from EaveLuxOS).
- On an iPhone, swiping ntfy away in the app switcher can stop its alerts
  until you open it again.

Each problem is sent once, then at most every 6 hours while it lasts, and a
message follows when it's back to normal. Anyone who knows the topic can
read the alerts, so the one EaveLuxOS picks is random; change it under
**Topic and server**, where you can also use your own ntfy server. The topic
is kept out of exports. Messages never include your address.

### Webhooks and Home Assistant

Webhooks let other systems control the lights. For example, a motion sensor
can start the security flash at night.

1. In **Alerts › Webhooks**, tick **Allow webhooks**.
2. Tap **Copy token** and keep it private.
3. Have the other system send a **POST** request to
   `http://APP-COMPUTER-ADDRESS:8787/api/hook/ACTION` with the header
   `X-Token: YOUR-TOKEN`. Services that can't set headers, such as IFTTT, can
   send `{"token": "YOUR-TOKEN"}` in a JSON body instead. A token in the web
   address (`?token=`) is refused, because addresses end up in logs and browser
   history.

| Action | What it does | Optional body |
|---|---|---|
| `flash` | Start the security flash, or an alert flash (below) | `{"minutes": 10}`, or `{"effect": "package", "zone": "Front porch", "seconds": 30}` |
| `stop_flash` | End the flash | |
| `on` | Show a pattern | `{"effect": "christmas"}` (the pattern's internal name) |
| `off` | Turn off | |
| `resume` | Return to schedule | `{"force": true}`: Run the schedule (also ends a security flash and sends the lights again) |
| `levels` | Brightness or speed | `{"brightness": 120}` (0–255) |
| `music` | Start a music show (section 15) | `{"minutes": 60}`; `0` until stopped |
| `stop_music` | End the music show | |
| `dismiss_alert` | Put the lights back for the severe weather alert showing now (*Severe weather alerts*, above) | |
| `presence` | Someone arrived or left (*Who's home*, above) | `{"person": "Chris", "state": "home"}` or `"away"` |
| `status` | Change nothing; report what the lights are doing (also with **GET**) | |

Every action replies with what the lights are doing then: on or off, the
pattern and its internal name, why (`schedule`, `manual`, `weather`, `alert`,
`flash`, `music`), brightness, speed, and the list of your patterns. `status` changes
nothing, so another system can ask as often as it likes (it isn't written to
the activity list).

#### Siri, Alexa and Google (4.18)

**Siri:** in the Shortcuts app, make a shortcut with one action, **Get
Contents of URL** (Method POST, header **X-Token** with the webhook token,
and a JSON body if the action takes one), and name it what you'll say, for
example *Holiday lights on*. "Hey Siri, holiday lights on" then runs it, also
from the Lock Screen, CarPlay or an Apple Watch. **Alerts › Webhooks ›
Siri, Alexa and Google** lists the addresses: lights on with a pattern, off,
back to the schedule, the security flash, and an automation by name.

**Alexa and Google Assistant** go through Home Assistant: add the
`rest_command` shown on that panel, make a Home Assistant script for each
phrase, and expose the scripts to Alexa or Google in Home Assistant's voice
assistant settings (Home Assistant Cloud, or its Alexa and Google
integrations).

#### Alerts: a pattern, a length and a zone

`flash` with a body shows any pattern for a while, then everything goes back
to normal (including off in daylight):

| Field | What it means |
|---|---|
| `effect` | One of your patterns (its name or internal name), or a ready-made **alert pattern**: `package` (green), `alarm` (red strobe), `doorbell` (blue and white), `delivery` (cyan), `severe` (amber), `security` (bright white) |
| `color` | Instead of `effect`: one plain color, like `"#00FF00"` |
| `zone` | Optional: a zone from the House tab, like `"Front porch"`. Only those bulbs light; the rest stay dark |
| `seconds` | 5 to 14400. Leave it out for 30 seconds (or use `minutes`) |
| `label` | Optional: what Home and the activity list call it, like `"Package at the door"` |

A flash started while another runs replaces it. **Alerts › Webhooks › Try
an alert** lets you test a pattern and zone from the app.

**Zones** are made on the House tab: select a range of bulbs with the bulb
finder and save it as a zone (section 12). Trimlight's cloud has no command
for lighting only part of the house, so a zone flash is a pattern with every
bulb outside the zone switched off (the Trimlight app's "X"), and the alert's
colors spread over the zone. That works for patterns made of colors (custom
patterns and the alert patterns), not built-in effects or patterns saved only
in the Trimlight app. A pattern has 30 color slots, and dark stretches of
more than 90 bulbs use extra slots, so a pattern with many colors may not fit a
small zone in a long run; the reply says so. With **more than one controller**,
every controller gets the same zone pattern, counted against the longest
controller's bulbs, so a zone is most reliable on a single controller.

**When two things happen at once**, the more important one wins: the security
flash and urgent alerts (`alarm`, `security`, or `"urgent": true`) first, then
a severe weather warning, then other alerts, then score celebrations. A less
important flash is skipped (the reply says `"flash_started": false`), and a
shorter one that interrupts a longer one (a package during a doorbell) hands
back to it when it ends. During a music show, only urgent alerts show, and
they end the show, because a pattern knocks the controller out of music mode
and this app can't switch it back on.

Examples for Home Assistant (`configuration.yaml`):

```yaml
rest_command:
  lights_package:
    url: "http://192.168.1.20:8787/api/hook/flash"
    method: POST
    headers:
      X-Token: !secret trimlight_webhook_token
    content_type: "application/json"
    payload: '{"effect": "package", "zone": "Front porch", "seconds": 30, "label": "Package at the door"}'
  lights_alarm:
    url: "http://192.168.1.20:8787/api/hook/flash"
    method: POST
    headers:
      X-Token: !secret trimlight_webhook_token
    content_type: "application/json"
    payload: '{"effect": "alarm", "minutes": 10, "label": "Alarm"}'
```

For **Frigate**, trigger `rest_command.lights_package` from an automation on
Frigate's package (or person) detection in a front-door camera zone. For
**Blue Iris**, add an alert action of type **Web request or MQTT**: POST to the
same address, with the `X-Token` header and the JSON body above. Each alert
reaches the lights in about a second (through Trimlight's cloud).

#### Home Assistant: the ready-made package

The app comes with `tools/home-assistant/eaveluxos.yaml`, a Home Assistant
*package* that adds the house lights as a light with brightness and your
patterns as effects, a sensor for the pattern showing now, and scripts for
the security flash and Return to schedule. Its `README.md` explains the four
steps. With Home Assistant's **HomeKit Bridge**, the light then appears in
Apple Home too (on, off and brightness).

#### Home Assistant: a single action

For just one action, in `configuration.yaml`:

```yaml
rest_command:
  lights_security_flash:
    url: "http://192.168.1.20:8787/api/hook/flash"
    method: POST
    headers:
      X-Token: !secret trimlight_webhook_token
```

Then create an automation that is triggered by your motion sensor, with the
condition "Sun: below horizon" and the action **Call service ›
rest_command.lights_security_flash**.

If you reach the app by a name (for example `lights.home.example`) rather than
an IP address, and requests are refused with "Unknown host name", run this
once in the app folder on the app computer:

```
python3 main.py allow-host lights.home.example
```

To undo it, add `--remove`. For safety, this list can only be changed on the
app computer, not from the app's screens.

## 15. Music shows

The Music tab has three parts: **Music show** (the controller's own music
mode, below), **Music from this computer** (this app runs music mode itself,
no phone needed; version 4.1, experimental) and **Mood follow** (this app
listens and switches patterns). Both are described at the end of this
section.

The Trimlight controller can make the lights dance to music on its own: it
listens to sound and moves the pattern with the beat. That **music mode** is
switched on in the Trimlight Edge app, and only over your home Wi-Fi.
Trimlight's cloud, which this app uses, has no music controls.

What this app adds is a way to **step aside** during a show. Normally, if the
Trimlight app changes the lights, this app notices within a few minutes and
puts the schedule back, and the next scheduled change would cut the show off.
During a music show this app sends nothing to the controller: no patterns, no
checks, no timer copies.

### Start a show

1. On the **Music** tab, choose **How long** (or **Until I stop it**) and tap
   **Start a music show**. Home and the status pill now say *Music show*.
2. On a phone on your **home Wi-Fi**, open the **Trimlight Edge** app, choose
   your controller and tap **Music**.
3. Choose where the sound comes from:
   - **Auxiliary IN**: a player plugged into the port on top of the
     controller. This is the best choice: there's no delay, other sounds don't
     affect it, and you can put the phone away.
   - **Microphone**: the phone listens. Keep it close to a speaker; voices and
     traffic affect the lights too.
   - **Player**: MP3 files stored on the phone. Streaming apps (Spotify, Apple
     Music, Pandora, Amazon Music) don't work here.
4. Pick a music pattern and set **Music Sensitivity**, then start the music.
5. When you're done, tap **Stop the show** on the Music tab, or let it end on
   its own. The scheduled pattern comes back within a few seconds.

Choosing a pattern, **Return to schedule** or a security flash ends or
interrupts the show. The flash still wins, because it's for security; after a
flash the controller shows the flash pattern, so start music mode again in the
Trimlight app if the show should go on. Brightness and speed are set in the
Trimlight app during a show.

### Show nights

For shows you plan, like Fridays and Saturdays in December, add a **show
night** on the Music tab. It has the same dates, days of the week and start
and end times (sunset, dusk or a set time) as a schedule rule. Between those
times this app steps aside by itself, so a show you start in the Trimlight app
isn't switched back to the schedule. **Stop the show**, or choosing a
pattern, during a show night ends it for that night only. **Back to the
schedule** brings it back, because a show night is part of the schedule.

A show night doesn't start the music by itself: start music mode in the
Trimlight app (or leave the controller on Auxiliary IN with the player ready).

### Play the music from a computer

A computer that's on anyway, such as the one running this app, makes a good
show player:

1. Run an auxiliary (aux) audio cable from the computer's headphone or line
   output to the aux port on top of the controller. Check the port on your
   controller for the plug size before you buy the cable, and choose an
   outdoor-rated cable for any run outside.
2. To hear the music too, send the same sound to your speakers: a headphone
   splitter, or a speaker system with a line output, feeds both.
3. Start with the computer's volume around half and adjust **Music
   Sensitivity** in the Trimlight app until the beat shows clearly.
4. Make a playlist for the show, start the show here, select **Auxiliary IN**
   in the Trimlight app, then press play.

### From Home Assistant or a webhook

The webhook actions `music` and `stop_music` start and stop a show (section
14, *Webhooks and Home Assistant*).
`music` takes an optional `{"minutes": 60}`; `{"minutes": 0}` means until
stopped, and with no body it uses the usual length set on the Music tab.

### Limits

- **Music show** doesn't switch music mode on or off; that takes the Trimlight
  app on your home Wi-Fi, or **Music from this computer** below.
- During a show, the backup timer isn't updated and the controllers aren't
  checked. Both resume when the show ends.
- The beat-matching is the controller's own. Trimlight's cloud is far too slow
  (a quarter to a full second per command) to drive the lights in time with
  music from here.

### Music from this computer (experimental)

New in version 4.1. This app runs the controller's music mode itself, the way
the Trimlight app does from a phone: the app computer listens, works out how
loud the music is in 16 bands from bass to treble, and sends that to the
controller about 9 times a second over your **home network**. The controller
moves its music pattern to the beat. No phone, and nothing goes through
Trimlight's cloud.

**Set it up once (Administrator).**

1. Find the controller's address on your home network. The Trimlight Edge
   app shows it when it opens (for example `192.168.1.50`), and your
   router's device list shows it too. In the router, reserve that address
   for the controller so it doesn't change.
2. On the **Music** tab, under **Music from this computer**, enter it and tap
   **Save**. **Find** asks the network for controllers; if one answers, its
   address is filled in.
3. Tap **Test connection**. "The controller answered" means it works.
   **Test connection** only says hello. **Read the controller** also sets the
   controller's clock and lists the patterns and timers it holds, as the
   Trimlight app does every time it opens.

The app computer and the controller must be on the same home network (the
same router, or devices the router can reach directly).

**Run a show.**

1. On the app computer itself, open EaveLuxOS at **http://localhost:8787**.
   As with mood follow, a browser only lets a page listen on the computer it
   runs on.
2. Choose **Listen to**:
   - **Default microphone or line-in**, or a particular one from the list.
     A microphone near the speakers works; a cable from a player into the
     computer's line-in is better (only the music, no room noise).
   - **Music playing in a browser tab**: play the music in another tab
     (YouTube, Spotify's web player). When you start, the browser asks what
     to share: pick that tab and keep **Also share tab audio** on (it is by
     default). Only the sound is used; the picture is dropped right away.
     No delay and no room noise. This needs **Microsoft Edge** (built into
     Windows) or **Chrome**: Firefox and browsers built on it, such as
     LibreWolf, can't share sound. (**Entire screen** with **Also share
     system audio** works too where Edge or Chrome offers it, but that
     switch doesn't appear on every computer.)
   - **Stereo Mix**: everything the computer plays, including the Spotify
     app. Many Windows sound cards have it, turned off: open **Sound
     settings › More sound settings › Recording**, right-click the list ›
     **Show disabled devices**, right-click **Stereo Mix** › **Enable**. It
     then shows under **Listen to** (allow the microphone once so the browser
     lists its name). It works in any browser, LibreWolf and Firefox
     included. No sound card Stereo Mix? The free VB-Audio Virtual Cable does
     the same.
3. Choose a **Music pattern**: the controller's 18 built-in music effects,
   by name and in the Trimlight app's order (see the list below). For a
   **Single Color** pattern, also choose its **Color**. Then **How long**
   and **Sensitivity** (1 to 14, as in the Trimlight app). **Input level** makes quiet or loud sound fit better; the bars show
   what's sent, and a good level keeps most of them moving without all of
   them hitting the top.
4. Tap **Start the show**. The bars move with the music and so do the lights.
   Music pattern and Sensitivity can be changed while it runs.
5. Tap **Stop**. The app sends the scheduled pattern again, which ends
   music mode on the controller.

While it runs, this app steps aside like any music show (no patterns, checks
or timer copies). Keep the page open; a background tab is fine. The show ends
by itself, and the schedule comes back, when you stop it, when you choose a
pattern or **Stop the show** above, when **How long** is up, when the page
closes or stops sending sound for 20 seconds, or when the connection to the
controller is lost: it tries again first, and only counts it lost when the
controller hasn't answered at all for 15 seconds. A slow answer on busy Wi-Fi
never holds up the music, and anything the controller sends that this app
doesn't understand is skipped (and noted once in the log). Only one page runs it at a time,
and mood follow can't run at the same time.

**The music patterns** are built into the controller, so they're the same as
in the Trimlight app:

| # | Pattern | # | Pattern |
|---|---|---|---|
| 1 | Full Color Rhythm Spectrum | 10 | Single Color Ejection Forward |
| 2 | Single Color Rhythm Spectrum | 11 | Full Color Ejection Backward |
| 3 | Full Color Rhythm Twinkle | 12 | Single Color Ejection Backward |
| 4 | Single Color Rhythm Twinkle | 13 | Full Color VuMeter |
| 5 | Gradient Energy | 14 | Single Color VuMeter |
| 6 | Single Color Energy | 15 | Independence Day (red, white, blue) |
| 7 | Gradient Pulse | 16 | Christmas (red, green) |
| 8 | Single Color Pulse | 17 | HeatBeat |
| 9 | Full Color Ejection Forward | 18 | Party |

The seven **Single Color** patterns move in the color you choose (red until
you change it); it can be changed while the show runs. The others have their
own colors. For Christmas colors, choose **16. Christmas**, or a Single Color
pattern in red or green.

**What's sent.** Only the 16 loudness numbers, the music pattern, its color and the
sensitivity; the sound itself never leaves the browser and isn't recorded.

**Why "experimental".** Trimlight doesn't publish these local messages. They
were worked out from a capture of the Trimlight app (firmware 1.17.77) with
the kit in `tools/music-capture`. A firmware update could change them; if
**Test connection** stops working after one, a new capture shows what
changed. How many music patterns there are isn't known yet, so the list goes
to 20; a number past the last one does whatever the controller does with it.

### Mood follow (beta)

Mood follow listens to the music through the **app computer's microphone**
and switches between three of your patterns as it gets calmer or livelier,
about every 10 seconds. It follows the mood, not the beat (for the beat, use
the controller's own music mode above).

1. On the **Music** tab, choose a pattern for **Calm**, **Lively** and
   **Party** music.
2. On the app computer itself, open EaveLuxOS at **http://localhost:8787**.
   A browser only lets a web page use the microphone on the computer it runs
   on, so a phone can't do this over your Wi-Fi.
3. Tap **Start listening** and allow the microphone. Play music near that
   computer.
4. Tap **Stop** to go back to the schedule.

Keep that page open while it runs; it keeps working when the page is in a
background tab or behind another window. After 30 seconds of quiet the
lights return to the schedule; when the page closes, right away (or within
3 minutes if the computer went to sleep). Only one page listens at a time:
a second one says mood follow is already listening elsewhere. The sound is measured in the browser and never recorded or sent
anywhere; only "calm", "lively" or "party" is sent to the app.

Mood follow ranks below everything you or the house decided:

- A **weather alert** stays on top while music plays, and isn't dismissed.
- A **music show** (the controller's music mode) keeps running.
- A pattern you **choose by hand** wins: mood follow waits ("waiting: a
  pattern chosen by hand is on") and takes over again when yours ends, for
  example when you tap **Run the schedule**. Stopping mood follow, or 30
  seconds of quiet, ends only mood follow's own pattern, never yours.
- A flash still wins over everything, as always.

### Music sync 2.0: zones that follow the music (4.13)

**Music from this computer** can now drive your **zones** itself instead of
the controller's music patterns: each zone follows the **bass**, the
**mids**, the **treble** or **the beat**, in its own color. Under **The
lights follow**, choose **My zones (bass, mids, treble, beat)**.

**How it works.** The app listens as before, and works out from the sound
(a frequency analysis, 50 to 60 times a second):

- **Bass** (30-250 Hz), **mids** (250-4,000 Hz) and **treble** (4-14 kHz),
  each with an automatic level, so quiet and loud songs both use the full
  range. The three bars show them.
- **Beats**: sudden rises in the low end (kicks and bass notes). The dot
  flashes with each one.
- **Tempo (BPM)**, from how regularly the beats come, once it has heard a
  few seconds of them. "(unsure)" means the music doesn't have a steady
  beat.

Then it draws each moment as a pattern and shows it on the controller live,
the way the Trimlight app previews a pattern while you edit it. Nothing is
saved on the controller.

**Set it up once.**

1. Save zones on the **House** tab (section 12). Each controller uses its
   own zones and its own number of bulbs.
2. The controller needs its address on your home network (**Setup › Local
   mode**).
3. On the **Music** tab, choose **My zones**, tick the controller, and tap
   **Speed test**. For about ten seconds the lights shimmer between two dim
   warm whites while the app sends frames faster and faster (2, 4, 6 and 8 a
   second) and checks the controller keeps up. The result, for example
   "4 frames a second", is the most a show will ever use on it. A show
   can't start on a controller until it has passed.
4. For each zone, choose what it **follows** (Bass, Mids, Treble, The beat,
   or Nothing), how it **shows** (**Glow**: the whole zone brightens with
   it; **Meter**: it fills along the zone, from its first bulb, or its last
   if the zone runs the other way), and its color. **Everything else** is
   the color for bulbs outside these zones (black is dark). Choices save as
   you make them.

A controller takes at most 30 color blocks at a time. A glow uses one
block, a meter two; if your choices could need more, the page says so.

**Safety.** Only the newest frame is sent, never faster than the speed test
allowed and only when something visible changed. The app checks every
second that the controller answers. If its answers come late twice in a
row, the show slows down a step (and can speed up again later); if it stops
answering for six seconds, the show ends and the schedule's pattern comes
back. Stop, the end of **How long**, or closing the page do the same.

### Sound delay and music files (4.13)

The lights trail the music a little: the time it takes to reach the
controller. **Sound delay** holds back what you hear by the same amount, so
sound and lights land together. It works with:

- **Music playing in a browser tab**: the tab goes quiet and this page plays
  its sound, held back (Microsoft Edge or Chrome).
- **A music file on this computer**: choose **Listen to › A music file on
  this computer**, then pick one or more of your own MP3, WAV or M4A files.
  They play here, one after another, held back by the delay. **Pause /
  play** and **Next file** are under the meters. Nothing is uploaded.

A microphone, line-in or Stereo Mix is heard in the room as it plays, so
its sound can't be held back.

To set it: the page suggests a value during a show ("Suggested from this
show"). With zones, tap **Sync test**: a click every second, and every zone
flashes white with it. Move **Sound delay** until the flashes land on the
clicks. The delay is remembered in this browser.

**With the controller's music patterns** (the original way), the analysis,
the meters and Sound delay work the same; set Sound delay by ear.

## 16. Backup timer (safety net)

### After a restart or a power cut (4.15)

- **The app restarts** (an update, the computer restarted): what you chose
  by hand (On, Off, a pattern, for every controller or one), the slider
  levels, a running security flash and a music show started from the
  button or a webhook all come back, unless the schedule moved on meanwhile
  (the same rule as always: a choice made by hand lasts until the next
  scheduled change). Activity says what came back. Previews of unsaved
  patterns and shows from this computer's Music page don't come back.
- **Right after a restart** the app doesn't send the lights again when it
  sent them less than 30 minutes earlier (no restarting motion, no extra
  commands). It reads the controllers at once instead, and sends again at
  the first difference.
- **A controller loses power:** while Trimlight's cloud says it's offline,
  the app looks every minute instead of every five. As soon as it's back
  online, its lights are set again, whatever it came back showing.
- **A short power cut** (over before the next check, 4.16.6): a controller
  that restarts reports its state to Trimlight's cloud again. When that
  report changes twice in a row while the app isn't sending anything, the
  lights are set again, usually within 6 to 10 minutes. Seen on Nov 21,
  2026: unplugged for 77 seconds, the controller came back in its own
  **Timer** mode and later showed its own pattern.
- **Not a change (4.28.2):** Trimlight's cloud hears about a pattern sent over
  the home network late, and describes it its own way. That report is no
  longer taken for a change from outside, so the lights aren't sent again
  about 7 minutes after every change, and while the lights are off only on
  and off are checked. Another saved pattern, another animation, the lights
  off or in **Timer** mode still are. When the app does send them again, the
  log (**eaveluxos.log**) says what the cloud reported before and after.

(Called the **safety net** before version 4.0.)

Normally, the app computer runs your lights. If it's off, unplugged or offline,
nothing turns the lights on or off. The **backup timer** fixes that by also
copying the next few nights into the controller's **own timers**.

### Turn it on

1. Open **Setup › Lights & controller** and open **Backup timer**.
2. Tick **On** and choose how many nights to copy (3 to 14; 7 is a good
   choice).
   The app asks you to confirm first and says what it will and won't do.
3. After about two minutes (it waits until the controller is settled) it
   says **Armed: 7 nights copied to the controller**.

**One timer per day.** Trimlight's calendar takes one timer per date, so
when a day has more than one stretch (a morning and an evening rule), the
backup timer copies one: stretches with the same pattern become one from the
first on to the last off; otherwise the longest is copied, and the others are
listed under **Not copied**.

**Save each night's pattern on the controller first.** Since version 4.2.1
the backup timer never saves patterns. Each night uses a pattern that is
already saved on the controller (in the Trimlight Edge app) with the **same
name** as the pattern here, such as "Warm white" (capitals don't matter).
A night whose pattern isn't saved there is skipped and listed under **Not
copied**. The controller's own pattern plays with its own brightness and
speed.

### What it does

- Each day, and whenever you change the schedule, it writes one controller
  calendar entry for each time the lights come on (two a day if you have a
  morning and an evening rule). Each entry has its pattern and on/off times.
- Each entry points at the controller's own saved pattern of the same name.
  It never saves, changes or deletes patterns. (Before 4.2.1 it saved copies
  named "Auto …". On Nov 15, 2026 such a save through Trimlight's cloud left
  a controller unreadable, code 12006, and resetting the controller then
  lost its saved patterns. Turning the backup timer off removes any "Auto"
  copies an older version left.)
- **On a normal night, the controller runs the lights itself** from its copy,
  in **Timer** mode. It turns them on at the planned time and off at the end,
  even if this computer stops in the middle of the evening.
- The app steps in (Manual mode) whenever something needs it: a manual change,
  weather, the security flash, sliders or minute-by-minute rotation. After
  that, it keeps control for the rest of that night.
- Between scheduled windows the controller rests in **Timer** mode instead of
  Off. If you turn the lights off by hand, it goes to real **Off**.

### How it stays safe

- **Backup first:** before every change, the controller's full state is saved
  in `data/controller-backups` (the last 20 are kept). Use the **Download the
  controller backup** link to get the latest one.
- **Only its own timers:** it only writes calendar timers, and only creates,
  changes or deletes the ones it made. Patterns, and timers from the
  Trimlight app, are left alone.
- **Only when settled:** before writing it reads the controller twice, at
  least two minutes apart, and writes only if nothing changed in between
  (patterns, calendar, daily timers). Someone using the Trimlight app, or a
  controller just plugged back in, makes it wait.
- **Never next to a music show:** no writes while a music show runs (from
  the button, a show night or **Music from this computer**), while the local
  link is being tested, or for 15 minutes after.
- **Read back, and stop:** after writing, it reads the controller back and
  checks every entry. If anything differs, or if Trimlight's cloud can't read
  the controller (code 12006), it removes what it wrote and **stops itself**:
  the panel shows **Stopped itself** with the reason, and it writes nothing
  more until you untick **On** and tick it again. Your lights keep running
  from the app as usual.
- **Changed underneath it:** if a timer it wrote is changed or removed, or
  the pattern number a night uses now holds a different pattern (a reset
  numbers patterns afresh), it stops relying on the copy and writes it again
  once the controller is settled.

### Warnings you might see

- **"The Trimlight app's daily timers are on":** in Timer mode those would
  run too and turn the lights on when your schedule says off, so the copy is
  written but **not used** (it shows **Not armed**, and the controller rests
  in Off) until they're off. Tap **Turn them off**; the controller is backed
  up first.
- **"The controller already has calendar timers from the Trimlight app on the
  coming nights":** the controller won't accept a second set of timers on the
  same nights, and in Timer mode both would run. So nothing is written, and
  any "Auto" items from earlier are taken back. Those Trimlight timers already
  run the lights without this computer. To use the backup timer instead, delete
  them in the Trimlight Edge app (if you imported them, your schedule here
  keeps them), then tap **Update now**. Timers on other dates don't matter.
  It checks again the next day or when you change the schedule, not every
  few minutes.
- **"Not copied: nights showing …":** the controller has no saved pattern
  with that name. Save one under the same name in the Trimlight Edge app (or
  choose a saved pattern for that rule), then tap **Update now**.
- **"Checking that the controller is settled":** it's waiting for two
  matching readings; nothing to do.
- **"Stopped itself":** see above. Open the Trimlight Edge app on your home
  Wi-Fi so it syncs the controller, check your patterns and timers there,
  then untick **On** and tick it again.
- **"Trimlight can't read its copy of this controller" (code 12006):** see
  Troubleshooting (section 23).

### Limits

- On its own, the controller runs the planned on/off times and the night's
  pattern. Weather rules, minute-by-minute rotation, slider changes and
  anything after midnight need the app. A night that runs past midnight is
  covered until 11:59 PM.
- If the app stops on a night it took over (after a manual change, weather or
  the flash), the lights stay on until it comes back, because that night the
  controller is in Manual mode. On normal nights this can't happen.
- To remove it, untick **On**. The app deletes its entries (and any "Auto"
  patterns an older version saved) from the controller.
- The controller's calendar entries have a month and day but **no year**. If
  you stop using this app for good, untick **On** first (with the app still
  running and online). Otherwise the last nights it copied stay on the
  controller and come on again on the same dates every year while the
  controller is in Timer mode. To clean up later, delete the entries in the
  Trimlight app's calendar, or start this app again and untick **On**.

## 17. Setup › Lights & controller

### Start the controllers together (4.21)

With two or more controllers, a moving pattern starts when each one gets it,
so the motion on the garage and on the house can be out of step. **Start
them together** (Home, under the controllers) restarts every controller's
pattern at the same moment over the home network: all connections are
opened first, then the patterns go out back to back. It needs Local mode
commands on, and two or more controllers showing EaveLuxOS's patterns.

### Controller health (4.15)

**Setup › Controller health** shows, for each controller: online or offline
and its firmware (from Trimlight's cloud); how many requests this app sent
it today and how many worked, its typical answer time, and how many worked
this week; a bar for each of the last 14 days (failed ones in red); the last
problem and when; and its answer time on your home network. **Check now**
asks the cloud again, reads each controller and greets it on your home
network. Kept in the data folder (`health.json`).

Since 4.9.2, **Color correction**, **Local mode** and **Pattern backups** are
sections of their own in Setup's row of buttons, next to **Lights &
controller**, rather than folded panels at the bottom of it. They work as
before; Local mode and Pattern backups are for Administrators. The parts of
this section about them apply there.

These settings are stored **on the controller itself**. They match the
controller's Settings screen in the Trimlight Edge app.

### More than one controller

If your Trimlight account has several controllers (for example *House* and
*Deck*), the top of Setup › Lights & controller shows a card for each one, like the
Devices list in the Trimlight Edge app. Each card shows:

- the controller's name, and whether it's **Online** (green dot) or **Offline**;
- what its lights are doing: **On**, **Off** or **On its own timer**;
- how many bulbs it has;
- **Not run by this app**, if it isn't ticked under **Controlled by this app**.

Tap a card to show that controller's ports, name, LED chip and color order
below; the heading shows its name. Saving changes only that controller. If you
changed something and didn't save it yet, the app asks before switching.

The cards don't show IP addresses: Trimlight's cloud doesn't report them. The
Trimlight Edge app finds those itself on your home network.

**Controlled by this app**, at the bottom of the tab, picks which controllers
the schedule, Home's buttons and music shows run. Ticking a controller off
leaves it to the Trimlight Edge app; you can still change its settings here.

#### A different pattern on each controller

A controller runs **one pattern at a time**: one motion, one speed and one
brightness for all of its bulbs. That's the controller, not this app. So parts
of the house can only move independently, for example a slow warm twinkle on
the second story while the garage stays solid white, when they're on
**different controllers**.

With two or more controllers, open **Patterns › My patterns › Split by
controller**, name it, and choose a pattern (or ✕ Off) for each controller. A
split pattern works anywhere a pattern does: Turn on, rules, rotations, game
days and the backup timer (each controller gets its own part on its own timer).
A controller the split doesn't name, such as one added later, shows the first
pattern that's on. A rule's (or the slider's) **brightness** dims or brightens
every part by the same ratio, so the second story stays dimmer than the
garage; a rule's **speed** is ignored, because each part keeps its own.
Editing a split keeps the parts of controllers the app isn't running right
now. Split patterns can't be saved in the Trimlight app; save
each part instead.

### Ports and bulbs

- **Simple mode:** enter how many bulbs are on each port, in order along the
  roofline. Use **0** for a port with nothing plugged in. The app numbers the
  bulbs end to end.
- **Advanced mode:** enter the first and last bulb number for each port, or
  tick **Not connected**. Ports may **overlap**, which makes them show the
  same part of the pattern (mirroring). For example, Port 2 = 84–138 and
  Port 3 = 100–138.

**Not connected ports.** Since 4.3, when the controller's home-network
address is set (**Local mode**, below), ports are saved over the home network,
where a port marked Not connected is really **switched off** on the
controller and keeps its numbers. Without the address they go through
Trimlight's cloud, which has no off: it refuses a port without bulb numbers
(code 12000, "Invalid parameter [port -> start]"), so a port marked Not
connected keeps the numbers the controller already holds. Either way this app
leaves it out of the bulb count, the bulb finder and the house tools. A controller reports a port that
was never set up as **bulbs 1–600**; if yours shows that on ports with nothing
plugged in, Setup › Lights & controller suggests marking them Not connected, so the app
counts your real bulbs (for example 138) instead of 600. If a port really
does run bulbs 1–600, tap **It's really connected** in that note and it
won't ask again; a port you give other numbers on Setup › Lights & controller never gets
the note. To keep a port that
*is* connected dark, use ✕ (zone off) in the pattern instead.

**Port numbers (version 4.0.3).** Some controllers (Trimlight Edge firmware
1.17.77) report their ports as 1–4 but the cloud takes them numbered 0–3
when saving, and refused the save with code 12000, "Invalid parameter
[port -> id]". A refused save changes nothing, so the app now tries the
other numbering once, remembers what worked, and reads the controller back
to check each port landed where it should. If it says a port isn't showing
as set yet, wait a minute and open Setup › Lights & controller again.

The bar diagram shows the layout. Tap **Save to controller**, then confirm.
The lights may flicker briefly.

The app opens in the mode that matches your current layout. Switching an
overlapping layout to Simple asks first, because Simple mode lays the ports
end to end.

### Controller

- **Name:** the name shown in both apps.
- **LED chip:** Trimlight's guide says the standard chip is **UCS1903**. Only
  change this if your installer says to; the wrong value makes the lights
  misbehave until it's set back.
- **Color order:** Trimlight's guide says this should almost always be **RGB**.
  If colors look wrong, tap **Test colors › Red**. If the house shows green or
  blue, change the color order and test again until Red, Green and Blue all
  match. Then tap **Return to schedule** on Home.
- If a dealer or installer set up your system, check with them before changing
  ports, chip type or color order.

### Local mode (home network)

**Find and match my controllers (4.15).** Under **Setup › Local mode**,
**Find and match** asks the network for controllers, reads each one that
answers (its ports and patterns), and matches it to your controllers by the
ports Trimlight's cloud has for them: "This is **Front** (its ports match)".
**Use for Front** (or **Use all matches**) saves the addresses. If nothing
answers, or one is missing, **Look harder** knocks on the controllers' port
(8586) at each address of the app computer's own home network (nothing else
is sent, and never outside your network), then reads what it found.

(Version 4.3, Administrators.) The app reads and changes the controller
straight over your home network, the way the Trimlight Edge app does when it
shows **Local**: saved patterns, and ports. **Nothing about patterns goes
through Trimlight's cloud any more.** Saving and deleting patterns there left
the cloud's copy of a controller unreadable (code 12006) three times in
November 2026, and deletes by number while that copy was out of step removed
the owner's own patterns.

1. Open **Setup › Local mode**.
2. Enter the controller's address on your home network (the Trimlight Edge
   app shows it when you open the controller on your home Wi-Fi), or tap
   **Find it**, then **Save**. With one controller, it's the same address
   **Music from this computer** uses.

**Two or more controllers** (4.5). Each controller on the Trimlight account
gets its own row and its own address, however many there are; a controller
added to the account later shows up with an empty row.

- Tap **Find controllers** to list every controller answering on your home
  network. **Which is this?** shows what one holds (its ports and first
  pattern names), so you can tell them apart; choose the controller and tap
  **Use for this controller**. Or type each address and tap **Save**.
- Before saving an address, the app reads the controller there and compares
  its ports with what Trimlight's cloud says that controller has. If they
  differ, or the cloud can't be read to tell, it asks first: that is
  usually another controller's address. The same check runs before
  **Ports and bulbs** changes a controller's ports (4.5.1): if the router
  ever gives two controllers each other's addresses, nothing is changed and
  the app says to update the address.
- An address saved before 4.5 isn't taken to be either controller's until
  you tap which one it is, at the top of the panel. (Before 4.5 there was one
  address, and everything done over the home network went to that one
  controller, even with another chosen.)
- **Controller to read** chooses which one the list below shows; **Delete**
  and **Back up now** act on that one. Pattern backups put patterns back on
  the controller the backup came from. **Also save it on the controllers**
  in the pattern designer saves on each controller this app runs that has an
  address, and names any that don't. **Ports and bulbs** saves each controller's
  ports to its own address, and **Send on/off and saved patterns over the
  home network** sends each controller's commands to its own address (one
  without an address, or not answering, uses the cloud; the others carry
  on).
3. The panel lists the ports and every pattern saved on the controller, with
   its number and colors, read from the controller itself, and the
   controller's own two **daily timers** (the Trimlight app's: on or off,
   times, repeat and pattern; 4.6, shown only, so change them in the
   Trimlight app). This app's schedule doesn't use them.
4. **Send on/off and saved patterns over the home network** (4.4, marked
   *Try it*): the schedule then turns the lights on and off, and shows
   patterns saved on the controller, straight over your home network instead
   of through Trimlight's cloud, which is quicker and keeps working when the
   cloud has trouble. The checkbox sits right under the address, and is
   there even when the controller can't be read just then. If the controller
   doesn't answer there, the app uses the cloud as before and tries again
   every 5 minutes; the log says so once, then once an hour, and says when
   it works again.
   This app's own patterns go this way too. When one saved on the
   controller looks exactly the same (same colors and bulb counts, motion,
   speed and brightness), that one is shown by its number (4.4.2; the
   controller is read first, so the right number is shown). Any other
   pattern of your own colors, and the built-in effects, are shown live, the
   way the Trimlight app shows a pattern while you edit it (4.6): like
   Trimlight's cloud preview, that isn't saved on the controller. The
   **Brightness and speed** sliders on Home go the same way. Only a built-in
   effect with a length other than 30, or a pattern over 30 colors or 255
   bulbs in one color, still goes through the cloud. Nothing is sent this
   way during a music show from this computer. When Trimlight's cloud
   disagrees about whether the lights are on, the app asks the controller
   itself (4.5.1: only then, so the controller isn't read all night).
   While a saved pattern was sent this way, the app can't yet tell if someone
   changed the pattern with the Trimlight app (on/off is still checked and
   put back).
5. **Back up now** saves those patterns and ports on this computer (in the
   controller-backups folder, listed under Pattern backups) and downloads a
   copy. Do it before changing patterns in the Trimlight app, too.

What goes over the home network:

- **Pattern backups › Put back selected** (below).
- **Also save it on the controller** when you save a pattern of your own
  colors.
- **Delete** in the Local mode list. A pattern is deleted only if its number
  still holds the pattern of that name; otherwise nothing is deleted and you
  are asked to read the controller again.
- **Ports** saved on this page.
- **Effect** (4.22): Lightning or Snowflake on a saved pattern (below).

**Lightning and Snowflake (4.22).** Each pattern in the list has an
**Effect** choice: None, Lightning or Snowflake. See [Lightning and
Snowflake](#lightning-and-snowflake-422) in section 10 for how they work and
when they play.

How it stays safe: the controller is read first and that is kept as a backup
(listed under Pattern backups). Changes go one at a time; the controller
doesn't answer a change, so after each one it is read back and checked: the
change is there exactly as sent, nothing else changed, and no two patterns
share a number. At the first difference it stops before the next change and
tells you what was done. Afterward the app asks the controller to send
Trimlight's cloud a fresh copy.

Limits: built-in effects (the 180) can't be written this way yet, only
patterns of your own colors. Names on the controller can be at most 25
characters. One change runs at a time. It works with one controller. The name, LED chip
and color order still go through the cloud (they don't touch patterns). A
port's on/off switch isn't in what the controller sends back, so that one
part can't be checked (nor the numbers of a port switched off). Stop **Music from this computer** first; it uses the
same connection.

**Slots that aren't patterns (4.9.1).** A controller can send slots numbered
0 or past 60, usually without a name or with garbled letters, after its real
patterns. They aren't patterns, so the list leaves them out and says how many
there were; nothing in this app deletes, copies or shows one. Before 4.9.1
they were listed with a **Delete** button: don't use it on them in an older
version.

### Pattern backups

Before every change it makes, the backup timer (section 16) saves a backup of
the controller, including every pattern saved in the Trimlight app. Local
mode saves one before each change too. The first
one, from before EaveLuxOS ever changed the controller, is kept forever. After
a factory reset, or after deleting a pattern by mistake, you can put patterns
back from these backups (Administrators only):

To take one yourself, tap **Back up now** under the list (4.16.6; also in
Local mode). Close the Trimlight app on phones and tablets first: the
controller answers one connection at a time.

1. Open **Setup › Pattern backups**. With two or more controllers, choose the
   **Controller** at the top. Then choose a **Backup** (newest first).
2. Tick the patterns to put back. Ones already on the controller (by name)
   are marked and can't be ticked.
3. Tap **Put back selected**.

It only adds: nothing on the controller is changed or deleted. Since 4.3 it
works **over your home network** (Local mode, above; set the controller's
address there first), never through Trimlight's cloud. It backs up the
controller first and puts patterns back **one at a time**, reading the
controller back after each and stopping at the first difference. A pattern
gets **its old number** when that's free, so timers made in the Trimlight app
that use it find it again. Built-in effects in a backup are listed as not put
back. The controller's library holds 60 patterns.

### Color correction (gamma)

Colors picked on a screen often look pale or washed out on LEDs. A soft
orange can come out nearly yellow, and pastel colors look almost white.
Screens apply a *gamma curve* to brightness and LEDs don't, so in-between
values look much brighter on the house than on the screen. Gamma correction
(the same math used by apps such as Gamma Correct for Windows or Gamma
Corrector for iPhone and iPad) adjusts each color before it's sent, so the
house looks closer to what you picked.

1. Open **Setup › Color correction**.
2. Tick **Correct colors for the lights (gamma)**.
3. Set **Gamma**. **2.2** is a good start. If colors still look pale, try up to
   **2.8**. **1.0** means no change.
4. To compare, pick a color under **Try a color**. The panel shows the color
   as picked and the color that will be sent to the lights, with hex and RGB
   values. Tap **Show as picked**, then **Show corrected**, to see both on the
   house. The schedule comes back by itself after 15 minutes.
5. Tap **Save color correction**.

What it applies to:

- Patterns you make in this app, everywhere they're used: the schedule,
  **Try on my lights**, the backup timer, and patterns you add to the Trimlight
  app's library.
- **Not** built-in effects, patterns that point to a pattern saved in the
  Trimlight app, or patterns imported from the Trimlight app. Those colors
  were already tuned on the lights, so they're sent exactly as they are.
- Screens in this app (swatches, previews) always show the colors as you
  picked them.
- A color channel that's on never drops to 0, so very dim colors keep their
  hue.

Turning it on changes how your existing patterns look on the house, usually
richer and less pale. To keep one pattern exactly as it is, open it in
**Create** and tick **Exact colors**. Only an Administrator can change color
correction.

## 18. Setup › Location & time

- **The clock** shows the app computer's time, which your schedule uses. The
  computer keeps it correct over the internet. If your phone and the computer
  disagree by more than 2 minutes, a warning appears; fix the computer's date
  and time settings.
- **Location:** search for your town, or enter latitude and longitude. Then tap
  **Save**.
- **Time zone:** usually filled in by the town search.
- **Daylight saving time:**
  - **Automatic (recommended)** follows the official rules for your time zone
    and shows the date of the next change. Arizona and Hawaii are handled
    correctly here.
  - **Always daylight saving time** keeps the clock one hour ahead of standard
    time all year.
  - **Always standard time** never moves the clock forward in spring.
- **Sun today:** dawn, sunrise, sunset and dusk for your location.
- **Controller clock:** the app sends the time to your controllers every day.
  - **Send the time now** does it immediately.
  - **Use this time on the controllers** sets the controllers to a time you
    choose. It's kept as a fixed difference from the real time, so it stays
    set. **Use the real time** undoes it. This only affects the controllers'
    own clocks, not this app's schedule. Most people never need it.

## 19. Setup › Accounts & access, and App

These were the **Settings** tab before 4.0. **Accounts & access** has the
Trimlight account, your account, accounts for other people and phones;
**App** has sharing and backup, updates, lights usage, the app address, start
automatically, AI pattern ideas, version history and Setup and about.
**Webhooks** and **Phone alerts** are on the **Alerts** tab.

- **Trimlight account:** change your Client ID or Client Secret. Leave the
  secret box empty to keep the saved one. **Test and save** checks them with
  Trimlight before saving.
- **Your account** (on a signed-in phone or computer): change your password
  (this signs you out on your other devices) or sign out of this device.
- **Accounts** (Administrators): everyone who uses the app gets their own
  account with one of three roles:

  | Role | Can |
  |---|---|
  | **Administrator** | Everything, including accounts, the Trimlight connection, location, controllers, webhooks and the app address. |
  | **Editor** | Create and change patterns, schedules and the house map, turn the lights on and off, run the bulb finder and import patterns ("Add to mine"). |
  | **Viewer** | Look at everything except credentials and tokens. No changes and no light controls. |

  **Add an account** with a user name, role and password. **Edit** changes
  the name, role or password, or disables the account; **Delete account**
  removes it. Any change signs that account out everywhere. At least one
  active Administrator always remains, so the app refuses to demote, disable
  or delete the last one. Other options:
  - **Stay signed in while unused for:** 1 hour to 7 days (8 hours by
    default). Every sign-in also ends 7 days after it began.
  - **Sign out all devices**, for example after losing a phone.
  - **Require signing in on this computer too.** Normally the app computer
    itself doesn't need to sign in. Turn this on if other people or programs
    use that computer. If you forget a password, run
    `python3 main.py reset-password NAME` in the app folder (`--admin` also
    makes that account an Administrator). `python3 main.py users` lists the
    accounts.
- **Phones and other computers:** the address to use on your home Wi-Fi.
- **Share and back up:** export or import patterns and schedules (section 20).
- **App address:** shows the port the app uses (8787 unless you change it).
  To change it, type a port from 1024 to 65535, such as 8790, and tap
  **Restart on new port**. The app checks the port is free, moves there in a
  few seconds, and reopens the page on the new address. Then update bookmarks
  and Home Screen icons on your phones. On a computer without a screen, run
  `python3 main.py port 8790` in the app folder and restart the app.
- **Start automatically:** see section 7.
- **Webhooks:** on the **Alerts** tab now; see section 14, *Webhooks and Home Assistant*.
- **Lights usage:** hours the lights were on each month, for the last 12
  months. Under **Estimate the cost**, enter your system's watts (on the power
  supply's label; that's its maximum, so the estimate errs high) and your
  price per kWh from your electric bill. Only time the app was running counts.
  **Estimated from your patterns** (4.21) works the draw out from what the
  lights actually show: now (while they're on), the next 30 nights on the
  schedule in hours, kWh and (with a price) dollars, and your five
  brightest patterns. Under **How it's estimated**, enter your number of
  bulbs (filled in from the House tab's count if you set one) and the watts
  of one bulb at full white (0.3 W to start; from your lights'
  specifications). A bulb draws about in proportion to how brightly its red,
  green and blue are lit, so full white draws the most, one deep color about
  a third, a dark bulb almost nothing; a built-in effect counts as half of
  white, and the controller adds about 3 W. Weather, flashes and choices made
  by hand aren't known ahead.
- **Updates:** see section 21.
- **Phone alerts:** on the **Alerts** tab; see section 14, *Phone alerts*.
- **Version history:** every save is kept, up to the last 100. Tap
  **Restore** to go back to the patterns, schedule and house map from that
  moment. Your account, phones and app address stay as they are. The restore
  is itself saved as a new version, so you can switch back.
- **Run the setup assistant again** repeats setup at any time. Your patterns
  and rules are kept.
- **Quit the app** (also the **Quit** button at the top of every screen):
  stops the app. This is on the app computer only. The lights stay as they
  are, and the schedule stops until you start the app again. If **Start
  automatically** is on, the app also starts by itself at your next login; on
  Linux and macOS, quitting stops the login service properly so it isn't
  restarted right away. In Docker, stop the container with
  `docker compose stop` instead.

### Local-first and security (4.17)

**API tokens** (Accounts & access, Administrators). Give each program that
controls the lights (Home Assistant, a script) its own token instead of a
person's password:

1. Open **API tokens › Make a token**, say who uses it, what it can do
   (**Viewer**, **Editor** or **Administrator**) and how long it lasts.
2. Copy the token (it starts with `elx_`) at once: it's shown only once.
   Only a fingerprint of it is kept.
3. The program sends it with each request as the header
   `Authorization: Bearer elx_...`.

A token never manages accounts or tokens, never changes the Trimlight
connection, never installs updates or quits the app, and never sees the
account's secrets, whatever its role. **Revoke** stops it at once. Each
token shows when and from where it was last used. Making one from a phone
asks for your password again. Webhooks keep their own link (section 14, *Webhooks and Home Assistant*).

**Audit log** (Accounts & access, Administrators): who changed what and
from where, for a year. It lists people by account, API tokens, webhooks and
automations. Only changes are listed, not looking around; brightness and
speed sliders aren't listed each time they move. Refused attempts are
marked **refused**. **Search** finds words in it; **Download (CSV)** saves
it for a spreadsheet.

**Encrypted backup** (App, Administrators): everything needed to set
EaveLuxOS up again on another computer, locked with a passphrase of at least
10 characters. That's the settings, the Trimlight account details, the
accounts (with their passwords, still hashed) and, if you tick it, the house
photos (up to 60 MB). Keep the passphrase safe: a backup can't be opened
without it, by you or anyone else. To use it, open **Put a backup back**,
choose the file and type the passphrase. The settings are replaced (the
current ones stay in Version history); the app's own port stays. With the
accounts, everyone signs in again. A wrong passphrase, or a file that was
changed, is refused.

**Away from home** (4.27): use EaveLuxOS from anywhere, without opening it to
the internet. The panel walks you through **Tailscale** (free for personal
use), which connects this computer and your phone privately, encrypted, with
nothing to change on your router. Each step gets a ✓ when it's done:

1. **Install Tailscale on this computer** (tailscale.com/download) and sign in
   with a Google, Microsoft or Apple account.
2. **Connect it.** The panel shows this computer's Tailscale name, such as
   `minipc.tail1234.ts.net`.
3. **Point Tailscale at EaveLuxOS (once).** Copy the command the panel shows
   and run it in a Command Prompt (Windows) or Terminal (Mac, Linux), for
   example:
   ```
   tailscale serve --bg https+insecure://127.0.0.1:8787
   ```
   This is **Tailscale Serve**: it gives this computer an
   `https://NAME.ts.net` address with a real certificate (no certificate to
   install on phones) and passes requests on to the app. It keeps running
   after restarts. If Tailscale asks you to turn on HTTPS for your tailnet, open
   the link it prints, choose **Enable**, and run the command again.
4. **On your phone**, install Tailscale and sign in with the **same
   account**. Then open the address the panel shows (or scan its QR code),
   sign in, and use **Add to Home Screen**. It works at home too.

Tap **Check again** after each step. Requests through Tailscale are treated
as coming from away: they always need signing in, and changes ask for your
password again. **Your router's own VPN** (WireGuard on a Firewalla, UniFi or
ASUS router) works too: connect the phone to it, then use the usual home
address. **Never forward a port** on your router to EaveLuxOS. The **Safety
checklist** checks that everyone has a password and HTTPS is on at home.

**No internet**: with Local mode's **Send on/off and saved patterns over the
home network** on, the schedule keeps running when the internet (or
Trimlight's cloud) is down, even if EaveLuxOS starts during the outage: it
uses the controllers it listed last time. Home says so meanwhile. Weather,
scores and patterns not saved on the controller wait until the cloud is
back.

**When EaveLuxOS is quit, hand the lights to the controller's own timers**
(Setup › Local mode): on **Quit** (or Ctrl+C), each controller goes to its
own **Timer** mode (the Timer choice in the Trimlight Edge app's settings), so
its two daily timers run the lights until EaveLuxOS starts again. Set those
timers in the Trimlight Edge app (clock icon). This can't happen when the
computer loses power or shuts down suddenly. When EaveLuxOS starts again it
takes over as usual.

## 20. Share patterns with other owners

### A share code or QR code (one pattern, or a few)

1. On **Patterns › My patterns**, tap **Share** on a pattern, or **Share
   patterns** to pick up to 8 (as a playlist, each showing a few minutes).
2. A code starting with `ELX1:` appears, with a **QR code**. Tap **Copy the
   code** (or **Send…** on a phone) and paste it into a text, email or post,
   or let someone scan the QR code.

**To use a code someone sent you:** **Patterns › Open a share code**, paste it
(the rest of their message can come along) and tap **Show the patterns**. Try
each on your lights, then **Add to my patterns**.

- **QR codes:** a phone's camera app reads the QR code and shows the code as
  text; copy it and paste it. In browsers that can read QR codes themselves
  (Chrome on Android, and on a Mac), **Open a share code** also has **Scan a
  QR code** (on the app computer, or a secure https address, where browsers
  allow the camera) and **QR code from a picture**.
- Anyone with an account can make a code, Viewers included; adding a code's
  patterns needs an Editor or Administrator.
- A code can be pasted with the rest of the message around it, even when a
  messaging app wrapped it onto several lines.
- A code holds only colors, motion, speed and brightness. Never your
  schedule, location, controllers or credentials.
- A code from someone else is checked on the app computer before you see it,
  exactly like a Community pattern: anything else in it is dropped, and a
  damaged or oversized code is refused.
- Patterns saved on your controller, patterns split by controller and
  patterns drawn bulb by bulb for your house can't go in a code (they only
  make sense on your lights); export a file instead.

### A file (everything)

**To share:**

1. Go to **Setup › App › Share and back up › Export patterns and schedule**.
2. A file named like `eaveluxos-patterns-2026-11-11.json` downloads. It
   contains your patterns, rules, weather rules and security flash settings.
   It **never** contains your Trimlight credentials, password, location,
   controller details, away mode (it would tell others when you're away) or
   usage settings.

**To use someone else's file:**

1. Go to **Setup › App › Share and back up › Import a file** and choose the file.
2. Choose one of:
   - **Add to mine:** adds patterns and rules whose names you don't already
     have.
   - **Replace mine:** replaces your patterns and schedule. Your location,
     controllers, away mode and usage settings are kept.

Export is also a good backup before big changes.

### The community library

**Patterns › Community** lists patterns other EaveLuxOS owners have shared.
Search by name, color or occasion, tap **Try** to see one on your lights (for
15 minutes), and **Add to my patterns** to keep it. Adding copies only that
pattern; it never changes your schedule or settings.

- Patterns are reviewed before they appear, and the app checks each one again
  before you can try or add it.
- Opening the list contacts GitHub, where the library is kept
  (`raw.githubusercontent.com`), from the app computer. Nothing about you or
  your lights is sent; the app only downloads the list. It isn't contacted
  unless you open **Community**.
- The list is kept for 15 minutes; **Refresh** fetches it again.
- Where the library is fetched from can only be changed by an Administrator,
  and only to an `https://` address. Importing a file never changes it, and
  the app doesn't follow a redirect to anywhere else.

**To share a pattern there (4.26):** the library is the public GitHub
repository `ThinkTank4n6/eaveluxos-patterns`, and patterns arrive as proposals
(pull requests) that are reviewed before they appear. You need a free GitHub
account.

1. In **Patterns › My patterns**, press **Share** on the pattern, then
   **Share to the community library…** at the bottom.
2. Check the **Name**, and add your name or handle (shown with it), a short
   **Description** and a few **Tags** (fall, autumn, orange…). Press **Next**.
3. Press **Open GitHub** and sign in. GitHub opens with the pattern's file
   already written for you.
4. Press **Commit changes…**, then **Propose changes**, then **Create pull
   request**. The library's automatic check runs on it.
5. Once it's reviewed and merged, it appears in **Patterns › Community** for
   everyone (within 15 minutes, or at once with **Refresh**).

Only the pattern goes in the file (its colors, bulbs, animation, speed and
brightness, under the name you give it); nothing about your home. EaveLuxOS
doesn't send anything itself: your browser opens GitHub, signed in as you.
Patterns saved only in the Trimlight app, drawn bulb by bulb or split by
controller can't be shared this way. If the library isn't on GitHub (an
Administrator changed its address), **Download the file** instead. (The
repository's starter kit is in this app's `tools/community-library` folder.)

### Share Studio shows and automations (4.21)

Share codes now carry more than patterns:

- **A Studio show:** **Share** in Studio. The other person opens the code
  (**Open a share code** in Patterns or Studio) and the show opens in their
  Studio, to play on their lights and approve. Only the looks and their
  minutes are in it.
- **An automation:** **Share** next to it under **Alerts › Automations**.
  The patterns it uses travel with it (only your own color patterns; one on
  your controller or drawn for your house can't). Nothing about your home
  does: a team becomes "any team", a person "anyone", a controller "all of
  them", a condition on one of your rules and a team's sound are left out,
  and a zone stays only if their house has one of that name. Opened, it
  shows what it does first; **Add it** adds its patterns to theirs and the
  automation **turned off**, to check and point at their own teams, people
  or zones before turning it on.

The **Community** list has **Studio shows** and **Automations** too
(**Everything / Patterns / Studio shows / Automations** at the top): **Open
in Studio** or **Add (turned off)**, checked exactly like a code pasted in.
In the library's repository, a show or an automation is an index entry with
`"kind": "show"` or `"kind": "automation"` and a file in `shows/` or
`automations/` holding its share code (`{"code": "ELX1:…"}`).

## 21. Update, move or uninstall

**Know when there's a new version**

Once a day the app computer asks GitHub which EaveLuxOS release is the
newest. When it's newer than yours, a green bar appears at the top of every
screen: **EaveLuxOS 3.x.x is available**. If you use a ready-made download,
it has a **Download** button for your computer's file. Either way there's a
**What's new** button for the release page. **Not now** hides the bar until
the next version comes out.

**Setup › App › Updates** shows the version you have, when it last checked and
the release notes, and has **Check now**. Administrators can turn the daily
check off there. Only the question "which version is newest?" goes to GitHub;
nothing about your home is sent.

**Install it from the app (4.15; Windows, and the Linux .tar.gz).** Under
**Setup › App › Updates**, an Administrator can tap **Install X now**:

1. The app downloads the release's file for this computer and the release's
   `SHA256SUMS.txt`, from GitHub only, and checks the file's SHA-256 against
   the list. A damaged or incomplete download is never used. (Both come from
   the same GitHub release, so this checks the download, not who made it.)
2. It keeps the version you have now beside the program (`EaveLuxOS.exe.previous`),
   puts the new one in its place, and restarts as the new version. The
   lights pause for a moment.
3. If the new version doesn't start, doesn't show its page, or doesn't keep
   answering for 20 seconds, the app puts the previous version back and
   starts it again by itself. **Updates** then says what happened.

**4.15.0 to 4.16.2 on Windows:** installing from the app could leave
EaveLuxOS answering `{"error": "not found"}` with no page (fixed in 4.16.3).
If that happened: in a Command Prompt, run `taskkill /IM EaveLuxOS.exe /F /T`,
then start EaveLuxOS.exe again (or unzip the new version over the folder).
The safest way from those versions to 4.16.3 is by hand, once (below);
installs from the app work from 4.16.3 on.

**Go back to X** puts the kept version back the same way. **Install new
versions by themselves, while the lights are off** (off unless you turn it
on) installs a new version during the day, when the schedule has the lights
off and no show or flash is running; a version that had to be rolled back
isn't tried again by itself. From a phone, these ask for your password
again.

A Mac app, the Linux package (.deb), a system service, and a copy run from
the source code update as before, below; **Updates** says which applies.

**Update to a new version**

1. Quit the app (**Quit** at the top, or **Setup › App › Quit the app**).
2. Unzip the new version.
3. **Windows:** nothing to copy. Your data stays in `%LOCALAPPDATA%\EaveLuxOS`
   for every version.
   **Mac and Linux from source:** copy the **data** folder from your old
   eaveluxos folder into the new one. It holds your database, photos and
   backups.
4. Start the new version with its launcher. On Windows, **Start
   automatically** switches to the new version by itself.

**First start of 3.7 or newer on Windows:** the app copies your settings
from the earlier version's `data` folder into `%LOCALAPPDATA%\EaveLuxOS` and
says where they came from. It looks next to itself and in sibling version
folders (for example `Downloads\eaveluxos-3.6.0\eaveluxos\data`) and uses the
most recently used one. The old folder isn't changed; delete it once
everything looks right. If it picked the wrong one, quit the app, delete
`%LOCALAPPDATA%\EaveLuxOS`, copy the right `data` folder next to the new
`main.py`, and start again.

**Portable (USB stick):** put an empty file named `portable.txt` next to
`main.py` or `EaveLuxOS.exe`; the app then keeps its data in `data` next to
itself on Windows too.

Versions before 3.0 kept settings in JSON files; 3.0 imports them into the
database on first start and keeps the old files, renamed
`….migrated-….json`.

**Move to a new computer:** install Python on the new computer, copy the
eaveluxos folder and your data folder (on Windows `%LOCALAPPDATA%\EaveLuxOS`;
put it in the same place on the new computer), and start it there. The
backup timer picks up where it left off, because its records are in the data
folder. Turn off
**Start automatically** on the old computer and quit the app there first.
Two computers running it at once would both control the lights.

**Uninstall:**

1. Turn off **Start automatically**.
2. Quit the app.
3. Delete the app folder, and on Windows also `%LOCALAPPDATA%\EaveLuxOS`
   (your settings; keep a copy if you might come back).

Nothing else is left on the computer.

### Run it in a container (Docker)

On a home server or NAS with Docker, the app folder includes a `Dockerfile`
and `compose.yaml`:

1. Optional: copy `env.example` to `.env`. Set `BIND_ADDRESS` to the server's
   home-network address (for example `192.168.1.10`) so phones can reach it;
   by default only the server itself can. `HOST_PORT` changes the port, and
   `EAVELUXOS_ALLOWED_HOSTS` lists host names you use instead of an address.
2. Run `docker compose up -d --build`.
3. Run `docker compose logs eaveluxos` and note the **setup code**. Open
   `http://SERVER-ADDRESS:8787` and enter it, then finish the setup assistant
   and create your Administrator account.

In a container nobody counts as "this computer", so everyone signs in. The
container runs as an ordinary user (uid 10001), never as root; its files are
read-only except the `eaveluxos-data` volume (database, key, photos, log);
it has no Linux capabilities and can't gain privileges. **Start
automatically** and **App address** aren't used: Docker restarts the
container, and the port is set in `.env`. Back up the volume, for example
with `docker compose stop`, then copy it, then `docker compose start`.

## 22. Test with your controller

Some things can only be checked on real hardware. The guided hardware test
checks them one by one and saves a report. It takes about 10 minutes, and you
need to be able to see the lights.

1. Quit the app (**Quit** at the top, or **Setup › App › Quit the app**), so it doesn't change the lights
   during the test.
2. In the app folder, run `python3 main.py hwtest`.
3. Answer each question by looking at the house or the Trimlight Edge app.

What it checks:

| Check | What it tells you |
|---|---|
| Controller clock | Whether the time this app sends really sets the controller's clock |
| First 10 bulbs | That bulb numbering starts where you expect |
| 90 bulbs per color | Whether the cloud accepts 90 or only 60 (the app adapts either way) |
| Save to library | Skipped since 4.3: patterns are never saved through the cloud (Local mode does it over the home network) |
| Port 0-0 refused | That Trimlight still refuses a port without bulbs, which is why Setup › Lights & controller keeps a Not connected port's numbers (asks first; nothing changes when refused) |
| Controller timer | Whether the backup timer works: the lights should come on by themselves 2 minutes later with one of the controller's own patterns, and go off 2 minutes after that (asks first) |
| Command rate | Whether quick changes, like the bulb finder's, are accepted |

Before changing anything, the test saves the controller's full state as
`hwtest-backup-….json`. It puts everything back at the end, even if you press
Ctrl+C. The report is saved as `hardware-test-….txt` in the data folder.
Sharing it helps other Trimlight owners know what works on their firmware.

## 23. Troubleshooting

| Problem | What to do |
|---|---|
| Another program uses port 8787 | The app moves to the next free port by itself and remembers it. To pick one, use **Setup › App › App address** (section 19). |
| The browser says it can't connect, or the desktop icon says **Can't reach EaveLuxOS** | The program isn't running (the icon and bookmarks only show it). Click **Start EaveLuxOS** on that page (4.22.2; your browser asks first), or open the program from its folder (the page shows where it is). On Mac or Linux, when run from the source code, keep its window open. Turn on **Start automatically** (section 7) so it's always running. |
| Mac: it didn't come back after a shutdown or restart | Open **EaveLuxOS** from **Applications** (nothing is lost; your settings are in ~/Library/Application Support/EaveLuxOS). If Home or **Setup › App** says it runs from a temporary copy or the disk image, quit, drag it into Applications, eject the .dmg and open it from there, then turn **Start automatically** on. It starts after someone logs in to the Mac. If phones still can't reach it, the Mac may have a new address after the restart: see **Setup › Accounts & access › Phones and other computers**, and reserve the Mac's address in your router. If macOS asks to allow incoming connections for EaveLuxOS, click **Allow**. |
| "Couldn't check these with Trimlight" during setup | The app couldn't reach Trimlight, so your keys weren't checked yet. Check the internet connection and try again. If the message also says the **certificate check failed**: on a Mac, update to version 3.11.1 or later, which fixes this. Otherwise check the computer's date and time, and whether antivirus or network filtering software checks secure (HTTPS) connections. |
| "Trimlight didn't accept these" | Re-enter the Client ID and Secret. They're case-sensitive, so check for spaces. Also check the computer's clock is correct, because Trimlight's sign-in uses the time. |
| "Trimlight's cloud can't read its copy of this controller" (code 12006, "Device data could not be parsed … declared 21 and scanned 20 effect records") | Trimlight's cloud copy of the controller is out of step, for example because two saved patterns got the same number. The lights keep running. The app first asks the controller to resend its data and tries again. Since 4.2.1 the backup timer never saves patterns and doesn't try to repair this itself: it removes its timers and stops itself until you turn it off and on again. Since 4.3 nothing in this app saves or deletes patterns through the cloud (Local mode does it over the home network), and with the controller's address set, Setup › Lights & controller still saves ports while the cloud can't read it. While it lasts, Setup › Lights & controller shows the error and turns saving off, so the port layout can't be overwritten. If it doesn't clear: tap **Resync with Trimlight's cloud** in Setup › Lights & controller (4.4), which asks the controller to send the cloud a fresh copy and changes nothing on it; give it a few minutes and try again. First tap **Back up now** in Local mode, which works without the cloud. **Don't unplug or reset the controller while this shows**: twice in November 2026 a restart then left it with only its factory patterns (put yours back with Pattern backups if that happens). |
| "Can't reach lights" on Home | Check the controller is online in the Trimlight Edge app and the computer has internet. The app retries automatically. |
| Lights are on or off at the wrong time | **Setup › Location & time:** check the location, time zone and Daylight saving (Automatic). Check the computer's own clock. Check **Schedule › Coming up**. |
| A different pattern than expected is showing | Look at the Home headline. It names the rule, weather rule or manual change in charge. Check priorities on the Schedule tab. |
| The lights turned back on after I switched them off in the Trimlight app | That's by design (section 6). Use **Turn off** in this app instead. |
| Colors are wrong (red shows as green) | **Setup › Lights & controller › Color order** (section 17). |
| My phone can't open the address (nothing happens, or it times out) | On the app computer, open **Setup › Accounts & access › Phones and other computers › A phone can't open it?** and tap **Check this computer**. On Windows it finds the usual causes: the network set to **Public** (Windows blocks phones; switch it to Private in Windows Settings › Network & internet), or Windows Firewall blocking the app (often from pressing **Cancel** when Windows first asked). **Let phones in** fixes the firewall after one Windows permission prompt. Also check: the phone is on home Wi-Fi (not mobile data or a guest network), the address starts with `http://` and ends with the port, and try any other address listed there. The computer's address can change, so consider a reserved IP in your router. When it works, the phone shows the sign-in page. |
| The phone says "create an account" | On the app computer, go to **Setup › Accounts & access** and add one. |
| "These settings were changed on another device" | Someone saved changes from another phone or computer at the same time. The latest settings have been loaded; make your change again. |
| "Unknown host name" | You used a name the app doesn't know. Use the IP address, or run `python3 main.py allow-host NAME` on the app computer (section 14, *Webhooks and Home Assistant*). |
| Weather isn't working | Weather rules are US only. Check **Weather: On** on the Alerts tab. Home shows the current reading or the error. |
| On Linux, it doesn't start at power-on until someone logs in | Run `loginctl enable-linger` once in a terminal. That's the only command in this manual. |
| The controller shows offline, or nothing responds | Use the controller steps in Trimlight's guide ("Basic Troubleshooting"). **1)** Unplug the controller for 30 seconds, then let it boot for a few minutes. **2)** If the **Network Connected** light isn't green, press the **STA/AP** button briefly until it is (blue-light mode can't be reached by this app). **3)** A factory reset is a last resort; see the question below. |
| A rule never seems to run | Check for a **"Never runs"** note on the Schedule tab (section 13) and raise that rule's priority. |
| Backup timer says "Not armed" | Read the reason shown. Most often the controller's library is full, or it was offline. Tap **Update now** to retry; the app also retries on its own every 30 minutes. |
| "That image is too large" when uploading a photo | The image is over 40 megapixels and not a JPEG (for example a huge PNG). Save it as a JPEG, or smaller, and upload it again. Photos straight from a phone are fine. |
| A house photo shows as solid green, stripes, or one flat color | Some graphics drivers garble photos when the browser processes them. Since version 3.11.5 the app computer processes photos itself, so this shouldn't happen; upload the photo again. If you still see a message about a flat color (the browser is used for iPhone HEIC photos, or when the app runs from source without Pillow), try another browser, or turn off **Use graphics acceleration when available** in the browser's settings (System section). |
| The finder lights the wrong spot | Check the port layout on Setup › Lights & controller (section 17). Bulb numbers follow it. |
| "The settings database couldn't be read" | Rare, usually after a disk problem. The app kept the damaged file, restored your patterns and schedule from its plain-text copy (`settings.last-good.json`), and asks you to enter your Trimlight account and app password again. |
| Music from this computer: "Couldn't reach the controller" or "didn't answer" | Check the address the Trimlight Edge app shows when it opens, and that the app computer is on the same home network (not a guest network). Unplugging the controller for 30 seconds clears a stuck connection. Close the Trimlight app on your phone while testing; it may hold the controller's attention. After a firmware update, a new capture (`tools/music-capture`) shows whether the messages changed. |
| Music from this computer: "The controller stopped answering" | Nothing came back from the controller for 15 seconds. Check it's online in the Trimlight app, and that the app computer's Wi-Fi or cable is steady; unplugging the controller for 30 seconds clears a stuck one. |
| Music from this computer: the bars move but the lights don't follow the beat | Raise **Sensitivity** or **Input level**; try another music pattern. With a microphone, move it closer to the speakers, or use **This computer's sound**. |
| Music from this computer: "No sound was shared" | Pick the **browser tab** that's playing the music and keep **Also share tab audio** on. Sharing a window leaves the sound out, and **Also share system audio** for Entire screen doesn't appear on every computer. For music from an app (Spotify), use **Stereo Mix** (section 15). |
| Microsoft Defender blocks or removes EaveLuxOS.exe ("executes commands from an attacker", Suspicious Behavior) | A false alarm: Defender guesses from behavior, and an unsigned program that runs a small web server and starts helpers (PowerShell for the phone check, `icacls` to lock its data folder) looks like that to it. Since 4.1.3 the Windows build uses its own launcher, which Defender flags far less. **1)** Check the file is the one GitHub built: in Command Prompt, `certutil -hashfile "%USERPROFILE%\Downloads\EaveLuxOS-Windows.zip" SHA256` must match the zip's line in **SHA256SUMS.txt** on the release page. **2)** In **Windows Security › Virus & threat protection › Protection history**, open the item and choose **Restore** (or **Allow on device**). **3)** Report it so Microsoft clears it for everyone: microsoft.com/wdsi/filesubmission, "Software developer" or "Home customer", **Incorrectly detected**. |
| I changed something and want it back | **Setup › App › Version history**: tap **Restore** next to an earlier save (section 19). |
| Forgot a password | Ask an Administrator to set a new one under **Setup › Accounts & access**, or on the app computer run `python3 main.py reset-password NAME`. |
| "This account can only view" | You're signed in as a Viewer. An Administrator can make you an Editor. |
| Something else | The log is **eaveluxos.log** in your data folder (on Windows `%LOCALAPPDATA%\EaveLuxOS`). |

## 24. Questions and answers

**Does this replace the Trimlight Edge app?** For scheduling, yes. Keep the
Trimlight Edge app for:
- Pairing and Wi-Fi setup.
- Firmware updates.
- Groups of controllers.
- **Switching music mode on.** Trimlight's guide says music only works on the
  local network, so it isn't available through the cloud API this app uses.
  The **Music** tab keeps this app from interfering while it runs (section 15).
- The **lightning and snowflake** overlays: in the Trimlight app's library,
  press and hold a pattern.
- Alexa and Google Home skills.

**What's the difference between rotation here and the Trimlight app's
"Combined Effect"?** Both cycle patterns on an interval. The Combined Effect
in the Trimlight app holds up to 5 patterns. Rotation here takes any number,
of any type, and can differ per rule.

**What happens after a factory reset of the controller?** According to
Trimlight's guide, a factory reset erases the controller's saved patterns and
timers. Patterns you made or added in **this** app are stored on your
computer and keep working. Patterns that existed only in the Trimlight app's
library are lost, so add any you want to keep to **My patterns** beforehand.
After a reset, re-pair the controller to your account in the Trimlight Edge
app. The app will then find it again. If its ID changed, run the setup
assistant once more.

**Does it work with Alexa or Google Home?** Trimlight's own skills keep
working alongside this app, but a voice change lasts only until this app's
next scheduled change or its 5-minute check (section 6). Home Assistant users
can control this app directly (section 14, *Webhooks and Home Assistant*).

**Does it work without internet?** The schedule and sun times are calculated
on your computer. However, every command goes through Trimlight's cloud,
exactly as the Trimlight app's commands do. If the internet is down, the app
waits and catches up as soon as it's back. With the **backup timer** on (section
17), the controller also runs the coming nights from its own timers while the
app or internet is down.

**What does the app keep on my computer, and is anything stored on the
controller?** Your settings, patterns, schedule, house map, version history,
credentials and sign-ins are in one database file, `eaveluxos.db`, in your
data folder (on Windows `%LOCALAPPDATA%\EaveLuxOS`; elsewhere usually `data`
next to the app; see section 4). Readable only by your account, it's a
standard SQLite file. Photos, controller backups and the log are in the same
folder.

Nothing has to be stored on the controller. The app writes to it only when
you ask: the backup timer's copy of the coming nights, and (over the home
network) ports and the patterns you save, put back or delete there.

To back everything up while the app runs, use
`python3 main.py backup ~/trimlight-backup.db`. Or quit the app and copy the
data folder.

**Is my information safe?**
- Your secret stays on the app computer, in `data/eaveluxos.db`, readable only
  by your user account, and encrypted with AES-256-GCM using the key in
  `data/secret.key`. On Windows, the app sets the files' permissions so only
  your account (and Windows itself) can read them. **Back up `secret.key`**
  along with the database, but keep the copies apart: without the key, the
  saved Trimlight details can't be read and must be entered again.
- Passwords are stored only as salted scrypt hashes.
- Sign-ins end after 8 hours without use (or what an Administrator chose) and
  always after 7 days. Security changes from a phone ask for your password
  again.
- Nothing is sent anywhere except Trimlight's API, the US National Weather
  Service (for weather rules), and a place-name search when you use town
  search.

**Can several people use it at once?** Yes, from any number of signed-in
devices. If two people edit settings at the same moment, the second save is
refused rather than silently overwriting the first.

**Can it control more than one controller?** Yes. Everything you turn on is
sent to all the controllers ticked under **Setup › Lights & controller › Controlled by this app**.
Setup › Lights & controller shows a card for each controller; tap one to manage its
settings (section 17).

## 25. License

EaveLuxOS is free software released under the **MIT License**:

> Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

Trimlight and Trimlight Edge are trademarks of their owner. This project is
independent and isn't endorsed by Trimlight.

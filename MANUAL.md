# EaveLuxOS: User Manual
### The Intelligent Lighting Control Platform

Version 3.11.0 · © 2026 Christopher A. Tankelewicz (ThinkTank4n6) · MIT License

EaveLuxOS is a free, community-made lighting control platform. Today it runs
**Trimlight Edge** permanent lights. It is not made, sold, endorsed or
supported by Trimlight; Trimlight and Trimlight Edge are trademarks of their
owner and appear here only to say which hardware EaveLuxOS works with. EaveLuxOS was
previously called "LumaOS", and before that "Trimlight Scheduler". Updating
keeps all your settings.

This manual takes you from nothing installed to a working schedule, then
explains every screen. You never need to type commands.
Inside the app, the **Manual** button in the top ribbon opens it, with a
search box. The bottom of every screen shows the app's version, the
copyright notice and a link to the MIT License.

It complements Trimlight's own **Trimlight Select EDGE Wi-Fi V2 User's Guide**.
That guide covers the hardware, pairing and the Trimlight Edge app, and you
can find it and Trimlight's videos at **trimlight.com/edge**. Where this
manual refers to "Trimlight's guide", that's the document it means.

---

## Contents

1. [What you need](#1-what-you-need)
2. [Get your Trimlight API credentials](#2-get-your-trimlight-api-credentials)
3. [Install Python](#3-install-python)
4. [Download and start the app](#4-download-and-start-the-app)
5. [The setup assistant](#5-the-setup-assistant)
6. [Prepare the Trimlight Edge app](#6-prepare-the-trimlight-edge-app)
7. [Make it start automatically](#7-make-it-start-automatically)
8. [Use it from your phone](#8-use-it-from-your-phone)
9. [Home](#9-home)
10. [Patterns](#10-patterns)
11. [Create a pattern](#11-create-a-pattern)
12. [House map](#12-house-map)
13. [Schedule](#13-schedule)
14. [Weather rules](#14-weather-rules)
15. [Security flash](#15-security-flash)
16. [Music shows](#16-music-shows)
17. [Safety net](#17-safety-net)
18. [Lights: ports, bulbs and LED settings](#18-lights-ports-bulbs-and-led-settings)
19. [Date and time](#19-date-and-time)
20. [Settings](#20-settings)
21. [Home Assistant and webhooks](#21-home-assistant-and-webhooks)
22. [Share patterns with other owners](#22-share-patterns-with-other-owners)
23. [Update, move or uninstall](#23-update-move-or-uninstall)
24. [Test with your controller](#24-test-with-your-controller)
25. [Troubleshooting](#25-troubleshooting)
26. [Questions and answers](#26-questions-and-answers)
27. [License](#27-license)

---

## 1. What you need

| Item | Details |
|---|---|
| Trimlight Edge controller | Already installed and **connected to your home Wi-Fi**, not just to its own "Trimlight" network. On the controller, the light labeled **Network Connected** should be **green**. |
| A Trimlight account with the controller paired to it | Done in the Trimlight Edge app: **Sign up**, then **+ › Add device** (Trimlight's guide, "Creating an Account" and "Pairing to a local WIFI Network"). |
| Trimlight API Client ID and Client Secret | A pair of codes from Trimlight (see step 2). |
| A computer that stays on | Windows 10 or 11, macOS, or Linux. A small mini PC is ideal. It must be on for the schedule to run. |
| Python 3.11 or newer | Free (see step 3). |
| Home Wi-Fi | The computer and your phone should be on the same home network. |

The computer does **not** need to be near the lights. It controls them
through Trimlight's cloud service, the same way the Trimlight app does when
you're away from home.

> **Important:** In blue-light mode ("Wifi Broadcasting"), the controller only
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
**Settings › Trimlight account**.

If the page doesn't accept your account or doesn't give you credentials,
contact Trimlight support and ask for **API access (Client ID and Client
Secret) for your Trimlight Edge controller**.

## 3. Install Python

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

> **No Python? Use the installer instead,** from the project's GitHub
> **Releases** page. Then skip section 3. The README explains the first-run
> security prompts for each system.
> - **Windows:** `EaveLuxOS-Windows.zip`. Unzip it and double-click
>   `EaveLuxOS.exe`.
> - **Mac:** `EaveLuxOS-macOS.dmg`. Drag the app to Applications.
> - **Linux PC:** `eaveluxos_…_amd64.deb`
> - **Raspberry Pi (64-bit):** `eaveluxos_…_arm64.deb`
>
> Install either `.deb` with `sudo apt install ./<file>`. Commands in this
> manual written as `python3 main.py …` become `EaveLuxOS-cli.exe …` on
> Windows, and `eaveluxos …` on Linux or a Pi.

1. Download **eaveluxos.zip** and unzip it somewhere permanent, such
   as your **Documents** folder. Don't run it from inside the zip or from
   Downloads, since you'll want to keep this folder.
2. Open the **eaveluxos** folder and double-click the launcher for
   your computer:

| Computer | Double-click | Notes |
|---|---|---|
| Windows | **Start EaveLuxOS.bat** | The first time, it may install a small time-zone package (needs internet). The app then runs in the background without a window. |
| Mac | **Start EaveLuxOS.command** | The first time, macOS may block it. Right-click the file, choose **Open**, then **Open** again. Keep the Terminal window that appears open while the app runs. |
| Linux | **start-eaveluxos.sh** | If asked, choose **Run in Terminal**. Keep the window open. |

3. Your web browser opens to **http://localhost:8787** and shows the setup
   assistant. If the browser doesn't open, open it yourself and go to that
   address.

> **Tip:** Launching it twice is safe. A second launch only opens the browser
> to the copy that's already running.

> **If it doesn't start:** on Windows a message box explains why.

> **Where your data is kept:** on **Windows**, always in
> `%LOCALAPPDATA%\EaveLuxOS` (for example `C:\Users\you\AppData\Local\EaveLuxOS`),
> whichever version you run, so you never copy it between versions. On a Mac,
> the app uses `~/Library/Application Support/EaveLuxOS`; on Linux, the
> `data` folder next to `main.py` (or `~/.local/share/eaveluxos` if that
> can't be written). **Settings › Setup and about** shows the folder in use.

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
     not to (see section 19).
   - Click **Save and continue**.
5. **Phone access.** Create your **Administrator account**: a user name
   (`admin` unless you change it) and a password of at least 8 characters.
   Phones and other computers use it to sign in. You can skip this if you'll
   only ever use the app on this computer, and add accounts for other people
   later (section 20).
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

> **Good to know:** Every 5 minutes EaveLuxOS checks that the lights
> are doing what the schedule says. If someone turns them off in the Trimlight
> app, or the controller restarts after a power blip, the scheduler restores
> them within about 10 minutes. To override the schedule, use **Turn on** or
> **Turn off** in this app instead.

## 7. Make it start automatically

1. Go to the **Settings** tab.
2. Under **Start automatically**, tick **Start this app when the computer
   starts**.

On Linux, it starts when you log in. To make it start at power-on without
anyone logging in, see section 25.

Also turn off sleep in the computer's power settings, so the computer never
goes to sleep.

## 8. Use it from your phone

1. On the app computer, open **Settings** and look under **Phones and other
   computers** for an address such as `http://192.168.1.20:8787`.
2. On your phone, connect to your home Wi-Fi and open that address in Safari
   or Chrome.
3. Enter your user name and password.
4. **iPhone:** tap **Share › Add to Home Screen**. **Android:** tap the **⋮**
   menu, then **Add to Home screen**. You now have a "Lights" app icon.

A phone stays signed in until it goes **8 hours without being used**, and
never longer than **7 days** (an Administrator can change the first number
under **Settings › Accounts**). The sign-in is stored for this
app's exact address, including the port, so other web apps on the same
computer never see it. If you change the app's port (section 20), or update
from a version before 2.3.2, each phone signs in once more.

> **Tip:** The address can change when your router restarts. To keep it fixed,
> give the app computer a **reserved IP address** (sometimes called a DHCP
> reservation) in your router's settings.

> **Optional: HTTPS.** By default, the app uses plain HTTP on your home
> network, so the app password crosses your Wi-Fi unencrypted. The quickest
> fix: on the app computer run `python3 main.py make-cert` (installed apps:
> `eaveluxos make-cert`, or `EaveLuxOS-cli.exe make-cert` on Windows) and
> restart the app. Each browser warns once that the certificate is
> self-signed; accept it on your own devices. For no warning at all, make a
> certificate with the free tool **mkcert** (`mkcert -install`, then
> `mkcert -cert-file cert.pem -key-file key.pem 192.168.1.20 localhost`). Put
> `cert.pem` and `key.pem` in the `data/tls` folder and restart the app. The
> address then starts with `https://`. Phones trust it after you install
> mkcert's root certificate on them, as mkcert's instructions describe.

> **Away from home:** The app only works on your home network, which is
> deliberate. Never "port forward" it on your router. For remote access, use a
> VPN that connects you to your home network (many routers include one).
>
> **If you put a reverse proxy in front of the app** (Caddy, nginx, Tailscale
> Serve, cloudflared), the app tells outside requests apart from this computer
> by the `X-Forwarded-For` header the proxy adds. Caddy, Tailscale Serve and
> cloudflared add it on their own. nginx needs
> `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` in its
> `location` block. Anything that forwards without adding that header (`ssh -L`,
> `socat`, a TCP-only tunnel) can't be told apart from a browser on this
> computer, so first turn on **Settings › Require signing in on this computer
> too**.

## 9. Home

Home shows what the lights are doing now and lets you take over quickly.

**On every screen,** the top right shows what the lights are doing (*Lights
on*, *Lights off* or *Music show*) next to three buttons. On a phone they show
as icons only: a light bulb, a power symbol and a door.

- **On** turns the lights on with tonight's scheduled pattern: the one
  showing now, or the next one on the schedule. With nothing scheduled in the
  coming week, it uses the last pattern you turned on by hand, or Warm white.
- **Off** turns the lights off.
- Both last until the next scheduled change, like **Turn on** and **Turn off**
  below. The one that matches what the lights are already doing is grayed out.
  Viewers don't see them.
- **Quit** stops the app, after asking first. It's shown only on the computer
  the app runs on (see **Quit the app** in section 20).

- **The headline** says whether the lights are on and why. For example, "Every
  night: Warm white until 11:00 PM" or "Christmas, set by hand".
- **The day bar** runs from midnight to midnight:
  - Dark is night, light blue is daytime, and the in-between shades are dawn
    and dusk.
  - **Amber** shows when the lights are scheduled on.
  - The thin line is now.
- **Turn on:** tap any pattern to show it right away. It stays on until the
  next scheduled change.
- **Turn off:** turns the lights off until the next scheduled change.
- **Return to schedule** appears after a manual change. Tap it to go back to
  the schedule immediately.
- **Security flash:** see section 15.
- **Brightness and speed:** these change whatever is showing now, until the
  next scheduled change.
- **This week:** each day's on and off times and which rule runs. A note
  appears on the day daylight saving time changes.
- **Controllers and activity:** each controller's status, plus a log of
  everything the app did.

## 10. Patterns

The buttons at the top switch between three lists.

**My patterns** are the ones schedules can use. On each card:
- **Turn on** shows the pattern now.
- **Edit** opens it in Create, or for built-in effects lets you change speed,
  brightness and length.
- **Delete** removes it. A pattern that a rule uses can't be deleted until
  you change that rule.

**In the Trimlight app** lists the patterns saved in your Trimlight Edge app,
read from your controller.
- **Try** shows one on the lights.
- **Add to my patterns** copies it here so your schedule can use it.
  Colors and bulb counts carry over exactly.

**Built-in (180)** lists all of Trimlight's built-in effects. Search by color,
for example "red green", or filter by family (Wave, Snake, Stars, Fire and so
on).
- **Try** shows one on the lights.
- **Add** saves it to My patterns, after asking for speed, brightness and
  pattern length.

## 11. Create a pattern

This works like the color circles in the Trimlight app.

1. Open the **Create** tab, or tap **New pattern** on the Patterns tab.
2. Type a **Name**, for example "Candy cane".
3. Under **Colors in order**, each circle is one color, and its number is how
   many bulbs that color covers, from 1 to 90. There can be up to 30 circles,
   just like the 30 sequence slots in the Trimlight app. The sequence repeats
   along the whole roofline.
   - Tap a circle to select it.
   - Tap a color in the palette to change it, or use the rainbow circle to pick
     any color.
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
4. Choose an **Animation** (Static, Chase, Stars, Breath, Comet, Wave, Strobe or
   Solid fade) and set **Speed** and **Brightness**.
5. Watch the **Preview**. It's drawn with your real number of bulbs, and the
   animation is a close approximation of the controller's.
6. Tap **Try on my lights** to see it on the house. A preview lasts 15
   minutes, then the schedule takes over again.
7. Tap **Save pattern**. Tick **Also add it to the Trimlight app's library**
   first if you want it in the Trimlight Edge app too.

When **color correction** is on (see
[Lights](#18-lights-ports-bulbs-and-led-settings)), the lights get adjusted
colors so they look like the preview. Tick **Exact colors** to send this
pattern's colors unchanged, for example colors you already tuned by eye on the
house.

To change a pattern later, open **Patterns › My patterns** and tap **Edit**.

### Paint single bulbs, ranges or every Nth bulb

For detail the color circles can't give you, tap **Paint bulbs** in **Create**.
The circles become a strip with one dot per bulb (numbers every 10).

1. Choose what you're painting:
   - **One repeat:** one copy of your sequence, which then repeats along the
     roofline. Set **Bulbs in one repeat** to make it longer or shorter.
   - **Whole house:** every bulb from 1 to your total (House map › Address
     space), painted once with no repeat. Landmarks from the House map show
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

### Paint by zone

If you've saved zones on the House map (section 12), you can color whole
sections at once:

1. In **Create**, tap **Paint by zone**.
2. Choose a color for each zone, such as Garage roof = Red and Main roof =
   White. Leave a zone as "Leave as the rest" to skip it.
3. Choose **Everything else**: ✕ Zone off (dark, never moves), Black, or a
   color.
4. Tap **Paint**, check the preview, name the pattern and tap **Save pattern**.

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
port setup on the Lights tab (section 18), so get that right first.

### Tips from Trimlight's guide

- **Comet and Wave** only run when each color covers **more than 5 bulbs**. The
  designer warns you when a color is set to 5 or fewer.
- **Chase** is very fast with 1 bulb per color. Slow it down with larger counts
  or black spaces between the colors. For example, 1 red followed by 7 black
  sends a single red light running along the roofline.
- **For a pulse**, fill several circles with a large count (up to 90) of one
  color, and add one circle of a second color that will travel through it.

## 12. House map

The House map tab helps you find where each bulb is, label your house, and
name sections of roofline.

### Find a bulb

1. Open **House map**. The **Bulb finder** shows bulb **1** of your address
   space. That's the total number of bulbs, taken from the controller's ports
   (section 18).
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
Change the name or the first and last bulb; **Light these bulbs** shows the
zone on the house so you can check it, and **Use the finder's range** copies
the bulb finder's current selection. Tap **Save zone**. **Show** lights a zone
and ✕ deletes it. Patterns you already painted with a zone keep their colors;
paint them again to use the new bulbs.

### Address space

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

**Show flat diagram** unfolds every side into one picture: roof edges in
green, ridges in purple, wire-only stretches in gray, and your landmarks with
their bulb numbers. **Download SVG** saves it as a file you can print or open
in a drawing program. Traced lines follow your photos, so the diagram isn't
to scale.

## 13. Schedule

A **rule** says when the lights turn on and off, and which pattern shows.

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
   - **Switch every … minutes**, or
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

The **Coming up** list on the right shows the next three weeks so you can
check the result. Daylight saving changes are marked.

If a rule shows **"Never runs in the next year"**, another rule wins on every
one of its nights, usually one with the same priority that is listed first.
The note names that rule and how to fix it, usually by raising this rule's
priority.

### Several schedules a day

Like the Trimlight Edge app's timers, a day can have more than one rule, as
long as their times don't overlap. Each one runs in its own time. For
example:

- **Evening:** all year, Sunset → 11:00 PM.
- **Morning:** all year, 6:00 AM → Sunrise.

**Add a morning schedule** on the Schedule tab fills in the second one for
you (6:00 AM → Sunrise, with your everyday pattern); change anything before
tapping **Save**. Both show in **Coming up** and in **This week** on Home,
and the safety net copies both to the controller.

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
| Dim accent until morning | All year, 11:00 PM → Sunrise, Warm white, own brightness 25%, Low |
| Morning lights on dark mornings | All year, weekdays, 6:00 AM → Sunrise, Warm white, Everyday (alongside an evening rule) |

### Bring over timers from the Trimlight app

Tap **Import from Trimlight app**, tick the timers you want, and tap
**Import**. They come across with their fixed clock times; edit them
afterward to switch to sunset-based times. The patterns they use are added
to My patterns automatically.

### How overlapping rules are decided

From highest to lowest:

1. **Security flash.**
2. **Something you turned on or off by hand** (until the next scheduled change).
3. **A weather rule** (section 14).
4. **The scheduled rule with the highest priority.** If two have the same
   priority, the one listed first wins. This only decides overlapping time:
   rules at different times of day (morning and evening) each run.

## 14. Weather rules

Weather rules change the pattern based on current conditions, using the US
National Weather Service. They work in the United States only, and no
account is needed.

1. On the **Schedule** tab, tick **On** in the **Weather** box.
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

## 15. Security flash

The security flash is bright lights on demand for a few minutes. After that,
everything returns to normal, including turning the lights back off in
daylight.

1. On the **Schedule** tab, under **Security flash**, choose a pattern
   (Security white is included) and the minutes, then tap **Save**.
2. Start it from **Home › Security flash**, or from a motion sensor through
   Home Assistant (section 21).

Starting it again while it's running restarts the timer. **Stop flash** ends it.

## 16. Music shows

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
isn't switched back to the schedule. **Stop the show** during a show night
ends it for that night only.

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

The webhook actions `music` and `stop_music` start and stop a show (section 21).
`music` takes an optional `{"minutes": 60}`; `{"minutes": 0}` means until
stopped, and with no body it uses the usual length set on the Music tab.

### Limits

- This app can't switch music mode on or off; that still takes the Trimlight
  app on your home Wi-Fi.
- During a show, the safety net isn't updated and the controllers aren't
  checked. Both resume when the show ends.
- The beat-matching is the controller's own. Trimlight's cloud is far too slow
  (a quarter to a full second per command) to drive the lights in time with
  music from here.

## 17. Safety net

Normally, the app computer runs your lights. If it's off, unplugged or offline,
nothing turns the lights on or off. The **safety net** fixes that by also
copying the next few nights into the controller's **own timers**.

### Turn it on

1. Open **Schedule** and find **Safety net**.
2. Tick **On** and choose how many nights to copy (3 to 14; 7 is a good
   choice).
3. Within a few seconds it says **Armed: 7 nights copied to the controller**.

### What it does

- Each day, and whenever you change the schedule, it writes one controller
  calendar entry for each time the lights come on (two a day if you have a
  morning and an evening rule). Each entry has its pattern and on/off times.
- The patterns it needs are saved in the controller's library with names
  starting **"Auto "**, such as "Auto Warm white". They take up a few of the
  controller's 60 pattern spaces. Your own patterns in the Trimlight app are
  never changed.
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
- **Only its own items:** it only creates, changes or deletes the timers and
  "Auto" patterns it made. Timers and patterns from the Trimlight app are left
  alone.
- **Read back:** after writing, it reads the controller back and checks every
  entry. If anything differs, it removes what it wrote and shows **Not
  armed** with the reason. Your lights keep running from the app as usual.

### Warnings you might see

- **"The Trimlight app's daily timers are on":** in Timer mode those would
  run too. Tap **Turn them off**; the controller is backed up first.
- **"The controller also has calendar events made in the Trimlight app":**
  they're left alone, but they also run in Timer mode if their dates overlap.
  Delete them in the Trimlight app if you don't want them.
- **"The controller's pattern library is too full":** delete a few patterns in
  the Trimlight app, or copy fewer nights.

### Limits

- On its own, the controller runs the planned on/off times and the night's
  pattern. Weather rules, minute-by-minute rotation, slider changes and
  anything after midnight need the app. A night that runs past midnight is
  covered until 11:59 PM.
- If the app stops on a night it took over (after a manual change, weather or
  the flash), the lights stay on until it comes back, because that night the
  controller is in Manual mode. On normal nights this can't happen.
- To remove it, untick **On**. The app deletes its entries and "Auto" patterns
  from the controller.

## 18. Lights: ports, bulbs and LED settings

These settings are stored **on the controller itself**. They match the
controller's Settings screen in the Trimlight Edge app.

### More than one controller

If your Trimlight account has several controllers (for example *House* and
*Deck*), the top of the Lights tab shows a card for each one, like the
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

### Ports and bulbs

- **Simple mode:** enter how many bulbs are on each port, in order along the
  roofline. Use **0** for an unused port. The app numbers the bulbs end to end.
- **Advanced mode:** enter the first and last bulb number for each port, or
  tick **Off**. Ports may **overlap**, which makes them show the same part of
  the pattern (mirroring). For example, Port 2 = 84–138 and Port 3 = 100–138.

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

### Color correction (gamma)

Colors picked on a screen often look pale or washed out on LEDs. A soft
orange can come out nearly yellow, and pastel colors look almost white.
Screens apply a *gamma curve* to brightness and LEDs don't, so in-between
values look much brighter on the house than on the screen. Gamma correction
(the same math used by apps such as Gamma Correct for Windows or Gamma
Corrector for iPhone and iPad) adjusts each color before it's sent, so the
house looks closer to what you picked.

1. On **Lights**, find **Color correction**.
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
  **Try on my lights**, the safety net, and patterns you add to the Trimlight
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

## 19. Date and time

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

## 20. Settings

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
- **Share and back up:** export or import patterns and schedules (section 22).
- **App address:** shows the port the app uses (8787 unless you change it).
  To change it, type a port from 1024 to 65535, such as 8790, and tap
  **Restart on new port**. The app checks the port is free, moves there in a
  few seconds, and reopens the page on the new address. Then update bookmarks
  and Home Screen icons on your phones. On a computer without a screen, run
  `python3 main.py port 8790` in the app folder and restart the app.
- **Start automatically:** see section 7.
- **Webhooks:** see section 21.
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

## 21. Home Assistant and webhooks

Webhooks let other systems control the lights. For example, a motion sensor
can start the security flash at night.

1. In **Settings › Webhooks**, tick **Allow webhooks**.
2. Tap **Copy token** and keep it private.
3. Have the other system send a **POST** request to
   `http://APP-COMPUTER-ADDRESS:8787/api/hook/ACTION` with the header
   `X-Token: YOUR-TOKEN`. Services that can't set headers, such as IFTTT, can
   send `{"token": "YOUR-TOKEN"}` in a JSON body instead. A token in the web
   address (`?token=`) is refused, because addresses end up in logs and browser
   history.

| Action | What it does | Optional body |
|---|---|---|
| `flash` | Start the security flash | `{"minutes": 10}` |
| `stop_flash` | End the flash | |
| `on` | Show a pattern | `{"effect": "christmas"}` (the pattern's internal name) |
| `off` | Turn off | |
| `resume` | Return to schedule | |
| `levels` | Brightness or speed | `{"brightness": 120}` (0–255) |
| `music` | Start a music show (section 16) | `{"minutes": 60}`; `0` until stopped |
| `stop_music` | End the music show | |

### Home Assistant example

In `configuration.yaml`:

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

## 22. Share patterns with other owners

**To share:**

1. Go to **Settings › Share and back up › Export patterns and schedule**.
2. A file named like `eaveluxos-patterns-2026-11-11.json` downloads. It
   contains your patterns, rules, weather rules and security flash settings.
   It **never** contains your Trimlight credentials, password, location or
   controller details.

**To use someone else's file:**

1. Go to **Settings › Import a file** and choose the file.
2. Choose one of:
   - **Add to mine:** adds patterns and rules whose names you don't already
     have.
   - **Replace mine:** replaces your patterns and schedule. Your location and
     controllers are kept.

Export is also a good backup before big changes.

## 23. Update, move or uninstall

**Update to a new version**

1. Quit the app (**Settings › Quit the app**).
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
safety net picks up where it left off, because its records are in the data
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

## 24. Test with your controller

Some things can only be checked on real hardware. The guided hardware test
checks them one by one and saves a report. It takes about 10 minutes, and you
need to be able to see the lights.

1. Quit the app (**Settings › Quit the app**), so it doesn't change the lights
   during the test.
2. In the app folder, run `python3 main.py hwtest`.
3. Answer each question by looking at the house or the Trimlight Edge app.

What it checks:

| Check | What it tells you |
|---|---|
| Controller clock | Whether the time this app sends really sets the controller's clock |
| First 10 bulbs | That bulb numbering starts where you expect |
| 90 bulbs per color | Whether the cloud accepts 90 or only 60 (the app adapts either way) |
| Save to library | Whether designs can be added to the Trimlight app's library (asks first; deleted afterward) |
| Port off | Whether a port can be switched off from the Lights tab (asks first; put back afterward) |
| Controller timer | Whether the safety net works: the lights should turn green by themselves 2 minutes later and off 2 minutes after that (asks first) |
| Command rate | Whether quick changes, like the bulb finder's, are accepted |

Before changing anything, the test saves the controller's full state as
`hwtest-backup-….json`. It puts everything back at the end, even if you press
Ctrl+C. The report is saved as `hardware-test-….txt` in the data folder.
Sharing it helps other Trimlight owners know what works on their firmware.

## 25. Troubleshooting

| Problem | What to do |
|---|---|
| Another program uses port 8787 | The app moves to the next free port by itself and remembers it. To pick one, use **Settings › App address** (section 20). |
| The browser says it can't connect | The app isn't running. Double-click the launcher. On Mac or Linux, keep its window open. |
| "Trimlight didn't accept these" | Re-enter the Client ID and Secret. They're case-sensitive, so check for spaces. Also check the computer's clock is correct, because Trimlight's sign-in uses the time. |
| "Can't reach lights" on Home | Check the controller is online in the Trimlight Edge app and the computer has internet. The app retries automatically. |
| Lights are on or off at the wrong time | **Date & Time:** check the location, time zone and Daylight saving (Automatic). Check the computer's own clock. Check **Schedule › Coming up**. |
| A different pattern than expected is showing | Look at the Home headline. It names the rule, weather rule or manual change in charge. Check priorities on the Schedule tab. |
| The lights turned back on after I switched them off in the Trimlight app | That's by design (section 6). Use **Turn off** in this app instead. |
| Colors are wrong (red shows as green) | **Lights › Color order** (section 18). |
| My phone can't open the address | The phone must be on home Wi-Fi, not mobile data. The computer's address may have changed, so check **Settings**, and consider a reserved IP. |
| The phone says "create an account" | On the app computer, go to **Settings › Accounts** and add one. |
| "These settings were changed on another device" | Someone saved changes from another phone or computer at the same time. The latest settings have been loaded; make your change again. |
| "Unknown host name" | You used a name the app doesn't know. Use the IP address, or run `python3 main.py allow-host NAME` on the app computer (section 21). |
| Weather isn't working | Weather rules are US only. Check **Weather: On** on the Schedule tab. Home shows the current reading or the error. |
| On Linux, it doesn't start at power-on until someone logs in | Run `loginctl enable-linger` once in a terminal. That's the only command in this manual. |
| The controller shows offline, or nothing responds | Use the controller steps in Trimlight's guide ("Basic Troubleshooting"). **1)** Unplug the controller for 30 seconds, then let it boot for a few minutes. **2)** If the **Network Connected** light isn't green, press the **STA/AP** button briefly until it is (blue-light mode can't be reached by this app). **3)** A factory reset is a last resort; see the question below. |
| A rule never seems to run | Check for a **"Never runs"** note on the Schedule tab (section 13) and raise that rule's priority. |
| Safety net says "Not armed" | Read the reason shown. Most often the controller's library is full, or it was offline. Tap **Update now** to retry; the app also retries on its own every 30 minutes. |
| The finder lights the wrong spot | Check the port layout on the Lights tab (section 18). Bulb numbers follow it. |
| "The settings database couldn't be read" | Rare, usually after a disk problem. The app kept the damaged file, restored your patterns and schedule from its plain-text copy (`settings.last-good.json`), and asks you to enter your Trimlight account and app password again. |
| I changed something and want it back | **Settings › Version history**: tap **Restore** next to an earlier save (section 20). |
| Forgot a password | Ask an Administrator to set a new one under **Settings › Accounts**, or on the app computer run `python3 main.py reset-password NAME`. |
| "This account can only view" | You're signed in as a Viewer. An Administrator can make you an Editor. |
| Something else | The log is **eaveluxos.log** in your data folder (on Windows `%LOCALAPPDATA%\EaveLuxOS`). |

## 26. Questions and answers

**Does this replace the Trimlight Edge app?** For scheduling, yes. Keep the
Trimlight Edge app for:
- Pairing and Wi-Fi setup.
- Firmware updates.
- Groups of controllers.
- **Switching music mode on.** Trimlight's guide says music only works on the
  local network, so it isn't available through the cloud API this app uses.
  The **Music** tab keeps this app from interfering while it runs (section 16).
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
can control this app directly (section 21).

**Does it work without internet?** The schedule and sun times are calculated
on your computer. However, every command goes through Trimlight's cloud,
exactly as the Trimlight app's commands do. If the internet is down, the app
waits and catches up as soon as it's back. With the **safety net** on (section
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
you ask: the safety net's copy of the coming nights, and patterns you choose
to also add to the Trimlight app's library.

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
sent to all the controllers ticked under **Lights › Controlled by this app**.
The Lights tab shows a card for each controller; tap one to manage its
settings (section 18).

## 27. License

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

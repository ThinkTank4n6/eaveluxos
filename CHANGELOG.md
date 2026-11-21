# Changelog

## 4.16.4: no false "changed outside this app" at every start; Find and match; Who wins tonight

- **Fixed: every start of the app resent the pattern** and logged
  "Trimlight's pattern was changed outside this app (power blip or the
  Trimlight app)" when it hadn't been (seen in Chris's log, Nov 20). The
  pattern had gone over the home network, which Trimlight's cloud doesn't
  hear about; after a restart the app (since 4.15) forgot that, compared the
  pattern with the cloud's, and sent it again. It now keeps which way each
  command went with the rest of what was sent
  (tests/repro_restart_resends.py).
- **Find and match** (Setup › Local mode) with one controller whose
  address was saved the original way (one address for all) offered "Use for
  Trimlight" for the address already in use; it now says it's saved. A
  controller with more patterns than are listed says "and 13 more".
- **Who wins tonight** (Schedule) no longer warns that weather rules could
  take over while weather is turned off (Alerts › Weather).
- Manual: where the HTTPS certificate goes on Windows
  (`%LOCALAPPDATA%\EaveLuxOS\tls`), and which mkcert file stays on the
  computer.

## 4.16.3: installing an update from the app on Windows works

- **Fixed: Install from Setup › App left EaveLuxOS without its page**
  (Windows; the Linux .tar.gz could do the same). The download is one file
  that unpacks itself into a temporary folder each time it starts, and
  tells the copy it runs where that is through the environment. The updater
  started the new version with that environment, so the new version used
  the old copy's folder instead of unpacking its own; when the old copy
  closed, it deleted the folder ("Failed to remove temp directory"), and the
  new version was left answering `{"error": "not found"}`. Starting
  EaveLuxOS again then only opened the broken copy. The new version is now
  started as a program of its own (tests/repro_update_borrows_files.py).
  The same went for moving the app to another port (Setup › App), since
  4.8.
- **The updater now checks the page, not just the answer:** a new version
  counts as started only when its page and script load too; otherwise the
  previous version goes back, as for one that doesn't start.
- **Updates started by 4.15.0 to 4.16.2:** each build now carries a note of
  its own version (bundle-version.txt). A copy that finds itself running
  on another version's unpacked files starts itself again, once, on its
  own, and stays until the older copy has handed over. Installing 4.16.3
  by hand is still the safest way from those versions.
- **Fixed: an install closed by hand partway through** stayed "in progress" forever and its download (about 100 MB) was never tidied up; after a few minutes it now counts as interrupted, Setup › App says so, and the download goes.
- The manual says how to recover if an earlier update left the app with no
  page.

## 4.16.2: two more timing tests for GitHub's Mac

No change to the app itself. GitHub's Mac was slower still on 4.16.1's run,
and two music tests that count frames came up short:

- **Slows down when the controller lags** now keeps feeding until the show
  has slowed (up to 12 seconds) instead of stopping at 4; the Mac had sent
  only 13 frames by then, too few to see two late answers in a row.
- **Levels keep going out** after a single feed now asks for at least 2
  frames (the Mac sent 3; the line was "more than 3").

Both were also run with the computer's processors kept busy, along with the
other music, sound and controller tests, and passed.

## 4.16.1: the tests pass on Windows and macOS too

No change to the app itself; 4.16.0 works the same. GitHub's Tests run on
Windows and macOS failed four of 4.16.0's tests, all in how the tests ran:

- **Windows:** the 4.11 weather-warning check ran its script and read the
  output as UTF-8, while Windows wrote it in its own code page; a curly
  quote couldn't be read and the test saw nothing. The review scripts now
  run through one helper (tests/reprorun.py) that has the script write UTF-8
  and reads it the same way.
- **macOS:** only 127.0.0.1 answers on a Mac, so the 4.15 and 4.16 review
  scripts that need a second controller at 127.0.0.2 couldn't start. The
  tests they come from already skip there; now the scripts do too, instead
  of failing.
- **macOS:** a timing test (music levels keep flowing while a keep-alive
  answer is late) counted 18 frames on a busy GitHub Mac against a line of
  20; when it's broken it's under 10, so the line is now 14.

## 4.16.0: calibrate the house with a camera

- **Calibrate with the camera** (House): a phone, propped up at night,
  watches while the controller shows about 16 black-and-white frames (for
  106 bulbs); each bulb's number is spelled out in binary across them, so
  the camera reads every bulb's number and place at once. Each frame is a
  short pattern the controller repeats along its lights, so it fits 30
  color blocks however many bulbs there are, and each is also shown the
  other way round, so the brightness of a bulb or the night doesn't matter.
- The result is saved as a new version of the elevation (**Calibrated**):
  the camera's photo, a line for each run of bulbs, and every bulb found
  pinned where it was seen (missed ones spread evenly between). Worked out
  in the browser; nothing is sent anywhere.
- Mirrored runs show up in both places; other controllers' lights in view,
  even moving patterns, are ignored. Needs the https:// address on a phone
  (browsers allow the camera only on secure pages).
- Review before release (code review of the new code):
  1. A preview on one controller (calibration frames, the bulb finder)
     ended with that controller back on the schedule, losing a choice made
     by hand before it. Previews now remember what they cover, and ending
     one (or its running out) puts it back; the same for previews on every
     controller (`tests/repro_preview_end.py`).
  2. A house with more than 40 runs of bulbs lost the extra runs quietly;
     the result now says how many didn't fit.

## 4.15.0: reliability

- **Who wins tonight** (Schedule): any night, for each controller, what
  shows when, what it beats and why, and what weather could take over, with
  warnings for ties (same priority, listed first wins), rules that never
  show, and the automations that night.
- **Controller health** (Setup): online and firmware; requests today, how
  many worked, typical answer time, 14 days of bars, the last problem, and
  the home-network answer time. **Check now**.
- **Smart recovery**: choices made by hand, slider levels, a security flash
  and a music show come back after the app restarts (unless the schedule
  moved on meanwhile); what was just sent isn't sent again, but checked at
  once.
- **Find and match my controllers** (Setup › Local mode): finds controllers
  on the home network (and, with **Look harder**, knocks on port 8586 across
  the app computer's own network), reads each and matches it to your
  controllers by their ports. **Use all matches**.
- **Updates that install** (Windows and the Linux .tar.gz): download, check
  the SHA-256 against the release's list, keep the version you have,
  restart as the new one, and go back by itself if it doesn't start. **Go
  back to X**, and **Install new versions by themselves, while the lights
  are off** (off unless chosen).
- Review before release (code review of the new code):
  1. A controller that lost power and came back with its lights in another
     state waited for two read-backs, five minutes apart, before the app put
     them back. It's set again as soon as it's back online, and checked every
     minute while offline (`tests/repro_power_back.py`).
  2. A finished update left its download and unpacked copy beside the
     program; they're removed now (the previous version stays).
  3. An unexpected error while preparing an update left "already being
     installed" until a restart.
  4. Setup › Local mode's buttons (Find, Save) did nothing until the
     controller had been read, and Find and match's results vanished when the
     panel redrew.

## 4.14.0: EaveLuxOS on your phone's home screen

- **Installable app** (a Progressive Web App): a maskable icon, full screen,
  and an **Install** bar in a phone's browser (Chrome's install button where
  it's offered; the steps for Safari). **Setup › App › On your phone** shows
  how and whether this phone has it.
- **Quick**, the screen the icon opens: big buttons for On, Off, Back to the
  schedule, Security flash, patterns, scenes and automations (the household
  chooses up to 12 with **Edit**; until then, favorites and scenes), and
  brightness. **Quick buttons** on Home opens it in any browser.
- **Shortcuts on the icon** (press and hold, Android): Lights on, Lights off,
  Back to the schedule, Security flash.
- **Kept on the phone** (https:// addresses and the app computer): the app's
  own files, never anything from the app computer's data, so it opens at
  once and says **Can't reach EaveLuxOS** away from home instead of a browser
  error. Each version replaces the kept files.
- Review before release (code review of the new code):
  1. A shortcut's address opened as an ordinary link (an email, another web
     page) acted at once for anyone signed in, for example turning the
     lights off. Only the installed app's own shortcuts act at once; a link
     asks first (`tests/repro_link_acts.py`).
  2. The first visit after an update could run the kept, older files with
     the new page. The app's files now come fresh from the app computer
     first, and the kept copy only when it can't be reached.
  3. **Try again** on the away-from-home screen did nothing: the page's
     security policy blocks inline handlers.

## 4.13.0: Music sync 2.0

- **The music, analyzed** (Music › Music from this computer): bass, mids
  and treble with an automatic level, beat detection and the tempo (BPM),
  50 to 60 times a second, shown as three bars, a beat dot and the BPM.
- **My zones**: each House-tab zone follows the bass, mids, treble or the
  beat, in its own color, as a **Glow** or a **Meter** (filling from its
  first bulb, or its last if the zone runs the other way), on one controller
  or several. The app draws each moment and shows it live on the controller
  over the home network (the Trimlight app's editing preview; nothing is
  saved on the controller).
- **Safeguards** for that: a **speed test** each controller must pass first
  (2 to 8 frames a second, the most a show will use); only the newest frame,
  only when it changed; a keep-alive every second, slowing down a step when
  answers come late and ending the show, with the schedule back, when the
  controller stops answering.
- **Sound delay** (latency compensation): what you hear is held back to land
  with the lights, for a browser tab's sound and for music files; a
  suggested value from the show, and a **Sync test** (clicks and white
  flashes) to set it.
- **A music file on this computer** as a source: your own MP3, WAV or M4A
  files, played in the page, one after another.
- Review before release (code review of the new code):
  1. One late keep-alive answer (a moment of busy Wi-Fi) slowed a zone show
     for the rest of the show. It now takes two in a row, and the pace that
     lagged is tried again after a quiet minute
     (`tests/repro_zone_hiccup.py`).
  2. One late answer could also fail a whole rate in the speed test.
  3. Stopping a zone show without naming its page stopped any page's show.
  4. After reconnecting during a show, frames went out before a keep-alive;
     the controller ignores requests on a new connection until one comes.

## 4.12.0: the House Mapping Studio

- **Place bulbs** (House view): drag a bulb to where it really sits on the
  photo. It's pinned there, and the bulbs between pins spread out evenly
  again along the line. Tap one to select it, nudge it with the arrow keys,
  and **Light bulb N on the house** to check it. The preview, scenes and the
  whole-house view all use the pins.
- **Line a zone up** (Zones › Edit): light it with its first bulb green and
  its last red; **First**, **Last** and **Whole zone −1 / +1** move the ends
  while the house follows; a picture shows the zone on each elevation photo.
  **Runs the other way** makes Combine patterns by zone lay that zone's
  pattern from its last bulb.
- **Whole house: every elevation at once**: every elevation side by side,
  animating one pattern, **tonight's schedule** (each controller its own;
  drag the time, Now, or Play), or **a pattern for each zone** (with
  **Make it a pattern** into Combine patterns by zone).
- **Elevations**: Front, Right side, Rear and Left side elevations by name;
  add more (several side elevations, a garage) with a kind. Each can have
  **versions** (day and night photos, before and after), each with its own
  photo, rooflines and pins, optionally started from another version's; the
  ★ one is shown in the whole house and the flat diagram.
  **Export this elevation** saves one with its photos to a file, and
  **Import an elevation** brings it back.
- **This side's lights** is now **This elevation's lights**.
- Review before release (code review of the new code):
  1. A version deleted on one device left its photo on disk when the photo
     had been uploaded from another device since the page loaded, and the
     next version with the same name showed that old photo. Deleting now
     removes every version's photo, and new versions never take the name of
     a leftover one (`tests/repro_version_photo_left.py`).
  2. A version of an elevation that isn't there was accepted, and stayed
     hidden where it couldn't be opened or deleted.
  3. The House tab said photos are never exported; an exported elevation
     does include them, and now says so (the Manual too).
  4. Lighting a zone to check it: with the finder's color set to pure red
     or green, the middle looked like an end; and a two-bulb zone had no
     ends marked.
  5. **Make it a pattern** could leave its choices for the next Combine
     patterns by zone if Create didn't open.

## 4.11.0: automations (When · If · Then)

- **Alerts › Automations**: build your own rules. **When** a team scores, a
  game starts or ends (a win, a loss or either), a weather warning starts, a
  webhook event comes, a time or sunrise/sunset (with an offset) arrives, or
  the schedule turns the lights on or off; **if** it's dark, between or
  before or after a time, on certain days or dates, the lights are on or
  off, a rule or pattern is showing, or (for games) the team is home, away,
  winning or losing; **then** flash a pattern, a color or a zone and go
  back, show a pattern for a while, turn off for a while, or play a team's
  sound, on all controllers or one.
- **Priority**, **Cooldown** and **Beats a manual choice** for each one. The
  higher priority goes first when two start together; a lower one doesn't
  cut into a higher one's flash.
- **Try it now**, **Check it now** (each condition, ✓ or ✗) and **Lately**
  (what ran or why it was skipped, also in Activity).
- Webhook events by name: `POST /api/hook/event` with `{"name": "doorbell"}`.
- **Schedule › Game-day lights › Make it an automation** turns a team's score
  celebration into an automation to add conditions to. Celebrations you
  don't convert work as before.
- The scoreboard now notices a game starting and ending, and which team is
  at home.
- Review before release (code review of the new code):
  1. During a weather warning, an automation that showed a pattern, turned
     the lights off or flashed one controller dismissed the warning, as a
     choice by hand does. The warning now stays on top and the automation
     is skipped (`tests/repro_auto_dismisses_alert.py`). A music show isn't
     interrupted either, unless **Beats a manual choice** is on.
  2. **Lately** never loaded: the server didn't send the history it read.
  3. A flash on one controller went back to the schedule afterward instead
     of to the choice it covered (one by hand, for that controller or all).
  4. An automation's own **Show** or **Turn off** counted as a choice by
     hand, so later automations were skipped as if you had set the lights.
  5. **Try it now** started the cooldown, so the real event right after was
     skipped.
  6. A webhook event before setup was a server error, and an automation that
     failed could stop the scoreboard's check; both are handled now.

## 4.10.1: an Intel Mac download

- **`EaveLuxOS-macOS-Intel.dmg`**: the app for Intel Macs, built on GitHub's
  Intel Mac next to the Apple silicon one (`EaveLuxOS-macOS.dmg`). An Intel
  Mac no longer needs Python and Terminal. **Setup › App › Updates** offers
  each Mac its own download.
- The Manual covers the Mac message "could not be executed because you do
  not have appropriate access privileges" for **Start EaveLuxOS.command**:
  `chmod +x` (once), `xattr -c` if needed, and not running it from a USB
  stick or disk image.
- **Start EaveLuxOS.command** updates pip first and installs only the
  ready-made encryption package, so an older Mac no longer stops on "Failed
  building wheel for cryptography"; if none fits, it says so and starts
  without it. The Manual has the two Terminal lines that fix it by hand.
- Review before release: the release workflow's note about how many builds
  must succeed now says five.

## 4.10.0: the House tab with two or more controllers

- **House › Controller**: with two or more controllers, choose which one the
  bulb finder, zone checks and scene previews light. Only that controller
  lights up, along its own bulbs (Front 106, Deck 96); the others keep
  showing what they were. **All controllers** works as before.
- **This side's lights** gives a side of the house to one controller;
  choosing the side then chooses its controller.
- **Zones and landmarks** saved while a controller is chosen are that
  controller's (the lists say whose). One zone name can be used once for
  each controller.
- **Combine patterns by zone** with a zone for one controller makes one
  pattern for each controller, along its own bulbs, and saves them together
  as a **Split by controller** pattern (the parts go in a **Zone parts**
  folder). **Paint by zone** lists the zones for the controller **Bulbs of**
  counts.
- A preview on one controller ends by itself after 10 minutes, like the
  finder always has.
- Review of 4.10 before release: with every controller turned Off by hand
  during a scheduled evening, the finder on one controller turned the others
  back on with the schedule (`tests/repro_finder_wakes_others.py`); the
  others now keep their Off. A scene made for one controller's bulbs no
  longer says it was made for another count.
- Not yet per controller: a weather or webhook alert set to light a zone
  lights those bulb numbers on every controller.

## 4.9.2: Color correction, Local mode and Pattern backups in their own sections

- **Setup** now has buttons for **Color correction**, **Local mode** and
  **Pattern backups** next to **Lights & controller**, instead of folded
  panels at the bottom of it. Each works as before. Local mode and Pattern
  backups are for Administrators, as they were, and their buttons show only
  for them. **Pattern backups** has a **Controller** choice with two or
  more controllers. Links elsewhere in the app, messages, the feature
  search and the Manual point to the new places; the Lights page links to
  them too.
- Review before release: an Editor or Viewer who opens one of the
  Administrator sections by its address is taken to Lights & controller.

## 4.9.1: what a user's screenshots showed, and patterns in folders

- **Slots that aren't patterns are left out.** A user's Front controller
  sent its 2 real patterns and then 54 slots numbered 0 or 255, nameless or
  with garbled names, which Setup › Local mode listed with Delete buttons.
  They're left out of the list now (it says how many), of backups and of
  matching patterns, and nothing deletes a slot that isn't numbered 1 to 60,
  even if asked directly.
- **Create › Bulbs of**: with controllers of different lengths (Front 106,
  Deck 96), choose whose bulbs the preview and Paint bulbs count. Before, it
  always counted the first controller's.
- **Patterns › My patterns**: **Order** (A to Z, the usual; newest or oldest
  first) and **Folder** on each pattern (Christmas, Fourth of July, Easter
  ...), with a button for each folder above the list. Saving a pattern again
  in Create keeps its folder.
- A test meant for Macs compared a file path the Mac way and failed on
  GitHub's Windows (4.9.0); no change to the app.
- Review of 4.9.1 before release: **No folder** didn't work in the first
  try (it used a character browsers change in a page), and a request to
  delete slot 0 or 255 is now refused before anything is sent to the
  controller.

## 4.9.0: a sound when your team scores

- **Schedule › Game-day lights**: a team with celebrations on can play a
  sound when it scores (a goal horn, a fight song) through the speakers of
  the computer EaveLuxOS runs on. Choose an MP3 or WAV file you have (up
  to 15 MB), where it starts and how long it plays (1 to 30 seconds, 20 to
  start). **Listen here** plays it in your browser, **Play on the app
  computer** through that computer's speakers. **Play the sound** turns it
  off without losing the file. The file stays in the app's data folder; the
  app comes with no team sounds.
- Plays through Windows' own media player or the Mac's `afplay`; on Linux
  with `paplay`, `aplay`, `mpg123` or `ffplay`. The part that plays is cut
  without re-encoding, so nothing else is needed.
- Review of 4.9 before release: a second score while the first sound still
  plays now plays it again (on Windows the open file couldn't be rewritten,
  and the error reached the score check); a problem with the sound never
  stops the lights celebrating; and an MP3 with large cover art is taken as
  an MP3.

## 4.8.1: a test that was too strict on Windows

- No change to the app. A test of the short pause after greeting a
  controller over the home network measured 0.297 seconds on GitHub's
  Windows for a 0.3-second pause (Windows' clock ticks about every 15 ms)
  and failed. It now allows for that.

## 4.8.0: each controller on its own

- **A schedule for each controller.** With two or more controllers, a rule
  has **Controllers**: untick the ones it isn't for (all ticked, the usual,
  means every controller). Each controller follows its own rules by the
  usual priorities, so the Deck can go off at 9:00 while the Front runs to
  11:00, or each show its own pattern at its own brightness. Rules saved
  before stay for all controllers.
- **Home's controller cards** say what each controller shows and give it
  its own **On**, **Off** and **Show a pattern…**, until its schedule
  changes (or **Back to schedule**). The top **On** and **Off** still mean
  all of them. The headline lists each controller when they differ, and
  the week and the next 24 hours name whose times they are.
- **Schedule › Coming up** has a controller choice: all controllers'
  nights together, or one controller's own month.
- **Sent safely.** Different patterns go out together the way Split by
  controller already does, and a controller whose own pattern didn't change
  is sent nothing (no restarted motion, no extra commands). A rule for one
  controller never reaches another, also in the first moments after the
  app starts (it learns which controllers there are first). On nights the
  controllers differ, the app runs them itself instead of handing the night
  to their own timers. The 5-minute check expects a controller that's off
  by its own rule to be off, so it's never "restored". The backup timer
  plans each controller's own nights (it stays paused, as since 4.3.9).
- Review of 4.8 before release: while waiting to retry after Trimlight's
  cloud failed, the app no longer asks it for the account's controllers
  every pass; a choice made on a controller the app then stopped running
  waits for it instead of changing how the others' nights are run; and a
  preview (Try, the bulb finder) leaves each controller's own choice in
  place when it ends.

### Also in 4.8.0: fixes from GitHub's first Mac test run

- **Setup, sign-in and Setup › Phones and tablets no longer wait on a slow
  name lookup.** To list this computer's home-network addresses, the app
  looks up the computer's own name. On a Mac whose name the network doesn't
  know, that can take many seconds, and these pages waited for it (on the
  test Mac, past 10 seconds). Now it waits a second at most; the address the
  computer's internet traffic leaves from is still found right away.
- **A computer with a long name gets its phone certificate** (Setup ›
  Phones and tablets › secure connection). A certificate's name holds 64
  characters; with a longer computer name, making it failed. The name is
  shortened there, and the full name is still one the certificate answers
  to.
- A music-sync timing test allows for slower computers (GitHub's Mac).
- Review of these fixes before release: only one name lookup runs at a
  time, and an answer that comes in late is used the next time instead of
  being thrown away.

## 4.7.3: review of 4.7.2

- **Keep awake, turned off and straight back on** (two quick taps, or two
  phones at once) now stays on. Before, the request being let go of could
  take the new one with it: on a Mac, which has one request for the app,
  the Mac could then sleep while Setup › App said it was being kept awake.
  Now the old request is let go of before the new one is made.
- The Mac release is built on macOS 15, the same Mac the tests run on,
  rather than whichever Mac GitHub calls "latest" at the time.

## 4.7.2: Macs stay awake, and get tested

- **Keep this computer awake while the app runs** (Setup › App) now works
  on a Mac too, on by default, the way the built-in `caffeinate -i` command
  does it: the Mac doesn't go to sleep on its own while the app runs; the
  screen can still turn off, and Sleep, the power button and closing a
  laptop's lid still work. `pmset -g assertions` lists it as *EaveLuxOS:
  following the lights' schedule*. Quitting the app lets the Mac sleep again.
- **GitHub tests on a Mac** as well as Windows and Linux (before, the Mac
  build was made but nothing tested it). On the Mac, a test also checks that
  the keep-awake request really appears and goes away.

## 4.7.1: each controller's patterns, and which one is active

- **Patterns › In the Trimlight app** has a **Controller** choice when the
  account has two or more, listing every controller, including ones this
  app doesn't run. Before, it showed only one controller's patterns.
  Administrators get the list read over the home network when the
  controller has an address there (what it holds now), with Trimlight's
  cloud as the fallback; the note says which. **Add to my patterns** names
  a second "Christmas" *Christmas (Front)*.
- **Home › Controllers** marks the controllers this app runs **Active**
  (green) and grays out the others on the account, labeled **Not run by
  this app**.
- Built-in effects saved in the Trimlight app are read as built-in effects
  over the home network. Before, a backup taken over the home network called
  them patterns of their own colors, and putting one back would have
  written a blank pattern by that name (now it's skipped by name, as from
  the cloud). Patterns of their own colors keep their gaps of bulbs left
  off.
- The controller cards under Setup › Lights & controller no longer count
  ports marked as not connected in the bulb total (a deck showed 1500
  bulbs).
- Review of the new code before release: choosing another controller while
  one is still being read works; adding the same pattern twice numbers the
  name; **Try** on a pattern known only by its name says when it can't be
  shown on the controllers this app runs; two different built-in effects are
  no longer taken for the same look.

## 4.7.0: combine patterns by zone

- **Combine patterns by zone** (Create): a different one of your patterns
  along each zone of the house, for example Christmas on the garage,
  Thanksgiving on the main roof and American Flag on the porch, as one
  pattern. Still (each zone stays in place) or moving with a motion of your
  choice; a strip shows the result, then Preview on house, Try and Save as
  for any pattern. When the zones together need more than the controller's
  30 color blocks, the busiest zone's colors are made longer until it fits,
  and the note says which zones and how much. A dimmer pattern's zone is
  darkened to keep its look (a controller has one brightness).
- Review of the new code before release: it uses the controller's own limit
  per color block (60 on some controllers, as scenes do), keeps bulbs that
  are off in a painted pattern dark, says so when the chosen zones are
  outside the lights' bulb count, notes when only some of the patterns use
  exact colors, and fits a phone screen.

## 4.6.1: the month first

- Schedule › Coming up opens as the month, and **Month** comes before
  **List** in its switch.

## 4.6.0: everything over the home network

From the Trimlight app's own traffic, captured on Nov 17, 2026:

- **Patterns of your own colors and built-in effects go over the home
  network** too (with "Send on/off and saved patterns over the home
  network" on), shown live the way the Trimlight app shows a pattern while
  you edit it. Like Trimlight's cloud preview, that isn't saved on the
  controller. Before, only patterns saved on the controller went this way;
  American Flag (brighter here than there), HALLOWEEN, Christmas and the
  rest went through the cloud. The cloud is still used when the controller
  doesn't answer, and for what wasn't seen in the capture: a built-in
  effect with a length other than 30, over 30 colors, or over 255 bulbs in
  one color.
- **Brightness and speed sliders** on Home go the same way, as the
  Trimlight app's sliders do.
- **The controller's daily timers** (its own two, the Trimlight app's) are
  shown in Local mode: on or off, times, repeat and pattern, read from the
  controller. Shown only for now; writing them waits for one more test.
- **Waits 12 seconds before reconnecting** after the controller ignores a
  read. The capture showed the Trimlight app's own read going unanswered
  ("Failed to sync" at 7:20 PM) and its next connection, 12 seconds later,
  answered at once; this app tried again after 1 second.
- Learned, not changed: opening the Trimlight app shows pattern 14 on the
  controller by itself (it did each time it connected), so the lights come
  on. This app notices a changed pattern only when it sent its own through
  the cloud; over the home network it can't tell yet, so after using the
  Trimlight app, tap Run schedule (or wait for the next scheduled change). The
  controller's own pattern rotation isn't needed: this app's rotation
  changes patterns itself, and now each change goes over the home network.
  Renaming the controller stays with Trimlight's cloud: over the home
  network the controller can't confirm it, and it dropped the connection a
  minute after a rename.

## 4.5.1: review of 4.5, the controllers' health first

Nothing in 4.5 saves or deletes anything through Trimlight's cloud, the
cause of the 12006 errors and lost patterns (the backup timer, the only
part that wrote timers there, stays paused). This review looked at
everything that talks to the controllers over the home network:

- **Far fewer reads of the controllers.** With "Send on/off and saved
  patterns over the home network" on, the 5-minute check read each
  controller every time (a full read, which also sets its clock), all
  day and night: about 288 reads a day per controller, even when Trimlight's
  cloud already agreed. On Nov 17 the controller stopped answering reads at
  2:56 AM after hours of them. Now it reads only when the cloud disagrees
  with what was sent (tests/repro_verify_reads.py: 7 reads in half an hour
  before, none now).
- **Ports never go to the wrong controller.** With two or more controllers,
  changing a controller's ports first checks that the controller at its
  address has that controller's ports (as Trimlight's cloud knows them, or
  as this app last set them). If the router gave two controllers each
  other's addresses, nothing is changed and the app says so.
- Saving a controller's address no longer says yes without checking when
  Trimlight's cloud can't be read (12006 or offline): it asks.
- "Send on/off and saved patterns over the home network" can't be turned on
  when the only address is one saved before 4.5 that isn't known to be any
  controller's (nothing would have gone over the home network).
- Search: typing a new search right after picking a result could leave the
  new results hidden (a close left over from the pick, 150 ms later). Seen
  as a test that failed only now and then.
- tests/repro_mixed_paths.py works again (it predated the pattern matching
  of 4.4.2).

## 4.5.0: each controller on its own

- **A home-network address for each controller** (Setup › Lights &
  controller › Local mode), for two, three or more. Before, there was one
  address: with two controllers, saving to the controller, Pattern backups,
  deleting, the Lights tab's ports and the home-network commands all went to
  whichever controller had that address, even with only the other one
  chosen (a user with a Deck and a Front controller saw only the Deck's
  patterns, and couldn't save anything on the Front).
  - **Find controllers** lists every controller answering on the home
    network; **Which is this?** shows one's ports and first pattern names;
    **Use for this controller** saves it.
  - Before an address is saved, the controller there is read and its ports
    compared with what Trimlight's cloud says that controller has; when
    they differ, the app asks first. One address can't be two controllers'.
  - An address saved before 4.5 counts only when the account has one
    controller (nothing changes then). With two or more, the panel asks
    which controller it is, and nothing goes to it until you say.
  - Local mode reads the controller you choose; Delete and Back up now act
    on it; Pattern backups put patterns back on the controller the backup
    came from; the designer's "Also save it on the controllers" saves on
    each controller this app runs that has an address and names any that
    don't; the Lights tab saves ports to that controller's own address.
  - Home-network commands go to each controller's own address, and each
    controller's failures, reads and reminders are its own: one not
    answering doesn't send the others to the cloud.
- **Home lists each controller** on its own card, as the Trimlight app's
  first screen does: name, online or offline, on or off, firmware, and its
  home-network address with whether it answers. The activity log is under
  **Activity**.
- The controller cards on the Lights tab spilled 3 pixels past a phone's
  screen (their Online label took another style's 10-pixel width).
- Search finds the new pieces.

## 4.4.5: house photos from any camera

- A house photo wouldn't upload for a user ("Something went wrong. Details
  are in the log."). Their camera wrote a resolution of 0/0 into the photo's
  hidden camera information (EXIF), and the image library in the Windows
  release divided by zero while turning the photo upright. The app now turns
  photos upright itself without rewriting that information (the saved photo
  doesn't keep it anyway), all eight orientations as before
  (tests/repro_photo_zero_rational.py).
- Anything else the app computer can't handle in a photo now lets the
  browser shrink it instead, as an iPhone HEIC photo already did, and the
  log says why.

## 4.4.4: keep the computer awake

- **Keep this computer awake while the app runs** (Setup › App › Start
  automatically; Windows; on by default). A sleeping computer can't follow
  the schedule: the mini PC slept on its own five times from Nov 14 to 16,
  three of them through sunrise, when 0-Security turns the lights off (Nov
  16: 5:33 to 8:03 AM). The app now asks Windows not to sleep on its own,
  the way a video player does while it plays. The screen can still turn
  off, the power button and Sleep still work, and quitting the app lets the
  computer sleep again. The log says when it's holding. Search finds it.

## 4.4.3: quieter when the controller won't answer

- On Nov 17 from 2:56 to 6:00 AM the controller answered keep-alives but no
  read, and the log got 74 warnings. Now a stretch like that gets one
  warning, a reminder each hour (with the hint about the Trimlight app), and
  "Over the home network works again" when it does. During a stretch, each
  try uses one connection instead of two. As before, commands go through
  Trimlight's cloud meanwhile (the 6:00 AM lights came on that way).
- When nothing at all comes back to a read, the app asks again on the same
  connection after 3 seconds before trying a new one (the controller often
  ignores only the first request). A plain "0 bytes came" is now an
  information line, not a warning; bytes that don't fit still warn.

## 4.4.2: your own patterns over the home network too

- When one of this app's patterns looks exactly like one saved on the
  controller (same colors and bulb counts, motion, speed and brightness), the
  app shows the saved one by its number over the home network instead of
  sending it through Trimlight's cloud. On Nov 16 that covered Fall,
  EVERYDAY, 0-Security and 9-11; American Flag differs in brightness (255
  here, 188 there) and HALLOWEEN in its motion, so they still go through the
  cloud. The controller is read first in the same connection, so a pattern
  that moved to another number is never shown by its old one; a look not on
  the controller isn't read for again for 10 minutes.
- A command over the home network that gets no answer is sent once more on a
  fresh connection before the app falls back to the cloud (the controller
  sometimes ignores the first request: "0 bytes came").

## 4.4.1: review of 4.4

- Each command that goes over the home network is now in the log ("Over the
  home network: lights off."), so you can see it working; before, only a
  failure was.
- With "Send on/off and saved patterns over the home network" on, a rule
  showing a pattern of its own colors turned the lights on over the home
  network but sent the pattern through the cloud, and the app then went back
  to trusting the cloud's on/off. The cloud doesn't hear about changes made
  over the home network, so every check saw "off", warned "changed outside
  this app" and sent everything again. On/off and the pattern are now
  tracked separately, each checked where it was sent
  (tests/repro_mixed_paths.py).
- Home showed the cloud's on/off for a controller switched over the home
  network; it now shows what the controller says.
- A music show from this computer that started while a command waited for
  the connection could be ended by it; the command now goes through the
  cloud instead.
- Anything unexpected going wrong over the home network now falls back to
  the cloud, instead of leaving the lights as they were.
- The checkbox sits under the controller's address and is there even when
  the controller can't be read just then (it only showed after a good read).
- The reachability check no longer counts "busy" as "answers" (a connection
  stuck waiting on a controller that's gone isn't proof); it keeps what was
  known and checks again on the next look.
- Resync with Trimlight's cloud: a second tap within 30 seconds is refused,
  and one controller's trouble doesn't skip the others.

## 4.4.0: local first

- **Send on/off and saved patterns over the home network** (Setup › Lights
  & controller › Local mode, marked *Try it*, off until you tick it): the
  schedule turns the lights on and off, and shows patterns saved on the
  controller, straight over the home network, as the Trimlight app does in
  Local mode. When the controller doesn't answer there, the app uses
  Trimlight's cloud as before for 5 minutes. Patterns of your own colors and
  the built-in effects still go through the cloud (how the controller keeps
  a live preview hasn't been seen yet), Timer mode always does, and nothing
  goes this way during a music show from this computer or a local-mode job.
  A controller set this way is checked with the controller itself, not the
  cloud's copy, which may lag behind.
  After each command the app waits for one answered keep-alive before
  hanging up, so the controller has taken it in.
- **Resync with Trimlight's cloud** (Setup › Lights & controller): asks the
  controller to send the cloud a fresh copy of its data and reads it back,
  what the Trimlight app's sync did. It changes nothing on the controller.
  The "can't read its copy of this controller" (12006) message and the
  backup timer's point to it instead of the Trimlight app, and say not to
  unplug the controller meanwhile.
- After greeting the controller, the app waits half a second before asking
  anything, as the Trimlight app does (asked at once, the controller often
  ignored the first read: "0 bytes came").
- The background check that the controller answers on the home network now
  waits its turn for the connection like everything else (one may have
  dropped a show on Nov 16 at 5:45 PM).
- Search finds both.

## 4.3.13: an answer that says it's longer than it is

- **Fixed:** on Nov 16 at 4:43 PM Pattern backups kept saying "Couldn't read
  the controller: The controller didn't answer", with no warning in the log
  and nothing saved. The likely cause: the controller's answer said it was
  longer than what it sent (the same kind of mismatch as at 3:13 PM, the
  other way round), so the app waited for bytes that never came. When a read
  times out, the app now looks for an answer whose own check fits the bytes
  that did come and reads that; otherwise it logs how much came and saves it
  (lan-unread-*.bin) for a look.
- The message no longer has two periods ("answer..").

## 4.3.12: a controller that goes quiet while storing

- **Fixed:** on Nov 16 at 4:06 PM putting back "American Flag" stopped with
  "the connection failed: The controller didn't answer". Right after taking a
  pattern, the controller can stop answering on that connection for a while.
  Local mode now asks again on a fresh connection after a pause (before and
  after a change), waits longer for a change to show (up to 7 seconds), and
  only then decides; a pattern found already saved isn't sent twice. If it
  still doesn't answer, it stops as before and says to close the Trimlight
  Edge app.

## 4.3.11: the Windows test

- **Fixed:** GitHub's Windows test of 4.3.10 failed ("4 != 5"): Windows'
  clock gave two saved unreadable messages the same microsecond, so one
  overwrote the other. Names are now numbered within the second and never
  reused (as controller backups already were), and a test freezes the clock
  to check it.

## 4.3.10: reading a controller whose own data is off

- **Fixed:** on Nov 16 at 3:13 PM the controller answered a read with 1,940
  bytes whose length field said 1,855 (58 bytes short), so the check failed
  and local mode reported "The controller didn't answer". The same afternoon
  Trimlight's cloud couldn't parse the controller's data (12006: "unable to
  identify effect boundary"). The extra bytes fit the 14 calendar timers the
  backup timer wrote and then tried to take back through the cloud, which
  could no longer reach the controller. When a length doesn't match, the app
  now finds the length the controller's own check fits and reads that.
- Messages the app still can't read are saved in the data folder
  (lan-unread-*.bin, the last 5) for a look, and local backups (Back up now,
  and before every change) keep the controller's whole answer, including the
  timers this app doesn't decode yet.

## 4.3.9: backup timer paused; full review and a browser sweep

- **The backup timer is paused for everyone.** Every time Trimlight's cloud
  stopped being able to read a controller (code 12006), it came within
  minutes of the backup timer writing calendar timers through the cloud:
  Nov 13 17:22 to 17:26, Nov 15 17:52 to 17:56, Nov 16 13:46 to 13:50. Until
  that is understood it writes nothing; the panel says so, a choice to use it
  is kept for when it returns, and the hardware test skips its timer step.
- **Local mode:** a change now reads the controller once more before giving
  up ("Couldn't read the controller first ... didn't answer", Nov 16), and the
  message says to close the Trimlight Edge app if it's open: the controller
  seems to answer one connection at a time.
- **Fixed (most important): the backup timer wrote two timers on one date.**
  Trimlight's calendar won't take two timers on the same date ("The calendar
  schedules cannot be crossed", code 12000, Nov 13), and the backup timer
  already avoided the Trimlight app's own timers for that reason, but with a
  morning and an evening rule it wrote two of its own on every date. That is
  why it has never armed on a real controller: on Nov 15 and 16 all 14
  timers for 7 nights "differed" and it stopped itself. Now one timer per
  date: two stretches with the same pattern become one, otherwise the longest
  is copied and the others are listed as not copied. (Reproduced in
  `tests/repro_calendar_same_day.py`.)
- Its timers are numbered from 1, as the Trimlight app numbers its own.
- A rejected Client ID and Secret (code 10002) now says what to check,
  including this computer's date and time.
- Setup › Location & time no longer sends an empty place-name search.
- A browser sweep of every page (desktop and phone width) with every panel
  open, pressing every button and changing and restoring every checkbox and
  list, found no page errors and no layout overflow besides these.

## 4.3.8: from the first real use of local mode and the backup timer

- **Backup timer:** on Nov 16 it wrote its 14 calendar timers and stopped
  itself at once: "14 entries differed". The safety worked (it took them back
  and wrote nothing more), but every entry differing at once looks like
  Trimlight's cloud not having updated its copy yet. It now reads back again
  after 5 and then 20 seconds before calling it a mismatch, and the log says
  what an entry was written as and what came back, so a real difference can
  be found.
- **Local mode:** on Nov 15, three patterns went back in a row and the fourth
  wasn't on the controller a second later, yet putting it back again minutes
  afterward worked. A read that doesn't match yet is now repeated after a
  pause, and a change that left the controller exactly as it was is sent once
  more. Any other difference still stops.
- **Cloud reads** (the controller list, the controller's details) are tried
  once more after a network hiccup, such as "Network error calling
  /v1/oauth/resources/devices: timed out" on the Lights tab. Changes are
  never repeated.
- The backup timer's status line says "(last copied …)" next to the date, so
  an older date next to a newer message isn't confusing.

## 4.3.7: review fixes (one connection to the controller)

- **Fixed (most important):** reads and changes over the home network took
  turns on the connection, but starting **Music from this computer** didn't.
  A show started while a panel was reading opened a second connection, which
  the controller doesn't answer, so the show could fail with "didn't answer".
  A show now waits its turn too (before the app steps aside for it), and a
  read or change checks for a show once it has the connection. (Reproduced in
  `tests/repro_show_vs_read.py`.)
- **Fixed:** **Back up now** saved the most recent shared read rather than
  its own; a change elsewhere at that moment could make it fail.
- **Fixed:** a read shared between panels (5 seconds) could be of the
  previous controller right after its address was changed.
- Waiting for the connection gives up after 20 seconds (was 30), so a page
  never waits about a minute.
- **Fixed:** with only score celebrations on, a team whose pattern had been
  deleted silently never celebrated. Saving now says to choose its pattern,
  as game-day lights already did.

## 4.3.6: local mode reads reliably, and Back up now

- **Fixed:** Pattern backups could say "Couldn't read the controller: The
  controller didn't answer" while Test connection read it fine. Opening
  Setup › Lights & controller, the Local mode and Pattern backups panels read
  the controller at the same moment on two connections, and the controller
  seems to answer one at a time; a plain read also skipped the keep-alive
  that Test connection sends first. Now there is one connection to the
  controller at a time (music test, reads and changes alike), each starts
  with a keep-alive answered, a read that gets no answer is tried once more,
  and panels opened together share one read.
- Pattern backups still lists the backups when the controller can't be read
  just now (putting back waits until it can), instead of showing only the
  error.
- **Back up now** in Local mode saves what the controller holds (patterns and
  ports) on this computer, lists it under Pattern backups and downloads a
  copy.
- Reading the controller during a music show from this computer says to stop
  the show first, instead of timing out.

## 4.3.5: score celebrations have their own switch

- **Celebrate scores** is now its own switch, separate from **Use game-day
  lights**: celebrations work with game-day lights off (flashing over your
  normal schedule), and game-day lights work without celebrations. Before,
  celebrations only ran while game-day lights were on.
- Each team still has **Celebrate this team's scores**. A team's schedule is
  checked when it has game-day lights or celebrations on.
- Settings from before keep working as they were (the one switch ran both).
- The folded panel's summary says which are on ("lights + celebrations").

## 4.3.4: tests pass on GitHub again

- **Fixed:** the tests' sample controller files (tests/data, new in 4.3.0)
  never reached GitHub: the ".gitignore" line that keeps your private data
  folder out (data/) matched them too, so the local-mode tests failed there on
  Ubuntu and Windows. Only the app's own data folder is ignored now, and a
  test checks the sample files aren't.
- A test of the background services started the real holiday and score
  threads, which then logged "Cannot operate on a closed database" for the
  rest of the run. They're stubbed out like the others.
- After a change over the home network, the app asks the controller to
  update Trimlight's cloud in the background; if the app was closing at that
  moment, that printed an error. It's now only noted in the log.

## 4.3.3: ESPN review fixes

- **Fixed (most important):** since 4.3.2 a game starting after midnight
  counts for the evening before, but on that evening the score watcher only
  asked ESPN's board for that day, which doesn't list the game, so the panel
  said "Not on ESPN's scoreboard today" all evening. It now also looks at
  tomorrow's board for a game starting within 12 hours. (Reproduced in
  `tests/repro_scores_late_game.py`.)
- **Fixed:** the wait before a game was worked out with the computer's clock
  while everything else in the score watcher used its own, so a test clock
  (or a clock change) could make it check too early or too late.

## 4.3.2: game-day lights review fixes

- **Fixed (most important):** the regular season was asked for with no season
  type, so ESPN answered with whatever it calls current. In the preseason that
  is the preseason: preseason games lit up, and the season opener wasn't known
  until ESPN flipped over, often the day before or the day of. The regular
  season and the playoffs are now asked for by name. (Reproduced in
  `tests/repro_gameday_seasontype.py`.)
- **Fixed:** postponed and canceled games still lit up their nights.
- **Fixed:** a game starting after midnight local time (a late West Coast
  start) lit up the night after; it counts for that evening now. A game whose
  time ESPN hasn't set yet uses ESPN's own date.
- **Fixed:** an answer from ESPN listing no games at all (as during its
  rollovers) erased the nights already known. They're kept now, and the panel
  says so.
- **Fixed:** "Check now" and the background check could ask ESPN at the same
  time; one runs at a time.
- **Fixed:** changing the time zone left game nights worked out in the old
  one for up to 12 hours; they're worked out again at once.
- Schedules are checked every 6 hours (was 12), so a game moved on short
  notice (an NFL flex, a playoff date) is picked up sooner.
- **Fixed:** a second score within 45 seconds of a celebration was never
  celebrated; it's celebrated when the 45 seconds are up.
- The panel says "Not checked while game-day lights are off" instead of
  "Schedule not checked yet" when the switch is off.

## 4.3.1: review fixes (local mode)

- **Fixed (most important):** switching a port off over the home network was
  checked by reading back its first and last bulb, but what the controller
  reports for a port that is off has never been seen. If it reports anything
  else (0-0, say), a correct save of your layout (ports 3 and 4 off) would be
  called a failure and stop halfway. An off port's numbers are no longer
  judged; every other port still is. (Reproduced in
  `tests/repro_off_port_readback.py`.)
- **Fixed:** a pattern read back was compared byte for byte, including color
  slots that hold no bulbs. If the controller tidies those, every correct save
  would stop a restore after the first pattern. Now the name, motion, speed,
  brightness and the slots that hold bulbs are compared.
- **Fixed:** reading the controller over the home network sets its clock, and
  that ignored the clock offset in Setup › Location & time (so did Music from
  this computer since 4.1), moving the clock the backup timer's timers run on.
- **Fixed:** two local-mode jobs at once (two pages, or ports and a restore)
  could interleave their changes on two connections. One runs at a time now,
  and a music show from this computer waits for it.
- **Fixed:** a port list naming one port twice could set the wrong port.
- **Fixed:** an answer from the controller shorter than its own header was an
  error page instead of a clear refusal.
- **Fixed:** local mode needed Trimlight's cloud to know which controller it
  was; it uses the controllers it already knows when the cloud is down.
- **Fixed:** saving a pattern with a name over 25 characters cut the name
  short on the controller (so the backup timer, which matches by name,
  couldn't find it). Such names are refused with a clear message.

## 4.3.0: local mode, and no pattern writes through the cloud

- **Local mode** (Setup › Lights & controller, Administrators): the app reads
  and changes the controller straight over the home network, as the Trimlight
  Edge app does when it shows "Local". The panel lists the ports and every
  pattern saved on the controller, read from the controller itself, with a
  **Delete** for each.
- **Nothing saves or deletes patterns through Trimlight's cloud any more.**
  Every 12006 so far followed one, and on Nov 13 deletes by number, sent while
  the cloud's copy was out of step, removed the owner's own patterns (by Nov
  15 the controller held 11 of its 19). Now:
  - **Pattern backups › Put back selected** works over the home network, one
    pattern at a time, each read back. A pattern gets its old number when
    that's free, so the Trimlight app's timers find it again.
  - **Also save it on the controller** in the designer saves over the home
    network.
  - **Delete** checks that the number still holds the pattern of that name.
  - Turning the **backup timer** off no longer deletes old "Auto" patterns; it
    names them, to delete in Local mode.
  - The **hardware test** no longer saves a test pattern; its timer test uses
    one of the controller's own patterns.
- **Ports** are saved over the home network when the controller's address is
  known, where a port marked **Not connected** is really switched off. Saving
  ports works even while Trimlight's cloud can't read the controller.
- How it stays safe: the controller is read and backed up first; changes go
  one at a time, each read back and checked (the change is there exactly,
  nothing else changed, no two patterns on one number); it stops at the first
  difference. The backup timer holds off meanwhile.
- The layout of the controller's own messages (patterns, ports) was decoded
  from captures and checked against its cloud backup byte for byte: the
  owner's patterns encode exactly as the controller held them.

## 4.2.1: feature search, and a backup timer that can't break a controller

- **Search features** at the top of every page. Type a few letters ("backup",
  "eagles", "ports", "sunset") and choose a result, or press Enter for the
  first: the app goes to that page, opens the panel, scrolls to it and
  outlines it. **/** jumps to the box from anywhere; Esc clears it. Works with
  the keyboard and screen readers, and on a phone.
- **Fixed (serious): the backup timer could leave a controller unreadable.**
  On Nov 15, 2026 it saved "Auto 0-Security" and "Auto Fall" through
  Trimlight's cloud; the controller didn't read back as written and the cloud
  answered 12006 ("declared 13 and scanned 13 effect records"). Unplugging the
  controller then reset it to its factory patterns. Now:
  - It **never saves patterns.** Each night uses a pattern already saved on
    the controller with the same name; a night whose pattern isn't there is
    skipped and listed under "Not copied". It only writes its own calendar
    timers.
  - It writes only to a **settled** controller: two readings at least 2
    minutes apart must match (patterns, calendar, daily timers).
  - **No writes during a music show**, local-link use, or the 15 minutes
    after.
  - On a read-back mismatch or a 12006 it removes its timers and **stops
    itself**. It writes nothing more until it is turned off and on again. It
    no longer deletes patterns by number to "repair" a controller (after a
    reset, a number can belong to any pattern).
  - It notices when a night's pattern number now holds a different pattern.
  - Turning it on asks first, and says what it will and won't do.
- **Pattern backups** put patterns back one at a time and read the controller
  back after each, stopping before another save at the first sign of trouble.
- **Fixed:** at the end of a show, **Music from this computer** sent `04 0e`,
  which a new capture showed means "show saved pattern #14", not "leave music
  mode". It sends nothing now; the schedule's next pattern ends the show.
- The capture kit decodes the newly understood messages: show and delete
  saved pattern #N, port pixels, new and saved pattern records (name, mode,
  speed, brightness) and the live pattern preview.

## 4.2.0: music patterns by name, and their color

- **Music from this computer** lists the controller's **18 built-in music
  patterns by name**, in the Trimlight app's order (1. Full Color Rhythm
  Spectrum … 15. Independence Day, 16. Christmas, 17. HeatBeat, 18. Party),
  instead of numbers up to 20 (there are 18).
- **Color** for the seven "Single Color" patterns: a color choice appears
  next to the pattern, is remembered on this computer, and can be changed
  while the show runs. A fourth capture showed the three bytes after the
  pattern number follow the Trimlight app's color bar (red, green, blue);
  until now they were always sent as red.
- The capture kit names the pattern and shows its color in "music settings".

## 4.1.4: review fixes (music from this computer)

- **Fixed (most important):** the keep-alive sent every 5 seconds waited for
  its answer, up to 3 seconds, and no sound levels went out meanwhile: on
  busy Wi-Fi the lights froze to the beat every few seconds (12 level frames
  in 4 seconds instead of about 36), and a late answer could end a working
  show as "connection lost". Keep-alives no longer wait; answers are counted
  as they arrive, and only 15 seconds with no answer at all counts as lost.
  (Reproduced in `tests/repro_keepalive_stall.py`.)
- **Fixed:** two pages starting a show at the same moment could both
  connect, leaving two streams and a thread that couldn't be stopped. A start
  is now claimed before connecting; the second is told one is already
  starting.
- **Fixed:** anything the controller sent that this app didn't understand (a
  newer firmware's message, a damaged frame) counted as a lost connection.
  It's now skipped up to the next message and noted once in the log.
- **Fixed:** the controller's address check let `0.0.0.0` through (which
  reaches this computer itself), and 169.254.x and 240.x. Only home-network
  device addresses (10.x, 172.16-31.x, 192.168.x) are accepted now.
- **Fixed:** the server let a show from this computer start over another
  music show or a show night (only the page's button was off), and stopping
  it then ended the show night too. It now says which show is on.
- **Fixed:** Home's "answering" check could run twice at once, and a slow
  check finishing after **Test connection** replaced its answer.
- **Fixed:** **Stop** could answer before the schedule was back, and a
  stream winding down late could end a show started right after it. Each
  show now has its own ID, and Stop hands the lights back itself.
- The release build shows a warning on its page if building PyInstaller's
  launcher from source fails, so Defender's false alarm can't quietly return.
- **Capture kit:** TCP sequence numbers that roll over, and re-sent pieces
  that overlap differently, no longer cut the decoded stream short.
- The page keeps the input level in memory while listening instead of
  reading saved settings ten times a second.

## 4.1.3: the Music tab stays put; sharing sound

- **Fixed:** the Music tab rebuilt itself every 15 seconds, so the page
  jumped and open menus closed. It now redraws only when the music show
  starts, stops or changes, never while you're using it, and Music from this
  computer no longer blanks while it checks its status.
- **Sharing sound:** the share window now opens on the list of browser tabs:
  pick the tab playing the music and keep "Also share tab audio" on (on by
  default). "Also share system audio" for Entire screen doesn't appear on
  every computer.
- **Firefox and LibreWolf** can't share sound at all; the page now says so
  up front ("Edge or Chrome only") instead of after the share window.
- The page and the Manual explain **Stereo Mix**, which lets any browser
  (LibreWolf included) hear everything the computer plays.
- **Windows Defender false alarm** ("executes commands from an attacker" on
  EaveLuxOS.exe): the Windows build now compiles PyInstaller's launcher from
  source instead of using the ready-made one that countless programs share
  (malware included), and the .exe carries its name, publisher and version
  under Properties › Details. Each release now lists **SHA256SUMS.txt**, so a
  download can be checked against what GitHub built. The Manual's
  Troubleshooting says how to check, restore and report it.

## 4.1.2: the controller's address on Home

- **New:** Home shows the controller's IP address on your home network and
  whether it's answering there, above Controllers and activity. Trimlight's
  cloud doesn't report the address, so it's the one entered under Music ›
  Music from this computer; until then, Administrators see a link to add it.
  The app checks every 5 minutes, in the background, by opening and closing
  a connection (nothing is sent); **Test connection** updates it at once.
  "Not answering" usually means the router handed out a new address.

## 4.1.1: the capture tool on a Windows screen

- **Fixed:** `summarize_capture.py` without `--out` stopped with
  "UnicodeEncodeError: 'charmap' codec can't encode character" on Windows,
  where Command Prompt isn't UTF-8 and the report has characters like "↔".
  It now prints the report as UTF-8 everywhere. (Found by the GitHub tests on
  Windows; the test now runs the tool with a Windows-style console.)

## 4.1.0: music from this computer (experimental)

- **New: Music from this computer** (Music tab). The lights dance to music
  the app computer hears or plays, beat by beat, with no phone. This app now
  talks to the controller directly on the home network, the way the
  Trimlight app does in music mode: the browser measures the music in 16
  bands, about 9 times a second, and the app passes that to the controller.
  Listen through a microphone or line-in, or to the computer's own sound
  (screen sharing with system audio, in Chrome or Edge). Music pattern,
  sensitivity and how long are chosen on the page; it steps aside like any
  music show and hands the lights back when stopped, when the page closes or
  goes quiet, or when the connection is lost. Off until an Administrator
  enters the controller's address; Editors can run shows.
  - Worked out from a capture of the Trimlight app (firmware 1.17.77): the
    app finds controllers on UDP port 8589 and talks on TCP port 8586, in
    "SPTECH" frames with an MD5 of the contents and a one-byte scramble; no
    account or key is involved. See `eaveluxos/lanlink.py`.
  - A second capture showed the rest: lights off and on, and leaving
    Music. A show now ends the way the Trimlight app leaves Music (out of
    music mode), then the scheduled pattern comes back. The greeting is new
    each time, as the app's is.
  - **Test connection** (says hello) and **Read the controller** (sets its
    clock and lists the patterns and timers it holds, as the Trimlight app
    does on opening). **Find** asks the network for controllers.
- **Capture kit:** `summarize_capture.py` now puts Trimlight's messages back
  together and decodes them in plain words ("music settings: input …; music
  pattern 2; sensitivity 14", "sound levels …", "set the controller's
  clock …", "lights off", "back to normal (out of music mode)"), with
  repeats and retransmissions shown once.
- The controller's local address is this home's own: it isn't exported or
  taken from an imported file, and only an Administrator can change it.

## 4.0.3: saving ports ("Invalid parameter [port -> id]")

- **Fixed:** **Save to controller** on Setup › Lights & controller failed
  with "code 12000 (Invalid parameter [port -> id].)" on controllers that
  report their ports as 1–4 (Trimlight Edge firmware 1.17.77). The cloud
  shows those ports as 1–4 but wants them numbered 0–3 when saving. A
  refused save changes nothing, so the app now tries the other numbering
  once, remembers what worked for that controller, logs it, and reads the
  controller back to check every port landed where it was meant to; if one
  doesn't show yet, it says so instead of "Ports saved". Any other refusal
  is reported as before, without a second try. (Reproduced in
  `tests/repro_port_ids.py`.)
- The test cloud now checks a whole save before changing anything, like
  the real one, and can number ports the way firmware 1.17.77 does.
- README: "safety net" is now "backup timer", as in the app, and the
  pattern designer line mentions named colors and describing a pattern.

## 4.0.2: the tidiness test checks the repository

- The test that keeps stray folders out of the project (3.19) now checks
  what's in the repository, not every folder on disk, so a folder of your
  own next to the code doesn't fail it. A folder that is committed by
  mistake still does, with how to fix it.
- `.gitignore` leaves out `Claude outputs/`, so `git add -A` never commits it.

## 4.0.1: review fixes (saving, New pattern, phones)

- **Fixed (most important):** changes made quickly one after another (a few
  clicks on a number field, two settings changed together) kept only the
  first and showed "changed on another device". Saves now wait their turn,
  only what each one changed is put on top of the latest settings, and
  saves waiting together go as one, so version history isn't filled with
  tiny steps. A real change from another device is still caught.
  (Reproduced in `tests/repro_quick_saves.py`.)
- **Fixed:** **New pattern** didn't open the designer. It never had, but
  Create used to have its own tab; in 4.0 it's the way in.
- **Fixed:** on a phone, the Setup section you're in was off the screen.
- **Fixed:** on a phone, the tab bar sat on top of the keyboard while
  typing; it steps aside now.
- **Fixed:** Viewers could change Alerts controls (the change wasn't saved).
- "Coming up" shows the next night once tonight's lights are off; Holidays
  and Game-day lights show what's next ("next: Thanksgiving, Thu, Nov 26").
- Folded panels load when opened, not on every visit.
- The browser's **Back** button returns to the previous tab.
- Folding panels tell screen readers what they open; leftover webhook code
  removed from Setup; where each address goes is in `nav.js` and the save
  merging in `merge.js`, both tested with Node on every machine.

## 4.0.0: a new layout (seven tabs)

Nothing was removed or changed in how the lights run; the app is
reorganized so each tab has one job.

- **Seven tabs** instead of ten: Home, Patterns, Schedule, **Alerts**, Music,
  House and **Setup**. The pattern designer (Create) opens from Patterns
  (**New pattern**, **Edit**, **‹ Patterns** back); the Manual is the **?**
  button at the top of every screen.
- **Schedule** has two parts: **Every night** (rules, Coming up) and
  **Special days** (holidays, game-day lights, away mode).
- **Alerts** (new) gathers everything that reacts: weather rules, severe
  weather alerts, the security flash, webhooks and phone alerts.
- **Setup** has four sections: **Lights & controller** (with the backup
  timer, color correction and pattern backups), **Location & time** (was
  Date & Time), **Accounts & access** and **App** (were Settings).
- **Folding panels** with a one-line summary ("Holidays · 3 holidays",
  "Security flash · Security white for 5 min"); the app remembers which
  ones you keep open. On a phone the Schedule tab went from about 9 screens
  of scrolling to about 3, and Settings' 7 became Setup sections of 2 to 3.
- **On phones the tabs are along the bottom**, all seven always in reach.
- **Saving is consistent**: the security flash and the usual show length
  save as you change them, like the rest of the app.
- **Plainer names**: the safety net is now the **backup timer** (also in the
  event log); Address space is **Bulb numbering**; the screen theme button
  says "Theme" so it isn't mistaken for the lights' automatic mode.
- Old bookmarks still work: `#settings`, `#lights`, `#time`, `#create`.
- The Manual has a "Where things are" guide and renamed chapters to match.

## 3.20.0: named colors (the RGB charts)

- **Color by name or code** (Create): type a name ("crimson", "forest green";
  suggestions as you type) or a code from an RGB chart ("FF1493", "#FF1493",
  "255 20 147", "FF 14 93"), or paste a list or chart rows to use as the
  pattern or add after the selected color.
- **Named colors…**: the 141 standard web color names, grouped like the
  charts, searchable, each with a note on how it looks on LED lights
  (whites and pale colors look white, grays are dim white, browns look
  orange, dark colors are dim versions); a switch shows only the colors that
  show well.
- Colors have names everywhere: the selected color in Create, and any color
  strip when you hold the pointer over it ("#E0A060 · near Sandy Brown").
- **Describe it** knows all the names ("crimson and forest green chase",
  "midnight blue twinkle"); the app's own color words and themes still win,
  and "dim gray" or "dark green" is a color, not a dimmer pattern.
- Crimson is now exactly the standard #DC143C (in Describe it and the
  Thanksgiving and Columbus Day themes).

## 3.19.1: review fixes (share codes, public holidays, holidays)

- **Fixed (most important):** a share code pasted with the rest of a message
  ("Here's my pattern: ELX1:… enjoy!") was often refused as damaged: every
  space was removed to rejoin wrapped lines, which glued the next word on.
  Only line breaks are joined now, and a code must end exactly where its
  data does, so a damaged code is reported, never half-read.
  (Reproduced in `tests/repro_share_message.py`.)
- **Fixed:** checking another country's holidays replaced the chosen
  country's dates; each country is kept separately, and only the chosen
  one can be checked.
- **Fixed:** after choosing a new country, a failed first check wasn't
  retried for a week; it's retried within hours.
- **Fixed:** deleting a pattern a holiday uses gave a confusing error; it now
  says which holiday uses it.
- **Fixed:** big QR codes were wider than a phone screen.
- **Fixed:** Viewers saw Share but were refused; they can make codes now.
- Restarting the app on a holiday no longer announces it twice.
- "Next" says when a holiday season's lights start ("lights from …").
- Dates moved for past years are dropped, so they never pile up.
- Adding several shared patterns is one save; a holiday never clashes with
  your own rule names; the holiday service can't redirect elsewhere; Check
  now works once a minute; the Holidays panel loads faster.

## 3.19.0: holidays that find their own dates, share codes and QR codes

- **Holidays** (Schedule tab): pick holidays and give each a playlist; the
  app works out the date every year and loads the playlist that morning.
  Fixed dates, rules (Thanksgiving, Memorial Day, Mother's Day…), Easter and
  the days from it, Rosh Hashanah and Hanukkah from the Hebrew calendar
  (exact for any year), and Lunar New Year, Holi, Diwali and the Eids from
  published dates through 2035. Days before and after make a season; a date
  can be moved for one year. Each comes with ready-made themed patterns.
  Holidays (priority 210) beat seasons and the everyday schedule; game days
  beat holidays.
- **Another country's public holidays** from the free Nager.Date service
  (weekly, kept in a file, only the country code sent), with one playlist.
- **Share codes and QR codes** (Patterns): share a pattern or up to 8 as a
  playlist as an `ELX1:` code and a QR code drawn by the app. **Open a share
  code** previews before adding; codes are checked like Community patterns
  (only colors and motion get in, size limits before and after unpacking).
  Browsers that can read QR codes can scan one, or read it from a picture.
- Removed a test screenshot folder (`ui3182`) that slipped into 3.18.2.

## 3.18.2: review fixes (mood follow, AI key, night curves, ports)

- **Fixed (most important):** mood follow during a severe weather warning
  dismissed the warning (for up to 7 days), because it went through the same
  path as choosing a pattern by hand. Mood follow now ranks below everything
  you or the house decided: an alert stays on top and isn't dismissed, a
  music show keeps running, and a pattern chosen by hand wins until it ends.
  (Reproduced in `tests/repro_mood_alert.py`.)
- **Fixed:** saving or removing the AI key didn't ask for the app password
  again, as other credentials do.
- **Fixed:** mood follow counted timer ticks to know when 10 seconds had
  passed. Browsers slow timers in background tabs (Chrome to once a minute),
  so reports could stop and the lights went back to the schedule while music
  played. It now goes by the clock, and samples from the audio thread.
- **Fixed:** 30 seconds of quiet (or Stop) ended any pattern chosen by hand,
  not just mood follow's own.
- **Fixed:** two listening pages flipped the lights between them. One page
  listens at a time; closing it hands the lights back right away.
- **Fixed:** a night curve restarted a moving pattern's motion every 10
  minutes; moving patterns now step every 30. A weather pattern keeps its own
  whites (and still dims with the curve).
- **Fixed:** saving only some ports (an older page or the API) marked the
  rest connected again.
- **Fixed:** "warm white and white" gave only warm white.
- **New:** AI ideas are limited to 6 a minute and 100 a day (they cost money
  on your key), and the AI model is a setting, with a clear message when a
  model is retired. Only an Administrator can change it, and files don't
  carry it.
- The note when mood follow ends says so, instead of "Preview ended".
- The "bulbs 1–600" note on the Lights tab no longer shows for ports you
  set up there, and has an **It's really connected** button.
- The hardware test reports a cloud that accepts a port at 0-0 without
  failing when it can't put the port back.

## 3.18.1: ports that aren't connected

- **Fixed:** saving ports with one turned off failed with "code 12000
  (Invalid parameter [port -> start])". The app sent start 0, end 0 to mean
  "off", and Trimlight's cloud has no off for a port. A port marked **Not
  connected** now keeps the numbers the controller already holds (nothing
  invalid is sent), and this app remembers to leave it out of the bulb count,
  the bulb finder and the house tools.
- Ports that read **bulbs 1–600** (how the controller reports a port that was
  never set up) are pointed out on the Lights tab, so the app can count the
  real bulbs instead of 600.

## 3.18.0: describe a pattern, night curves, mood follow

- **Describe it** (Create): type "cyberpunk rainy night" or "slow candy cane
  twinkle" and get colors, motion, speed and brightness to adjust and save.
  Built in (themes, color, motion and speed words; free, on this computer),
  or with Claude through your own Anthropic API key (Settings › AI pattern
  ideas; stored encrypted, never exported; the answer is checked like any
  pattern). **Try another** gives other takes.
- **Night curves** (rules): 2 to 6 points of time, white and brightness; the
  lights change at every 10-minute mark between them. Whites take the
  curve's color temperature, other colors keep their hue. A brightness set
  by hand wins. The safety net copies the opening look. Home shows where the
  curve is.
- **Mood follow (beta)** (Music): the app computer's microphone (a browser
  allows it only on the computer itself) tells calm, lively and party music
  apart every 10 seconds and switches between three of your patterns. The
  mood, not the beat (Trimlight's cloud is too slow for that). Ends by itself
  after 30 seconds of quiet or 3 minutes after the page closes. Sound is
  never recorded or sent; only the mood is.
- The app's pages may now use the microphone (Permissions-Policy
  `microphone=(self)`), for mood follow; other sites still can't.

## 3.17.1: fixes from the code review of 3.17.0

- **Fixed:** a rule's brightness and speed flattened a pattern split by
  controller: a slow, dim twinkle upstairs ran at the garage's speed and
  brightness. Each part now keeps its own speed, and a rule's or the slider's
  brightness scales every part by the same ratio.
- **Fixed:** on a controller that takes only 60 bulbs per color slot, a scene
  that fit at 90 could fail when sent. The scene counter now counts at the
  controller's own limit, and the error says why when a pattern can't fit.
- **Fixed:** a malformed scene (from an imported file, for example) was
  accepted and broke the House view; it's refused now.
- **Fixed:** editing a split pattern dropped the part for a controller the
  app wasn't running at that moment.
- **Fixed:** the House map loaded each photo twice at once, and the second
  load could release the first one's copy, leaving a broken photo.
- House view redraws still scenes and patterns twice a second instead of 60
  times (easier on a phone's battery). Scenes made for a different number of
  bulbs, and line bulb numbers past the last bulb, are flagged. Group buttons
  count the bulbs each group really lights. Scenes can be built by typing
  bulb numbers (`10-12, 40`). The manual explains dimming with color
  correction off. New browser tests cover the scene builder and the split
  dialog.

## 3.17.0: the house photo as a design tool

- **Bulbs on each line:** a traced roof edge on the House map can hold its
  bulb numbers (first and last point, counting up or down). The bulbs are
  spread along it, skipping wire-only stretches.
- **House view: preview on your house.** Any pattern made of colors animates
  on the photo, with a Night view. Create has **Preview on house** for a
  design before it's saved. Create's own preview and the house view now share
  one motion model.
- **Scenes:** tap bulbs on the photo (1 to 9 at a time), light every landmark
  named "window" in one step, use groups with their own color and brightness,
  and save the result as an ordinary pattern with the rest of the house dark.
  A live counter shows the controller's 30 color slots. Saved scenes can be
  edited again.
- **Brightness per zone** in Paint by zone (100% to 10%), done by darkening
  the zone's color, since a controller has one brightness per pattern.
- **Split by controller:** with two or more controllers, one pattern can run
  a different pattern on each (or leave one off), each with its own motion,
  speed and brightness. It works in rules, rotations, game days and the
  safety net, and the live check expects a controller left off to be off.
  Importing patterns keeps a split's parts pointing at the right patterns.

## 3.16.1: fixes from the code review of 3.16.0

- **Fixed:** a short alert ended a longer one: a 15-second package alert
  during a 10-minute alarm ended the alarm. Flashes now have an order (the
  security flash and urgent alerts such as `alarm`, then a severe weather
  warning, then other alerts, then score celebrations). A less important one
  is skipped (the webhook reply says `"flash_started": false`), and a shorter
  one hands back to the longer one it interrupted.
- **Fixed:** a score celebration could cut a security flash short when
  "Only while the lights are on" was off.
- **Fixed:** a flash during a music show left its pattern on for the rest of
  the show (it knocks the controller out of music mode). Only urgent alerts
  show during a show now, and they end it, so the schedule runs afterward.
- **Fixed:** a score celebration replaced a severe weather warning.
- **Fixed:** MLB doubleheaders: the first game listed was followed even when
  it was over, so game 2 never celebrated. The game being played is followed.
- **Fixed:** a dismissed weather warning came back each time the Weather
  Service updated it. It now stays dismissed by name until it's over, also
  after a restart; dismissals older than a week are forgotten.
- **Fixed:** changing the weather alert settings dropped a warning that was
  showing for up to 30 seconds.
- **Fixed:** Off (or any pattern) chosen by hand during a warning did nothing
  when warnings turn the lights on; it now dismisses the warning.
- A team that isn't on ESPN's scoreboard on a game day is reported on the
  Game-day panel. Last night's game is followed only until 4 AM, and a game
  that's over is checked every 3 hours, not every 15 minutes. A game still
  being played after midnight is looked up on its own day. A score taken back
  after a review and restored isn't celebrated twice. Old scores are
  forgotten. Viewers no longer see a Dismiss button they can't use. The
  manual explains zones with more than one controller.

## 3.16.0: lights that react to events

- **Alerts from webhooks:** `flash` now takes a pattern, a length in seconds
  and a zone: `{"effect": "package", "zone": "Front porch", "seconds": 30}`.
  Ready-made alert patterns (package, alarm, doorbell, delivery, severe,
  security) work without adding them to your patterns, or send a plain
  `color`. A zone lights only its bulbs (the rest stay dark, the Trimlight
  app's "X"), with the alert's colors spread over it. **Settings › Webhooks ›
  Try an alert** tests one from the app. Plain `flash` is still the security
  flash.
- **Severe weather alerts** (Schedule tab): National Weather Service warnings
  for your location switch the lights to an alert pattern until the warning
  ends: tornado, severe thunderstorm, winter storm, flash flood, hurricane,
  extreme heat or cold, and high wind. Optionally turns the lights on for a
  warning. Never during a music show; **Dismiss weather alert** on Home (or
  the `dismiss_alert` webhook) puts the lights back.
- **Score celebrations** (Game-day lights): when your team scores, the lights
  flash its colors, moving fast, for 10 to 60 seconds, then go back to what
  was on. Live scores from ESPN's free scoreboard, checked every 20 seconds
  during the game; the panel shows the live score. Only while the lights are
  on unless you change that.
- A short flash now ends on time: the scheduler wakes when a flash ends
  instead of at its next 20-second check, and stops promptly.
- Home, Tonight and the activity list name the flash or alert that's
  showing.

## 3.15.1: fixes from the code review of 3.15.0

- **Privacy:** exported pattern files included away mode, with the date
  you're back, and your usage settings; "Replace mine" took someone else's
  away mode. Both are now this home's own: never exported, never imported.
- **Fixed:** choosing a pattern in the Trimlight app twice within about 10
  minutes could get it "learned" as how the controller reports this app's
  pattern, so it was never undone again, even after a restart. Only a report
  that's clearly the same pattern is learned now (never another saved
  pattern, kind or animation), and the file is written outside the status
  lock.
- **Fixed:** putting patterns back from a backup held the command lock the
  whole time (about 3 s per pattern), so a scheduled on/off could wait
  minutes. It's now held for each pattern's save and its wait for the cloud
  together, and released between patterns.
- **Fixed:** two teams with the same name (two "PHI" teams from different
  leagues, or a rule of your own called "Eagles game day") couldn't be saved.
  Game-day rules now get unique names, and "Another team" is named with its
  league.
- **Fixed:** every settings save fetched every team's schedule from ESPN
  again; now only adding a team does.
- **Fixed:** "Tonight" said "Lights on in 4 h" while the lights were on by
  hand; it now says "On by hand · the schedule takes over at …" (and names a
  security flash or music show).
- A second pattern with the same name in a backup is reported as such, not as
  "already on the controller". Monthly usage follows a changed time zone.
  "Check schedules now" runs in the background. Phone alerts and game days no
  longer depend on the update check's switch (EAVELUXOS_BACKGROUND=0 turns
  off all background services).
- Tests: the "Tonight" heading test read Node's output in the old Windows
  character set on GitHub's Windows machine and failed on the "·"; every test
  that runs Node now reads UTF-8, and a check keeps it that way. No change to
  the app.

## 3.15.0: theme switch, favorites, calendar, away mode, game days, alerts and more

- **Light / Dark / Auto:** a theme button at the top of every screen. Auto
  follows the device; the choice is kept per device and applies before the
  page is drawn, so there's no flash of the other theme.
- **Favorites:** star up to 6 patterns on the Patterns tab; they become big
  one-tap buttons on Home, with the rest folded under "All patterns".
- **Tonight on Home:** the next 24 hours of the schedule (sunset, on, a
  switch to another rule, off) with a countdown worked out on the app
  computer.
- **Month calendar:** Schedule › Coming up has List and Month views. Each
  rule has its own color; tap a day for its times.
- **Away mode:** each night's on and off times move by up to 10-60 minutes
  until the day you're back. The same night always moves the same way (a
  restart can't change tonight), and all rules move together so they still
  meet.
- **Game-day lights:** team colors on game nights, with the Eagles, Phillies,
  76ers and Flyers ready to add (any NFL, MLB, NBA or NHL team works). Game
  dates come from ESPN's public schedule twice a day; if it can't be reached,
  the normal schedule runs. Game nights win over seasonal rules.
- **Pattern backups (Lights tab):** put patterns back on the controller from
  the safety net's backups, for example after a factory reset. Only adds,
  backs up first, waits between patterns so each gets its own number, and
  stops with clear advice if one doesn't.
- **Phone alerts (ntfy):** when the lights can't be reached, a controller is
  offline or unreadable, or a new version is out. Once per problem, again at
  most every 6 hours, then "back to normal". Kept out of settings exports.
- **Lights usage:** hours on per month for a year, with an optional cost
  estimate.
- **Fixed:** about 5 minutes after every start, the app resent the pattern
  ("changed outside this app ... Restoring") because the controller reports
  it back slightly differently, which could make the lights flicker. It now
  learns how the controller reports each pattern, keeps that across restarts,
  and keeps checking against it, so a real change in the Trimlight app is
  still caught.
- The Patterns tab won't delete a pattern a game day uses.

## 3.14.1: fixes from the code review of 3.13–3.14

- **Fixed (could delete your pattern):** while Trimlight couldn't read the
  controller, the safety net's repair deleted by number alone. A pattern you
  made that reused a number the safety net once had could be deleted. Now
  the repair only deletes patterns the safety net saved since the last
  successful read (the only ones that can have caused it). If the copy broke
  another way, or while the app was off, nothing is deleted. Every successful
  read also forgets numbers that no longer hold an "Auto" pattern.
- **Fixed (could leave the controller unreadable):** if Trimlight gave a new
  "Auto" pattern the same number as one of yours, the safety net stopped with
  "It will try again later", which couldn't help. Now it names the pattern to
  delete in the Trimlight Edge app, says so on every check (also when turning
  the safety net off) without deleting anything, and carries on by itself
  once the controller reads normally.
- **Fixed:** a calendar conflict with the Trimlight app's own timers re-ran
  every 30 minutes, writing a controller backup each time (which pushed
  useful backups out) and a warning to the log. It now runs once a day, or
  when you change the schedule or tap Update now.
- **Fixed:** a damaged `updates.json` made the Updates panel and the
  new-version bar fail until the file was deleted. Bad values are now
  ignored.
- While the controller can't be read, routine reads ask Trimlight to resync
  at most every 5 minutes (each one waited 3 seconds holding the command
  lock), and a repair is capped at 3 rounds.
- The new-version bar's Download button says "for the app computer" when
  seen on another device. A moved GitHub project gives a clear message
  instead of "GitHub answered 301". The log notes when a controller numbers
  its ports 1-4.
- Tests: the safety net's partial-write test (3.9) no longer passes without
  doing the partial write.

## 3.14.0: tells you when a new version is out

- Once a day (starting a minute after the app starts) the app computer asks
  GitHub for the latest EaveLuxOS release. When it's newer, a green bar at the
  top of every screen says so, with **What's new** and, for the ready-made
  downloads, a **Download** button for this computer's file. **Not now** hides
  it until the next version.
- **Settings › Updates**: the version you have, the last check, release notes,
  **Check now**, and (Administrators) a switch to turn the daily check off.
- Only reads: nothing is sent about the household, nothing downloads or
  installs by itself. The answer is size-capped, a redirect is refused, links
  are kept only if they point into this project on GitHub, and test releases
  are ignored. Kept in `data/updates.json`.

## 3.13.2: Lights tab showed ports one row off

- **Fixed:** controllers that number their ports 1-4 (Trimlight Edge firmware
  1.17.77 does) showed on the Lights tab one row down: Port 1 "off", each port
  showing the one before it, and port 4 missing. Saving would have written
  that shifted layout. The app now detects how the controller numbers its
  ports, shows them as Port 1-4, and writes them back in the controller's own
  numbers (it reads the controller first if it hasn't yet). The hardware test
  labels ports the same way.
- **Safety net:** when removing or reusing its patterns, it now deletes only
  ones whose name still starts with "Auto". A number alone isn't trusted,
  because Trimlight reuses numbers after a delete.
- **Safety net repair:** why a delete fails is now written to the log.

## 3.13.1: fix "Device data could not be parsed" (code 12006)

- **Fixed:** turning the safety net on could break Trimlight's cloud copy of
  the controller. Two new "Auto" patterns saved back to back could get the
  same number from the cloud. After that, every read of the controller failed
  with code 12006 ("declared 21 and scanned 20 effect records"), on the
  Schedule tab and the Lights tab. The safety net now waits for the cloud to
  catch up after each new pattern, and stops (and cleans up) if a number is
  reused anyway.
- **Repair:** when the controller can't be read and the safety net owns
  patterns on it, it deletes its own "Auto" patterns (never ones that were
  there before this app first wrote to the controller), asks the controller
  to resync, and reads again. Turning the safety net off repairs it the same
  way.
- Every controller read now handles code 12006 by asking the controller to
  resync and trying once more. The message says what's going on and what to
  do.
- **Fixed:** if the Trimlight app's own calendar timers cover the coming
  nights, the controller refuses the safety net's timers ("The calendar
  schedules cannot be crossed"), but patterns had already been saved and were
  left behind. Now nothing is written, earlier "Auto" items are taken back,
  and the message explains the choice.
- **Safety:** while a controller can't be read, the Lights tab shows that its
  port layout is unknown and turns off **Save to controller** and **Save
  controller settings**. Before, it showed every port as off and let you save
  that. The server also refuses a layout with every port off.

## 3.13.0: Run the schedule

- The Schedule tab has a **Right now** box that says what the lights are doing
  (following the schedule, or set by hand) and a **Run the schedule** button
  that's always there. It ends anything set by hand (a pattern, Off,
  brightness or speed, a music show from the Music button, a security flash)
  and sends the scheduled lights to the controller again in full, which also
  undoes changes made in the Trimlight Edge app. Show nights keep running.
- Webhooks: `resume` accepts `{"force": true}` to do the same.
- Manual: new "Run the schedule" part in section 13.

## 3.12.4: manual quick start for the ready-made download

- The top of the manual now says that the downloads on the Releases page
  include Python and everything else, so you skip installing Python and the
  zip steps. It lists each download, how to start it, the first-run security
  prompt, and where to continue (section 5).
- Sections 1 and 3 of the manual, and the README's requirements, now say
  Python is only needed when running from source.
- No changes to the app itself.

## 3.12.3: GitHub build updates

- GitHub's build and test workflows use the Node.js 24 versions of their
  actions (`checkout@v6`, `setup-python@v6`, `upload-artifact@v6`,
  `download-artifact@v7`, `softprops/action-gh-release@v3`). GitHub removed
  Node.js 20 from its runners, and the old versions printed deprecation
  warnings and would eventually stop working. Same for the community
  library's two workflows.
- Tests and the release step run on `ubuntu-24.04` instead of `ubuntu-latest`,
  which moves to Ubuntu 26 on its own. The Linux and Raspberry Pi builds stay
  on Ubuntu 22.04 so they keep running on older systems.
- A new test fails if a workflow goes back to an old action version or to
  `ubuntu-latest`.
- No changes to the app itself.

## 3.12.2: community library setup fix

- **Fix in `tools/community-library/README.md`:** it said to protect the
  library repository's `main` branch. That blocks the **Build index** workflow,
  which saves the updated pattern list to `main` after each merge, so new
  patterns would never appear. The step is removed: on a repository you own,
  others can only propose patterns by pull request and only you can merge.
- No changes to the app itself.

## 3.12.1: code review fixes

- **Security: a shared patterns file could make the app computer request any
  address on the home network.** Importing a file with **Replace mine** took
  the community library's address from the file, and opening Patterns ›
  Community then fetched from wherever it pointed (a router's admin page, for
  example). Now the address is an Administrator-only household setting; imports
  never change it and exports leave it out. It must be `https://` (plain http
  only for this computer itself), with no `?`, `#` or user name, and redirects
  are refused instead of followed.
- **A small PNG could make the app use gigabytes of memory.** Images other
  than JPEG are decoded at full size; one 136 KB PNG took about 860 MB. Images
  over 40 megapixels that aren't JPEGs are now refused before decoding, with a
  message. JPEGs (phone photos) are unaffected.
- **Home Assistant: changing the brightness of an off light did nothing.**
  Home Assistant sends only a brightness change, which the app refused while
  the lights were off. The `levels` webhook takes `"on": true` to turn the
  lights on first (tonight's pattern), and the package sends it.
- **Home Assistant: no more "invalid effect" log entries** every 30 seconds
  while the lights were off or a music show ran; the package now reports a
  pattern only when it's one of yours.
- Viewers can no longer send a 30 MB photo upload (refused by size before it
  is read); this computer's addresses are kept for a minute, so Settings opens
  quickly even with a slow name server; and on Windows, when the app runs from
  Python, **Let phones in** says that it unblocks Python itself.
- A refused redirect's connection is now closed.
- 13 new tests (312 total).

## 3.12.0: Home Assistant, whites, recreate, playlists, community library

Five additions, each answering a common complaint from Trimlight owners.

- **Home Assistant and Apple Home.** A new `status` webhook reports what the
  lights are doing without changing anything (with GET or POST; not written
  to the activity list), and every webhook now replies with the full state:
  on/off, pattern and its internal name, why, brightness, speed, and your
  pattern list. `tools/home-assistant/eaveluxos.yaml` is a ready-made Home
  Assistant package: the house lights as a light with brightness and your
  patterns as effects, a pattern sensor, and flash and Return to schedule
  scripts. Through Home Assistant's HomeKit Bridge the light appears in Apple
  Home.
- **Whites by color temperature.** Create and Paint have six whites,
  Candlelight (2200 K) to Daylight (6500 K), and a Warm–Cool slider, mixed
  from red, green and blue (Trimlight bulbs have no white chip) and adjusted
  by the app's color correction like every color.
- **Recreate with my colors.** Every built-in effect can be opened in Create
  with its colors and the closest animation, to recolor. Built-in effects'
  colors are fixed in the controller, so this makes a new pattern that moves a
  little differently, and says so.
- **Playlists.** A rule can give each pattern its own time ("Its own time for
  each pattern": Christmas 10 minutes, Snowfall 5, Warm white 15, then again).
  In a settings file: `rotate_each`. Weather rules can use it too. Existing
  rules are unchanged.
- **Community library.** Patterns › Community lists patterns shared by other
  owners in the public GitHub repository `ThinkTank4n6/eaveluxos-patterns`:
  search, Try, Add to my patterns. Only that pattern is added. The app
  computer fetches the list only when it's opened, over verified HTTPS, with
  size limits; only known fields are kept and each pattern is checked like one
  saved by hand. `tools/community-library` is the repository's starter kit:
  four sample patterns, a checker that builds the index, and GitHub workflows
  that check pull requests and rebuild the index after a merge.
- Color strips now have a thin outline, so white sections show on white cards.
- 34 new tests (299 total).

## 3.11.5: house photos processed by the app; phone connection help

- **Fix: house photos could still come out garbled (stripes) on some
  computers.** The browser now uploads the original photo untouched, and the
  app computer turns it upright, shrinks it and saves it with Pillow, on its
  processor. The browser's graphics never touch the pixels. The browser
  still does it only for files the app computer can't read (an iPhone HEIC
  photo) or when the app runs from source without Pillow, with the 3.11.2
  checks. Original photos up to 30 MB are accepted from signed-in users.
- **New: Settings › Phones and other computers › "A phone can't open it?"**
  Steps to check, and on the app computer **Check this computer**: on
  Windows it reports a network set to Public, firewall rules blocking the app
  (often from pressing Cancel when Windows first asked) and a missing allow
  rule. **Let phones in** switches off the block rules and allows the app's
  port on Private networks, after one Windows permission prompt. It never
  changes a network from Public to Private; the steps for that are shown. On a
  Mac or Linux it shows where to allow the app.
- The address phones use now comes from the network adapter this computer's
  internet traffic uses, with any others listed below it (VPNs and virtual
  adapters could make the old guess wrong). The card says what a working
  address shows: a sign-in page.
- Pillow is now bundled with the app and installed in Docker.
- 20 new tests (265 total).

## 3.11.4: the lights' pattern is checked too

- **Fix: a pattern changed outside this app was never put back.** Every 5
  minutes the app checks each controller, but it only looked at on, off or
  Timer mode. Someone picking another pattern in the Trimlight app, or a
  power cut dropping a pattern that was only previewed, went unnoticed all
  night. The check now also compares the pattern the controller reports as
  running (`currentEffect` in Trimlight's API) with what this app sent, and
  restores it after two readings in a row disagree, the same as for on and
  off.
- If a controller reports a pattern back differently from how it was sent
  (so it would look "changed" every time), the app restores it once, then
  notes it under Controllers and activity and checks only on and off until
  the next pattern or night. Controllers that don't report the running
  pattern are checked as before.
- `main.py make-cert`: the HTTPS key is always created private. A leftover
  temporary file from an interrupted run could have kept looser permissions.
  The key and certificate are now swapped in together, so a failure can't
  leave a mismatched pair.
- Start automatically on Linux: a folder name containing `%` or `$` no longer
  breaks the login service (systemd treats those as placeholders).
- 6 new tests (245 total).

## 3.11.3: code review fixes

- **Fix: an edited pattern could be silently ignored until the next scheduled
  change.** If you saved settings while the app was in the middle of sending
  a command, the send that was already under way marked itself as done and
  cancelled the resend of your new settings. Now a send only counts as done
  if no new settings arrived while it ran. (Stopping a music show and
  "Back to the schedule" had the same race.)
- **Fix: east of UTC (Australia, New Zealand, Europe in summer), morning and
  after-midnight windows were missing** from the week view, the safety net's
  copy, the rule check and the "next show" lookup. They still ran live.
- **Fix: clearing the security-flash pattern during a flash broke the app**
  (the scheduler and Home screen failed until the flash would have ended).
  The flash now just ends.
- **Fix: a network hiccup while saving a pattern with runs over 60 bulbs could
  save it twice** on the controller (an orphan copy using one of its 60
  spaces), and permanently switched to 60-bulb runs. The smaller retry is now
  sent only when Trimlight actually refused the request.
- **Fix: a controller added to the list (or set up on the Lights tab) wasn't
  switched on** until the regular check repaired it about 10 minutes later.
- **Safety net: the Trimlight app's own timers now hold the copy back.** Its
  daily timers, or its calendar events on the coming nights, would also run
  while the controller rests in Timer mode and turn the lights on when the
  schedule says off. The copy is still written, but shows Not armed (and the
  controller rests in Off) until they're off. Calendar events on other dates
  no longer count.
- On, Off, flash and other buttons no longer wait for a safety-net update or
  controller read-back; the scheduler does those on its next pass.
- Weather set to "either": a weather station that's down no longer throws
  away a good forecast (and the reverse).
- `main.py backup` creates the copy private from the start (it holds your
  credentials); before, it was readable by others for a moment.
- `main.py allow-host` no longer says a restart is needed (the running app
  picks up the list right away).
- The Copy button's keyboard hint no longer uses the deprecated
  `navigator.platform`.
- Manual: the safety net's timer copies have no year, so turn it off before
  you stop using the app for good.
- **Fix: "Back to the schedule" ended tonight's music show night.** A show
  night is part of the schedule, so it now keeps running, and one skipped
  earlier tonight (by choosing a pattern or stopping the show) comes back. A
  show started from the Music button still ends.
- **Fix: in Samoa, Tonga and Kiribati (UTC+13/+14), sunrise and sunset were a
  day off,** so every sun-based rule ran on the wrong date.
- **Fix: a weather rule with `rotate = "nightly"` always showed its first
  pattern** (labeled "every 0 min"). It now takes the next pattern each night.
- Fix: a rare crash when the schedule's window cache was cleared by one
  thread while another read it.
- Fix: a saved pattern referenced only by its controller id could take the
  brightness and speed of an unnamed pattern on the controller for the
  sliders.
- 18 new tests (239 total).

## 3.11.2: Start automatically and house photo fixes

- **Fix: "Start this app when the computer starts" showed "Something went
  wrong"** (since 3.10.0, on every system). An import added for the Quit
  button hid the app's start-at-login code from the rest of the settings
  handler. A new test now fails the build if that kind of import comes back.
- **Fix: an uploaded house photo could show as solid green.** On some
  graphics drivers the browser garbles a photo while shrinking it on the
  graphics card. The app now shrinks photos in regular memory, checks the
  result isn't one flat color, tries the browser's other image decoder if it
  is, and otherwise explains what to do instead of saving a bad photo.
- Replacing a photo keeps the rooflines traced on the old one until the new
  photo has actually been read, so a failed upload no longer removes them.
- Photos are saved all at once (written to a temporary file, then swapped
  in), so one can't be read half-written.
- 6 new tests (221 total).

## 3.11.1: Mac setup fix

- **Fix: on a Mac, setup failed with "Trimlight didn't accept these: …
  CERTIFICATE_VERIFY_FAILED … unable to get local issuer certificate".** The
  keys were fine: the Mac app bundles its own OpenSSL, which looks for the
  list of trusted certificate authorities in a folder that doesn't exist
  inside the app, so every secure connection failed. The app now also trusts
  Mozilla's list (the `certifi` package, bundled with the app) and, on a Mac,
  the list macOS ships. Certificate and name checks stay on. The same problem
  silently broke weather rules and the place search on Macs; both are fixed.
- Setup no longer blames your keys when Trimlight couldn't be reached: it says
  "Couldn't check these with Trimlight", and a failed certificate check says
  it isn't a problem with your keys.
- 7 new tests (215 total).

## 3.11.0: controller cards on the Lights tab

- **Accounts with several controllers** (for example House and Deck) now see a
  card for each one at the top of the Lights tab, like the Devices list in the
  Trimlight Edge app: name, online or offline, what its lights are doing (On,
  Off or On its own timer), bulb count, and "Not run by this app" for one
  that's ticked off. Tap a card to manage that controller; the heading shows
  its name. This replaces the small drop-down list.
- Switching controllers with unsaved changes (ports, name, chip, color order)
  asks first, instead of silently dropping them.
- The status at the top right (and its On/Off buttons) now loads on every
  tab and refreshes every minute. It used to say "Starting…" until Home or
  Music had been opened.
- A user's name with "&" or "<" in it no longer shows garbled in the "Delete
  user?" question.
- 5 new tests (208 total). The test stand-in for Trimlight's cloud can now
  hold several controllers.

## 3.10.0: On, Off and Quit at the top of every screen

- **On** and **Off** buttons next to the status at the top right, on every
  screen. On uses tonight's scheduled pattern (or the next one on the
  schedule, then the last pattern turned on by hand, then Warm white). Both
  last until the next scheduled change, like Home's Turn on and Turn off. The
  button matching what the lights already do is grayed out; Viewers don't see
  them.
- **Quit** button, shown only on the computer the app runs on.
- **Fix: Quit now really quits when the app starts at login on Linux or
  macOS.** The login service restarted the app as soon as it exited; Quit now
  asks the service to stop. It starts again at the next login. In Docker,
  Quit explains how to stop the container instead.
- On phones the three buttons show as icons, and below 400 px wide the header
  shows the logo without the name, so it never scrolls sideways.
- 13 new tests (203 total).

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

# Changelog

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

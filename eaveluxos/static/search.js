/* SPDX-License-Identifier: MIT
   Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)

   Feature search (4.2.1): the search box at the top of every page. Each
   entry says where a feature lives: the view (and its tab or section), the
   folding panel to open (f) or the heading to scroll to (h). Plain logic,
   tested with Node. Works as a plain <script> (window.Search) and as a Node
   module (tests). */
(function (root) {
  'use strict';

  // t: title, w: where it is, v: view, x: the view's argument, f: fold key,
  // h: heading to scroll to, k: other words people might type.
  const FEATURES = [
    // Home
    { t: 'Turn the lights on or off', w: 'Home', v: 'home', h: 'Turn on', k: 'power switch quick favorites pinned patterns on off now' },
    { t: 'Brightness and speed', w: 'Home', v: 'home', h: 'Brightness and speed', k: 'dim dimmer bright slider speed fast slow' },
    { t: 'This week', w: 'Home', v: 'home', h: 'This week', k: 'tonight week calendar upcoming when' },
    { t: 'Controllers and their addresses', w: 'Home', v: 'home', h: 'Controller', k: 'ip address local network lan online offline deck front several two three' },
    { t: 'Activity', w: 'Home', v: 'home', h: 'Controller', k: 'log history what happened events' },
    { t: 'Each controller\u2019s home-network address', w: 'Setup › Local mode', v: 'local', k: 'address ip find which controller deck front two three several more add' },
    // Patterns
    { t: 'My patterns', w: 'Patterns', v: 'patterns', x: 'mine', k: 'saved favorites edit delete my own' },
    { t: 'Patterns in the Trimlight app', w: 'Patterns', v: 'patterns', x: 'controller', k: 'controller saved trimlight app import each controller front deck library' },
    { t: 'Built-in effects (180)', w: 'Patterns', v: 'patterns', x: 'builtin', k: 'builtin effects chase rainbow twinkle animation' },
    { t: 'Community patterns', w: 'Patterns', v: 'patterns', x: 'community', k: 'shared download others gallery' },
    { t: 'New pattern', w: 'Patterns › Create', v: 'create', k: 'create make design colors paint editor describe ai' },
    { t: 'Combine patterns by zone', w: 'Patterns › Create', v: 'create', k: 'zone zones combine mix different pattern each section garage roof porch' },
    { t: 'Share patterns', w: 'Patterns', v: 'patterns', x: 'mine', k: 'share code send friend export' },
    { t: 'Open a share code', w: 'Patterns', v: 'patterns', x: 'mine', k: 'import share code receive' },
    { t: 'Split by controller', w: 'Patterns', v: 'patterns', x: 'mine', k: 'split multiple controllers different each' },
    { t: 'House tab with two controllers', w: 'House › Controller', v: 'map', k: 'controller house finder zone side deck front each separately bulb' },
    { t: 'Pattern folders and order', w: 'Patterns › My patterns', v: 'patterns', k: 'folder folders sort order alphabetical a to z christmas easter july organize group' },
    { t: 'A sound when your team scores', w: 'Schedule › Game-day lights', v: 'schedule', f: 'game', k: 'sound horn goal fight song audio mp3 wav' },
    { t: 'A schedule for each controller', w: 'Schedule › a rule › Controllers', v: 'schedule', k: 'controllers each separate individually own rule deck front' },
    { t: 'One controller on or off', w: 'Home › Controllers', v: 'home', k: 'controller own on off individually separately card deck front' },
    // Schedule
    { t: 'Right now', w: 'Schedule', v: 'schedule', h: 'Right now', k: 'current override resume back to schedule' },
    { t: 'Coming up', w: 'Schedule', v: 'schedule', f: 'upcoming', k: 'next upcoming tonight tomorrow' },
    { t: 'Rules', w: 'Schedule', v: 'schedule', h: 'Rules', k: 'schedule times sunset sunrise on off rule rotation nightly dates season' },
    { t: 'Import timers from the Trimlight app', w: 'Schedule', v: 'schedule', h: 'Rules', k: 'import timers daily calendar trimlight' },
    { t: 'Holidays', w: 'Schedule', v: 'schedule', f: 'holidays', k: 'christmas halloween july fourth thanksgiving public holiday' },
    { t: 'Game-time lights', w: 'Schedule', v: 'schedule', f: 'game', k: 'game day game-day lights sports team football baseball basketball hockey nfl nba nhl mlb wnba ncaa college eagles score win touchdown' },
    { t: 'Celebrate scores', w: 'Schedule', v: 'schedule', f: 'game', k: 'score goal touchdown flash celebration party live' },
    { t: 'Away mode', w: 'Schedule', v: 'schedule', f: 'away', k: 'vacation away random times travel' },
    { t: 'Birthdays & anniversaries', w: 'Schedule', v: 'schedule', f: 'dates', k: 'birthday anniversary personal date family wedding every year calendar' },
    { t: 'Studio: layers, gradients and shows', w: 'Patterns', v: 'studio', k: 'studio editor advanced layers gradient keyframes timeline show animation describe words sequence' },
    { t: 'Set up a phone or tablet', w: 'Setup › App', v: 'phone', k: 'iphone ipad android tablet install certificate mkcert home screen qr scan phone setup trust' },
    { t: 'Who\u2019s home', w: 'Alerts', v: 'alerts', f: 'people', k: 'arrive leave geofence presence phone location people family welcome home' },
    { t: 'Siri, Alexa and Google', w: 'Alerts › Webhooks', v: 'alerts', f: 'webhooks', k: 'voice siri alexa google assistant shortcuts say hey' },
    { t: 'Motion lights', w: 'Alerts › Automations', v: 'alerts', f: 'autos', k: 'motion camera sensor frigate driveway porch template' },
    { t: 'API tokens', w: 'Setup › Accounts & access', v: 'access', f: 'tokens', k: 'token api bearer home assistant integration script key' },
    { t: 'Audit log', w: 'Setup › Accounts & access', v: 'access', f: 'audit', k: 'audit log who changed history activity security' },
    { t: 'Encrypted backup', w: 'Setup › App', v: 'app', k: 'encrypted passphrase move new computer whole app' },
    { t: 'Away from home (VPN)', w: 'Setup › Accounts & access', v: 'access', k: 'remote access vpn tailscale wireguard firewalla away from home outside' },
    { t: 'Hand the lights to the controller\u2019s timers on Quit', w: 'Setup › Local mode', v: 'local', k: 'timer mode quit controller own timers fallback' },
    { t: 'Pause the schedule', w: 'Schedule', v: 'schedule', k: 'pause stop hold suspend resume schedule leave lights alone' },
    { t: 'Quick buttons', w: 'Home', v: 'quick', k: 'quick buttons tiles phone scenes favorites one tap big' },
    { t: 'Install on your phone', w: 'Setup', v: 'app', h: 'On your phone', k: 'install phone home screen app pwa iphone android icon shortcut offline' },
    { t: 'Who wins tonight', w: 'Schedule', v: 'schedule', f: 'whowins', k: 'conflict priority overlap wins beats tie override which rule' },
    { t: 'Controller health', w: 'Setup', v: 'health', k: 'health online offline firmware response failures errors 12006 ping' },
    { t: 'Find and match controllers', w: 'Setup', v: 'local', h: 'Local mode', k: 'find discover scan network address controller match ip' },
    { t: 'Install updates', w: 'Setup', v: 'app', h: 'Updates', k: 'update install rollback roll back version automatic sha256' },
    { t: 'Calibrate with the camera', w: 'House', v: 'map', k: 'camera calibrate phone photo find bulbs automatic positions scan video' },
    // Alerts
    { t: 'Automations', w: 'Alerts', v: 'alerts', f: 'autos', k: 'automation if then when rule builder condition trigger event score sunset priority override doorbell' },
    { t: 'Weather', w: 'Alerts', v: 'alerts', f: 'weather', k: 'rain snow temperature wind weather rules' },
    { t: 'Severe weather alerts', w: 'Alerts', v: 'alerts', f: 'wxalerts', k: 'storm tornado warning nws flood hurricane' },
    { t: 'Security flash', w: 'Alerts', v: 'alerts', f: 'security', k: 'security flash bright motion intruder alarm' },
    { t: 'Webhooks', w: 'Alerts', v: 'alerts', f: 'webhooks', k: 'web hook home assistant camera alarm url api trigger automation' },
    { t: 'Phone alerts', w: 'Alerts', v: 'alerts', f: 'phone', k: 'notification push ntfy phone message problem' },
    // Music
    { t: 'Music show', w: 'Music', v: 'music', h: 'Music show', k: 'music show start stop dance' },
    { t: 'Music from this computer', w: 'Music', v: 'music', h: 'Music from this computer', k: 'sound audio microphone share tab spotify youtube local link lan levels music pattern sensitivity color' },
    { t: 'Music zones (sync 2.0)', w: 'Music', v: 'music', h: 'Music from this computer', k: 'music zones bass mid treble beat bpm tempo fft frequency meter glow speed test sync' },
    { t: 'Sound delay', w: 'Music', v: 'music', h: 'Music from this computer', k: 'latency delay sync test lag music file mp3 play' },
    { t: 'Mood follow', w: 'Music', v: 'music', h: 'Mood follow', k: 'mood calm lively party microphone' },
    { t: 'Then, on the controller', w: 'Music', v: 'music', f: 'howto', k: 'trimlight app music mode steps' },
    { t: 'Show nights', w: 'Music', v: 'music', f: 'shownights', k: 'music schedule nights automatic show' },
    { t: 'Show length', w: 'Music', v: 'music', f: 'showlen', k: 'minutes how long duration' },
    // House
    { t: 'House view', w: 'House', v: 'map', k: 'house photo map roofline picture' },
    { t: 'Whole house', w: 'House', v: 'map', f: 'whole', k: 'whole house every elevation tonight timeline animation preview zones play' },
    { t: 'Place bulbs', w: 'House', v: 'map', h: 'House view', k: 'drag bulb position pin move spacing calibrate' },
    { t: 'Elevations and versions', w: 'House', v: 'map', k: 'elevation front side rear version night day before after export import' },
    { t: 'Landmarks', w: 'House', v: 'map', f: 'landmarks', k: 'corner peak door garage marker' },
    { t: 'Zones', w: 'House', v: 'map', f: 'zones', k: 'zone section area paint by zone calibrate align nudge direction reverse' },
    { t: 'Bulb finder', w: 'House', v: 'map', h: 'Bulb finder', k: 'find bulb number locate light blink' },
    { t: 'Bulb numbering', w: 'House', v: 'map', f: 'numbering', k: 'bulb count total numbering order' },
    // Setup › Lights & controller
    { t: 'Lights', w: 'Setup › Lights & controller', v: 'lights', h: 'Lights', k: 'bulbs strand' },
    { t: 'Ports and bulbs', w: 'Setup › Lights & controller', v: 'lights', h: 'Ports and bulbs', k: 'port pixels start end count 1 2 3 4' },
    { t: 'Controller', w: 'Setup › Lights & controller', v: 'lights', h: 'Controller', k: 'controller name firmware online' },
    { t: 'Resync with Trimlight\u2019s cloud', w: 'Setup › Lights & controller', v: 'lights', h: 'Controller', k: 'resync sync 12006 cannot read cloud fix parsed' },
    { t: 'Send commands over the home network', w: 'Setup › Local mode', v: 'local', k: 'local commands on off faster lan without cloud' },
    { t: 'Controlled by this app', w: 'Setup › Lights & controller', v: 'lights', h: 'Controlled by this app', k: 'which controllers several devices' },
    { t: 'Lightning and Snowflake', w: 'Setup › Local mode', v: 'local', h: 'Local mode', k: 'lightning snowflake effect pattern library storm snow flashes' },
    { t: 'Backup timer', w: 'Setup › Lights & controller', v: 'lights', f: 'safety', k: 'safety net offline timers calendar internet down fallback' },
    { t: 'Color correction', w: 'Setup › Color correction', v: 'color', k: 'gamma color accuracy calibrate white balance' },
    { t: 'Pattern backups', w: 'Setup › Pattern backups', v: 'backups', k: 'restore lost patterns reset backup put back' },
    { t: 'Local mode (home network)', w: 'Setup › Local mode', v: 'local', k: 'local lan wifi ip address delete pattern save controller library trimlight list offline 12006' },
    // Setup › Location & time
    { t: 'Date and time', w: 'Setup › Location & time', v: 'time', h: 'Date and time', k: 'clock time date' },
    { t: 'Sun today', w: 'Setup › Location & time', v: 'time', h: 'Sun today', k: 'sunset sunrise dusk dawn' },
    { t: 'Controller clock', w: 'Setup › Location & time', v: 'time', h: 'Controller clock', k: 'clock sync drift controller time' },
    { t: 'Location, time zone and daylight saving', w: 'Setup › Location & time', v: 'time', h: 'Location, time zone', k: 'address latitude longitude timezone dst zip' },
    // Setup › Accounts & access
    { t: 'Trimlight account', w: 'Setup › Accounts & access', v: 'access', h: 'Trimlight account', k: 'client id secret api credentials' },
    { t: 'Your account and password', w: 'Setup › Accounts & access', v: 'access', h: 'Your account', k: 'password sign out logout change' },
    { t: 'Accounts', w: 'Setup › Accounts & access', v: 'access', h: 'Accounts', k: 'users family editor viewer administrator add person' },
    { t: 'Phones and other computers', w: 'Setup › Accounts & access', v: 'access', h: 'Phones and other computers', k: 'phone qr code tablet remote access' },
    // Setup › App
    { t: 'Share and back up settings', w: 'Setup › App', v: 'app', h: 'Share and back up', k: 'export import backup settings file' },
    { t: 'Updates', w: 'Setup › App', v: 'app', h: 'Updates', k: 'update new version upgrade download' },
    { t: 'Setup and about', w: 'Setup › App', v: 'app', h: 'Setup and about', k: 'about version wizard setup again quit' },
    { t: 'App address', w: 'Setup › App', v: 'app', h: 'App address', k: 'port https certificate url address' },
    { t: 'Keep this computer awake', w: 'Setup › App', v: 'app', h: 'Start automatically', k: 'sleep awake power standby hibernate stay on caffeinate mac' },
    { t: 'Start automatically', w: 'Setup › App', v: 'app', h: 'Start automatically', k: 'startup boot windows login autostart' },
    { t: 'Lights usage', w: 'Setup › App', v: 'app', f: 'usage', k: 'hours cost electricity power usage kwh' },
    { t: 'AI pattern ideas', w: 'Setup › App', v: 'app', f: 'ai', k: 'ai key openai anthropic claude describe generate' },
    { t: 'Version history', w: 'Setup › App', v: 'app', f: 'history', k: 'undo history earlier settings revert' },
    // Manual
    { t: 'Manual', w: 'Help', v: 'manual', k: 'help guide instructions documentation how' },
  ];

  const norm = s => String(s || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, ' ').trim();

  /* Best matches first. Every word typed must match the start of a word in
     the title, where it is or the other words (so "back" finds Backup timer
     and "gam" finds Game-day lights). Title matches count most. */
  function find(query, limit = 8) {
    const words = norm(query).split(' ').filter(Boolean);
    if (!words.length) return [];
    const out = [];
    FEATURES.forEach((f, i) => {
      const title = norm(f.t).split(' '), rest = norm(`${f.w} ${f.k || ''}`).split(' ');
      let score = 0;
      for (const w of words) {
        const inTitle = title.some(x => x.startsWith(w)), exact = title.includes(w);
        const inRest = rest.some(x => x.startsWith(w));
        if (!inTitle && !inRest) return;
        score += exact ? 6 : inTitle ? 4 : 1;
      }
      if (norm(f.t).startsWith(words.join(' '))) score += 5;
      out.push({ f, score, i });
    });
    return out.sort((a, b) => b.score - a.score || a.i - b.i).slice(0, limit).map(r => r.f);
  }

  const api = { FEATURES, find, norm };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Search = api;
})(typeof window !== 'undefined' ? window : globalThis);

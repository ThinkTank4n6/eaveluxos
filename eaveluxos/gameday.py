# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Game-day lights (3.15): team colors on the nights your team plays.

Game dates come from ESPN's public site API (the one its own web pages use;
free, no key, not officially documented, so it may change without notice):
  https://site.api.espn.com/apis/site/v2/sports/<sport>/<league>/teams/<team>/schedule
Every 6 hours (4.3.2; it was 12) the app computer fetches each chosen team's
schedule, regular season and playoffs, each asked for by name (4.3.2: asked
for with no season type, ESPN answered with the preseason in September, so
the opener wasn't known in time), and keeps just the dates, in
data/gamedays.json. Postponed and canceled games are left out. A game that
starts after midnight counts for the night before, and one whose time ESPN
hasn't set (timeValid false) for ESPN's own day. If the
source can't be reached or changes shape, the last dates are kept, and with
none the normal schedule simply runs: game days can only ever add a pattern.

Each team becomes a schedule rule that only runs on its game dates (local
time of the game), with a higher priority than seasonal rules (250 vs 200),
so an Eagles game in December shows Eagles colors.
"""
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from .trust import client_context

log = logging.getLogger("eaveluxos.gameday")
LEAGUES = {"nfl": ("football/nfl", "NFL"), "mlb": ("baseball/mlb", "MLB"),
           "nba": ("basketball/nba", "NBA"), "nhl": ("hockey/nhl", "NHL")}
HOST = "https://site.api.espn.com/apis/site/v2/sports/"
TEAM_RE = re.compile(r"[a-z]{2,5}")
MAX_BYTES = 6_000_000
EVERY = 6 * 3600
SEASONS = (2, 3)            # regular season, playoffs (1 would be the preseason)
NOT_PLAYED = ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED", "STATUS_FORFEIT")
EARLY_HOUR = 5              # a game starting before 5 AM belongs to the night before
ESPN_TZ = ZoneInfo("America/New_York")
RETRY = 2 * 3600
PRIORITY = 250

# Ready-made teams (Philadelphia first), with team colors for a one-tap pattern.
PRESETS = [
    {"id": "nfl-phi", "name": "Eagles", "league": "nfl", "team": "phi", "colors": ["#004C54", "#FFFFFF", "#A5ACAF"]},
    {"id": "mlb-phi", "name": "Phillies", "league": "mlb", "team": "phi", "colors": ["#E81828", "#FFFFFF", "#002D72"]},
    {"id": "nba-phi", "name": "76ers", "league": "nba", "team": "phi", "colors": ["#006BB6", "#FFFFFF", "#ED174C"]},
    {"id": "nhl-phi", "name": "Flyers", "league": "nhl", "team": "phi", "colors": ["#F74902", "#FFFFFF", "#F74902"]},
]


class GameDayError(Exception):
    pass


def team_key(league: str, team: str) -> str:
    return f"{league}-{team}"


def check_team(t) -> dict:
    """A team entry from the settings, checked. Raises GameDayError."""
    if not isinstance(t, dict):
        raise GameDayError("Each game-day team must be an object.")
    league, team = str(t.get("league", "")).lower(), str(t.get("team", "")).lower()
    if league not in LEAGUES:
        raise GameDayError("Game-day league must be nfl, mlb, nba or nhl.")
    if not TEAM_RE.fullmatch(team):
        raise GameDayError("Game-day team must be ESPN's short team code, like phi.")
    name = str(t.get("name") or team.upper()).strip()[:30]
    return {"league": league, "team": team, "name": name}


def schedule_url(league: str, team: str, seasontype: int | None = None) -> str:
    url = f"{HOST}{LEAGUES[league][0]}/teams/{team}/schedule"
    return url + (f"?seasontype={seasontype}" if seasontype else "")


def parse_dates(raw: bytes, tz) -> list[str]:
    """Local game dates (YYYY-MM-DD) from an ESPN schedule answer. Forgiving
    about shape: anything that isn't a dated event is skipped."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise GameDayError("The schedule answer wasn't readable.") from None
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        raise GameDayError("The schedule answer had no games.")
    out = set()
    for ev in events[:400]:
        if not isinstance(ev, dict):
            continue
        s = ev.get("date")
        comp = ev.get("competitions")
        c0 = comp[0] if isinstance(comp, list) and comp and isinstance(comp[0], dict) else {}
        if not isinstance(s, str):
            s = c0.get("date")
        st = c0.get("status") if isinstance(c0.get("status"), dict) else ev.get("status")
        name = str(((st or {}).get("type") or {}).get("name") or "") if isinstance(st, dict) else ""
        if name.upper() in NOT_PLAYED:
            continue                                       # 4.3.2: no game that night
        if not isinstance(s, str):
            continue
        s = s.strip().replace("Z", "+00:00")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+00:00", s):    # ESPN often omits seconds
            s = s[:16] + ":00+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if c0.get("timeValid") is False or ev.get("timeValid") is False:
            out.add(dt.astimezone(ESPN_TZ).date().isoformat())   # time not set yet: ESPN's own day
            continue
        loc = dt.astimezone(tz)
        if loc.hour < EARLY_HOUR:
            loc -= timedelta(days=1)                       # after midnight: that evening's game
        out.add(loc.date().isoformat())
    return sorted(out)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url: str) -> bytes:
    if not url.startswith(HOST):
        raise GameDayError("Not a schedule address.")
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=client_context()), _NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "EaveLuxOS", "Accept": "application/json"})
    try:
        with opener.open(req, timeout=20) as r:
            raw = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        e.close()
        raise GameDayError(f"The schedule service answered {e.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GameDayError(f"Couldn't reach the schedule service: {getattr(e, 'reason', e)}") from None
    if len(raw) > MAX_BYTES:
        raise GameDayError("The schedule answer was too large.")
    return raw


class GameDays:
    def __init__(self, data_dir: Path, fetch=None, now=time.time, on_change=None):
        self.path = Path(data_dir) / "gamedays.json"
        self.fetch = fetch or _fetch
        self.now = now
        self.on_change = on_change
        self.lock = threading.Lock()
        self.busy = threading.Lock()         # one refresh at a time (the loop and "Check now", 4.3.2)
        self.tz_used = None                  # the time zone the dates were worked out in
        self.cache = self._load()            # key -> {"dates": [...], "fetched": ts, "error": str|None}
        self.next_at = 0.0
        self.thread = None
        self.stop = threading.Event()

    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        out = {}
        for k, v in (raw.items() if isinstance(raw, dict) else []):
            if isinstance(v, dict) and isinstance(v.get("dates"), list):
                ds = [d for d in v["dates"] if isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)]
                out[str(k)] = {"dates": ds[:500], "fetched": v.get("fetched") if isinstance(v.get("fetched"), (int, float)) else 0,
                               "error": v.get("error") if isinstance(v.get("error"), str) else None}
        return out

    def _save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("Couldn't save game days: %s", e)

    def dates(self) -> dict:
        """key -> set of date objects, for build_config."""
        with self.lock:
            return {k: {date.fromisoformat(d) for d in v["dates"]} for k, v in self.cache.items()}

    def summary(self, teams, today: date) -> list[dict]:
        out = []
        with self.lock:
            for t in teams:
                k = team_key(t["league"], t["team"])
                c = self.cache.get(k) or {}
                nxt = [d for d in c.get("dates", []) if d >= today.isoformat()][:5]
                out.append({"key": k, "name": t.get("name"), "next": nxt, "known": len(c.get("dates", [])),
                            "error": c.get("error"), "fetched": c.get("fetched") or None})
        return out

    def refresh(self, teams, tz) -> bool:
        """Fetch every team's schedule. Returns True if any dates changed.
        A failure keeps the dates already known."""
        with self.busy:
            return self._refresh(teams, tz)

    def _refresh(self, teams, tz) -> bool:
        changed = False
        self.tz_used = str(tz)
        for t in teams:
            k = team_key(t["league"], t["team"])
            dates, err = None, None
            try:
                dates = set(parse_dates(self.fetch(schedule_url(t["league"], t["team"], SEASONS[0])), tz))
                try:                         # playoffs too, when there are any
                    dates |= set(parse_dates(self.fetch(schedule_url(t["league"], t["team"], SEASONS[1])), tz))
                except GameDayError:
                    pass
                if not dates:
                    # 4.3.2: an answer listing no games at all (a rollover at
                    # ESPN) mustn't erase the nights already known.
                    dates = None
                    raise GameDayError("ESPN listed no games for this team just now; the dates already known are kept.")
            except GameDayError as e:
                err = str(e)
                log.info("Game days for %s: %s", t.get("name"), e)
            with self.lock:
                old = self.cache.get(k) or {"dates": [], "fetched": 0}
                if dates is not None:
                    new = sorted(dates)
                    changed |= new != old["dates"]
                    self.cache[k] = {"dates": new, "fetched": self.now(), "error": None}
                else:
                    self.cache[k] = {**old, "error": err}
        with self.lock:
            self._save()
        return changed

    def _loop(self, teams_fn, tz_fn):
        while not self.stop.wait(60):
            tz = tz_fn()
            if self.now() < self.next_at and (self.tz_used is None or str(tz) == self.tz_used):
                continue                     # a new time zone: work the dates out again now (4.3.2)
            teams = teams_fn() or []
            if not teams:
                self.next_at = self.now() + 3600
                continue
            try:
                changed = self.refresh(teams, tz)
                with self.lock:
                    errs = any((self.cache.get(team_key(t["league"], t["team"])) or {}).get("error") for t in teams)
                self.next_at = self.now() + (RETRY if errs else EVERY)
                if changed and self.on_change:
                    self.on_change()
            except Exception:
                log.exception("Game-day refresh failed")
                self.next_at = self.now() + RETRY

    def start(self, teams_fn, tz_fn):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, args=(teams_fn, tz_fn), daemon=True, name="gamedays")
            self.thread.start()

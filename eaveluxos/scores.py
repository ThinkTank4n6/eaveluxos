# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Score celebrations (3.16): when your team scores, flash its colors for a
few seconds, then everything goes back to what was on.

Live scores come from ESPN's public scoreboard (the one its web pages use;
free, no key, not officially documented, so it may change without notice):
  https://site.api.espn.com/apis/site/v2/sports/<sport>/<league>/scoreboard
It is only asked on your team's game days: every 20 seconds while the game
is on, less often before it starts, and not at all afterward. ESPN's feed
runs some seconds behind live TV, and each change passes through Trimlight's
cloud, so the lights celebrate shortly after you see the score, not at the
same moment.

The first score seen for a game is only remembered (so starting the app in
the middle of a game doesn't celebrate the score so far), and a game that's
over is never celebrated.
"""
import json
import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .gameday import BOARD_QUERIES, HOST, LEAGUES, GameDayError, _fetch

log = logging.getLogger("eaveluxos.scores")
LIVE_EVERY = 20          # seconds between checks while a game is on
SOON_EVERY = 60          # within 15 minutes of the start
IDLE_EVERY = 15 * 60     # a game day, game not near
COOLDOWN = 45            # seconds between two celebrations for one team
FINAL_EVERY = 3 * 3600   # after the game: only in case of a second game that day
LATE_HOURS = 4           # a game that started yesterday is followed until 4 AM
KEEP_GAMES = 200
ESPN_TZ = ZoneInfo("America/New_York")    # ESPN's scoreboard days
_ORDER = {"in": 0, "pre": 1, "post": 2}


def scoreboard_url(league: str, day: date | None = None, query: str = "") -> str:
    """Today's board, or a given day's (ESPN's dates=YYYYMMDD); query: a
    college division (BOARD_QUERIES, 4.24)."""
    q = "&".join(x for x in (f"dates={day:%Y%m%d}" if day else "", query) if x)
    return f"{HOST}{LEAGUES[league][0]}/scoreboard" + (f"?{q}" if q else "")


def _as_code(g: dict, team: str):
    """The game with the team under the code it was saved as (4.24: a college
    saved by ESPN's team number appears on the board by its letters)."""
    if team in g["teams"]:
        return g
    abbr = (g.get("ids") or {}).get(team)
    if abbr is None or abbr not in g["teams"]:
        return None
    return {**g, "teams": {(team if a == abbr else a): s for a, s in g["teams"].items()},
            "home": team if g.get("home") == abbr else g.get("home")}


def pick_game(games: list, team: str):
    """The team's game to follow: one being played, else the next, else the
    last one over (an MLB doubleheader lists both games all day)."""
    mine = [x for x in (_as_code(g, team) for g in games) if x is not None]
    return min(mine, key=lambda g: _ORDER[g["state"]]) if mine else None


def parse_games(raw: bytes) -> list[dict]:
    """[{"id", "state": pre|in|post, "start": datetime|None, "detail",
    "teams": {abbr lower: score int}}] from an ESPN scoreboard answer."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise GameDayError("The scoreboard answer wasn't readable.") from None
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        raise GameDayError("The scoreboard answer had no games.")
    out = []
    for ev in events[:100]:
        if not isinstance(ev, dict):
            continue
        comp = ev.get("competitions")
        comp = comp[0] if isinstance(comp, list) and comp and isinstance(comp[0], dict) else {}
        st = (ev.get("status") or comp.get("status") or {})
        typ = st.get("type") if isinstance(st, dict) else None
        state = str((typ or {}).get("state") or "").lower()
        if state not in ("pre", "in", "post"):
            continue
        teams, home, ids = {}, None, {}
        for c in comp.get("competitors") or []:
            if not isinstance(c, dict):
                continue
            abbr = str(((c.get("team") or {}).get("abbreviation")) or "").lower()
            try:
                score = int(str(c.get("score", "0")).strip() or 0)
            except ValueError:
                continue
            if abbr:
                teams[abbr] = score
                tid = str(((c.get("team") or {}).get("id")) or c.get("id") or "").strip()
                if tid.isdigit():
                    ids[tid] = abbr                 # 4.24: colleges are saved by team number
                if c.get("homeAway") == "home":
                    home = abbr                 # 4.11: for automations' home and away
        start = None
        s = ev.get("date")
        if isinstance(s, str):
            try:
                start = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
            except ValueError:
                start = None
        out.append({"id": str(ev.get("id") or ""), "state": state, "start": start,
                    "detail": str((typ or {}).get("shortDetail") or "")[:40], "teams": teams, "home": home,
                    "ids": ids})
    return out


class ScoreWatch:
    def __init__(self, on_score, fetch=None, now=time.time, on_game=None):
        """on_score(team, points, game): called when a watched team scores.
        on_game(team, "start" or "end", game): a game seen starting or ending
        (4.11, for automations); a game first seen already under way or over
        isn't announced."""
        self.on_score = on_score
        self.on_game = on_game
        self.states: dict = {}          # (game id, team key) -> the state last seen
        self.fetch = fetch or _fetch
        self.now = now
        self.lock = threading.Lock()
        self.last: dict = {}            # (game id, team key) -> score
        self.high: dict = {}            # (game id, team key) -> highest score seen (no second party after a review)
        self.live_game: dict = {}       # team key -> {"day": date, "seen": t} for a game being played
        self.last_party: dict = {}      # team key -> time of the last celebration
        self.next_at: dict = {}         # league -> time of the next check
        self.live: dict = {}            # team key -> {"state", "detail", "score", "them", "vs"}
        self.errors: dict = {}          # league -> last error
        self.thread = None
        self.stop = threading.Event()

    def _watching(self, teams: dict, dates: dict, today: date, hour: int | None = None) -> dict:
        """league -> [team settings] for teams playing today (or last night,
        until 4 AM, for a game that runs past midnight)."""
        out = {}
        late = hour is None or hour < LATE_HOURS
        for key, t in teams.items():
            ds = dates.get(key) or set()
            if today in ds or (late and (today - timedelta(days=1)) in ds) or key in self.live_game:
                out.setdefault(t["league"], []).append({**t, "key": key})
        return out

    def check(self, teams: dict, dates: dict, today: date, force: bool = False, hour: int | None = None):
        """One pass: ask ESPN for each league with a game today, when due."""
        now = self.now()
        for league, ts in self._watching(teams, dates, today, hour).items():
            if not force and now < self.next_at.get(league, 0):
                continue
            try:
                games = self._board(league, None, ts)
                self.errors.pop(league, None)
            except GameDayError as e:
                self.errors[league] = str(e)
                self.next_at[league] = now + SOON_EVERY
                log.info("Scoreboard (%s): %s", league, e)
                continue
            wait = FINAL_EVERY
            for t in ts:
                g = pick_game(games, t["team"])
                lg = self.live_game.get(t["key"])
                if (g is None or g["state"] == "pre") and lg and now - lg["seen"] < 6 * 3600:
                    # The game was being played at the last look but today's
                    # board no longer lists it (past midnight): ask for its day.
                    try:
                        g = pick_game(self._board(league, lg["day"], [t]), t["team"]) or g
                    except GameDayError:
                        pass
                if g is None and today in (dates.get(t["key"]) or ()):
                    # 4.3.3: a game after midnight counts for this evening
                    # (gameday.py), but ESPN lists it on tomorrow's board.
                    try:
                        later = pick_game(self._board(league, today + timedelta(days=1), [t]), t["team"])
                    except GameDayError:
                        later = None
                    if later and later["state"] != "post" and later["start"] is not None \
                            and (later["start"] - datetime.fromtimestamp(now, timezone.utc)).total_seconds() < 12 * 3600:
                        g = later
                if g is None:
                    self.live_game.pop(t["key"], None)
                    with self.lock:
                        self.live[t["key"]] = {"state": "missing", "detail": "", "score": None, "vs": "", "them": None,
                                               "code": t["team"].upper()}
                    wait = min(wait, IDLE_EVERY)
                    continue
                if g["state"] == "in":
                    day = (g["start"] or datetime.now(timezone.utc)).astimezone(ESPN_TZ).date()
                    self.live_game[t["key"]] = {"day": day, "seen": now}
                else:
                    self.live_game.pop(t["key"], None)
                wait = min(wait, self._see(t, g, now))
            self.next_at[league] = now + wait

    def _board(self, league: str, day, ts) -> list:
        """A day's games. 4.24: a college league's board is asked for by
        division, the next division only if a team is still missing."""
        games, seen = [], set()
        for i, q in enumerate(BOARD_QUERIES.get(league, ("",))):
            if i and all(pick_game(games, t["team"]) for t in ts):
                break
            try:
                more = parse_games(self.fetch(scoreboard_url(league, day, q)))
            except GameDayError:
                if i == 0:
                    raise
                continue
            for g in more:
                if g["id"] not in seen:
                    seen.add(g["id"])
                    games.append(g)
        return games

    def _see(self, t: dict, g: dict, now: float) -> float:
        """Record a game's score for a team; celebrate a new score. Returns
        how soon to look again."""
        score = g["teams"][t["team"]]
        others = [(a, s) for a, s in g["teams"].items() if a != t["team"]]
        sk = (g["id"], t["key"])
        was = self.states.get(sk)
        self.states[sk] = g["state"]
        while len(self.states) > KEEP_GAMES:
            del self.states[next(iter(self.states))]
        kind = "start" if (was, g["state"]) == ("pre", "in") else "end" if was == "in" and g["state"] == "post" else None
        if self.on_game and kind:
            try:
                self.on_game(t, kind, g)
            except Exception:
                log.exception("Game event failed")
        with self.lock:
            self.live[t["key"]] = {"state": g["state"], "detail": g["detail"], "score": score,
                                   "vs": others[0][0].upper() if others else "", "them": others[0][1] if others else None}
            k = (g["id"], t["key"])
            before = self.last.get(k)
            base = max(before, self.high.get(k, before)) if before is not None else None
            if (g["state"] == "in" and base is not None and score - base >= t["min_points"]
                    and now - self.last_party.get(t["key"], 0) < COOLDOWN):
                # 4.3.2: a second score inside the cooldown used to be
                # forgotten; leave it unseen, so it's celebrated when the
                # cooldown ends.
                return LIVE_EVERY
            self.last[k] = score
            self.high[k] = max(score, self.high.get(k, score))
            for d in (self.last, self.high):
                while len(d) > KEEP_GAMES:
                    del d[next(iter(d))]
        if g["state"] == "in" and base is not None and score - base >= t["min_points"]:
            if now - self.last_party.get(t["key"], 0) >= COOLDOWN:
                self.last_party[t["key"]] = now
                try:
                    self.on_score(t, score - base, g)
                except Exception:
                    log.exception("Score celebration failed")
        if g["state"] == "in":
            return LIVE_EVERY
        if g["state"] == "pre" and g["start"] is not None:
            until = (g["start"] - datetime.fromtimestamp(now, timezone.utc)).total_seconds()   # this watcher's clock (4.3.3)
            return SOON_EVERY if until < 15 * 60 else max(SOON_EVERY, min(IDLE_EVERY, until - 10 * 60))
        return FINAL_EVERY if g["state"] == "post" else IDLE_EVERY

    def summary(self) -> dict:
        with self.lock:
            return {k: dict(v) for k, v in self.live.items()}

    def _loop(self, teams_fn, dates_fn, now_fn):
        while not self.stop.wait(5):
            try:
                teams = teams_fn() or {}
                if teams:
                    now = now_fn()
                    self.check(teams, dates_fn(), now.date(), hour=now.hour)
            except Exception:
                log.exception("Score check failed")

    def start(self, teams_fn, dates_fn, today_fn):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, args=(teams_fn, dates_fn, today_fn), daemon=True, name="scores")
            self.thread.start()

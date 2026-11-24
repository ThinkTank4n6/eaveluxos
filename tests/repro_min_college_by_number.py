"""4.24 review #1: a college team is saved by ESPN's team number (codes like
M-OH or TA&M aren't short letters), but the scoreboard was searched by the
letters only, so Penn State (213) was never found and its scores never
celebrated. Standalone; prints BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
board = [{"id": "401", "state": "in", "teams": {"psu": 14, "osu": 7}, "ids": {"213": "psu", "194": "osu"}}]


def pick_game(games, team):
    for g in games:
        if team in g["teams"]:
            return g
        if FIXED and g["ids"].get(team) in g["teams"]:
            return {**g, "teams": {(team if a == g["ids"][team] else a): s for a, s in g["teams"].items()}}
    return None


g = pick_game(board, "213")
print(f"OK: Penn State found, {g['teams']['213']} points" if g else "BUG: Penn State (213) not found on the board")

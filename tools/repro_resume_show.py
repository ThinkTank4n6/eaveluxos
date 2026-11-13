import threading  # Repro: "Back to the schedule" ends tonight's scheduled music show (EaveLuxOS controller.py)
class ShowSchedule:  # mock of cfg.music["schedule"]: a show night is running right now
    def active_window(self, now): return type("W", (), {"key": "on|Show night|2026-12-24T18:00"})()
class Ctrl:
    def __init__(s): s.lock, s.music, s.music_skipped, s.override, s.sched = threading.RLock(), None, None, None, ShowSchedule()
    def _end_music(s, why):  # same logic as Controller._end_music
        w, ended = s.sched.active_window(None), bool(s.music)
        s.music = None
        if w is not None and w.key != s.music_skipped: s.music_skipped, ended = w.key, True
        return ended
    def target(s):  # same order as Controller._target: show night beats the schedule unless skipped
        w = s.sched.active_window(None)
        return "manual" if s.override else "music show" if w and w.key != s.music_skipped else "schedule"
    def manual(s, effect):
        with s.lock: s._end_music("a pattern was chosen"); s.override = effect   # skipping tonight is intended here
    def resume(s):
        with s.lock: s._end_music("back to the schedule"); s.override = None      # BUG: the show night IS the schedule
c = Ctrl(); print("show night running:", c.target())
c.resume(); print("after Back to the schedule:", c.target(), "-> BUG" if c.target() != "music show" else "-> OK")
c = Ctrl(); c.manual("christmas"); c.resume(); print("pattern, then back:", c.target(), "-> BUG" if c.target() != "music show" else "-> OK")

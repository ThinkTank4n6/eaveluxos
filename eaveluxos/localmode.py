# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Local mode (4.3): change the controller's saved patterns and ports over
the home network, the way the Trimlight Edge app does when it shows "Local",
with no writes through Trimlight's cloud.

Why: on Nov 13 and 15, 2026, pattern saves and deletes through the cloud
left its copy of the controller unreadable (12006) while the cloud's numbers
were out of step with the controller's, and a reset then lost the owner's
patterns. Over the home network the controller itself is read and written,
so there is no second copy to fall out of step.

How it stays safe
- The controller is read first (patterns and ports), and that is saved as a
  backup in controller-backups, like the backup timer's.
- One change at a time. The controller doesn't answer changes, so after each
  one it is read again and checked: the change is there exactly as sent,
  nothing else changed, and no two patterns share a number. At the first
  difference it stops, before the next change.
- A pattern is deleted only if the number still holds the pattern of that
  name.
- Only custom-color patterns (the Trimlight app's own kind) are written; the
  layout of built-in effect records hasn't been seen yet.
"""
import logging
import time
from datetime import datetime

from . import lanlink as L

log = logging.getLogger("eaveluxos.localmode")
GAP = 1.0                     # seconds for the controller to store a change before it's read back


class LocalError(Exception):
    pass


# 4.3.9: on Nov 16 a read right after Back up now got no answer while the
# Trimlight app was likely open for its sync; the controller seems to answer
# one connection at a time.
ONE_AT_A_TIME = (" If the Trimlight Edge app is open on a phone or tablet, close it fully (the controller seems to "
                 "answer one connection at a time), wait a few seconds and try again.")


def as_backup(st: dict) -> dict:
    """The controller as read over the home network, in the shape of a cloud
    backup, so Pattern backups can list it and put patterns back from it."""
    effects = [{"id": p["id"], **cloud_effect(p, every_slot=True)} for p in st["patterns"]]
    return {"source": "home network (local mode)", "ports": [dict(x) for x in st["ports"]], "effects": effects,
            "controller_raw": st.get("raw", "")}


def cloud_effect(p: dict, every_slot: bool = False) -> dict:
    """A pattern read over the home network in the layout Trimlight's cloud
    reports patterns. 4.7.1: a built-in effect (kind 1) is category 0 with
    its effect number; before, backups called it a pattern of its own colors
    and would have put it back as one. Off slots stay ('disable'), so the
    spacing between colors stays; every_slot keeps the empty ones too."""
    e = {"name": p["name"], "speed": p["speed"], "brightness": p["brightness"]}
    if p.get("kind") == 1:
        return {**e, "category": 0, "mode": p.get("effect", 0), "reverse": bool(p.get("reverse")), "pixelLen": 30}
    return {**e, "category": 1, "mode": p["mode"],
            "pixels": [{"index": i, "count": c, "color": int(col[1:], 16), "disable": not on}
                       for i, (c, col, on) in enumerate(p["slots"]) if c or every_slot]}


def _essence(p: dict) -> tuple:
    """What a pattern shows: its name, motion, speed, brightness and the color
    slots that hold bulbs. Review #2 (4.3.1): the bytes of an unused slot (a
    color left from editing) aren't compared, in case the controller tidies
    them; a correct save must never be called a failure."""
    return (p["name"], p.get("kind"), p.get("effect"), p.get("reverse"), p["mode"], p["speed"], p["brightness"],
            tuple((i, c, col, on) for i, (c, col, on) in enumerate(p["slots"]) if c))


def _clock(t) -> str:
    return t.strftime("%I:%M %p").lstrip("0") if hasattr(t, "strftime") else str(t)


def _look(p: dict) -> tuple:
    """What a pattern shows, without its name or number (4.4.2): two
    patterns with the same look are the same on the house."""
    return (p.get("kind"), p.get("effect"), p["mode"], p["speed"], p["brightness"],
            tuple((c, col, on) for c, col, on in p["slots"] if c))


def look_of(payload: dict):
    """The look of a pattern as sent to Trimlight's cloud (this app's own
    pattern, with any brightness or speed already in it); None when it can't
    be one saved on the controller (a built-in effect, too many colors)."""
    if payload.get("category", 1) != 1 or not payload.get("pixels"):
        return None
    try:
        return _look(L.read_record(L.record_from_effect(1, {**payload, "name": "x"})))
    except (ValueError, TypeError, KeyError):
        return None


def _check(before: dict, after: dict, *, added=None, removed=None, port=None, effects=None):
    """Raise LocalError unless `after` is `before` with exactly this change.
    port: (index, start, end, on)."""
    ids = [p["id"] for p in after["patterns"]]
    if len(ids) != len(set(ids)):
        raise LocalError("two patterns on the controller now share a number")
    old = {p["id"]: _essence(p) for p in before["patterns"]}
    new = {p["id"]: _essence(p) for p in after["patterns"]}
    if added is not None:
        old = {**old, added[0]: _essence(L.read_record(added[1]))}
    if removed is not None:
        old.pop(removed, None)
    if old != new:
        what = sorted(set(old) ^ set(new)) or [k for k in old if old[k] != new.get(k)]
        raise LocalError(f"the controller's patterns didn't read back as expected (number {', '.join(map(str, what))})")
    want = [dict(x) for x in before["ports"]]
    got = [dict(x) for x in after["ports"]]
    if port is not None:
        i, a, b, on = port
        want[i].update(start=a, end=b)
        if not on:
            # Review #1 (4.3.1): what the controller reports for a port that
            # is off hasn't been seen; only the other ports are checked.
            want[i] = got[i]
    if want != got:
        raise LocalError("the controller's ports didn't read back as expected")
    if effects is not None and after.get("effects") != effects:
        raise LocalError("the controller's effects didn't read back as expected")


# 4.6: after a read the controller ignored, wait this long before a new
# connection. On Nov 17 the Trimlight app's own read went unanswered ("Failed
# to sync"); its next connection, 12 seconds after the first closed, was
# answered at once. A retry 1 second later often went unanswered too.
RECONNECT_WAIT = 12


class Local:
    def __init__(self, host: str, now=datetime.now, backup=None, link_factory=L.Link, gap: float = GAP,
                 lock=None, busy=None, io=None, blocked=None):
        """backup(detail): saves the controller as read first. lock: the
        command lock, held for each change and its read-back, released
        between changes, so a scheduled on/off never waits for a long job."""
        self.host, self.now, self.backup = host, now, backup
        self.link_factory, self.gap = link_factory, gap
        import contextlib
        self.lock = lock or contextlib.nullcontext()
        # busy: a lock held for a whole job, so two jobs (two pages, or ports
        # and a restore) never interleave their changes (review #4, 4.3.1).
        self.busy = busy
        # io: held while a connection is open. 4.3.6: the controller seems to
        # answer one connection at a time; two panels reading at once (Local
        # mode and Pattern backups) left one with "didn't answer".
        self.io = io
        self.blocked = blocked            # a music show from this computer holds its own connection

    def _job(self):
        import contextlib
        if self.busy is None:
            return contextlib.nullcontext()
        if not self.busy.acquire(blocking=False):
            raise LocalError("Another change to the controller is running. Try again when it's done.")
        lk = self.busy

        @contextlib.contextmanager
        def held():
            try:
                yield
            finally:
                lk.release()
        return held()

    def _open(self):
        """Connect, greet, and have a keep-alive answered before anything
        else (4.3.6: as Test connection does, which read the controller when
        a plain read didn't)."""
        if self.io is not None and not self.io.acquire(timeout=20):   # review #4: a page never waits a minute
            raise LocalError("The connection to the controller is busy. Try again in a moment.")
        if self.blocked is not None and self.blocked():
            # Checked with the connection held: a show can't start in between (4.3.6).
            if self.io is not None:
                self.io.release()
            raise LocalError("A music show from this computer is using the connection to the controller. Stop it first.")
        link = None
        try:
            link = self.link_factory(self.host).open()
            link.ping()
            return link
        except L.LinkError as e:
            if link is not None:
                link.close()
            if self.io is not None:
                self.io.release()
            raise LocalError(f"Couldn't reach the controller on the home network: {e}") from None

    def _close(self, link):
        try:
            link.close()
        finally:
            if self.io is not None:
                self.io.release()

    def read(self) -> dict:
        """Read the controller; once more on a fresh connection if it didn't
        answer (4.3.6)."""
        for attempt in (1, 2):
            link = self._open()
            try:
                return link.state(self.now())
            except L.LinkError as e:
                if attempt == 2:
                    raise LocalError(f"Couldn't read the controller: {str(e).rstrip('.')}.{ONE_AT_A_TIME}") from None
            finally:
                self._close(link)
            time.sleep(RECONNECT_WAIT)

    def _start(self, link) -> dict:
        try:
            st = link.state(self.now())
        except L.LinkError:
            time.sleep(1)                    # 4.3.9: once more, as read() does
            try:
                st = link.state(self.now())
            except L.LinkError as e:
                raise LocalError(f"Couldn't read the controller first, so nothing was changed: {str(e).rstrip('.')}.{ONE_AT_A_TIME}") from None
        ids = [p["id"] for p in st["patterns"]]
        if len(ids) != len(set(ids)):
            raise LocalError("Two patterns on the controller share a number, so nothing was changed. "
                             "Check your patterns in the Trimlight Edge app.")
        if self.backup:
            self.backup(as_backup(st))
        return st

    def _again(self, link, what):
        """Do what(), and if the controller doesn't answer, once more on a
        fresh connection after a pause (4.3.12: on Nov 16 the controller went
        quiet right after a pattern was put back, and the restore stopped
        with "The controller didn't answer")."""
        try:
            return what()
        except L.LinkError as e:
            log.info("The controller didn't answer (%s); trying once more on a fresh connection.", e)
            link.close()
            time.sleep(self.gap * 3)
            link.open()
            link.ping()
            return what()

    def _change(self, link, before, send, **expect) -> dict:
        """Send one change and check it by reading the controller back.

        4.3.8: on Nov 15 the fourth of four patterns put back in a row wasn't
        on the controller one second later, yet putting it back again minutes
        afterward worked: the controller can need longer to store a change.
        So a read that doesn't match yet is repeated after a pause, and a
        change that left the controller exactly as it was (it didn't take,
        nothing else moved) is sent once more. Anything else still stops.
        4.3.12: a controller that goes quiet is asked again on a fresh
        connection, before and after the change."""
        read = lambda: self._again(link, lambda: link.state(self.now()))
        with self.lock:
            try:
                self._again(link, send)
                after = None
                for pause in (self.gap, self.gap * 2, self.gap * 4):
                    time.sleep(pause)
                    after = read()
                    try:
                        _check(before, after, **expect)
                        break
                    except LocalError as e:
                        why = e
                else:
                    try:
                        _check(before, after)                      # untouched: it didn't take
                    except LocalError:
                        raise why from None                       # something changed, but not as sent: stop
                    log.info("A change didn't take on the controller; sending it once more.")
                    self._again(link, send)
                    time.sleep(self.gap * 2)
                    after = read()
                    _check(before, after, **expect)
            except L.LinkError as e:
                raise LocalError(f"the connection failed: {str(e).rstrip('.')}.{ONE_AT_A_TIME}") from None
        time.sleep(0.05)              # give a waiting scheduled on/off a turn at the lock
        return after

    # ------------------------------------------------------------ patterns
    @staticmethod
    def free_id(st: dict, want=None) -> int:
        used = {p["id"] for p in st["patterns"]}
        if isinstance(want, int) and 1 <= want <= L.MAX_PATTERN_ID and want not in used:
            return want              # its old number: timers made in the Trimlight app still find it
        for i in range(1, L.MAX_PATTERN_ID + 1):
            if i not in used:
                return i
        raise LocalError(f"The controller's pattern library is full ({L.MAX_PATTERN_ID}).")

    def restore(self, det: dict, ids) -> dict:
        """Put back patterns from a backup (cloud or local), one at a time.
        Returns {"restored", "skipped", "duplicates", "builtin"}."""
        wanted = {i for i in ids if isinstance(i, int) and not isinstance(i, bool)}
        chosen = [e for e in det.get("effects", []) or [] if isinstance(e, dict) and e.get("id") in wanted]
        if not chosen:
            raise LocalError("Choose at least one pattern to put back.")
        restored, skipped, duplicates, builtin = [], [], [], []
        with self._job():
            return self._restore(chosen, restored, skipped, duplicates, builtin)

    def _restore(self, chosen, restored, skipped, duplicates, builtin) -> dict:
        link = self._open()
        try:
            st = self._start(link)
            for e in chosen:
                name = str(e.get("name") or "").strip()
                key = name.encode("ascii", "replace")[:L.NAME_LEN].decode().lower()
                if e.get("category") not in (1, None):
                    builtin.append(name)
                    continue
                have = {p["name"].strip().lower() for p in st["patterns"]}
                if key in have:
                    mine = {n.encode("ascii", "replace")[:L.NAME_LEN].decode().lower() for n in restored}
                    (duplicates if key in mine else skipped).append(name)
                    continue
                pid = self.free_id(st, e.get("id"))
                try:
                    rec = L.record_from_effect(pid, e)
                except ValueError as x:
                    raise LocalError(f"Stopped at “{name}”: {x}. Put back so far: {', '.join(restored) or 'none'}.") from None
                try:
                    st = self._change(link, st, lambda: link.save_pattern(rec), added=(pid, rec))
                except LocalError as x:
                    log.warning("Local restore stopped at %r: %s", name, x)
                    raise LocalError(f"Stopped after “{name}”: {x}. Nothing more was saved. Put back before it: "
                                     f"{', '.join(restored) or 'none'}. Check your patterns in the Trimlight Edge app.") from None
                restored.append(name)
                log.info("Put back %r as pattern %s over the home network.", name, pid)
        finally:
            self._close(link)
        return {"restored": restored, "skipped": skipped, "duplicates": duplicates, "builtin": builtin}

    def save(self, effect: dict) -> int:
        """Save a new custom-colors pattern; returns its number."""
        name = str(effect.get("name") or "").strip()
        if len(name.encode("ascii", "replace")) > L.NAME_LEN:
            raise LocalError(f"Names on the controller can be at most {L.NAME_LEN} characters; "
                             f"\u201c{name}\u201d has {len(name)}. Choose a shorter one.")
        with self._job():
            return self._save(name, effect)

    def _save(self, name, effect) -> int:
        link = self._open()
        try:
            st = self._start(link)
            key = name.encode("ascii", "replace")[:L.NAME_LEN].decode().lower()
            if key in {p["name"].strip().lower() for p in st["patterns"]}:
                raise LocalError(f"The controller already has a pattern named “{name}”.")
            pid = self.free_id(st)
            try:
                rec = L.record_from_effect(pid, effect)
            except ValueError as x:
                raise LocalError(f"Can't save it over the home network: {x}.") from None
            try:
                self._change(link, st, lambda: link.save_pattern(rec), added=(pid, rec))
            except LocalError as x:
                raise LocalError(f"Saving “{name}”: {x}. Check your patterns in the Trimlight Edge app.") from None
            return pid
        finally:
            self._close(link)

    def delete(self, pid: int, name: str):
        """Delete pattern `pid`, only if it is still the one called `name`."""
        with self._job():
            self._delete(pid, name)

    def _delete(self, pid, name):
        if isinstance(pid, bool) or not isinstance(pid, int) or not 1 <= pid <= L.MAX_PATTERN_ID:
            # 4.9.1: never a slot that isn't a pattern (numbered 0 or past 60)
            raise LocalError("That isn't one of the controller's patterns, so nothing was deleted.")
        link = self._open()
        try:
            st = self._start(link)
            cur = next((p for p in st["patterns"] if p["id"] == pid), None)
            if not cur or cur["name"].strip().lower() != str(name).strip().lower():
                raise LocalError(f"Pattern {pid} on the controller isn't “{name}” any more, so nothing was "
                                 "deleted. Read the controller again.")
            try:
                after = self._change(link, st, lambda: link.delete_pattern(pid), removed=pid)
            except LocalError as x:
                raise LocalError(f"Deleting “{name}”: {x}. Check your patterns in the Trimlight Edge app.") from None
            # Review #1 (4.22): a deleted pattern's Lightning or Snowflake
            # stays in the controller's effects list unless it is taken out,
            # and the next pattern saved under that number would flash or
            # snow. Only when the read-back still lists it (if the controller
            # drops it itself, nothing more is sent).
            left = (after or {}).get("effects")
            if left and any(n == pid for _, n in left):
                new = [x for x in left if x[1] != pid]
                try:
                    self._change(link, after, lambda: link.set_effects(new), effects=new)
                except LocalError as x:
                    log.warning("Deleted pattern %s, but its effect is still listed on the controller: %s", pid, x)
        finally:
            self._close(link)

    # ------------------------------------------------------------ effects (4.22)
    def set_effect(self, pid: int, kind: str | None) -> list:
        """Lightning, Snowflake or no effect on saved pattern `pid`, as the
        Trimlight app's Pattern Library sets it. The other patterns' effects
        are kept as they are; read back to check. Returns the new list."""
        if isinstance(pid, bool) or not isinstance(pid, int) or not 1 <= pid <= L.MAX_PATTERN_ID:
            raise LocalError("That isn't one of the controller's patterns, so nothing was changed.")
        if kind is not None and kind not in L.EFFECT_CODES:
            raise LocalError("The effect is Lightning, Snowflake or none.")
        with self._job():
            link = self._open()
            try:
                st = self._start(link)
                if not any(p["id"] == pid for p in st["patterns"]):
                    raise LocalError(f"There's no pattern {pid} on the controller any more. Read it again.")
                cur = st.get("effects")
                if cur is None:
                    raise LocalError("This controller's effects list isn't laid out as this app knows it, so nothing "
                                     "was changed. Set the effect in the Trimlight Edge app.")
                have = {p["id"] for p in st["patterns"]}
                # entries for numbers with no pattern (left by a delete before 4.22) go too
                new = sorted([x for x in cur if x[1] != pid and x[1] in have]
                             + ([(L.EFFECT_CODES[kind], pid)] if kind else []), key=lambda x: (x[1], x[0]))
                if new == cur:
                    return new
                self._change(link, st, lambda: link.set_effects(new), effects=new)
                return new
            finally:
                self._close(link)

    # ------------------------------------------------------------ ports
    def ports(self, ports) -> list[str]:
        """ports: 4 of {"start", "end", "on"} (ports 1-4), written one at a
        time and each read back. Returns what was sent. The on/off switch
        isn't in what the controller sends back, so it can't be checked;
        start and end are."""
        if not (isinstance(ports, list) and len(ports) == 4):
            raise LocalError("Give all four ports.")
        clean = []
        for i, p in enumerate(ports):
            try:
                st_, en, on = int(p["start"]), int(p["end"]), bool(p["on"])
            except (KeyError, TypeError, ValueError):
                raise LocalError(f"Port {i + 1}: start, end and on are needed.") from None
            if not 1 <= st_ <= en <= 2048:
                raise LocalError(f"Port {i + 1}: bulbs must be within 1-2048 and the start can't be after the end.")
            clean.append((st_, en, on))
        if not any(on for _, _, on in clean):
            raise LocalError("At least one port needs to be on. Turning every port off would leave the lights dark.")
        with self._job():
            return self._ports(clean)

    def _ports(self, clean) -> list[str]:
        changed = []
        link = self._open()
        try:
            st = self._start(link)
            for i, (a, b, on) in enumerate(clean):
                # The on/off switch can't be read back, so it's always sent;
                # start and end are checked.
                try:
                    st = self._change(link, st, lambda i=i, a=a, b=b, on=on: link.set_port(i, a, b, on), port=(i, a, b, on))
                except LocalError as x:
                    raise LocalError(f"Stopped at port {i + 1}: {x}. Changed before it: {', '.join(changed) or 'none'}.") from None
                changed.append(f"port {i + 1}: {a}-{b}{'' if on else ' (off)'}")
        finally:
            self._close(link)
        return changed


class Commands:
    """Everyday commands over the home network (4.4, an opt-in setting):
    lights on and off, and showing a saved pattern, as the Trimlight app does
    in Local mode. Each returns False when it can't be done that way (the
    setting is off, another controller, a music show from this computer, the
    connection busy or no answer), and the caller then uses Trimlight's cloud
    as before. Patterns of your own colors and the built-in effects still go
    through the cloud: how the controller keeps a live preview hasn't been
    seen yet."""

    def __init__(self, enabled, host, io, blocked, now=datetime.now, link_factory=L.Link):
        # host(dev): that controller's address on the home network, or "" (4.5:
        # one per controller; each has its own failures, reads and reminders)
        self.enabled, self.host = enabled, host
        self.io, self.blocked, self.now, self.link_factory = io, blocked, now, link_factory
        self.failed_at = {}                 # dev -> after a failure, the cloud for a while
        self.looks = {}                     # dev -> (time, {look: pattern number}) of the last read, 4.4.2
        self.trouble = {}                   # dev -> (since, last said): a stretch of failures, said once an hour (4.4.3)

    RETRY_AFTER = 300
    SAY_AGAIN = 3600                        # during a stretch of failures, a reminder this often
    LOOKS_FOR = 600                         # a look not on the controller: don't read it again for 10 minutes

    def usable(self, dev) -> bool:
        at = self.failed_at.get(dev)
        return bool(self.enabled() and self.host(dev) and not self.blocked()
                    and (at is None or time.monotonic() - at > self.RETRY_AFTER))

    def _do(self, dev, fn):
        if not self.usable(dev) or not self.io.acquire(timeout=3):
            return None
        try:
            if self.blocked():
                # A show from this computer may have started while this
                # waited for the connection (it holds it while starting):
                # a command now would end the show (4.4.1).
                return None
            # During a stretch of failures, one connection per try (4.4.3:
            # Nov 17, 2:56-6:00 AM, every read went unanswered).
            tries = (2,) if self.trouble.get(dev) else (1, 2)
            for attempt in tries:
                link = self.link_factory(self.host(dev)).open()
                try:
                    link.ping()
                    out = fn(link)
                    # The controller doesn't answer a change, and hanging up at
                    # once can lose it: one answered keep-alive after it says it
                    # was taken in (it handles requests in order).
                    link.ping()
                    self._worked(dev)
                    return out
                except L.LinkError:
                    # It sometimes ignores a request on a new connection ("0
                    # bytes came"); these commands can be sent again safely
                    # (4.4.2: once more, on a fresh connection; 4.6: after
                    # RECONNECT_WAIT, as the Trimlight app's retry was).
                    if attempt == 2:
                        raise
                    link.close()
                    time.sleep(RECONNECT_WAIT)
                    continue
                finally:
                    link.close()
        except Exception as e:          # never keep the cloud from doing it instead (4.4.1)
            self.failed_at[dev] = time.monotonic()
            if not isinstance(e, (L.LinkError, ValueError)):
                log.exception("Unexpected trouble over the home network")
            self._failed(dev, e)
            return None
        finally:
            self.io.release()

    def _failed(self, dev, e):
        """Once for a stretch of failures, then once an hour (4.4.3); each
        controller on its own (4.5)."""
        now, t, host = time.monotonic(), self.trouble.get(dev), self.host(dev)
        if t is None:
            self.trouble[dev] = (self.now(), now)
            log.warning("Over the home network (%s) didn't work (%s); using Trimlight's cloud, and trying again "
                        "every %d minutes.", host, e, self.RETRY_AFTER // 60)
        elif now - t[1] >= self.SAY_AGAIN:
            self.trouble[dev] = (t[0], now)
            log.warning("Over the home network (%s) still isn't working (since %s; %s); Trimlight's cloud is being "
                        "used.%s", host, _clock(t[0]), e, ONE_AT_A_TIME)

    def _worked(self, dev):
        t = self.trouble.pop(dev, None)
        if t is not None:
            log.info("Over the home network (%s) works again (it didn't from %s).", self.host(dev), _clock(t[0]))

    def power(self, dev, on: bool) -> bool:
        done = self._do(dev, lambda link: link.power(on) or True) is True
        if done:                        # each one in the log, so it can be seen working (4.4.1)
            log.info("Over the home network (%s): lights %s.", self.host(dev), "on" if on else "off")
        return done

    def timer_mode(self, dev) -> bool:
        """4.17: the controller's own timers take over (on Quit, when asked)."""
        done = self._do(dev, lambda link: link.timer_mode() or True) is True
        if done:
            log.info("Over the home network (%s): handed the lights to the controller's own timers.", self.host(dev))
        return done

    def show(self, dev, pid: int) -> bool:
        done = self._do(dev, lambda link: link.show_saved(pid) or True) is True
        if done:
            log.info("Over the home network (%s): showed saved pattern %d.", self.host(dev), pid)
        return done

    def show_like(self, dev, payload: dict):
        """Show the pattern saved on the controller that looks exactly like
        this one, by its number (4.4.2), so this app's own copies of the
        controller's patterns don't need the cloud. The controller is read
        first, in the same connection, so the number is never a stale one.
        Returns the number shown, or None (no such pattern: use the cloud)."""
        want = look_of(payload)
        if want is None or not self.usable(dev):
            return None
        at, known = self.looks.get(dev, (None, None))
        if known is not None and want not in known and time.monotonic() - at < self.LOOKS_FOR:
            return None                     # not on the controller a few minutes ago: don't read again

        def fn(link):
            st = link.state(self.now())
            known = {}
            for p in st["patterns"]:
                known.setdefault(_look(p), p["id"])
            self.looks[dev] = (time.monotonic(), known)
            pid = known.get(want)
            if pid:
                link.show_saved(pid)
            return pid or 0

        pid = self._do(dev, fn)
        if pid:
            log.info("Over the home network (%s): showed saved pattern %d (the same as this app's).", self.host(dev), pid)
            return pid
        return None

    def preview(self, dev, payload: dict) -> bool:
        """Show this app's own pattern (or a built-in effect) live over the
        home network, as the Trimlight app does while editing (4.6). Like
        the cloud's preview, it isn't saved on the controller. False when it
        can't go this way (then the cloud is used)."""
        try:
            L.preview_message(payload)
        except (ValueError, TypeError, KeyError):
            return False
        done = self._do(dev, lambda link: link.preview(payload) or True) is True
        if done:
            what = (f"built-in effect {payload.get('mode')}" if payload.get("category") == 0
                    else "a pattern of this app's")
            log.info("Over the home network (%s): showed %s, brightness %s, speed %s.", self.host(dev), what,
                     payload.get("brightness"), payload.get("speed"))
        return done

    def fade(self, dev, frames: list, every: float, sleep=None, cancel=None) -> bool:
        """4.19: still frames, one every `every` seconds, on one connection
        (transitions.py); the caller sends the real pattern after them.
        False when it can't go this way: the change is then sent at once."""
        import time as _t
        sleep = sleep or _t.sleep
        try:
            for f in frames:
                L.preview_message(f)
        except (ValueError, TypeError, KeyError):
            return False

        def run(link):
            for i, f in enumerate(frames):
                if cancel is not None and cancel():
                    return True           # Review #1 (4.19): a button was pressed: stop now
                link.preview(f)
                if i < len(frames) - 1:
                    sleep(every)
            return True
        done = self._do(dev, run) is True
        if done:
            log.info("Over the home network (%s): faded in %d steps.", self.host(dev), len(frames))
        return done

    def preview_many(self, items: list) -> list:
        """4.21: several controllers' patterns started together: every
        connection opened and answered first, then the patterns sent one
        right after another, so their motion starts within a moment of each
        other. items: [(dev, payload)]. Returns the devs it reached."""
        if not items or not self.io.acquire(timeout=3):
            return []
        links, done = [], []
        try:
            if self.blocked():
                return []
            for dev, payload in items:
                if not self.usable(dev):
                    continue
                try:
                    L.preview_message(payload)
                    link = self.link_factory(self.host(dev)).open()
                    link.ping()
                    links.append((dev, payload, link))
                except (L.LinkError, OSError, ValueError, TypeError, KeyError) as e:
                    self._failed(dev, e)
            for dev, payload, link in links:            # back to back
                try:
                    link.preview(payload)
                    done.append(dev)
                except (L.LinkError, OSError) as e:
                    self._failed(dev, e)
            for dev, _, link in links:
                try:
                    if dev in done:
                        link.ping()
                        self._worked(dev)
                except (L.LinkError, OSError):
                    pass
        finally:
            for _, _, link in links:
                link.close()
            self.io.release()
        if done:
            log.info("Over the home network: started %d controllers together.", len(done))
        return done

    def switch(self, dev):
        """1 on, 0 off, as the controller itself says; None if unknown."""
        st = self._do(dev, lambda link: link.state(self.now()))
        return None if st is None else st["switch"]

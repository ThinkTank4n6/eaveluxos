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


def as_backup(st: dict) -> dict:
    """The controller as read over the home network, in the shape of a cloud
    backup, so Pattern backups can list it and put patterns back from it."""
    effects = []
    for p in st["patterns"]:
        effects.append({"id": p["id"], "name": p["name"], "category": 1, "mode": p["mode"], "speed": p["speed"],
                        "brightness": p["brightness"],
                        "pixels": [{"index": i, "count": c, "color": int(col[1:], 16), "disable": not on}
                                   for i, (c, col, on) in enumerate(p["slots"])]})
    return {"source": "home network (local mode)", "ports": [dict(x) for x in st["ports"]], "effects": effects}


def _essence(p: dict) -> tuple:
    """What a pattern shows: its name, motion, speed, brightness and the color
    slots that hold bulbs. Review #2 (4.3.1): the bytes of an unused slot (a
    color left from editing) aren't compared, in case the controller tidies
    them; a correct save must never be called a failure."""
    return (p["name"], p["mode"], p["speed"], p["brightness"],
            tuple((i, c, col, on) for i, (c, col, on) in enumerate(p["slots"]) if c))


def _check(before: dict, after: dict, *, added=None, removed=None, port=None):
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
                    raise LocalError(f"Couldn't read the controller: {e}") from None
            finally:
                self._close(link)
            time.sleep(1)

    def _start(self, link) -> dict:
        try:
            st = link.state(self.now())
        except L.LinkError as e:
            raise LocalError(f"Couldn't read the controller first, so nothing was changed: {e}") from None
        ids = [p["id"] for p in st["patterns"]]
        if len(ids) != len(set(ids)):
            raise LocalError("Two patterns on the controller share a number, so nothing was changed. "
                             "Check your patterns in the Trimlight Edge app.")
        if self.backup:
            self.backup(as_backup(st))
        return st

    def _change(self, link, before, send, **expect) -> dict:
        """Send one change and check it by reading the controller back.

        4.3.8: on Nov 15 the fourth of four patterns put back in a row wasn't
        on the controller one second later, yet putting it back again minutes
        afterward worked: the controller can need longer to store a change.
        So a read that doesn't match yet is repeated after a pause, and a
        change that left the controller exactly as it was (it didn't take,
        nothing else moved) is sent once more. Anything else still stops."""
        with self.lock:
            try:
                send()
                after = None
                for pause in (self.gap, self.gap * 2):
                    time.sleep(pause)
                    after = link.state(self.now())
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
                    send()
                    time.sleep(self.gap * 2)
                    after = link.state(self.now())
                    _check(before, after, **expect)
            except L.LinkError as e:
                raise LocalError(f"the connection failed: {e}") from None
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
        link = self._open()
        try:
            st = self._start(link)
            cur = next((p for p in st["patterns"] if p["id"] == pid), None)
            if not cur or cur["name"].strip().lower() != str(name).strip().lower():
                raise LocalError(f"Pattern {pid} on the controller isn't “{name}” any more, so nothing was "
                                 "deleted. Read the controller again.")
            try:
                self._change(link, st, lambda: link.delete_pattern(pid), removed=pid)
            except LocalError as x:
                raise LocalError(f"Deleting “{name}”: {x}. Check your patterns in the Trimlight Edge app.") from None
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

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Celebration sounds (4.9): a short clip of a sound file you have (a goal
horn, a fight song) played through this computer's speakers when a team you
follow scores.

The file is kept in this app's data folder, never in the program or the
settings. MP3 and WAV are accepted. The part that plays (a start and a
length, up to 30 seconds) is cut without re-encoding: an MP3 is cut between
its frames, a WAV between its samples, so nothing outside Python is needed.

Playing uses what each system already has: Windows' own media player
(winmm), the Mac's afplay, or on Linux paplay, aplay, mpg123 or ffplay if
installed."""
from __future__ import annotations

import io
import logging
import platform
import queue
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

log = logging.getLogger(__name__)

UPLOAD_MAX = 15_000_000          # bytes: a few minutes of MP3
CLIP_MAX = 30                    # seconds that may play
START_MAX = 3600                 # seconds into the file a clip may start


class SoundError(ValueError):
    pass


# --- what kind of file -----------------------------------------------------------

def _id3_end(data: bytes) -> int:
    """Where an MP3's ID3v2 tag (title, cover art) ends, or 0."""
    if len(data) >= 10 and data[:3] == b"ID3":
        size = (data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F)
        return 10 + size + (10 if data[5] & 0x10 else 0)
    return 0


_BR1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_BR2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
_SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _frame(data: bytes, i: int):
    """(length in bytes, seconds) of an MPEG audio Layer III frame at i, or None."""
    if i + 4 > len(data):
        return None
    h = int.from_bytes(data[i:i + 4], "big")
    if (h >> 21) & 0x7FF != 0x7FF:
        return None
    ver, layer, bri, sri, pad = (h >> 19) & 3, (h >> 17) & 3, (h >> 12) & 15, (h >> 10) & 3, (h >> 9) & 1
    if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
        return None
    sr = _SR[ver][sri]
    br = (_BR1 if ver == 3 else _BR2)[bri] * 1000
    n = (144 if ver == 3 else 72) * br // sr + pad
    return n, (1152 if ver == 3 else 576) / sr


def _mp3_frames(data: bytes):
    """(offset, length, seconds) of each audio frame. A frame counts only
    when the next one follows it (or the file ends), so stray bytes that
    look like a frame header aren't taken for sound."""
    i, out, found = _id3_end(data), [], False
    while i < len(data):
        f = _frame(data, i)
        if f and (found or _frame(data, i + f[0]) or i + f[0] == len(data)):
            found = True
            out.append((i, f[0], f[1]))
            i += f[0]
            continue
        if found and data[i:i + 3] == b"TAG":          # an ID3v1 tag closes the file
            break
        found = False
        i += 1
    # The first frame is often an encoder's note (Xing/Info), not sound.
    if out and (b"Xing" in data[out[0][0]:out[0][0] + out[0][1]] or b"Info" in data[out[0][0]:out[0][0] + out[0][1]]):
        out.pop(0)
    return out


def kind_of(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    # Review #2 (4.9): after the tag, which can hold large cover art
    if len(_mp3_frames(data[:_id3_end(data) + 200_000])) >= 3:
        return "mp3"
    return None


def length_of(data: bytes, kind: str) -> float:
    if kind == "mp3":
        return round(sum(s for _, _, s in _mp3_frames(data)), 2)
    with wave.open(io.BytesIO(data)) as w:
        return round(w.getnframes() / w.getframerate(), 2)


# --- the part that plays ------------------------------------------------------------

def cut(data: bytes, kind: str, start: float, seconds: float) -> bytes:
    """The clip from start, seconds long (both in seconds)."""
    if not 0 <= start <= START_MAX or not 0 < seconds <= CLIP_MAX:
        raise SoundError(f"Choose a start in the file and up to {CLIP_MAX} seconds to play.")
    if kind == "mp3":
        t, parts = 0.0, []
        for off, n, s in _mp3_frames(data):
            if t + s / 2 >= start and t < start + seconds:
                parts.append(data[off:off + n])
            t += s
            if t >= start + seconds:
                break
        if not parts:
            raise SoundError("The start is after the end of the sound.")
        return b"".join(parts)
    try:
        with wave.open(io.BytesIO(data)) as w:
            rate, total = w.getframerate(), w.getnframes()
            first = int(start * rate)
            if first >= total:
                raise SoundError("The start is after the end of the sound.")
            w.setpos(first)
            frames = w.readframes(min(total - first, int(seconds * rate)))
            out = io.BytesIO()
            with wave.open(out, "wb") as o:
                o.setnchannels(w.getnchannels())
                o.setsampwidth(w.getsampwidth())
                o.setframerate(rate)
                o.writeframes(frames)
            return out.getvalue()
    except (wave.Error, EOFError) as e:
        raise SoundError(f"That WAV file can't be read: {e}") from None


def check_upload(data: bytes) -> tuple[str, float]:
    """(kind, length in seconds) of an uploaded file, or SoundError."""
    if not data:
        raise SoundError("No sound file was sent.")
    if len(data) > UPLOAD_MAX:
        raise SoundError(f"That file is over {UPLOAD_MAX // 1_000_000} MB. Use a shorter one.")
    kind = kind_of(data)
    if kind is None:
        raise SoundError("Use an MP3 or WAV file.")
    try:
        secs = length_of(data, kind)
    except (wave.Error, EOFError) as e:
        raise SoundError(f"That WAV file can't be read: {e}") from None
    if secs < 0.5:
        raise SoundError("That file has almost no sound in it.")
    return kind, secs


# --- playing ------------------------------------------------------------------

class Player:
    """Plays one clip at a time; a new one stops the one playing. Every
    call to Windows' player happens on one thread of its own."""

    def __init__(self, system: str | None = None, which=shutil.which, popen=subprocess.Popen, mci=None):
        self.system = system or platform.system()
        self.which, self.popen = which, popen
        self.mci = mci
        self.proc = None
        self.jobs: queue.Queue = queue.Queue()
        self.thread = None
        self.lock = threading.Lock()

    def _linux_cmd(self, path: Path, kind: str):
        for exe, args, kinds in (("paplay", [], ("wav", "mp3")), ("mpg123", ["-q"], ("mp3",)), ("aplay", ["-q"], ("wav",)),
                                 ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"], ("wav", "mp3"))):
            if kind in kinds and self.which(exe):
                return [exe, *args, str(path)]
        return None

    def supported(self, kind: str = "mp3") -> bool:
        if self.system == "Windows":
            return True
        if self.system == "Darwin":
            return bool(self.which("afplay"))
        return self._linux_cmd(Path("x"), kind) is not None

    def play(self, path: Path, kind: str, seconds: float) -> bool:
        path = Path(path)
        if self.system == "Windows":
            with self.lock:
                if self.thread is None or not self.thread.is_alive():
                    self.thread = threading.Thread(target=self._windows_loop, daemon=True, name="sound")
                    self.thread.start()
            self.jobs.put((path, seconds))
            return True
        cmd = ["afplay", str(path)] if self.system == "Darwin" and self.which("afplay") else \
            self._linux_cmd(path, kind) if self.system != "Darwin" else None
        if not cmd:
            log.info("No sound player on this computer; the celebration plays without sound.")
            return False
        with self.lock:
            self._stop_proc()
            try:
                self.proc = self.popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as e:
                log.warning("Couldn't play the celebration sound: %s", e)
                return False
        threading.Timer(seconds + 2, self._stop_if, args=(self.proc,)).start()   # never longer than the clip
        return True

    def _stop_proc(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self.proc = None

    def _stop_if(self, proc):
        with self.lock:
            if self.proc is proc:
                self._stop_proc()

    def _windows_loop(self):
        send = self.mci or _mci()
        playing_until = None
        while True:
            try:
                job = self.jobs.get(timeout=0.25)
            except queue.Empty:
                job = None
            if playing_until is not None and (job is not None or time.monotonic() >= playing_until):
                send("close elxsound")
                playing_until = None
            if job is None:
                continue
            path, seconds = job
            if '"' in str(path):
                continue
            kind = "waveaudio" if path.suffix.lower() == ".wav" else "mpegvideo"
            if send(f'open "{path}" type {kind} alias elxsound') != 0:
                log.warning("Windows couldn't open the celebration sound.")
                continue
            if send("play elxsound") != 0:
                send("close elxsound")
                log.warning("Windows couldn't play the celebration sound.")
                continue
            playing_until = time.monotonic() + seconds + 0.5


def _mci():
    import ctypes
    f = ctypes.windll.winmm.mciSendStringW
    f.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    f.restype = ctypes.c_uint32
    return lambda cmd: f(cmd, None, 0, None)

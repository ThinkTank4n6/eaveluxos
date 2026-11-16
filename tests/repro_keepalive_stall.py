import time  # 4.1.3 review #1: the keep-alive blocked the 9-a-second stream (lights froze on slow Wi-Fi)
class Controller:                                  # answers a keep-alive after `delay` seconds (busy Wi-Fi)
    def __init__(s, delay): s.delay, s.frames, s.asked = delay, 0, []
    def send_levels(s): s.frames += 1
    def ping_and_wait(s): time.sleep(s.delay)      # old: send the keep-alive, block until the answer
    def ping(s): s.asked.append(time.monotonic())  # new: send it, count answers as they arrive
def old_loop(c, secs, every=1.0):
    end, nxt = time.monotonic() + secs, 0
    while time.monotonic() < end:
        c.send_levels()
        if time.monotonic() >= nxt: c.ping_and_wait(); nxt = time.monotonic() + every
        time.sleep(0.11)
def new_loop(c, secs, every=1.0):                  # FIX: answers are collected as they arrive
    end, nxt = time.monotonic() + secs, 0
    while time.monotonic() < end:
        c.send_levels()                            # (no answers for 15 s = connection lost)
        if time.monotonic() >= nxt: c.ping(); nxt = time.monotonic() + every
        time.sleep(0.11)
for loop in (old_loop, new_loop):
    c = Controller(delay=0.8); loop(c, 3); print(loop.__name__, c.frames, "level frames in 3 s (about 27 expected)")

"""4.19 review #1, standalone: a button pressed during a fade waited for all of it. [--fixed]"""
import sys, threading, time
FIXED, STEP, FRAMES, CONTROLLERS = "--fixed" in sys.argv, 0.05, 20, 3   # an 8-second fade at 4 a second, scaled down
lock, presses = threading.Lock(), [0]                  # the controller's one-command-at-a-time lock; button presses so far
def fade():                                            # the scheduler: each controller in turn, frame by frame
    with lock:
        seen = presses[0]
        for _ in range(CONTROLLERS):
            for _ in range(FRAMES):
                if FIXED and presses[0] != seen:       # the fix: a press ends the fade at once
                    return
                time.sleep(STEP)
t = threading.Thread(target=fade); t.start(); time.sleep(0.2)
t0 = time.monotonic(); presses[0] += 1                 # "Lights off" pressed during the fade
with lock:                                             # it can only be sent when the fade lets go
    waited = time.monotonic() - t0
t.join()
print(f"BUG: a button pressed during a fade waited {waited:.1f} s (scaled; 22 s for real)" if waited > 0.5
      else f"OK: a button pressed during a fade waited {waited:.2f} s")
sys.exit(1 if waited > 0.5 else 0)

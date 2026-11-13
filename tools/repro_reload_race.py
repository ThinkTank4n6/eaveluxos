import threading, time  # Repro: a settings reload during an in-flight send is lost (EaveLuxOS controller.py)
class Cloud:  # mock Trimlight cloud; the first send stalls like a slow network call
    def __init__(s): s.sent, s.gate, s.slow = [], threading.Event(), True
    def send(s, color): (s.gate.wait(5) if s.slow else None); s.sent.append(color)
class Ctrl:
    def __init__(s, cloud): s.cloud, s.color, s.applied_key = cloud, "warm", None; s.lock, s.apply_lock = threading.RLock(), threading.Lock()
    def tick(s):
        with s.apply_lock:
            with s.lock: key, color = "on|Every night|step0", s.color   # key has no pattern contents
            if key == s.applied_key: return
            s.cloud.send(color)                                          # network call, self.lock NOT held
            with s.lock: s.applied_key = key                             # BUG: overwrites reload()'s reset
    def reload(s, color):
        with s.lock: s.color, s.applied_key = color, None                # "re-apply whatever the new settings say"
        s.tick()
cloud = Cloud(); c = Ctrl(cloud)
t = threading.Thread(target=c.tick); t.start(); time.sleep(0.1)         # scheduler is mid-send
r = threading.Thread(target=c.reload, args=("green",)); r.start(); time.sleep(0.1)  # user saves an edited pattern
cloud.slow = False; cloud.gate.set(); t.join(); r.join(); c.tick()
print("sent:", cloud.sent, "->", "BUG: edit lost" if cloud.sent[-1] != "green" else "OK")

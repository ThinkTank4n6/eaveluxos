"""EaveLuxOS 3.17.0 bug #1: a rule's brightness/speed flattens a split pattern. Run: python repro_split_levels.py"""
parts = {"Upstairs": {"mode": 5, "speed": 20, "brightness": 80},     # slow, dim warm twinkle
         "Garage": {"mode": 0, "speed": 0, "brightness": 255}}       # solid security white
rule_levels = {"brightness": 200, "speed": 200}                       # the rule's own brightness and speed
sent = {}                                                             # mock Trimlight cloud: what each controller got

def apply_buggy(levels):                       # controller._apply in 3.17.0
    for dev, part in parts.items():
        payload = dict(part); payload.update(levels); sent[dev] = payload
def apply_fixed(levels, base=parts["Upstairs"]["brightness"]):   # 3.17.1: keep each part's own speed; scale brightness
    for dev, part in parts.items():
        payload = dict(part)
        if "brightness" in levels:                # the rule dims or brightens every part by the same ratio
            payload["brightness"] = max(1, min(255, round(part["brightness"] * levels["brightness"] / base)))
        sent[dev] = payload

apply_buggy(rule_levels); print("3.17.0:", sent)
assert sent["Upstairs"]["speed"] == sent["Garage"]["speed"] == 200, "bug reproduced: both controllers flattened"
apply_fixed(rule_levels); print("3.17.1:", sent)
assert sent["Upstairs"]["speed"] == 20 and sent["Garage"]["speed"] == 0 and sent["Upstairs"]["brightness"] < sent["Garage"]["brightness"]

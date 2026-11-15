# 3.19.0 review #1: a code pasted in a sentence failed; removing all spaces glued the next word on.
import base64, json, re, zlib
def make(doc):                                   # what sharecode.encode makes (no app needed)
    c = zlib.compressobj(9, zlib.DEFLATED, -15); raw = c.compress(json.dumps(doc).encode()) + c.flush()
    return "ELX1:" + base64.urlsafe_b64encode(raw).decode().rstrip("=")
def unpack(body, strict):
    d = zlib.decompressobj(-15); out = d.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if strict and (d.unused_data or not d.eof): raise ValueError("extra data")
    return json.loads(out)
def old(text): return unpack(re.search(r"ELX1:[A-Za-z0-9_-]+", re.sub(r"\s+", "", text)).group(0)[5:], False)
def new(text):                                   # FIX: join only across line breaks, longest that decodes cleanly
    parts = re.search(r"ELX1:([A-Za-z0-9_-]+(?:[ \t]*\r?\n[ \t]*[A-Za-z0-9_-]+)*)", text).group(1)
    for n in range(len(segs := re.split(r"\s+", parts)), 0, -1):
        try: return unpack("".join(segs[:n]), True)
        except (ValueError, zlib.error): pass
    raise ValueError("damaged")
code = make({"v": 1, "p": [{"label": "Christmas", "colors": ["#FF0000", "#00C000"]}]})
for f, msg in ((f, m) for f in (old, new) for m in (f"Here's mine: {code} enjoy!", f"{code[:40]}\n{code[40:]}\nThanks")):
    try: print(f.__name__, "OK  ", f(msg)["p"][0]["label"])
    except Exception as e: print(f.__name__, "FAIL", type(e).__name__)

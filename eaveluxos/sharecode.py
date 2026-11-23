# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Share codes (3.19): one or a few patterns as a short text, like
"ELX1:eNq...", to paste in a message or show as a QR code (static/qr.js).

The code is compressed JSON: {"v": 1, "p": [pattern, ...], "r": minutes}
("r": how long each shows, when they're a playlist). A code from someone
else is data: only self-contained patterns get in (colors with motion, or a
built-in effect), each checked exactly like a Community pattern, never a
pattern saved on someone's controller, a split by controller, a schedule,
devices, a location or credentials. Sizes are capped before and after
decompressing, so a code can't be a "zip bomb".
"""
import base64
import json
import re
import zlib

from .community import PATTERN_KEYS, CommunityError, clean_pattern

PREFIX = "ELX1:"
MAX_PATTERNS = 8
MAX_CODE = 6000             # characters
MAX_JSON = 64_000           # bytes once decompressed


class ShareError(ValueError):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def encode(patterns: list, rotate: int | None = None, extra: dict | None = None) -> str:
    """Pattern definitions (as in settings) -> a share code. extra (4.21):
    {"s": a Studio show} or {"a": [an automation template]}."""
    if not (0 if extra else 1) <= len(patterns) <= MAX_PATTERNS:
        raise ShareError(f"Share 1 to {MAX_PATTERNS} patterns at a time.")
    doc = {"v": 1, "p": [{k: v for k, v in p.items() if k in PATTERN_KEYS} for p in patterns], **(extra or {})}
    if rotate and len(patterns) > 1:
        doc["r"] = int(rotate)
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = c.compress(json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()) + c.flush()
    code = PREFIX + _b64(raw)
    if len(code) > MAX_CODE:
        raise ShareError("Those patterns are too big for a share code. Share fewer, or export a file.")
    return code


def encode_show(show) -> dict:
    """4.21: a Studio show as a share code (its looks travel inside it)."""
    from .studio import check_show
    try:
        s = check_show(show)
    except ValueError as e:
        raise ShareError(str(e)) from None
    code = encode([], extra={"s": s})
    return {"code": code, "length": len(code), "labels": [s["name"]]}


def encode_automation(a: dict, effects: dict) -> dict:
    """4.21: an automation as a share code: a template and its patterns."""
    from .marketplace import TemplateError, make_template
    try:
        t, pats = make_template(a, effects)
    except TemplateError as e:
        raise ShareError(str(e)) from None
    code = encode(pats, extra={"a": [t]})
    return {"code": code, "length": len(code), "labels": [t["name"]]}


def encode_keys(effects: dict, keys, rotate=None) -> dict:
    """The /api/share request: the user's own patterns by key."""
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
        raise ShareError("Choose the patterns to share.")
    out = []
    for k in keys[:MAX_PATTERNS + 1]:
        e = effects.get(k)
        if not isinstance(e, dict):
            raise ShareError(f"There's no pattern '{k}'.")
        label = e.get("label") or k
        if e.get("scene"):
            raise ShareError(f"“{label}” is drawn bulb by bulb for this house, so it can't be shared as a code. Export a file instead.")
        if "colors" not in e and "builtin" not in e:
            raise ShareError(f"“{label}” lives on your controller or is split by controller, so it can't be shared. "
                             "Share the patterns it uses instead.")
        out.append({**e, "label": label})
    if rotate is not None and (isinstance(rotate, bool) or not isinstance(rotate, int) or not 1 <= rotate <= 240):
        raise ShareError("Each pattern shows 1 to 240 minutes.")
    code = encode(out, rotate)
    return {"code": code, "length": len(code), "labels": [p["label"] for p in out]}


# A code, possibly wrapped onto several lines by a messaging app. Words after
# it on the same line ("ELX1:… enjoy!") are never joined on (3.19.1).
CODE_RE = re.compile(r"ELX1:([A-Za-z0-9_-]+(?:[ \t]*\r?\n[ \t]*[A-Za-z0-9_-]+)*)")


def _unpack(body: str):
    """Base64 and deflate, strictly: the compressed data must end exactly
    where the code does (nothing extra, nothing cut off)."""
    raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    d = zlib.decompressobj(-15)
    data = d.decompress(raw, MAX_JSON + 1)
    if len(data) > MAX_JSON or d.unconsumed_tail:
        raise ShareError("That share code holds too much.")
    if not d.eof or d.unused_data:
        raise ValueError("not a whole code")
    return json.loads(data.decode("utf-8"))


def decode(text) -> dict:
    """A share code (or a message containing one) -> {"patterns": [...],
    "rotate": minutes|None}, every pattern checked."""
    if not isinstance(text, str):
        raise ShareError("Paste a share code (it starts with ELX1:).")
    m = CODE_RE.search(text[:MAX_CODE * 2])
    if not m:
        raise ShareError("That isn't an EaveLuxOS share code (it starts with ELX1:).")
    # Wrapped lines are joined back; a word on a line of its own after the
    # code ("Thanks") is dropped by trying the longest join that is a whole,
    # valid code first.
    segs = re.split(r"\s+", m.group(1))[:100]
    if len(PREFIX) + len(segs[0]) > MAX_CODE:
        raise ShareError("That share code is too long.")
    doc, code = None, None
    for n in range(len(segs), 0, -1):
        body = "".join(segs[:n])
        if len(PREFIX) + len(body) > MAX_CODE:
            continue
        try:
            doc, code = _unpack(body), PREFIX + body
            break
        except ShareError:
            raise
        except (ValueError, zlib.error, UnicodeDecodeError):
            continue
    if doc is None:
        raise ShareError("That share code is damaged. Copy all of it, from ELX1: to the end.")
    if not isinstance(doc, dict) or doc.get("v") != 1 or not isinstance(doc.get("p"), list):
        raise ShareError("That share code is from a newer EaveLuxOS, or damaged.")
    kind = "show" if "s" in doc else "automation" if "a" in doc else "patterns"
    if not (0 if kind != "patterns" else 1) <= len(doc["p"]) <= MAX_PATTERNS:
        raise ShareError(f"A share code holds 1 to {MAX_PATTERNS} patterns.")
    pats = []
    for i, p in enumerate(doc["p"]):
        try:
            pats.append(clean_pattern(f"shared-{i + 1}", {"pattern": p}))
        except CommunityError as e:
            raise ShareError(str(e).replace("That community pattern", f"Pattern {i + 1} in the code")) from None
    r = doc.get("r")
    rotate = r if isinstance(r, int) and not isinstance(r, bool) and 1 <= r <= 240 and len(pats) > 1 else None
    out = {"kind": kind, "patterns": pats, "rotate": rotate, "code": code}
    if kind == "show":                          # 4.21: a Studio show
        from .studio import check_show
        try:
            out["show"] = check_show(doc["s"])
        except ValueError as e:
            raise ShareError(f"That shared show isn't valid ({e}).") from None
    elif kind == "automation":                  # 4.21: an automation template
        from .marketplace import TemplateError, check_template
        a = doc["a"]
        if not (isinstance(a, list) and len(a) == 1):
            raise ShareError("That shared automation is damaged.")
        try:
            out["automation"] = check_template(a[0], len(pats))
        except TemplateError as e:
            raise ShareError(str(e)) from None
    return out

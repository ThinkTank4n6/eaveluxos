#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Check every pattern in patterns/ and build index.json for EaveLuxOS's
community library (Patterns › Community).

    python3 build_index.py           # check, then write index.json
    python3 build_index.py --check   # check only, and fail if index.json is out of date

Standard library only. The rules match what EaveLuxOS accepts, and EaveLuxOS
checks each pattern again when someone tries or adds it.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")
FILE_KEYS = {"name", "author", "description", "tags", "pattern"}
PATTERN_KEYS = {"label", "colors", "counts", "custom_mode", "speed", "brightness", "exact_colors",
                "builtin", "pixel_len", "reverse"}
MAX_BYTES = 100_000


def _int(p, k, lo, hi, errs, default=None):
    v = p.get(k, default)
    if v is None:
        return
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        errs.append(f"'{k}' must be a whole number {lo}-{hi}")


def check_file(path: Path) -> tuple[dict | None, list[str]]:
    errs = []
    pid = path.stem
    if not ID_RE.fullmatch(pid):
        errs.append("file name must be lower-case letters, digits and dashes, like candy-cane.json")
    if path.stat().st_size > MAX_BYTES:
        return None, errs + [f"file is larger than {MAX_BYTES} bytes"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        return None, errs + [f"not valid JSON ({e})"]
    if not isinstance(data, dict):
        return None, errs + ["must be a JSON object"]
    for k in sorted(set(data) - FILE_KEYS):
        errs.append(f"unknown field '{k}'")
    name = data.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        errs.append("'name' is required, up to 60 characters")
    for k, n in (("author", 40), ("description", 200)):
        if k in data and (not isinstance(data[k], str) or len(data[k]) > n):
            errs.append(f"'{k}' must be text, up to {n} characters")
    tags = data.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 8 or not all(isinstance(t, str) and 1 <= len(t) <= 24 for t in tags):
        errs.append("'tags' must be up to 8 short words")
    p = data.get("pattern")
    if not isinstance(p, dict):
        return None, errs + ["'pattern' is required"]
    for k in sorted(set(p) - PATTERN_KEYS):
        errs.append(f"pattern: unknown field '{k}' (a 'saved' pattern can't be shared: it points at one controller)")
    _int(p, "speed", 0, 255, errs)
    _int(p, "brightness", 0, 255, errs)
    if "colors" in p and "builtin" in p:
        errs.append("pattern: give either 'colors' or 'builtin', not both")
    if "colors" in p:
        cols = p["colors"]
        if not isinstance(cols, list) or not 1 <= len(cols) <= 30 or not all(isinstance(c, str) and HEX_RE.fullmatch(c) for c in cols):
            errs.append("pattern: 'colors' must be 1-30 colors like #FF8800")
            cols = []
        counts = p.get("counts", [3] * len(cols))
        if not isinstance(counts, list) or len(counts) != len(cols) or \
                not all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 90 for n in counts):
            errs.append("pattern: 'counts' must have one number 1-90 per color")
        _int(p, "custom_mode", 0, 16, errs)
    elif "builtin" in p:
        _int(p, "builtin", 0, 179, errs)
        _int(p, "pixel_len", 1, 90, errs)
    else:
        errs.append("pattern: needs 'colors' or 'builtin'")
    if errs:
        return None, errs
    preview = list(dict.fromkeys(c.upper() for c in p.get("colors", [])))[:8]
    entry = {"id": pid, "name": name.strip(), "author": (data.get("author") or "").strip(),
             "description": (data.get("description") or "").strip(), "tags": [t.strip().lower() for t in tags],
             "colors": preview}
    return entry, []


def build(root: Path = HERE) -> tuple[dict, dict]:
    entries, problems = [], {}
    for f in sorted((root / "patterns").glob("*.json")):
        e, errs = check_file(f)
        if errs:
            problems[f.name] = errs
        else:
            entries.append(e)
    entries.sort(key=lambda e: e["name"].lower())
    return {"version": 1, "patterns": entries}, problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    index, problems = build()
    for name, errs in problems.items():
        for e in errs:
            print(f"{name}: {e}")
    if problems:
        return 1
    text = json.dumps(index, indent=1, ensure_ascii=False) + "\n"
    target = HERE / "index.json"
    if "--check" in argv:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print("index.json is out of date: run python3 build_index.py")
            return 1
        print(f"{len(index['patterns'])} patterns OK")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"Wrote index.json with {len(index['patterns'])} patterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())

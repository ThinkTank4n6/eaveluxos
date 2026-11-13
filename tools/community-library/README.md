# EaveLuxOS community patterns

Patterns shared by EaveLuxOS owners. EaveLuxOS shows them under
**Patterns › Community**, where anyone can try one on their lights and add it
to their own patterns.

This folder is a starter kit: its contents become their own public GitHub
repository, which EaveLuxOS reads at
`https://raw.githubusercontent.com/ThinkTank4n6/eaveluxos-patterns/main/`.

## Create the repository (once)

1. On GitHub, create a **public** repository named `eaveluxos-patterns`.
2. Copy everything in this folder into it, including the hidden `.github`
   folder, and push it to the `main` branch.
3. That's all. Nobody else can change the repository: other people can only
   *propose* a pattern with a pull request, the **Check patterns** check runs
   on it, and only you can merge it. Don't add branch protection to `main`:
   after each merge the **Build index** workflow saves the new `index.json`
   there itself, and protection would block it, so new patterns would never
   appear.

EaveLuxOS shows the patterns within 15 minutes (or straight away with
**Refresh**).

## Share a pattern

1. In EaveLuxOS, open the pattern in **Create** and note its colors, counts,
   animation, speed and brightness (or export your patterns from **Settings ›
   Share and back up** and copy the pattern from that file).
2. Add a file to `patterns/` named like `candy-cane.json` (lower-case letters,
   digits and dashes):

   ```json
   {
    "name": "Candy cane",
    "author": "Your name or handle",
    "description": "Red and white stripes that slowly chase along the roofline.",
    "tags": ["christmas", "red", "white"],
    "pattern": {"label": "Candy cane", "colors": ["#FF0000", "#FFFFFF"], "counts": [4, 4],
                "custom_mode": 1, "speed": 60, "brightness": 200}
   }
   ```

   `pattern` is exactly what EaveLuxOS stores for a pattern: either `colors`
   (1 to 30, with `counts`, 1 to 90 bulbs each, and `custom_mode` 0 to 16) or
   `builtin` (0 to 179, with `pixel_len`), plus `speed` and `brightness`
   (0 to 255). A pattern saved only in one controller's Trimlight app (`saved`)
   can't be shared.
3. Open a pull request. The **Check patterns** check runs
   `python3 build_index.py`; fix anything it lists.

## Review and merge (owner)

Merge only when **Check patterns** has passed. Try the pattern before merging:
the pull request's file is plain text, and
EaveLuxOS checks every pattern again before anyone can try or add it. After you
merge, the **Build index** workflow rebuilds `index.json` and commits it.

To build it yourself instead: `python3 build_index.py` (or `--check` to only
check).

## What EaveLuxOS does with this

It reads `index.json` (at most 1 MB) and, when someone presses **Try** or
**Add**, that one pattern's file (at most 100 KB), over HTTPS. It keeps only the
known fields, checks the pattern like one saved by hand, and adds it only to
that person's patterns. Nothing in this repository can change schedules,
settings or anything else.

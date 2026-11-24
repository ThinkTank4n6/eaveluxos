"""4.22.1 review #1: a Mac app opened where it was downloaded runs from a
temporary copy; Start automatically saved that place, which is gone after a
restart, so the app never came back. Standalone; prints BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
disk = {"/private/var/folders/x1/T/AppTranslocation/9F3A/d/EaveLuxOS.app/Contents/MacOS/EaveLuxOS"}
running_from = next(iter(disk))


def turn_on_start_automatically():
    if FIXED and ("/AppTranslocation/" in running_from or running_from.startswith("/Volumes/")):
        return "refused: move EaveLuxOS to Applications and open it from there"
    return running_from                              # what the LaunchAgent will start


saved = turn_on_start_automatically()
disk.clear()                                         # shut down: macOS throws the temporary copy away
if saved in disk or saved.startswith("refused"):
    print("OK: nothing points at a copy that disappears;", saved)
else:
    print("BUG: after the restart launchd starts", saved, "which no longer exists")

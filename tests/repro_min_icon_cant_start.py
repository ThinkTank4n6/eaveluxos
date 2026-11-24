"""4.22.2 review #1: after Quit, the EaveLuxOS icon on the desktop (the
browser's installed app) only said "Can't reach EaveLuxOS"; nothing on it
could start the program. Standalone; prints BUG, or OK with --fixed."""
import sys

FIXED = "--fixed" in sys.argv
registry = {}                                      # what this computer knows how to open
running = False


def program_starts():
    if FIXED:                                      # 4.22.2: eaveluxos:// starts this copy
        registry["eaveluxos"] = lambda: "started"


def cant_reach_page():
    buttons = ["Try again"] + (["Start EaveLuxOS"] if FIXED else [])
    return buttons


program_starts()
running = False                                    # Quit
clicked = "Start EaveLuxOS" in cant_reach_page() and registry.get("eaveluxos", lambda: None)()
print("OK: the icon's page started EaveLuxOS" if clicked == "started"
      else "BUG: the icon's page can only Try again; the user must find and run the program by hand")

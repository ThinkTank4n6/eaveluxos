# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
import os

# Tests make their own temporary app folders and expect ./data inside them.
# Without this, on Windows they'd use the real %LOCALAPPDATA%\\EaveLuxOS (3.7).
os.environ["EAVELUXOS_PORTABLE"] = "1"

# The real cloud needs a moment after a resync request; the fake one does not.
from eaveluxos.api import TrimlightAPI as _T
_T.resync_wait = 0
_T.read_retry_wait = 0           # 4.3.8

# Tests never ask GitHub for new versions.
os.environ["EAVELUXOS_UPDATE_CHECK"] = "0"

# Nor do they start phone alerts or game-day fetching.
os.environ["EAVELUXOS_BACKGROUND"] = "0"

# The backup timer waits for two matching readings 2 minutes apart before it
# writes (4.2.1). Tests of everything else write at once; the tests of that
# wait set it back (tests/test_safety421.py).
import eaveluxos.safety as _safety
_safety.SETTLE = 0
_safety.READBACK_PAUSES = (0, 0, 0)    # read again at once (4.3.8)
# The backup timer is paused for everyone in 4.3.9 (safety.PAUSED); its own
# tests still test it. tests/test_review438.py tests the pause.
_safety.PAUSED = False
import eaveluxos.lanlink as _lanlink
_lanlink.GREET_PAUSE = 0               # no half-second pause after each greeting (4.4)

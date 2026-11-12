# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
import os

# Tests make their own temporary app folders and expect ./data inside them.
# Without this, on Windows they'd use the real %LOCALAPPDATA%\\EaveLuxOS (3.7).
os.environ["EAVELUXOS_PORTABLE"] = "1"

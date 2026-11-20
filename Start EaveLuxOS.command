#!/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
# macOS: double-click to start. Keep this window open while the app runs.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "EaveLuxOS needs Python 3.11 or newer: https://www.python.org/downloads/"
  open "https://www.python.org/downloads/"; read -r -p "Press Return to close."; exit 1
fi
# AES encryption of the saved Trimlight secret needs the "cryptography" package.
# 4.10.1: pip updated first, and only a ready-made package: an old pip (an
# Intel Mac's, for one) can't find it and tries to build it, which fails.
if ! python3 -c 'import cryptography' 2>/dev/null; then
  echo "Installing the encryption package (one time only)..."
  python3 -m pip install --user --quiet --upgrade pip 2>/dev/null
  if ! python3 -m pip install --user --quiet --only-binary :all: cryptography 2>/dev/null; then
    echo "There's no ready-made encryption package for this Mac's Python or macOS, so EaveLuxOS"
    echo "starts without it: your Trimlight secret is saved unencrypted on this Mac, and the"
    echo "secure phone connection waits. The Manual (section 4, Download and start the app) says what to try."
  fi
fi
exec python3 main.py run --open

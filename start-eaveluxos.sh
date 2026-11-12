#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
# Linux: double-click (choose "Run in terminal") or run ./start-eaveluxos.sh
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "EaveLuxOS needs Python 3.11 or newer (sudo apt install python3 on Ubuntu/Debian)."; exit 1
fi
# AES encryption of the saved Trimlight secret needs the "cryptography" package.
if ! python3 -c 'import cryptography' 2>/dev/null; then
  echo "Installing the encryption package (one time only)..."
  python3 -m pip install --user --quiet cryptography 2>/dev/null \
    || echo "Couldn't install it. On Raspberry Pi OS / Debian / Ubuntu run: sudo apt install python3-cryptography"
fi
exec python3 main.py run --open

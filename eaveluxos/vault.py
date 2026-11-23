# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Encrypted backups (4.17): everything needed to set EaveLuxOS up again on
another computer (settings, the Trimlight account details and other secrets,
the accounts, optionally the house photos), locked with a passphrase.

The passphrase is stretched with scrypt (Python's own, from OpenSSL) and the
data sealed with AES-256-GCM, so a wrong passphrase or a changed file is
refused rather than read wrongly. Nothing is kept about the passphrase: a
lost passphrase means a lost backup."""
from __future__ import annotations

import base64
import hashlib
import json
import os

FORMAT = "eaveluxos-encrypted-backup"
VERSION = 1
N, R, P = 2 ** 15, 8, 1            # about a tenth of a second on a mini PC, 32 MB
MIN_PASSPHRASE = 10
MAX_FILE = 200 * 1024 * 1024

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:                 # pragma: no cover - depends on the computer
    AESGCM = None


class VaultError(Exception):
    pass


def available() -> bool:
    return AESGCM is not None


def _key(passphrase: str, salt: bytes, n=N, r=R, p=P) -> bytes:
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=128 * r * n * 2, dklen=32)


def seal(obj, passphrase: str) -> dict:
    if not available():
        raise VaultError("Encrypted backups need the \"cryptography\" package, which isn't installed here.")
    if not isinstance(passphrase, str) or len(passphrase) < MIN_PASSPHRASE:
        raise VaultError(f"Use a passphrase of at least {MIN_PASSPHRASE} characters.")
    salt, nonce = os.urandom(16), os.urandom(12)
    head = {"format": FORMAT, "v": VERSION, "kdf": {"name": "scrypt", "n": N, "r": R, "p": P,
                                                    "salt": base64.b64encode(salt).decode()},
            "nonce": base64.b64encode(nonce).decode()}
    aad = json.dumps(head, sort_keys=True).encode()
    data = AESGCM(_key(passphrase, salt)).encrypt(nonce, json.dumps(obj).encode(), aad)
    return {**head, "data": base64.b64encode(data).decode()}


def open_(blob, passphrase: str):
    if not available():
        raise VaultError("Encrypted backups need the \"cryptography\" package, which isn't installed here.")
    if not (isinstance(blob, dict) and blob.get("format") == FORMAT):
        raise VaultError("That isn't an EaveLuxOS encrypted backup.")
    if blob.get("v") != VERSION:
        raise VaultError("That backup was made by a newer EaveLuxOS. Update first.")
    try:
        k = blob["kdf"]
        n, r, p = int(k["n"]), int(k["r"]), int(k["p"])
        if k.get("name") != "scrypt" or not (2 ** 14 <= n <= 2 ** 20 and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
            raise ValueError("kdf")
        salt, nonce = base64.b64decode(k["salt"], validate=True), base64.b64decode(blob["nonce"], validate=True)
        data = base64.b64decode(blob["data"], validate=True)
    except (KeyError, TypeError, ValueError):
        raise VaultError("That backup file is damaged.") from None
    head = {kk: blob[kk] for kk in ("format", "v", "kdf", "nonce")}
    aad = json.dumps(head, sort_keys=True).encode()
    try:
        plain = AESGCM(_key(str(passphrase or ""), salt, n, r, p)).decrypt(nonce, data, aad)
    except Exception:
        raise VaultError("Wrong passphrase, or the file was changed.") from None
    return json.loads(plain)

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Encryption at rest for the secrets table (AES-256-GCM).

Each value in the secrets table is stored as "enc1:" + base64(nonce + ciphertext),
with the row's key name as associated data, so a value can't be moved to a
different row. Older plain-JSON values are still read and are re-encrypted
the next time the app starts.

Where the key lives
- EAVELUXOS_SECRET_KEY (64 hex characters or url-safe base64 of 32 bytes), if
  set; use this to keep the key off the data disk.
- Otherwise data/secret.key, created on first use, owner-only.

What this protects: copies of the database on their own (a backup, a synced
folder, a damaged copy kept after recovery, a database sent for support). It
doesn't protect against someone who can read both the database and the key,
such as malware running as your user. Keep the data folder private.

AES needs the "cryptography" package. Without it the app keeps working and
stores values as before, and the app shows a warning asking to install it.
"""
import base64
import binascii
import os
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - depends on the computer
    AESGCM = None

PREFIX = "enc1:"
KEY_ENV = "EAVELUXOS_SECRET_KEY"


class SecretKeyError(Exception):
    pass


def available() -> bool:
    return AESGCM is not None


def _decode_key(text: str) -> bytes:
    text = text.strip()
    try:
        raw = bytes.fromhex(text)
    except ValueError:
        try:
            raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        except (ValueError, binascii.Error):
            raise SecretKeyError(f"{KEY_ENV} isn't valid hex or base64.") from None
    if len(raw) != 32:
        raise SecretKeyError("The secret key must be 32 bytes (256 bits).")
    return raw


def load_key(data_dir: Path, restrict=None, create: bool = True) -> bytes | None:
    """Return the 32-byte key, creating data/secret.key if needed."""
    env = os.environ.get(KEY_ENV)
    if env:
        return _decode_key(env)
    path = data_dir / "secret.key"
    if path.exists():
        raw = path.read_bytes().strip()
        try:
            return _decode_key(raw.decode())
        except (UnicodeDecodeError, SecretKeyError):
            raise SecretKeyError(f"{path} is damaged. Restore it from a backup, or delete it and enter your "
                                 "Trimlight details and app password again.") from None
    if not create:
        return None
    key = os.urandom(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key.hex() + "\n")
    if os.name == "nt" and restrict:
        restrict(path)
    return key


class SecretBox:
    def __init__(self, key: bytes | None):
        self.key = key
        self.aead = AESGCM(key) if (key and AESGCM) else None

    @property
    def active(self) -> bool:
        return self.aead is not None

    def seal(self, name: str, plaintext: str) -> str:
        if not self.aead:
            return plaintext
        nonce = os.urandom(12)
        ct = self.aead.encrypt(nonce, plaintext.encode(), name.encode())
        return PREFIX + base64.b64encode(nonce + ct).decode()

    def open(self, name: str, stored: str) -> str:
        """Plain values (from before encryption) pass through unchanged."""
        if not stored.startswith(PREFIX):
            return stored
        if not self.aead:
            raise SecretKeyError("This value is encrypted, but the key or the cryptography package is missing.")
        blob = base64.b64decode(stored[len(PREFIX):])
        try:
            return self.aead.decrypt(blob[:12], blob[12:], name.encode()).decode()
        except Exception:
            raise SecretKeyError("A stored secret couldn't be decrypted (wrong key or damaged).") from None


def is_sealed(stored: str) -> bool:
    return isinstance(stored, str) and stored.startswith(PREFIX)

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Where the app keeps its data: a SQLite database, data/eaveluxos.db.

  patterns          one row per pattern
  rules             schedule rules and weather rules, in order
  sections          everything else in the settings (location, map, ...)
  history           a snapshot of every save, for "restore an earlier version"
  secrets           Trimlight credentials, password hash, webhook token
  sessions          signed-in phones/computers (token hashes only)
  meta              settings revision and schema version

The database file holds secrets, so it's private to this user (chmod 600, or
an ACL on Windows). Every save is one transaction: a crash or power cut can't
leave half a file, and the app and the command-line tools can't overwrite
each other's changes. settings.last-good.json is rewritten after every save
as a plain-text recovery copy.

Installs from before 3.0 (settings.json / secrets.json / sessions.json, or
config.toml / .env) are imported once; the old files are kept, renamed.
"""
import hashlib
import sqlite3
import hmac
import json
import os
import secrets as pysecrets
import tempfile
import threading
import time
from pathlib import Path

from . import secretbox
from .schedule import _load_dotenv, read_toml

# Sign-ins end after this long without use (sliding). Administrators can pick
# another value from SESSION_IDLE_CHOICES; every sign-in also ends
# SESSION_MAX_DAYS after it began, however often it's used.
SESSION_IDLE_HOURS = 8
SESSION_IDLE_CHOICES = (1, 8, 24, 72, 168)
SESSION_MAX_DAYS = 7
SESSION_DAYS = SESSION_MAX_DAYS   # kept for older imports

ROLES = ("admin", "editor", "viewer")
USERNAME_RE = r"[a-z0-9_.-]{1,64}"
# scrypt cost: 2**15 x 8 x 128 bytes = 32 MiB of memory and roughly 50-150 ms per
# check, which is fine on a Raspberry Pi. The parameters are stored with each
# hash, so they can be raised later; older hashes are upgraded at sign-in.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1

DEFAULT_SETTINGS = {
    "location": {"latitude": 0.0, "longitude": 0.0, "timezone": "America/New_York", "dst_mode": "auto"},
    "service": {"devices": [], "web_host": "0.0.0.0", "web_port": 8787, "check_interval_seconds": 20},
    "effects": {
        "warm_white": {"label": "Warm white", "colors": ["#FFB46B"], "counts": [1], "custom_mode": 0, "brightness": 180},
        "christmas": {"label": "Christmas", "colors": ["#FF0000", "#00C000", "#FFFFFF"], "counts": [4, 4, 4],
                      "custom_mode": 1, "speed": 60, "brightness": 220},
        "halloween": {"label": "Halloween", "colors": ["#FF6A00", "#7A00FF"], "counts": [5, 5],
                      "custom_mode": 0, "brightness": 220},
        "july_4th": {"label": "Fourth of July", "colors": ["#FF0000", "#FFFFFF", "#0033FF"], "counts": [4, 4, 4],
                     "custom_mode": 0, "brightness": 220},
        "snowfall": {"label": "Snowfall", "colors": ["#FFFFFF", "#3A7BFF"], "counts": [3, 6],
                     "custom_mode": 6, "speed": 40, "brightness": 200},
        "security_white": {"label": "Security white", "colors": ["#FFFFFF"], "counts": [1],
                           "custom_mode": 0, "brightness": 255},
    },
    "rules": [
        {"name": "Christmas season", "dates": "11-27..01-06", "on": "sunset + 10", "off": "00:30",
         "effect": "christmas"},
        {"name": "Halloween week", "dates": "10-25..10-31", "on": "sunset", "off": "23:00", "effect": "halloween"},
        {"name": "Fourth of July", "dates": "07-03..07-05", "on": "sunset", "off": "01:00", "effect": "july_4th"},
        {"name": "Every night", "on": "sunset + 15", "off": "23:00", "effect": "warm_white"},
    ],
    "weather": {"enabled": False, "use": "either", "check_minutes": 15, "contact": ""},
    "weather_rules": [{"name": "Snowing", "when": ["snow"], "effect": "snowfall", "priority": 150}],
    "security": {"effect": "security_white", "minutes": 5},
}


def _restrict_windows(path: Path, folder: bool = False) -> bool:
    """chmod can't make a file private on Windows; use the system ACL tool to
    drop inherited permissions and allow only this user (and SYSTEM). For a
    folder, the grant is inherited by files created in it later."""
    import subprocess
    user = os.environ.get("USERNAME") or ""
    if not user:
        return False
    domain = os.environ.get("USERDOMAIN")
    who = f"{domain}\\{user}" if domain else user
    try:
        perm = "(OI)(CI)(F)" if folder else "(F)"
        r = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{who}:{perm}", "/grant:r", f"*S-1-5-18:{perm}"],
                           capture_output=True, text=True, timeout=15, creationflags=0x08000000)  # CREATE_NO_WINDOW
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _atomic_write(path: Path, data: dict, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    if private:
        if os.name == "nt":
            if not _restrict_windows(Path(tmp)):
                import logging
                logging.getLogger("eaveluxos").warning("Couldn't restrict access to %s; other accounts on this PC may be able to read it.", path.name)
        else:
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
    os.replace(tmp, path)


def _scrypt(pw: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(pw.encode(), salt=salt, n=n, r=r, p=p, maxmem=128 * r * (n + p + 2) + 1024 * 1024, dklen=32)


def hash_password(pw: str, salt: bytes | None = None) -> str:
    """scrypt (memory-hard), stored as scrypt$n$r$p$salt$hash."""
    salt = salt or os.urandom(16)
    dk = _scrypt(pw, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def _legacy_pbkdf2(pw: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 240_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    """Accepts scrypt hashes and the PBKDF2 hashes saved before 3.3."""
    try:
        parts = stored.split("$")
        if parts[0] == "scrypt" and len(parts) == 6:
            n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
            if not (2 ** 10 <= n <= 2 ** 20 and 1 <= r <= 32 and 1 <= p <= 16):
                return False
            dk = _scrypt(pw, bytes.fromhex(parts[4]), n, r, p)
            return hmac.compare_digest(dk.hex(), parts[5])
        if parts[0] == "pbkdf2" and len(parts) == 3:
            return hmac.compare_digest(_legacy_pbkdf2(pw, bytes.fromhex(parts[1])), stored)
        return False
    except (ValueError, AttributeError, TypeError):
        return False


def needs_rehash(stored: str) -> bool:
    """True for hashes weaker than the current setting (upgrade at sign-in)."""
    parts = (stored or "").split("$")
    if parts[0] != "scrypt" or len(parts) != 6:
        return True
    try:
        return (int(parts[1]), int(parts[2]), int(parts[3])) < (SCRYPT_N, SCRYPT_R, SCRYPT_P)
    except ValueError:
        return True


def _writable(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / f".write-test-{os.getpid()}"
        probe.write_text("ok")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_data_dir(base: Path) -> Path:
    """Data normally lives in ./data next to main.py. If that folder can't be
    written (for example the app was unzipped into Program Files), use the
    per-user app-data folder instead of failing. EAVELUXOS_DATA_DIR overrides
    both (the container image uses /data)."""
    forced = os.environ.get("EAVELUXOS_DATA_DIR")
    if forced:
        root = Path(forced)
        if not _writable(root):
            raise OSError(f"EAVELUXOS_DATA_DIR ({root}) can't be written by this user.")
        return root
    local = base / "data"
    # Never write inside a Mac app bundle (EaveLuxOS.app/Contents/MacOS):
    # it breaks the app's signature and the data would vanish on update.
    in_app_bundle = any(p.suffix == ".app" for p in base.parents) or base.suffix == ".app"
    if not in_app_bundle and _writable(local):
        return local
    import platform
    system = platform.system()
    if system == "Windows":
        parent, new, olds = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"), "EaveLuxOS", ("LumaOS", "TrimlightScheduler")
    elif system == "Darwin":
        parent, new, olds = Path.home() / "Library" / "Application Support", "EaveLuxOS", ("LumaOS", "TrimlightScheduler")
    else:
        parent, new, olds = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"), "eaveluxos", ("lumaos", "trimlight-scheduler")
    root = parent / new
    for old in olds:                                   # folders from before a rename
        if not root.exists() and (parent / old).is_dir():
            try:
                os.replace(parent / old, root)
            except OSError:
                root = parent / old
    if not _writable(root):
        raise OSError(f"Neither {local} nor {root} can be written. Move the app folder somewhere you can save files, such as Documents.")
    return root


class Conflict(Exception):
    """Settings were changed (by another device or tool) since the caller loaded them."""


SCHEMA_VERSION = 1
HISTORY_KEEP = 100
_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta     (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sections (name TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS patterns (key TEXT PRIMARY KEY, position INTEGER NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rules    (kind TEXT NOT NULL, position INTEGER NOT NULL, name TEXT NOT NULL,
                                     json TEXT NOT NULL, PRIMARY KEY (kind, position));
CREATE TABLE IF NOT EXISTS history  (rev INTEGER PRIMARY KEY, saved_at TEXT NOT NULL, summary TEXT NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS secrets  (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, label TEXT, created REAL NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS users    (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                                     role TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
"""
_RULE_KINDS = ("rules", "weather_rules")


def _summary(data: dict) -> str:
    def n(count, word):
        return f"{count} {word}{'' if count == 1 else 's'}"
    out = f"{n(len(data.get('effects') or {}), 'pattern')}, {n(len(data.get('rules') or []), 'rule')}"
    if data.get("weather_rules"):
        out += f", {n(len(data['weather_rules']), 'weather rule')}"
    return out


def read_service_settings(data_dir: Path) -> dict:
    """The 'service' section (host/port), read without opening a Store; used
    at startup before the app decides whether it's already running."""
    db = data_dir / "eaveluxos.db"
    for old_name in ("lumaos.db", "trimlight.db"):   # not yet renamed (first start after a rename)
        if not db.exists() and (data_dir / old_name).exists():
            db = data_dir / old_name
    try:
        if db.exists():
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                row = con.execute("SELECT json FROM sections WHERE name='service'").fetchone()
            finally:
                con.close()
            return json.loads(row[0]) if row else {}
        legacy = data_dir / "settings.json"
        return json.loads(legacy.read_text()).get("service", {}) if legacy.exists() else {}
    except (sqlite3.Error, OSError, ValueError, AttributeError):
        return {}


class Store:
    def __init__(self, base: Path):
        self.base = base
        self.dir = resolve_data_dir(base)
        self.db_path = self.dir / "eaveluxos.db"
        self.last_good_path = self.dir / "settings.last-good.json"
        for old_name in ("lumaos.db", "trimlight.db"):    # earlier names: LumaOS, Trimlight Scheduler
            legacy_db = self.dir / old_name
            if legacy_db.exists() and not self.db_path.exists():
                for suffix in ("", "-wal", "-shm"):
                    f = Path(str(legacy_db) + suffix)
                    if f.exists():
                        os.replace(f, Path(str(self.db_path) + suffix))
        self.lock = threading.RLock()
        self.warnings: list[str] = []   # shown in the app (e.g. a recovered database)
        self._cache, self._cache_rev = None, None
        self._sec_cache, self._sec_rev = None, None
        self.con = self._open()
        self.box = self._open_secretbox()
        if self._get_meta("schema") is None:
            self._first_run()
        self._seal_plain_secrets()
        self._migrate_accounts()
        if not self.last_good_path.exists():
            _atomic_write(self.last_good_path, self.settings)
        # one-time code for finishing setup from another device
        self.setup_code = f"{pysecrets.randbelow(10**6):06d}"

    # ---------------------------------------------------------------- database
    def _connect(self):
        con = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False, isolation_level=None)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")      # survive a power cut mid-save
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript(_SCHEMA)
        if "user_id" not in {r[1] for r in con.execute("PRAGMA table_info(sessions)")}:
            con.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")   # accounts (3.4)
        return con

    def _open(self):
        new = not self.db_path.exists()
        if new:
            # create the file private before anything is written to it
            self.db_path.touch(mode=0o600)
            if os.name == "nt":
                _restrict_windows(self.dir, folder=True)
        try:
            con = self._connect()
            ok = con.execute("PRAGMA quick_check").fetchone()[0]
            if ok != "ok":
                raise sqlite3.DatabaseError(ok)
        except sqlite3.DatabaseError as e:
            try:
                con.close()
            except Exception:
                pass
            stamp = time.strftime("%Y%m%d-%H%M%S")
            for suffix in ("", "-wal", "-shm"):
                f = Path(str(self.db_path) + suffix)
                if f.exists():
                    os.replace(f, f.with_name(f"eaveluxos.damaged-{stamp}.db{suffix}"))
            self.db_path.touch(mode=0o600)
            con = self._connect()
            restored = self._read(self.last_good_path)
            msg = f"The settings database couldn't be read ({e}). It was kept as eaveluxos.damaged-{stamp}.db"
            if isinstance(restored, dict):
                self._write_settings(con, restored, 0)
                msg += ", and your settings were restored from the last good copy. Enter your Trimlight account details and app password again under Settings."
            else:
                msg += ". No good copy was found, so the app started with the starter settings."
            self._set_meta("schema", str(SCHEMA_VERSION), con)
            self.warnings.append(msg)
            import logging
            logging.getLogger("eaveluxos").error(msg)
        if os.name != "nt":
            try:
                os.chmod(self.db_path, 0o600)
            except OSError:
                pass
        return con

    # ---------------------------------------------------------------- encryption at rest
    def _open_secretbox(self):
        if not secretbox.available():
            self.warnings.append("Your Trimlight secret is stored unencrypted because the \"cryptography\" package "
                                 "isn't installed. Install it (python3 -m pip install cryptography, or on Raspberry Pi "
                                 "OS / Debian: sudo apt install python3-cryptography) and restart the app.")
            return secretbox.SecretBox(None)
        sealed = any(secretbox.is_sealed(v) for (v,) in self.con.execute("SELECT value FROM secrets"))
        key_missing = not os.environ.get(secretbox.KEY_ENV) and not (self.dir / "secret.key").exists()
        try:
            key = secretbox.load_key(self.dir, restrict=_restrict_windows)
        except (secretbox.SecretKeyError, OSError) as e:
            self.warnings.append(f"Stored secrets can't be decrypted: {e}")
            return secretbox.SecretBox(None)
        if sealed and key_missing:
            self.warnings.append("The encryption key (secret.key) is missing, so your saved Trimlight details and app "
                                 "password can't be read. Restore secret.key from a backup, or enter them again.")
        return secretbox.SecretBox(key)

    def _seal_plain_secrets(self):
        """Encrypt values saved before encryption existed (once, at start)."""
        if not self.box.active:
            return
        with self.lock:
            rows = [(k, v) for k, v in self.con.execute("SELECT key, value FROM secrets") if not secretbox.is_sealed(v)]
            if not rows:
                return
            con = self.con
            con.execute("BEGIN IMMEDIATE")
            try:
                for k, v in rows:
                    con.execute("UPDATE secrets SET value=? WHERE key=?", (self.box.seal(k, v), k))
                self._set_meta("secrets_rev", pysecrets.token_hex(8), con)
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            # SQLite may keep the old plain pages in free space; clear them.
            try:
                con.execute("VACUUM")
                con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:
                pass
            self._sec_cache = None

    # ---------------------------------------------------------------- accounts (3.4)
    def _migrate_accounts(self):
        """Before 3.4 there was one shared app password. It becomes the
        password of an Administrator account named "admin", and devices that
        were signed in stay signed in as that account."""
        with self.lock:
            if self.con.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return
            ph = self.secrets.get("password_hash")
            if not ph:
                return
            uid = pysecrets.token_hex(8)
            con = self.con
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute("INSERT INTO users VALUES(?, 'admin', ?, 'admin', 0, ?)", (uid, ph, time.time()))
                con.execute("UPDATE sessions SET user_id=? WHERE user_id IS NULL", (uid,))
                con.execute("DELETE FROM secrets WHERE key='password_hash'")
                self._set_meta("secrets_rev", pysecrets.token_hex(8), con)
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            self._sec_cache = None
            self.warnings.append("EaveLuxOS now has user accounts. Your app password is now the password of the "
                                 "Administrator account \u201cadmin\u201d. Add accounts for other people under Settings \u203a Accounts.")

    @staticmethod
    def _public(row) -> dict:
        return {"id": row[0], "username": row[1], "role": row[3], "disabled": bool(row[4]), "created": row[5]}

    def has_users(self) -> bool:
        with self.lock:
            return self.con.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def users(self) -> list[dict]:
        with self.lock:
            return [self._public(r) for r in self.con.execute("SELECT * FROM users ORDER BY username")]

    def user(self, uid: str | None) -> dict | None:
        if not uid:
            return None
        with self.lock:
            row = self.con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return self._public(row) if row else None

    def user_by_name(self, username: str) -> tuple[dict, str] | None:
        """(public user, password hash) for sign-in, or None."""
        with self.lock:
            row = self.con.execute("SELECT * FROM users WHERE username=?", (str(username).strip().lower(),)).fetchone()
        return (self._public(row), row[2]) if row else None

    def password_hash_of(self, uid: str) -> str | None:
        with self.lock:
            row = self.con.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()
        return row[0] if row else None

    def _active_admins(self, con) -> int:
        return con.execute("SELECT count(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]

    def save_user(self, uid: str | None, username: str, role: str, disabled: bool = False,
                  password: str | None = None, keep_token: str | None = None) -> dict:
        """Create (uid None) or change an account. Raises ValueError with a
        message for the person. At least one active Administrator always
        remains. Any change to an existing account signs it out everywhere
        (except keep_token, the device making the change to its own account)."""
        import re
        username = str(username or "").strip().lower()
        if not re.fullmatch(USERNAME_RE, username):
            raise ValueError("Use 1-64 lowercase letters, numbers, dots, underscores or hyphens for the user name.")
        if role not in ROLES:
            raise ValueError("Choose Administrator, Editor or Viewer.")
        if password is not None and not 8 <= len(password) <= 256:
            raise ValueError("Passwords need 8-256 characters.")
        new_hash = hash_password(password) if password is not None else None   # slow: outside the lock
        with self.lock:
            con = self.con
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() if uid else None
                if uid and not old:
                    raise ValueError("That account no longer exists.")
                dup = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
                if dup and dup[0] != uid:
                    raise ValueError("That user name is taken.")
                if not old and new_hash is None:
                    raise ValueError("Set a password for the new account.")
                if old:
                    con.execute("UPDATE users SET username=?, role=?, disabled=?, password_hash=COALESCE(?, password_hash) WHERE id=?",
                                (username, role, int(bool(disabled)), new_hash, uid))
                    if self._active_admins(con) < 1:
                        raise ValueError("At least one active Administrator must remain.")
                    keep = hashlib.sha256(keep_token.encode()).hexdigest() if keep_token else None
                    con.execute("DELETE FROM sessions WHERE user_id=? AND hash IS NOT ?", (uid, keep))
                else:
                    uid = pysecrets.token_hex(8)
                    con.execute("INSERT INTO users VALUES(?, ?, ?, ?, ?, ?)",
                                (uid, username, new_hash, role, int(bool(disabled)), time.time()))
                    if self._active_admins(con) < 1:
                        raise ValueError("The first account must be an active Administrator.")
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
        return self.user(uid)

    def delete_user(self, uid: str):
        with self.lock:
            con = self.con
            con.execute("BEGIN IMMEDIATE")
            try:
                if not con.execute("DELETE FROM users WHERE id=?", (uid,)).rowcount:
                    raise ValueError("That account no longer exists.")
                if self._active_admins(con) < 1:
                    raise ValueError("At least one active Administrator must remain.")
                con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise

    def set_password_hash(self, uid: str, new_hash: str):
        """Silent upgrade of an older hash at sign-in (no sign-outs)."""
        with self.lock:
            self.con.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, uid))

    def end_user_sessions(self, uid: str, keep_token: str | None = None):
        keep = hashlib.sha256(keep_token.encode()).hexdigest() if keep_token else None
        with self.lock:
            self.con.execute("DELETE FROM sessions WHERE user_id=? AND hash IS NOT ?", (uid, keep))

    # ---------------------------------------------------------------- session policy
    def session_idle_hours(self) -> int:
        v = self.secrets.get("session_idle_hours")
        return v if v in SESSION_IDLE_CHOICES else SESSION_IDLE_HOURS

    def set_session_idle_hours(self, hours: int):
        if hours not in SESSION_IDLE_CHOICES:
            raise ValueError("Choose one of: " + ", ".join(f"{h} h" for h in SESSION_IDLE_CHOICES))
        self.save_secrets(session_idle_hours=hours)

    def _get_meta(self, key, con=None):
        row = (con or self.con).execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key, value, con=None):
        (con or self.con).execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                  (key, str(value)))

    @staticmethod
    def _read(path: Path):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, ValueError, OSError):
            return None

    # ---------------------------------------------------------------- import of older installs
    def _load_legacy(self, label: str, path: Path, fallback: Path | None = None):
        """Read a pre-3.0 JSON file. A damaged one is kept (renamed), the last
        good copy is used if there is one, and the app shows a warning."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("the file must contain a JSON object { ... }")
            return data
        except (ValueError, UnicodeDecodeError, OSError) as e:
            where = f" (line {e.lineno}, column {e.colno}: {e.msg})" if isinstance(e, json.JSONDecodeError) else f" ({e})"
            keep = path.with_name(f"{path.stem}.damaged-{time.strftime('%Y%m%d-%H%M%S')}.json")
            try:
                os.replace(path, keep)
            except OSError:
                keep = path
        if label == "sessions":
            return None
        restored = self._read(fallback) if fallback else None
        msg = f"{path.name} couldn't be read{where}. Your file was kept as {keep.name}"
        if isinstance(restored, dict):
            msg += ", and the last good copy of your settings was restored."
        elif label == "secrets":
            msg += ". Enter your Trimlight account details again under Settings."
        else:
            msg += ". No good copy was found, so the app started with the starter settings."
        self.warnings.append(msg)
        import logging
        logging.getLogger("eaveluxos").error(msg)
        return restored if isinstance(restored, dict) else None

    def _first_run(self):
        """Fill a new database: import an older install if there is one."""
        settings = secrets = sessions = None
        legacy = [self.dir / "settings.json", self.dir / "secrets.json", self.dir / "sessions.json"]
        if legacy[0].exists():
            settings = self._load_legacy("settings", legacy[0], self.last_good_path)
        elif (self.base / "config.toml").exists():
            settings = read_toml(self.base / "config.toml")
        if legacy[1].exists():
            secrets = self._load_legacy("secrets", legacy[1])
        elif (self.base / ".env").exists():
            _load_dotenv(self.base / ".env")
            secrets = {k2: v for k2, v in {"client_id": os.environ.get("TRIMLIGHT_CLIENT_ID", ""),
                                            "client_secret": os.environ.get("TRIMLIGHT_CLIENT_SECRET", ""),
                                            "webhook_token": os.environ.get("TRIMLIGHT_WEBHOOK_TOKEN", "")}.items() if v}
            pw = os.environ.get("TRIMLIGHT_UI_PASSWORD")
            if pw:
                secrets["password_hash"] = hash_password(pw)
            for k2 in ("TRIMLIGHT_CLIENT_ID", "TRIMLIGHT_CLIENT_SECRET", "TRIMLIGHT_WEBHOOK_TOKEN", "TRIMLIGHT_UI_PASSWORD"):
                os.environ.pop(k2, None)
        if legacy[2].exists():
            sessions = self._load_legacy("sessions", legacy[2])
        with self.lock:
            con = self.con
            con.execute("BEGIN IMMEDIATE")
            try:
                data = settings if isinstance(settings, dict) else json.loads(json.dumps(DEFAULT_SETTINGS))
                rev = int(data.get("_rev", 0) or 0)
                self._write_settings(con, data, rev)
                for k2, v in (secrets or {}).items():
                    if isinstance(v, (str, int, float, bool)):
                        con.execute("INSERT OR REPLACE INTO secrets(key, value) VALUES(?, ?)", (k2, json.dumps(v)))
                for h, v in (sessions or {}).items():
                    if isinstance(v, dict) and "expires" in v:
                        con.execute("INSERT OR REPLACE INTO sessions VALUES(?, ?, ?, ?)",
                                    (h, v.get("label", ""), v.get("created", time.time()), v["expires"]))
                self._set_meta("schema", SCHEMA_VERSION, con)
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for f in legacy:     # keep the old files, out of the way
            if f.exists():
                os.replace(f, f.with_name(f"{f.stem}.migrated-{stamp}.json"))

    # ---------------------------------------------------------------- settings
    def _write_settings(self, con, data: dict, rev: int):
        """Write the whole settings document as rows (inside a transaction)."""
        con.execute("DELETE FROM sections")
        con.execute("DELETE FROM patterns")
        con.execute("DELETE FROM rules")
        for i, (k, v) in enumerate((data.get("effects") or {}).items()):
            con.execute("INSERT INTO patterns(key, position, json) VALUES(?, ?, ?)", (k, i, json.dumps(v)))
        for kind in _RULE_KINDS:
            for i, r in enumerate(data.get(kind) or []):
                con.execute("INSERT INTO rules(kind, position, name, json) VALUES(?, ?, ?, ?)",
                            (kind, i, str(r.get("name", "")) if isinstance(r, dict) else "", json.dumps(r)))
        for k, v in data.items():
            if k not in ("effects", "_rev") + _RULE_KINDS:
                con.execute("INSERT INTO sections(name, json) VALUES(?, ?)", (k, json.dumps(v)))
        self._set_meta("rev", rev, con)

    def _assemble(self) -> dict:
        con = self.con
        data = {name: json.loads(j) for name, j in con.execute("SELECT name, json FROM sections")}
        data["effects"] = {k: json.loads(j) for k, j in con.execute("SELECT key, json FROM patterns ORDER BY position")}
        for kind in _RULE_KINDS:
            data[kind] = [json.loads(j) for (j,) in con.execute("SELECT json FROM rules WHERE kind=? ORDER BY position", (kind,))]
        data["_rev"] = int(self._get_meta("rev") or 0)
        return data

    @property
    def rev(self) -> int:
        with self.lock:
            return int(self._get_meta("rev") or 0)

    @property
    def settings(self) -> dict:
        """The settings document. Re-read when another process (a command-line
        tool, or a second copy of the app) has saved since we last looked."""
        with self.lock:
            rev = self.rev
            if self._cache is None or self._cache_rev != rev:
                self._cache, self._cache_rev = self._assemble(), rev
            return self._cache

    def save_settings(self, data: dict, expect_rev: int | None = None):
        """expect_rev: the _rev the editor started from; a mismatch means
        another device or tool saved in between, so refuse instead of
        overwriting. The check and the write are one database transaction."""
        with self.lock:
            con = self.con
            con.execute("BEGIN IMMEDIATE")
            try:
                cur = int(self._get_meta("rev") or 0)
                if expect_rev is not None and int(expect_rev) != cur:
                    raise Conflict()
                data = dict(data)
                data["_rev"] = cur + 1
                self._write_settings(con, data, cur + 1)
                con.execute("INSERT OR REPLACE INTO history(rev, saved_at, summary, json) VALUES(?, ?, ?, ?)",
                            (cur + 1, time.strftime("%Y-%m-%dT%H:%M:%S"), _summary(data), json.dumps(data)))
                con.execute("DELETE FROM history WHERE rev <= ?", (cur + 1 - HISTORY_KEEP,))
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            self._cache, self._cache_rev = data, cur + 1
            _atomic_write(self.last_good_path, data)  # plain-text recovery copy
            return cur + 1

    # ---------------------------------------------------------------- history
    def history(self, limit: int = 30) -> list[dict]:
        with self.lock:
            return [{"rev": r, "saved_at": t, "summary": s}
                    for r, t, s in self.con.execute("SELECT rev, saved_at, summary FROM history ORDER BY rev DESC LIMIT ?", (limit,))]

    def history_version(self, rev: int) -> dict | None:
        with self.lock:
            row = self.con.execute("SELECT json FROM history WHERE rev=?", (rev,)).fetchone()
            return json.loads(row[0]) if row else None

    # ---------------------------------------------------------------- secrets
    @property
    def secrets(self) -> dict:
        with self.lock:
            srev = self._get_meta("secrets_rev")
            if self._sec_cache is None or self._sec_rev != srev:
                out = {}
                for k, v in self.con.execute("SELECT key, value FROM secrets"):
                    try:
                        out[k] = json.loads(self.box.open(k, v))
                    except (secretbox.SecretKeyError, ValueError):
                        pass   # unreadable (key missing/wrong): treated as not set; a warning is shown
                self._sec_cache = out
                self._sec_rev = srev
            return self._sec_cache

    def save_secrets(self, **changes):
        with self.lock:
            con = self.con
            con.execute("BEGIN IMMEDIATE")
            try:
                for k, v in changes.items():
                    if v is None:
                        con.execute("DELETE FROM secrets WHERE key=?", (k,))
                    else:
                        con.execute("INSERT OR REPLACE INTO secrets(key, value) VALUES(?, ?)",
                                    (k, self.box.seal(k, json.dumps(v))))
                self._set_meta("secrets_rev", pysecrets.token_hex(8), con)
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            self._sec_cache = None

    # ---------------------------------------------------------------- sessions
    def new_session(self, label: str, user_id: str | None = None) -> str:
        """user_id None is a setup session (setup code, before any account
        exists); it stops working as soon as an account exists."""
        token = pysecrets.token_urlsafe(32)
        now = time.time()
        idle = self.session_idle_hours() * 3600
        with self.lock:
            self.con.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
            self.con.execute("INSERT INTO sessions(hash, label, created, expires, user_id) VALUES(?, ?, ?, ?, ?)",
                             (hashlib.sha256(token.encode()).hexdigest(), label[:80], now, now + idle, user_id))
        return token

    SETUP_USER = {"id": None, "username": "setup", "role": "admin", "disabled": False, "setup": True}

    def session_user(self, token: str | None) -> dict | None:
        """The account signed in with this token, or None. Sessions slide
        forward by the idle time, never past SESSION_MAX_DAYS after sign-in
        (or past the idle time, if that's longer). Sessions of disabled or
        deleted accounts don't count."""
        if not token:
            return None
        h = hashlib.sha256(token.encode()).hexdigest()
        now = time.time()
        idle = self.session_idle_hours() * 3600
        with self.lock:
            row = self.con.execute("SELECT expires, created, user_id FROM sessions WHERE hash=?", (h,)).fetchone()
            if not (row and row[0] > now):
                return None
            expires, created, uid = row
            if uid is None:
                user = None if self.has_users() else dict(self.SETUP_USER)
            else:
                user = self.user(uid)
                if user and user["disabled"]:
                    user = None
            if user is None:
                return None
            fresh = min(now + idle, created + max(SESSION_MAX_DAYS * 86400, idle))
            if fresh <= now:
                self.con.execute("DELETE FROM sessions WHERE hash=?", (h,))
                return None
            if expires > fresh or fresh - expires > 60:
                self.con.execute("UPDATE sessions SET expires=? WHERE hash=?", (fresh, h))
        return user

    def valid_session(self, token: str | None) -> bool:
        return self.session_user(token) is not None

    def end_session(self, token: str):
        with self.lock:
            self.con.execute("DELETE FROM sessions WHERE hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def end_other_sessions(self, keep_token: str | None):
        """Sign out every device except the one making the change."""
        keep = hashlib.sha256(keep_token.encode()).hexdigest() if keep_token else None
        with self.lock:
            self.con.execute("DELETE FROM sessions WHERE hash IS NOT ?", (keep,))

    def end_all_sessions(self):
        with self.lock:
            self.con.execute("DELETE FROM sessions")

    def close(self):
        with self.lock:
            try:
                self.con.close()
            except Exception:
                pass

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Minimal client for the Trimlight Edge V2 OAuth cloud API.

Auth (from Trimlight's API documentation): every request carries
  authorization = base64(HMAC-SHA256(clientSecret, "Trimlight|<clientId>|<timestampMs>"))
  S-ClientId    = clientId
  S-Timestamp   = timestampMs
"""
import base64
import os
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from .trust import CERT_HELP, client_context, is_cert_failure
from .version import VERSION

BASE_URL = os.environ.get("TRIMLIGHT_API_BASE", "https://trimlight.ledhue.com/trimlight")


class TrimlightError(Exception):
    """kind: "network" (couldn't reach Trimlight, including a failed
    certificate check, or the reply was lost or garbled, so whether the
    command took effect is unknown), "http" (an HTTP error status, in
    `status`) or "api" (Trimlight answered and refused, such as wrong keys)."""
    def __init__(self, msg: str = "", kind: str = "api", status: int | None = None, code: int | None = None):
        super().__init__(msg)
        self.kind = kind
        self.status = status
        self.code = code            # Trimlight's own error code, when it answered with one

    @property
    def unreadable(self) -> bool:
        """Trimlight's cloud can't make sense of its copy of the controller
        (code 12006, "Device data could not be parsed")."""
        return self.code == UNREADABLE

    @property
    def refused(self) -> bool:
        """Trimlight definitely didn't carry the command out (so sending a
        different version of it can't make a duplicate)."""
        return self.kind == "api" or (self.kind == "http" and self.status is not None and 400 <= self.status < 500)


UNREADABLE = 12006
UNREADABLE_HELP = ("Trimlight's cloud can't read its copy of this controller right now, so nothing on it can be "
                   "shown or changed from here. The lights keep running. Open the Trimlight Edge app on your home "
                   "Wi-Fi and open this controller so it syncs; see the manual, Troubleshooting.")


def split_runs(payload: dict, limit: int):
    """Same pattern with every color run cut into pieces of at most `limit`
    bulbs (looks identical on the house). None if it would need over 30 slots."""
    px = payload.get("pixels")
    if not px or all(p.get("count", 0) <= limit for p in px):
        return None
    out = []
    for p in sorted(px, key=lambda p: p.get("index", 0)):
        left = p.get("count", 0)
        while left > 0:
            out.append({**p, "count": min(limit, left)})
            left -= limit
    if len(out) > 30:
        return None
    for i, p in enumerate(out):
        p["index"] = i
    return {**payload, "pixels": out}


def make_token(client_id: str, client_secret: str, ts_ms: int) -> str:
    msg = f"Trimlight|{client_id}|{ts_ms}".encode()
    digest = hmac.new(client_secret.encode(), msg, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def trimlight_date(now_local) -> dict:
    """The controller's date format. Weekday: Sunday=1 ... Saturday=7."""
    return {
        "year": now_local.year - 2000,
        "month": now_local.month,
        "day": now_local.day,
        "weekday": (now_local.isoweekday() % 7) + 1,
        "hours": now_local.hour,
        "minutes": now_local.minute,
        "seconds": now_local.second,
    }


class TrimlightAPI:
    def __init__(self, client_id: str, client_secret: str, base_url: str | None = None, timeout: int = 15):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.timeout = timeout
        self.clock_offset_min = 0  # user-chosen difference for the controller's clock

    def _request(self, method: str, path: str, body=None):
        ts = int(time.time() * 1000)
        headers = {
            "authorization": make_token(self.client_id, self.client_secret, ts),
            "S-ClientId": self.client_id,
            "S-Timestamp": str(ts),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"EaveLuxOS/{VERSION}",
        }
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=client_context()) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode(errors="replace")
            raise TrimlightError(f"HTTP {e.code} from {path}: {detail}", "http", e.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            if is_cert_failure(e):
                raise TrimlightError(f"{CERT_HELP.format(who='Trimlight')} (Details: {reason})", "network") from None
            raise TrimlightError(f"Network error calling {path}: {reason}", "network") from None
        try:
            obj = json.loads(raw)
        except ValueError:
            raise TrimlightError(f"{path} returned something that isn't JSON", "network") from None
        if not isinstance(obj, dict):
            raise TrimlightError(f"{path} returned an unexpected reply")
        if obj.get("code") != 0:
            code = obj.get("code")
            msg = f"{path} failed: code {code} ({obj.get('desc')})"
            if code == UNREADABLE:
                msg = f"{UNREADABLE_HELP} (Details: {msg})"
            raise TrimlightError(msg, code=code if isinstance(code, int) else None)
        return obj.get("payload")

    # --- reads -------------------------------------------------------------
    def list_devices(self) -> list:
        payload = self._request("GET", "/v1/oauth/resources/devices", {"page": 0}) or {}
        return payload.get("data", []) or []

    def _controller_time(self, now_local):
        from datetime import timedelta
        return trimlight_date(now_local + timedelta(minutes=self.clock_offset_min))

    resync_wait = 3.0   # seconds; tests set 0

    def get_device(self, device_id: str, now_local, resync: bool = True) -> dict:
        """Device detail. Every call sends the local date/time (plus any offset
        the user chose), which keeps the controller's clock right across DST.
        If Trimlight's cloud can't read its copy of the controller (12006, it
        says "synchronize the device and retry"), ask the controller to send
        its data again and try once more."""
        body = {"deviceId": device_id, "currentDate": self._controller_time(now_local)}
        try:
            return self._request("POST", "/v1/oauth/resources/device/get", body) or {}
        except TrimlightError as e:
            if not (resync and e.unreadable):
                raise
        self.resync(device_id, now_local)
        body["currentDate"] = self._controller_time(now_local)
        return self._request("POST", "/v1/oauth/resources/device/get", body) or {}

    def resync(self, device_id: str, now_local):
        """Ask the controller to send its data to Trimlight's cloud again, and
        give it a moment."""
        try:
            self.notify_shadow(device_id, now_local)
        except TrimlightError:
            pass
        if self.resync_wait:
            time.sleep(self.resync_wait)

    def notify_shadow(self, device_id: str, now_local):
        body = {"deviceId": device_id, "currentDate": self._controller_time(now_local)}
        return self._request("GET", "/v1/oauth/resources/device/notify-update-shadow", body)

    # --- writes ------------------------------------------------------------
    def set_switch(self, device_id: str, state: int):
        """0 = off, 1 = manual (on), 2 = the controller's own timer mode."""
        body = {"deviceId": device_id, "payload": {"switchState": state}}
        return self._request("POST", "/v1/oauth/resources/device/update", body)

    # Trimlight's user guide allows 90 bulbs per color slot; its 2022 API
    # document says 60. Try what the pattern asks for; if the cloud refuses a
    # run over 60, split long runs and remember the limit for next time.
    slot_limit = 90

    def _with_slot_fallback(self, path: str, device_id: str, payload: dict):
        first = split_runs(payload, TrimlightAPI.slot_limit) if TrimlightAPI.slot_limit < 90 else None
        try:
            return self._request("POST", path, {"deviceId": device_id, "payload": first or payload})
        except TrimlightError as e:
            smaller = split_runs(payload, 60)
            # Only when Trimlight actually refused: after a timeout or a lost
            # reply the first request may have worked, and sending it again
            # would add a second copy of a saved pattern (and lower the limit
            # for good over a passing network problem).
            if smaller is None or TrimlightAPI.slot_limit == 60 or not e.refused:
                raise
            r = self._request("POST", path, {"deviceId": device_id, "payload": smaller})
            TrimlightAPI.slot_limit = 60
            import logging
            logging.getLogger("eaveluxos").warning(
                "The Trimlight cloud refused more than 60 bulbs per color (%s); long runs are now split automatically.", e)
            return r

    def preview_effect(self, device_id: str, payload: dict):
        return self._with_slot_fallback("/v1/oauth/resources/device/effect/preview", device_id, payload)

    def run_saved_effect(self, device_id: str, effect_id: int):
        body = {"deviceId": device_id, "payload": {"id": effect_id}}
        return self._request("POST", "/v1/oauth/resources/device/effect/view", body)

    # --- device setup -------------------------------------------------------
    def update_device(self, device_id: str, payload: dict):
        """Any of: name, colorOrder (0-5), ic (0-1), ports ([{id, start, end}]), switchState."""
        body = {"deviceId": device_id, "payload": payload}
        return self._request("POST", "/v1/oauth/resources/device/update", body)

    def save_effect(self, device_id: str, payload: dict):
        """Adds (id -1) or updates a pattern in the controller's own library.
        Returns {"id": n}."""
        return self._with_slot_fallback("/v1/oauth/resources/device/effect/save", device_id, payload)

    def set_clock(self, device_id: str, now_local):
        """Sends the current time (plus offset) to the controller."""
        return self.get_device(device_id, now_local)

    # --- the controller's own timers (used only by the safety net) ----------
    def calendar_save(self, device_id: str, payload: dict):
        """Add/update a calendar schedule (id 0-59). Returns {"id": n}."""
        body = {"deviceId": device_id, "payload": payload}
        return self._request("POST", "/v1/oauth/resources/device/calendar/save", body)

    def calendar_delete(self, device_id: str, cal_id: int):
        body = {"deviceId": device_id, "payload": {"id": cal_id}}
        return self._request("POST", "/v1/oauth/resources/device/calendar/delete", body)

    def effect_delete(self, device_id: str, effect_id: int):
        body = {"deviceId": device_id, "payload": {"id": effect_id}}
        return self._request("POST", "/v1/oauth/resources/device/effect/delete", body)

    def daily_save(self, device_id: str, payload: dict):
        body = {"deviceId": device_id, "payload": payload}
        return self._request("POST", "/v1/oauth/resources/device/daily/save", body)

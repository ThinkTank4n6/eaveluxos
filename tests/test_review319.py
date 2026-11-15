# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""3.19.1: fixes from the 3.19.0 code review, one test (or more) each."""
import base64
import copy
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import zlib
from datetime import date, datetime
from pathlib import Path

from eaveluxos import holidays as H
from eaveluxos import sharecode as SC
from eaveluxos.controller import Controller
from eaveluxos.schedule import Location, build_config
from eaveluxos.server import ApiError, App
from eaveluxos.store import DEFAULT_SETTINGS
from tests.test_controller import FakeAPI
from tests.test_holidays319 import SECRETS, settings
from tests import test_roles
from tests.test_triggers316 import NY

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
JS = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")


class Review1ShareCodeInAMessage(unittest.TestCase):
    """The most important one (tests/repro_share_message.py)."""
    code = SC.encode_keys(DEFAULT_SETTINGS["effects"], ["christmas", "snowfall"])["code"]

    def test_1_codes_inside_messages(self):
        c = self.code
        for msg in (f"Here's my pattern: {c} enjoy!", f"{c}\nThanks", f"{c[:50]}\n  {c[50:]}\n\nLove, Chris",
                    f"{c}.", f"({c})", f"Try this one ->{c}<- it's great", f"{c[:30]}\r\n{c[30:70]}\r\n{c[70:]} bye"):
            self.assertEqual([p["label"] for p in SC.decode(msg)["patterns"]], ["Christmas", "Snowfall"], msg)

    def test_1_repro_script_runs(self):
        r = subprocess.run(["python3", str(HERE / "repro_share_message.py")], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("old FAIL", r.stdout)
        self.assertNotIn("new FAIL", r.stdout)
        self.assertLessEqual(len((HERE / "repro_share_message.py").read_text(encoding="utf-8").splitlines()), 20)

    def test_13_extra_or_missing_data_is_refused_not_half_read(self):
        with self.assertRaises(SC.ShareError):
            SC.decode(self.code + "xyz")                  # letters glued on: a damaged code
        with self.assertRaises(SC.ShareError):
            SC.decode(self.code[:-4])                     # cut short
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        raw = c.compress(json.dumps({"v": 1, "p": [{"label": "A", "colors": ["#FF0000"]}]}).encode()) + c.flush()
        with self.assertRaises(SC.ShareError):
            SC.decode("ELX1:" + base64.urlsafe_b64encode(raw + b"JUNKJUNK").decode().rstrip("="))


class Review2and3Country(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self.clock = [1_000_000.0]
        self.answer = {"CA": [{"date": "2026-12-26", "name": "Boxing Day"}], "IE": [{"date": "2026-08-03", "name": "August"}]}
        self.calls = []
        self.down = False

        def fetch(url):
            self.calls.append(url)
            if self.down:
                raise H.HolidayError("down")
            return json.dumps(self.answer[url.split("/")[-1]]).encode()
        self.ch = H.CountryHolidays(self.d, fetch=fetch, now=lambda: self.clock[0], today=lambda: date(2026, 11, 1))

    def test_2_another_country_never_wipes_the_chosen_one(self):
        self.ch.refresh("CA")
        self.ch.refresh("IE")
        self.assertEqual(self.ch.dates("CA"), [date(2026, 12, 26)])
        self.assertEqual(self.ch.dates("IE"), [date(2026, 8, 3)])
        again = H.CountryHolidays(self.d, fetch=lambda u: 1 / 0)
        self.assertEqual(again.dates("CA"), [date(2026, 12, 26)], "kept in the file, per country")

    def test_2_the_old_file_is_read(self):
        (self.d / "country-holidays.json").write_text(json.dumps(
            {"code": "CA", "holidays": [{"date": "2026-07-01", "name": "Canada Day"}], "fetched": 5, "error": None}))
        self.assertEqual(H.CountryHolidays(self.d).dates("CA"), [date(2026, 7, 1)])

    def test_3_a_newly_chosen_country_is_checked_on_the_next_pass(self):
        self.ch.step("CA")
        self.assertEqual(len(self.calls), 2)
        self.clock[0] += 3600
        self.ch.step("CA")
        self.assertEqual(len(self.calls), 2, "a good check lasts a week")
        self.down = True
        self.ch.step("IE")                                   # changed country, and the service is down
        self.assertEqual(len(self.calls), 3, "checked right away, not next week")
        self.assertLessEqual(self.ch.next_at - self.clock[0], H.RETRY, "a failure retries in hours")
        self.down = False
        self.clock[0] += H.RETRY + 1
        self.ch.step("IE")
        self.assertEqual(self.ch.dates("IE"), [date(2026, 8, 3)])
        self.assertEqual(self.ch.next_at - self.clock[0], H.EVERY)


class Review2and7and10Server(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.app = App(self.d, start=False)
        s = settings(country={"code": "CA", "effects": ["warm_white"]})
        self.app.store.save_settings(s)
        self.app.store.save_secrets(**SECRETS)
        self.app.rebuild()
        self.n = 0

        def fetch(url):
            self.n += 1
            return json.dumps([{"date": "2026-12-26", "name": "Boxing Day"}]).encode()
        self.app.country.fetch = fetch

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_2_only_the_chosen_country_can_be_checked(self):
        self.app.holidays_refresh("CA")
        with self.assertRaises(ApiError) as cm:
            self.app.holidays_refresh("IE")
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.app.country_dates(), {"CA": [date(2026, 12, 26)]})

    def test_10_check_now_at_most_once_a_minute(self):
        self.app.holidays_refresh("CA")
        r = self.app.holidays_refresh("CA")
        self.assertTrue(r.get("recent"))
        self.assertEqual(self.n, 2, "two years, fetched once")
        self.app._country_checked["CA"] -= 61
        self.app.holidays_refresh("CA")
        self.assertEqual(self.n, 4)

    def test_7_holidays_status_doesnt_build_the_whole_status(self):
        self.app.ctrl.status = lambda: self.fail("the full status isn't needed")
        self.assertIn("today", self.app.holidays_status())


class Review9NoRedirects(unittest.TestCase):
    def test_9_a_redirect_is_an_error(self):
        import urllib.request
        from eaveluxos.holidays import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "Found", {}, "http://10.0.0.1/"))
        src = (ROOT / "eaveluxos" / "holidays.py").read_text(encoding="utf-8")
        self.assertIn("build_opener(urllib.request.HTTPSHandler(context=client_context()), _NoRedirect)", src)
        self.assertNotIn("urllib.request.urlopen(", src)
        del urllib


class Review8MorningNoteOnce(unittest.TestCase):
    def setUp(self):
        self.clock = [datetime(2026, 11, 26, 7, 0, tzinfo=NY)]
        orig = Location.now
        self.addCleanup(setattr, Location, "now", orig)
        Location.now = lambda loc: self.clock[0]
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def run_app(self):
        c = Controller(build_config(settings(), SECRETS), FakeAPI(), data_dir=self.d)
        c.devices = [{"deviceId": "D1", "name": "House"}]
        c.tick()
        return sum("Today is" in e["msg"] for e in c.events)

    def test_8_a_restart_doesnt_announce_it_again(self):
        self.assertEqual(self.run_app(), 1)
        self.assertEqual(self.run_app(), 0, "restarted the same day")
        self.clock[0] = datetime(2027, 11, 25, 7, 0, tzinfo=NY)
        self.assertEqual(self.run_app(), 1, "next year's Thanksgiving")


class Review11and12Dates(unittest.TestCase):
    def test_11_next_says_when_a_season_starts(self):
        st = next(h for h in H.summary(date(2026, 10, 1), {"halloween": {"before": 6}}) if h["key"] == "halloween")
        self.assertEqual((st["next"][0], st["starts"][0]), ("2026-10-31", "2026-10-25"))
        self.assertIn("lights from", JS)

    def test_12_moved_dates_from_past_years_dont_count(self):
        y = date.today().year
        old = {str(y - 30 + k): f"{y - 30 + k}-11-08" for k in range(25)}
        e = H.check_entry({"key": "diwali", "effects": ["a"], "moved": {**old, str(y): f"{y}-11-09"}}, {"a": 1})
        self.assertEqual(e["moved"], {str(y): f"{y}-11-09"})
        self.assertIn("Dates moved for years gone by are dropped", JS)


class Review15Names(unittest.TestCase):
    def test_15_names_are_numbered_until_free(self):
        s = settings()
        s["rules"] += [{"name": n, "on": "18:00", "off": "22:00", "effect": "warm_white", "dates": "11-26"}
                       for n in ("Thanksgiving", "Thanksgiving (holiday)")]
        names = [r.name for r in build_config(s, SECRETS).schedule.rules]
        self.assertIn("Thanksgiving (holiday 2)", names)


class Review4and5and14Page(unittest.TestCase):
    def test_4_deleting_a_holidays_pattern_says_why(self):
        self.assertIn("the holiday lights for", JS)
        self.assertIn("public holiday lights", JS)

    def test_5_the_qr_code_fits_a_phone(self):
        css = (ROOT / "eaveluxos" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".qrbox svg{max-width:100%;height:auto", css)

    def test_14_shared_patterns_are_added_in_one_save(self):
        self.assertIn("await addPatterns(r.patterns)", JS)
        self.assertNotIn("for (const p of r.patterns) await addPattern(p)", JS)


class Review6ViewersShare(unittest.TestCase):
    # The accounts test's helpers only (subclassing it would run its tests again).
    setUp, tearDown, call, add, login = (test_roles.Roles.setUp, test_roles.Roles.tearDown, test_roles.Roles.call,
                                           test_roles.Roles.add, test_roles.Roles.login)

    def test_6_a_viewer_can_make_a_code_but_not_open_one(self):
        self.add("owner", "admin")
        self.add("guest", "viewer")
        v = self.login("guest")
        st, r = self.call("/api/share", {"keys": ["christmas"]}, v)
        self.assertEqual(st, 200, r)
        self.assertTrue(r["code"].startswith("ELX1:"))
        self.assertEqual(self.call("/api/share/open", {"code": r["code"]}, v)[0], 403)
        self.assertEqual(self.call("/api/settings", {"effects": {}}, v)[0], 403)


if __name__ == "__main__":
    unittest.main()

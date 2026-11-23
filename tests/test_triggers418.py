# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.18 triggers and calendar: birthdays and anniversaries every year, who's
home (arriving and leaving, from a phone's webhook), and the motion and voice
recipes that ride on webhooks."""
import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date

from eaveluxos import automations as A
from eaveluxos import holidays as Hd
from eaveluxos.presence import Presence, check_people
from eaveluxos.schedule import ConfigError
from tests.test_local43 import ServerBase

TOKEN = "t" * 32


class PersonalDates(unittest.TestCase):
    EFF = {"warm_white": 1, "party": 1}

    def test_a_birthday_comes_back_every_year(self):
        n = Hd.YearlyNights(7, 14)
        self.assertIn(date(2027, 7, 14), n)
        self.assertIn(date(2040, 7, 14), n)
        self.assertNotIn(date(2027, 7, 15), n)

    def test_days_around_it_and_new_year(self):
        n = Hd.YearlyNights(1, 1, before=1, after=2)
        self.assertIn(date(2026, 12, 31), n, "the evening before, across the new year")
        self.assertIn(date(2027, 1, 3), n)
        self.assertNotIn(date(2027, 1, 4), n)

    def test_leap_day(self):
        n = Hd.YearlyNights(2, 29)
        self.assertIn(date(2027, 2, 28), n, "February 28 in other years")
        self.assertIn(date(2028, 2, 29), n)
        self.assertNotIn(date(2028, 2, 28), n, "a leap year has its own day")

    def test_not_before_it_happened(self):
        n = Hd.YearlyNights(6, 1, since=2027)
        self.assertNotIn(date(2026, 6, 1), n)
        self.assertIn(date(2027, 6, 1), n)

    def test_checking(self):
        e = Hd.check_personal({"name": "Chris", "date": "7-14", "effects": ["party"]}, self.EFF)
        self.assertEqual((e["kind"], e["date"], e["on"], e["off"]), ("birthday", "07-14", "sunset", "23:00"))
        self.assertEqual(Hd.personal_label(e), "Chris's birthday")
        self.assertEqual(Hd.personal_label({**e, "name": "Our wedding", "kind": "anniversary"}), "Our wedding anniversary")
        self.assertEqual(Hd.personal_label({**e, "name": "Mom's birthday"}), "Mom's birthday")
        for bad in ({"name": "", "date": "07-14", "effects": ["party"]}, {"name": "X", "date": "02-30", "effects": ["party"]},
                    {"name": "X", "date": "07-14", "effects": ["nope"]}, {"name": "X", "date": "07-14", "effects": ["party"], "year": 1700},
                    {"name": "X", "date": "07-14", "effects": ["party"], "kind": "funeral"},
                    {"name": "X", "date": "07-14", "effects": ["party"], "after": 30}):
            with self.assertRaises(Hd.HolidayError, msg=bad):
                Hd.check_personal(bad, self.EFF)


class People(unittest.TestCase):
    def test_names(self):
        self.assertEqual(check_people({"people": ["  Chris ", "Ann"]}), ["Chris", "Ann"])
        for bad in ({"people": ["Chris", "chris"]}, {"people": [""]}, {"people": ["x" * 31]}, {"people": [f"p{i}" for i in range(13)]},
                    {"people": ["<b>"]}, ["Chris"]):
            with self.assertRaises(ConfigError, msg=bad):
                check_people(bad)

    def test_first_and_last(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p, ppl = Presence(d), ["Chris", "Ann"]
        self.assertFalse(p.known(ppl))
        r = p.set(ppl, "Chris", "home")
        self.assertTrue(r["changed"] and r["first"])
        r = p.set(ppl, "Ann", "home")
        self.assertFalse(r["first"], "someone was already home")
        self.assertFalse(p.set(ppl, "Ann", "home")["changed"], "the phone saying it twice")
        self.assertFalse(p.set(ppl, "Chris", "away")["last"])
        r = p.set(ppl, "Ann", "away")
        self.assertTrue(r["last"])
        self.assertEqual(Presence(d).home(ppl), set(), "kept across a restart")
        p.set(ppl, "Ann", "home")
        self.assertEqual(Presence(d).home(ppl), {"Ann"})
        self.assertEqual(p.find(ppl, " ann "), "Ann")


class Server(ServerBase):
    def settings(self, **kw):
        s = copy.deepcopy(self.app.store.settings)
        s.update(kw)
        self.app.save_settings(s)
        return s

    def auto(self, when, cond=None, name="Welcome"):
        return {"id": name.lower(), "name": name, "when": when, "if": cond or [],
                "then": [{"type": "flash", "color": "#00FF00", "seconds": 10}], "cooldown": 0}

    def test_birthday_outranks_the_holiday_and_shows_on_home(self):
        eff = next(iter(self.app.store.settings["effects"]))
        self.settings(dates={"list": [{"name": "Chris", "kind": "birthday", "date": "12-25", "effects": [eff], "year": 1980}]},
                      holidays={"enabled": True, "list": [{"key": "christmas", "effects": [eff]}]})
        sch = self.app.ctrl.cfg.schedule
        plans = sch.day_plans(date(2027, 12, 25))
        self.assertEqual(plans[0].rule.holiday, "Chris's birthday", [p.rule.name for p in plans])
        self.assertEqual(plans[0].rule.priority, Hd.PERSONAL_PRIORITY)
        self.assertGreater(Hd.PERSONAL_PRIORITY, Hd.HOLIDAY_PRIORITY)
        self.assertFalse([p for p in sch.day_plans(date(2027, 12, 24)) if p.rule.holiday == "Chris's birthday"])

    def test_a_date_turned_off_or_bad(self):
        eff = next(iter(self.app.store.settings["effects"]))
        self.settings(dates={"list": [{"name": "Chris", "date": "07-14", "effects": [eff], "enabled": False}]})
        self.assertFalse([r for r in self.app.ctrl.cfg.schedule.rules if getattr(r, "holiday", None)])
        from eaveluxos.server import ApiError
        s = copy.deepcopy(self.app.store.settings)
        s["dates"] = {"list": [{"name": "Chris", "date": "13-01", "effects": [eff]}]}
        with self.assertRaises((ApiError, ConfigError)):
            self.app.save_settings(s)

    def test_dates_and_people_stay_out_of_shared_files(self):
        from eaveluxos.server import PRIVATE_KEYS
        self.assertIn("dates", PRIVATE_KEYS)
        self.assertIn("presence", PRIVATE_KEYS)

    def test_arriving_runs_its_automation(self):
        self.settings(presence={"people": ["Chris", "Ann"]},
                      automations=[self.auto({"type": "arrive", "person": "any", "first": True}),
                                   self.auto({"type": "leave", "person": "any", "last": True}, name="Bye")])
        r = self.app.presence_set("chris", "home")
        self.assertEqual(r["person"], "Chris")
        self.assertTrue(any("Welcome" in x and "ran" in x for x in r["automations"]), r)
        r = self.app.presence_set("Ann", "arrived")
        self.assertEqual(r["automations"], [], "only the first one home")
        self.assertEqual(self.app.presence_set("Ann", "home")["automations"], [], "no change, nothing runs")
        self.assertEqual(self.app.presence_set("Chris", "away")["automations"], [])
        r = self.app.presence_set("Ann", "left")
        self.assertTrue(any("Bye" in x for x in r["automations"]), r)
        self.assertEqual(self.app.presence_status()["home"], [])

    def test_someone_home_condition(self):
        self.settings(presence={"people": ["Chris"]},
                      automations=[self.auto({"type": "webhook", "name": "motion"}, [{"type": "nobody_home"}], name="Intruder")])
        a = self.app.ctrl.cfg.automations[0]
        self.assertIn("nobody has told", self.app.autos.check(a)[0][0])
        self.app.presence_set("Chris", "away")
        self.assertTrue(self.app.autos.check(a)[0][1])
        self.app.presence_set("Chris", "home")
        self.assertFalse(self.app.autos.check(a)[0][1])
        self.assertIn("nobody is home", A.describe(a))

    def test_unknown_people_are_refused(self):
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError):
            self.app.presence_set("Chris", "home")
        self.settings(presence={"people": ["Chris"]})
        with self.assertRaises(ApiError):
            self.app.presence_set("Bob", "home")
        with self.assertRaises(ApiError):
            self.app.presence_set("Chris", "sideways")
        s = copy.deepcopy(self.app.store.settings)
        s["automations"] = [self.auto({"type": "arrive", "person": "Bob"})]
        with self.assertRaises(Exception):
            self.app.save_settings(s)

    def test_paused_schedule_skips_automations(self):
        self.settings(automations=[{**self.auto({"type": "webhook", "name": "motion"}, name="Motion"), "beats_manual": True}],
                      paused={"since": "2026-11-22T18:00:00"})
        done = self.app._auto_event({"type": "webhook", "name": "motion"})
        self.assertTrue(done and "the schedule is paused" in done[0], done)

    def test_presence_webhook(self):
        from eaveluxos.server import make_server
        self.app.store.save_secrets(webhook_token=TOKEN)
        self.settings(presence={"people": ["Chris"]}, automations=[self.auto({"type": "arrive", "person": "Chris"})])
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def hook(body, tok=TOKEN):
            r = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/hook/presence", data=json.dumps(body).encode(),
                                       headers={"Content-Type": "application/json", "X-Token": tok})
            try:
                with urllib.request.urlopen(r, timeout=20) as x:
                    return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        self.assertEqual(hook({"person": "Chris", "state": "home"}, "x" * 32)[0], 403)
        st, r = hook({"person": "Chris", "state": "home"})
        self.assertEqual((st, r["state"], r["home"]), (200, "home", ["Chris"]), r)
        self.assertTrue(r["automations"])
        self.assertEqual(hook({"person": "Nobody", "state": "home"})[0], 404)
        self.assertTrue(any("Chris arrived" in x["what"] for x in self.app.store.audit_rows(20)))


class Review(unittest.TestCase):
    def test_1_one_phone_leaving_isnt_everyone_gone(self):
        from tests import reprorun
        reprorun.run(self, "repro_everyone_left_too_soon.py", 60)

    def test_1_conditions_wait_for_everyone(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p, ppl = Presence(d), ["Chris", "Ann"]
        self.assertIsNone(p.nobody_home(ppl))
        p.set(ppl, "Chris", "home")
        self.assertFalse(p.nobody_home(ppl), "someone is home, whoever else hasn't said")
        p.set(ppl, "Chris", "away")
        self.assertIsNone(p.nobody_home(ppl))
        self.assertTrue(p.set(ppl, "Ann", "away")["last"])
        self.assertTrue(p.nobody_home(ppl))


class Review4181(ServerBase):
    """The 4.18.1 code review."""

    def test_1_the_cloud_catching_up_isnt_a_change_from_outside(self):
        from tests import reprorun
        reprorun.run(self, "repro_cloud_catches_up.py", 120)

    def test_2_the_days_around_a_birthday(self):
        from datetime import datetime
        eff = next(iter(self.app.store.settings["effects"]))
        s = copy.deepcopy(self.app.store.settings)
        s["dates"] = {"list": [{"name": "Chris", "date": "07-14", "effects": [eff], "before": 2, "after": 1}]}
        self.app.save_settings(s)
        tz = self.app.ctrl.cfg.loc.tz
        h = lambda d: self.app.ctrl.holiday_today(datetime(2027, 7, d, 9, tzinfo=tz))
        self.assertEqual((h(12)["name"], h(12)["around"]), ("Chris's birthday", "in 2 days"))
        self.assertEqual(h(14)["around"], "")
        self.assertEqual(h(15)["around"], "1 day ago")
        n = Hd.YearlyNights(1, 1, before=1)
        self.assertEqual(n.offset(date(2026, 12, 31)), -1)
        self.assertIsNone(n.offset(date(2027, 1, 2)))

    def test_4_viewers_dont_see_whos_home(self):
        from eaveluxos.server import make_server
        self.settings_people()
        tok = self.app.store.new_token("Dashboard", "viewer")["token"]
        ed = self.app.store.new_token("HA", "editor")["token"]
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def get(t):
            r = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/presence",
                                       headers={"Authorization": f"Bearer {t}", "X-Forwarded-For": "203.0.113.9"})
            try:
                with urllib.request.urlopen(r, timeout=20) as x:
                    return x.status
            except urllib.error.HTTPError as e:
                return e.code
        self.assertEqual(get(tok), 403)
        self.assertEqual(get(ed), 200)

    def settings_people(self, people=("Chris", "Ann")):
        s = copy.deepcopy(self.app.store.settings)
        s["presence"] = {"people": list(people)}
        self.app.save_settings(s)

    def test_5_changes_run_one_at_a_time(self):
        self.settings_people()
        order = []
        real = self.app._auto_event

        def slow(ev):
            import time
            order.append(("start", ev["type"]))
            time.sleep(0.2 if ev["type"] == "arrive" else 0)
            order.append(("end", ev["type"]))
            return real(ev)
        self.app._auto_event = slow
        t = threading.Thread(target=self.app.presence_set, args=("Chris", "home"))
        t.start()
        import time
        time.sleep(0.05)
        self.app.presence_set("Chris", "away")
        t.join()
        self.assertEqual(order, [("start", "arrive"), ("end", "arrive"), ("start", "leave"), ("end", "leave")])

    def test_6_marking_by_hand_is_audited_with_who(self):
        from eaveluxos.server import AUDIT_NAMES, _audit_detail
        self.assertIn("/api/presence", AUDIT_NAMES)
        self.assertIn("person: Chris", _audit_detail("/api/presence", {"person": "Chris", "state": "home"}, None))

    def test_11_someone_taken_off_the_list_is_forgotten(self):
        self.settings_people()
        self.app.presence_set("Ann", "home")
        self.settings_people(["Chris"])
        self.app.presence_status()
        self.assertNotIn("Ann", (self.app.store.dir / "presence.json").read_text(encoding="utf-8"))

    def test_3_a_pattern_used_by_a_date_says_so(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        body = js[js.index("function usedBy(key)"):js.index("function fromController")]
        self.assertIn("s.dates?.list", body)
        self.assertIn("s.automations", body)


class Describe(unittest.TestCase):
    def test_lines(self):
        base = {"if": [], "then": [{"type": "off", "minutes": 5}]}
        say = lambda w: A.describe({**base, "when": w})
        self.assertIn("someone arrives home and nobody else is home", say({"type": "arrive", "person": "any", "first": True}))
        self.assertIn("Chris arrives home,", say({"type": "arrive", "person": "Chris"}))
        self.assertIn("everyone has left", say({"type": "leave", "person": "any", "last": True}))
        self.assertIn("Ann leaves,", say({"type": "leave", "person": "Ann"}))


try:
    from playwright.sync_api import sync_playwright
except ImportError:            # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(ServerBase):
    SHOTS = None

    def test_dates_people_template_and_recipes(self):
        import time
        from eaveluxos.server import make_server
        self.app.store.save_secrets(webhook_token=TOKEN)
        srv = make_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://localhost:{srv.server_address[1]}/"
        try:
            pw = sync_playwright().start()
            br = pw.chromium.launch()
        except Exception as e:
            self.skipTest(f"Chromium can't start: {e}")
        self.addCleanup(pw.stop)
        self.addCleanup(br.close)
        errors = []

        def until(cond, what):
            for _ in range(200):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")

        def unfold(pg, key):
            pg.wait_for_selector(f'[data-fold="{key}"]')
            if "closed" in (pg.get_attribute(f'[data-fold="{key}"]', "class") or ""):
                pg.click(f'[data-fold="{key}"] .foldbar')
        st = lambda: self.app.store.settings
        pg = br.new_page(viewport={"width": 1300, "height": 900})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "#schedule")
        unfold(pg, "dates")
        pg.wait_for_selector("[data-dtadd]")
        pg.click("[data-dtadd]")
        pg.wait_for_selector("#dlg #dtname")
        pg.fill("#dlg #dtname", "Chris")
        pg.select_option("#dlg #dtm", "7")
        pg.fill("#dlg #dtd", "14")
        pg.fill("#dlg #dty", "1980")
        pg.locator("#dlg .primary").last.click()
        until(lambda: len((st().get("dates") or {}).get("list") or []) == 1, "the date saved")
        e = st()["dates"]["list"][0]
        self.assertEqual((e["name"], e["date"], e["year"], e["kind"]), ("Chris", "07-14", 1980, "birthday"))
        until(lambda: "turns" in pg.inner_text("#datebox"), "the age shown")
        self.assertIn("Chris's birthday", pg.inner_text("#datebox"))
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/dates.png", full_page=True)
        pg.goto(base + "#alerts")
        unfold(pg, "people")
        pg.wait_for_selector("#pname")
        pg.fill("#pname", "Chris")
        pg.click("[data-padd]")
        until(lambda: (st().get("presence") or {}).get("people") == ["Chris"], "the person saved")
        pg.wait_for_selector('[data-pset="Chris"]')
        pg.click('[data-pset="Chris"]')
        until(lambda: self.app.presence.home(["Chris"]) == {"Chris"}, "marked home")
        pg.wait_for_selector("text=Set up an iPhone (Shortcuts)")
        if self.SHOTS:
            pg.screenshot(path=f"{self.SHOTS}/people.png", full_page=True)
        unfold(pg, "autos")
        pg.wait_for_selector("[data-autotpl]")
        pg.select_option("[data-autotpl]", "welcome")
        pg.wait_for_selector("#dlg [data-autoform]")
        until(lambda: "someone arrives home and nobody else is home" in pg.inner_text("#dlg [data-autosum]"), "the sentence")
        pg.locator("#dlg .primary").last.click()
        until(lambda: len(st().get("automations") or []) == 1, "the template saved")
        self.assertEqual(st()["automations"][0]["when"], {"type": "arrive", "person": "any", "first": True})
        unfold(pg, "webhooks")
        pg.wait_for_selector("text=Siri, Alexa and Google")
        self.assertIn("/api/hook/resume", pg.text_content("#voicebox"))
        ph = br.new_page(viewport={"width": 390, "height": 844})
        ph.on("pageerror", lambda e: errors.append(str(e)))
        for view, key in (("schedule", "dates"), ("alerts", "people")):
            ph.goto(base + "#" + view)
            unfold(ph, key)
            ph.wait_for_selector("#datebox .item" if key == "dates" else "#peoplebox .item")
            self.assertEqual(ph.evaluate("document.documentElement.scrollWidth"), 390, f"{key} fits a phone")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

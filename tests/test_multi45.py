# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""4.5: a home-network address for each controller. Nov 17: Jeff has two
controllers, Deck (192.168.1.136, the address he had saved) and Front
(192.168.1.134). With one address, everything done over the home network
went to the Deck, even with only the Front chosen. Here the Deck is
127.0.0.1, the Front 127.0.0.2 and a Garage 127.0.0.3, each a fake
controller holding its own patterns and ports."""
import copy
import json
import time
import unittest
from pathlib import Path

from eaveluxos import lanlink as L
from tests import fake_lan
from tests.test_local43 import Patterns, ServerBase, factory_holds

ROOT = Path(__file__).resolve().parent.parent
DECK, FRONT, GARAGE = "TL-EDGE-01", "TL-FRONT-02", "TL-GARAGE-03"


def front_cloud():
    from tests import fake_trimlight as F
    d = copy.deepcopy(F.STATE["dev"])
    d.update(deviceId=FRONT, name="Front",
             ports=[{"id": 0, "start": 1, "end": 120}, {"id": 1, "start": 0, "end": 0},
                    {"id": 2, "start": 0, "end": 0}, {"id": 3, "start": 0, "end": 0}])
    return d


class TwoBase(ServerBase):
    """Two controllers, Deck and Front, each a fake at its own address."""
    def setUp(self):
        super().setUp()
        F = self.F
        self.addCleanup(F.STATE.__setitem__, "more", F.STATE.get("more", []))
        F.STATE["more"] = [front_cloud()]
        F.STATE["dev"]["name"] = "Deck"
        # The Deck's own ports, as its cloud copy says (1-83, 84-138, 100-138, off)
        self.ctl.holds["ports"] = [(1, 83, 1), (84, 138, 1), (100, 138, 1), (1, 600, 0)]
        front = factory_holds()
        front["ports"] = [(1, 120, 1), (1, 600, 0), (1, 600, 0), (1, 600, 0)]
        front["patterns"] = {1: L.pattern_record(1, "Front Porch", 0, 128, 200, [(5, (255, 180, 107), 1)])}
        try:
            self.front = fake_lan.FakeController(holds=front, host="127.0.0.2", port=self.ctl.port)
        except OSError as e:        # a system without the whole 127.x loopback range
            self.skipTest(f"Can't listen on 127.0.0.2: {e}")
        self.addCleanup(self.front.close)
        self.app._acct = []
        self.app.ctrl.account = []
        self.app.devices()                       # lists the account, as the Lights tab does

    def names(self, ctl):
        return sorted(L.read_record(r)["name"] for r in ctl.holds["patterns"].values())


class TwoControllers(TwoBase):

    # --- the address saved before 4.5 ---
    def test_the_old_address_is_nobodys_until_chosen(self):
        self.assertEqual(self.app._lan_address(DECK), "")
        self.assertEqual(self.app._lan_address(FRONT), "")
        home = self.app.lan_home()
        self.assertEqual(home["devices"], {})
        self.assertEqual(home["unassigned"], "127.0.0.1")
        from eaveluxos.server import ApiError
        with self.assertRaises(ApiError) as cm:
            self.app.local(dev=FRONT)
        self.assertIn("Front’s address", str(cm.exception))
        with self.assertRaises(ApiError) as cm:
            self.app.local()
        self.assertIn("Choose a controller", str(cm.exception))

    def test_choosing_which_one_the_old_address_is(self):
        r = self.app.local_address(DECK, "127.0.0.1")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.app._lan_address(DECK), "127.0.0.1")
        self.assertEqual(self.app._lan_address(FRONT), "")
        self.assertIsNone(self.app.lan_home()["unassigned"])
        self.assertEqual(self.app._lan_address(), "127.0.0.1", "music from this computer keeps it")

    # --- the right controller ---
    def test_the_wrong_controller_is_caught_by_its_ports(self):
        r = self.app.local_address(FRONT, "127.0.0.1")          # the Deck's address, given to the Front
        self.assertFalse(r["ok"])
        self.assertIn("port 1: 1-83", r["confirm"])
        self.assertIn("Front has port 1: 1-120", r["confirm"])
        self.assertEqual(self.app._lan_address(FRONT), "")
        self.assertTrue(self.app.local_address(FRONT, "127.0.0.1", force=True)["ok"], "saved anyway when asked")

    def test_one_address_for_one_controller(self):
        from eaveluxos.server import ApiError
        self.app.local_address(DECK, "127.0.0.1")
        with self.assertRaises(ApiError) as cm:
            self.app.local_address(FRONT, "127.0.0.1", force=True)
        self.assertIn("already Deck’s address", str(cm.exception))

    def test_each_reads_and_changes_its_own(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.assertTrue(self.app.local_address(FRONT, "127.0.0.2")["ok"], "ports match: no question")
        deck, front = self.app.local_state(dev=DECK), self.app.local_state(dev=FRONT)
        self.assertEqual([p["name"] for p in front["patterns"]], ["Front Porch"])
        self.assertNotIn("Front Porch", [p["name"] for p in deck["patterns"]])
        self.assertEqual(front["ports"][0]["end"], 120)
        before = self.names(self.ctl)
        self.app.local_delete(1, "Front Porch", FRONT)
        self.assertEqual(self.names(self.front), [])
        self.assertEqual(self.names(self.ctl), before, "the Deck untouched")

    def test_save_on_the_controllers_saves_on_each(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        self.app.ctrl.devices = [{"deviceId": DECK, "name": "Deck"}, {"deviceId": FRONT, "name": "Front"}]
        r = self.app.save_to_controller({"name": "Porch", "effect": {"colors": ["#FFB46B"], "counts": [2]}})
        self.assertEqual(sorted(x["device"] for x in r["saved"]), [DECK, FRONT])
        self.assertIn("Porch", self.names(self.ctl))
        self.assertIn("Porch", self.names(self.front))
        r = self.app.save_to_controller({"name": "Gate", "effect": {"colors": ["#FF0000"], "counts": [2]},
                                         "devices": [FRONT]})
        self.assertEqual([x["device"] for x in r["saved"]], [FRONT])
        self.assertNotIn("Gate", self.names(self.ctl))

    def test_put_back_goes_to_the_controller_it_came_from(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        self.app.safety.backup_dir.mkdir(parents=True, exist_ok=True)
        name = f"{FRONT}-20261117-150000-000000.json"
        (self.app.safety.backup_dir / name).write_text(json.dumps(Patterns.BACKUP), encoding="utf-8")
        before = self.names(self.ctl)
        r = self.app.restore_patterns(name, [11])
        self.assertEqual(r["restored"], ["Dolly"])
        self.assertIn("Dolly", self.names(self.front))
        self.assertEqual(self.names(self.ctl), before)

    def test_lights_tab_ports_for_the_front_go_to_the_front(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        deck_ports = list(self.ctl.holds["ports"])
        r = self.app.update_device({"deviceId": FRONT, "ports": [{"id": 0, "start": 1, "end": 150},
                                    {"id": 1, "start": 0, "end": 0}, {"id": 2, "start": 0, "end": 0},
                                    {"id": 3, "start": 0, "end": 0}]})
        self.assertTrue(r["local"])
        self.assertEqual(self.front.holds["ports"][0], (1, 150, 1))
        self.assertEqual(self.ctl.holds["ports"], deck_ports)

    def test_commands_go_to_each_address(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        self.app.local_commands(True)
        c = self.app.ctrl
        c._switch(DECK, 0)
        c._switch(FRONT, 1)
        power = lambda ctl: [b[3] for _, _, b in ctl.frames(L.CMD_REQUEST) if b[0] == L.SUB_POWER]
        self.assertEqual(power(self.ctl), [0])
        self.assertEqual(power(self.front), [1])
        self.assertEqual(c.lan_sent, {DECK: {"switch"}, FRONT: {"switch"}})
        self.assertNotIn("/device/update", [p for p, _ in self.F.STATE["log"]])

    def test_one_failing_doesnt_send_the_other_to_the_cloud(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        self.app.local_commands(True)
        self.front.close()                               # the Front stops answering
        c = self.app.ctrl
        c._switch(FRONT, 1)
        self.assertIn(FRONT, c.lan.failed_at)
        self.assertNotIn(DECK, c.lan.failed_at)
        c._switch(DECK, 1)
        self.assertEqual(c.lan_sent.get(DECK), {"switch"}, "the Deck still over the home network")

    def test_home_lists_each(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        home = self.app.lan_home()["devices"]
        self.assertEqual({k: v["address"] for k, v in home.items()}, {DECK: "127.0.0.1", FRONT: "127.0.0.2"})
        self.assertEqual(home[FRONT]["name"], "Front")
        for _ in range(60):
            home = self.app.lan_home()["devices"]
            if home[DECK]["ok"] and home[FRONT]["ok"]:
                break
            time.sleep(0.05)
        self.assertTrue(home[DECK]["ok"] and home[FRONT]["ok"])

    def test_clearing_the_music_address_keeps_each_controllers(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        self.app.musiclink_address("")
        self.assertEqual(self.app._lan_address(FRONT), "127.0.0.2")
        self.assertEqual(self.app._lan_address(DECK), "127.0.0.1")


class ThreeControllers(TwoControllers):
    """Any number: a third controller (Garage) with no address yet."""
    def setUp(self):
        super().setUp()
        g = front_cloud()
        g.update(deviceId=GARAGE, name="Garage")
        self.F.STATE["more"].append(g)
        self.app._acct = []
        self.app.devices()

    def test_a_controller_without_an_address_is_named(self):
        self.app.local_address(DECK, "127.0.0.1")
        self.app.local_address(FRONT, "127.0.0.2")
        self.app.ctrl.devices = [{"deviceId": x, "name": n} for x, n in ((DECK, "Deck"), (FRONT, "Front"), (GARAGE, "Garage"))]
        r = self.app.save_to_controller({"name": "Porch", "effect": {"colors": ["#FFB46B"], "counts": [2]}})
        self.assertEqual(len(r["saved"]), 2)
        self.assertEqual(r["missing"], ["Garage"])
        self.assertNotIn(GARAGE, self.app.lan_home()["devices"])
        self.app.local_commands(True)
        self.assertFalse(self.app.ctrl.lan.usable(GARAGE), "the Garage uses the cloud")


class Screens(unittest.TestCase):
    def test_wired_in(self):
        js = (ROOT / "eaveluxos" / "static" / "app.js").read_text(encoding="utf-8")
        for s in ("function controllerCards(st)", "data-lcsavedev", "data-lcassign", "data-lcwhich", "data-lcuse",
                  "api('local/address'", "api('local/identify'", "'?device=' + encodeURIComponent(d.id)"):
            self.assertIn(s, js)
        server = (ROOT / "eaveluxos" / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/local/address"', server)
        self.assertNotIn("_lan_device", server)


if __name__ == "__main__":
    unittest.main()


try:
    from playwright.sync_api import sync_playwright
except ImportError:          # the tests still run without it
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed")
class Browser(TwoBase):
    """The screens, in a real browser: Local mode asks which controller the
    old address is, Find and "Which is this?" tell them apart, and Home
    shows a card for each controller."""
    SHOTS = None             # a folder to save screenshots in, when looking at them by hand

    def test_local_mode_and_home(self):
        import threading
        from eaveluxos.server import make_server
        self.app.musiclink_find = lambda: {"found": ["127.0.0.1", "127.0.0.2"]}
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
            for _ in range(100):
                if cond():
                    return
                time.sleep(0.05)
            self.fail(f"never: {what}")
        for size in ({"width": 1300, "height": 900}, {"width": 390, "height": 844}):
            ctx = br.new_context(viewport=size)
            self.addCleanup(ctx.close)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "#local")                 # its own Setup section since 4.9.2
            pg.wait_for_selector("#lcbox [data-lcsavedev]")
            self.assertEqual(pg.locator("#lcbox [data-lcsavedev]").count(), 2, "one row per controller")
            if size["width"] == 390:
                self.assertEqual(pg.evaluate("document.documentElement.scrollWidth"), 390, "fits a phone")
                if self.SHOTS:
                    pg.screenshot(path=f"{self.SHOTS}/local-phone.png", full_page=True)
                continue
            self.assertIn("127.0.0.1", pg.inner_text("#lcbox .callout"))
            pg.click(f'#lcbox [data-lcassign="{DECK}"]')                     # the old address is the Deck's
            until(lambda: pg.locator("#lcbox [data-lcassign]").count() == 0, "the question goes away")
            self.assertEqual(self.app._lan_address(DECK), "127.0.0.1")
            pg.click("#lcbox [data-lcfind]")
            pg.wait_for_selector('#lcbox [data-lcwhich="127.0.0.2"]')
            pg.click('#lcbox [data-lcwhich="127.0.0.2"]')
            until(lambda: pg.inner_text('[data-lcinfo="127.0.0.2"]').strip(), "what the Front holds")
            self.assertIn("Front Porch", pg.inner_text('[data-lcinfo="127.0.0.2"]'))
            pg.select_option('[data-lcfor="127.0.0.2"]', FRONT)
            pg.click('#lcbox [data-lcuse="127.0.0.2"]')
            until(lambda: pg.locator(f'[data-lcaddr="{FRONT}"]').count() and pg.input_value(f'[data-lcaddr="{FRONT}"]') == "127.0.0.2",
                  "the Front's address filled in")
            self.assertEqual(self.app._lan_address(FRONT), "127.0.0.2")
            pg.select_option("#lcdev", FRONT)
            pg.wait_for_selector("#lcbody .item")
            self.assertIn("Front Porch", pg.inner_text("#lcbody"))
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/local.png", full_page=True)
            for _ in range(60):
                h = self.app.lan_home()["devices"]
                if all(x["ok"] for x in h.values()):
                    break
                time.sleep(0.05)
            pg.goto(base + "#home")
            pg.wait_for_selector(".ctlcards")
            until(lambda: "127.0.0.2 · answering" in pg.inner_text(".ctlcards"), "the Front's card")
            text = pg.inner_text(".ctlcards")
            self.assertIn("127.0.0.1", text)
            self.assertIn("127.0.0.2 · answering", text)
            if self.SHOTS:
                pg.screenshot(path=f"{self.SHOTS}/home.png", full_page=True)
        self.assertEqual(errors, [])

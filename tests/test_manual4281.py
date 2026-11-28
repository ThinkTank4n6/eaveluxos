"""4.28.1: one Alerts section in the manual, numbered sections in order, and
every reference and link pointing at a section that exists."""
import json, re, shutil, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = (ROOT / "MANUAL.md").read_text(encoding="utf-8")


class ManualAlerts(unittest.TestCase):
    def test_one_alerts_section(self):
        self.assertEqual(re.findall(r"(?m)^## \d+\. Alerts.*$", MD), ["## 14. Alerts"])
        sec = MD.split("## 14. Alerts\n", 1)[1].split("\n## 15. ", 1)[0]
        for h in ("### Automations (When · If · Then)", "### Severe weather alerts", "### Security flash",
                  "### Phone alerts", "### Webhooks and Home Assistant", "#### Siri, Alexa and Google (4.18)"):
            self.assertIn("\n" + h + "\n", sec)
        self.assertIn("ntfy", sec)
        self.assertNotIn("in this section", sec)

    def test_sections_in_order(self):
        nums = [int(n) for n in re.findall(r"(?m)^## (\d+)\. ", MD)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))
        toc = [int(n) for n in re.findall(r"(?m)^(\d+)\. \[.*?\]\(#\1-", MD)]
        self.assertEqual(toc, nums)

    def test_references_exist(self):
        last = max(int(n) for n in re.findall(r"(?m)^## (\d+)\. ", MD))
        for f in ("MANUAL.md", "README.md", "eaveluxos/static/app.js", "eaveluxos/static/triggers.js"):
            for n in re.findall(r"\b[Ss]ection (\d+)\b", (ROOT / f).read_text(encoding="utf-8")):
                self.assertLessEqual(int(n), last, f)
        self.assertIn("Manual, section 21", (ROOT / "eaveluxos/static/app.js").read_text(encoding="utf-8"))
        self.assertIn("## 21. Update, move or uninstall", MD)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_links_resolve(self):
        js = ROOT / "eaveluxos" / "static" / "markdown.js"
        script = (f"const md=require({json.dumps(str(js))});let t='';process.stdin.on('data',d=>t+=d).on('end',()=>{{"
                  "const ids=new Set();let c=false;for(const l of t.split('\\n')){if(/^```/.test(l))c=!c;"
                  "const h=!c&&/^(#{1,6})\\s+(.*?)\\s*#*\\s*$/.exec(l);if(h)ids.add(md.slug(h[2]));}"
                  "const bad=[...t.matchAll(/\\]\\(#([^)]+)\\)/g)].map(m=>m[1]).filter(l=>!ids.has(l));"
                  "process.stdout.write(JSON.stringify(bad));})")
        out = subprocess.run(["node", "-e", script], input=MD, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(out.stdout), [], out.stderr)


if __name__ == "__main__":
    unittest.main()

"""Landing-page data provenance, visibility keys and shared design-system wiring."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
PAGES = ("index.html", "system-one.html")
ASSETS = ("assets/site.css", "assets/site.js")


class LandingPageTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "docs/data.json").read_text())

    def test_comparison_visibility_keys_exist_in_ledger(self):
        models = {row["model"] for row in self.data["results"]}
        s1 = self.data["systemOne"]
        for row in s1["rows"] + s1["realUseCase"]["rows"]:
            with self.subTest(model=row["model"]):
                self.assertIn(row["modelKey"], models)

    def test_mercury_scores_match_error_free_artifacts(self):
        model = "inception/mercury-decide:free"
        folder = ROOT / "results/2026-10-01-mercury-decide-rerun"
        s1 = json.loads((folder / "mercury-s1-rateaware.json").read_text())["summary"]
        phish = json.loads((folder / "mercury-phishing.json").read_text())[
            "variant_comparison"]["variants"]["typesafe_only"]
        self.assertEqual(s1["errored"], 0)
        self.assertEqual(s1["generations"], 98)
        self.assertEqual(phish["completeness"]["per_analyzer"]["typesafe_analyzer"]["failed"], 0)
        self.assertEqual(phish["samples_evaluated"], 16)
        rows = [r for r in self.data["results"] if r["model"] == model]
        self.assertEqual(len(rows), 2)
        expected = {"system1": round(s1["pass_at_1"] * 100, 1),
                    "phishing-eval": phish["detection"]["f1"] * 100}
        for row in rows:
            self.assertEqual(row["score"], expected[row["suite"]])
            self.assertTrue((ROOT / row["report"]).is_file())
        for chart in [self.data["systemOne"], self.data["systemOne"]["realUseCase"]]:
            mercury = next(r for r in chart["rows"] if r["modelKey"] == model)
            self.assertEqual(mercury["score"], expected[
                "system1" if chart is self.data["systemOne"] else "phishing-eval"])
        # The accuracy Wilson interval is not an F1 confidence interval.
        mercury_phish = next(r for r in self.data["systemOne"]["realUseCase"]["rows"]
                             if r["modelKey"] == model)
        self.assertIsNone(mercury_phish["ci"])

    def test_each_page_owns_a_disjoint_slice_of_the_ledger(self):
        suites = {row["suite"] for row in self.data["results"]}
        owned = {}
        for page in PAGES:
            with self.subTest(page=page):
                html = (DOCS / page).read_text()
                match = re.search(r'<body[^>]*\bdata-suites="([^"]+)"', html)
                self.assertIsNotNone(match, f"{page} declares no data-suites")
                owned[page] = set(match.group(1).split(","))
                self.assertTrue(owned[page] & suites, f"{page} owns no measured suite")
        # Every ledger row is reachable from exactly one page, and no page claims
        # a suite it never renders.
        claimed = [suite for page_suites in owned.values() for suite in page_suites]
        self.assertEqual(len(claimed), len(set(claimed)), "suites overlap across pages")
        self.assertEqual(set(claimed), suites, "a ledger suite belongs to no page")

    def test_pages_share_the_design_system_without_inline_code(self):
        for page in PAGES:
            with self.subTest(page=page):
                html = (DOCS / page).read_text()
                self.assertIn('<link rel="stylesheet" href="assets/site.css"', html)
                self.assertIn('<script src="assets/site.js">', html)
                self.assertEqual(re.findall(r"<style", html), [])
                self.assertEqual(
                    [body for body in re.findall(r"<script[^>]*>(.*?)</script>", html,
                                                 flags=re.DOTALL) if body.strip()],
                    [],
                )
        for asset in ASSETS:
            with self.subTest(asset=asset):
                self.assertTrue((DOCS / asset).is_file())

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for JS syntax validation")
    def test_javascript_parses(self):
        for asset in ASSETS:
            if asset.endswith(".js"):
                with self.subTest(asset=asset):
                    result = subprocess.run(["node", "--check", str(DOCS / asset)],
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
        for page in PAGES:
            with self.subTest(page=page):
                html = (DOCS / page).read_text()
                scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
                for script in scripts:
                    result = subprocess.run(["node", "--check"], input=script, text=True,
                                            capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)

"""Landing-page data provenance, visibility keys and shared design-system wiring."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from benchkit.fingerprint import suite_hash
from benchkit.suites import SUITES

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
PAGES = ("index.html", "system-one.html", "system-one-v2.html", "system-one-v1.html")
ASSETS = ("assets/site.css", "assets/site.js")


class LandingPageTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "docs/data.json").read_text())

    def test_comparison_visibility_keys_exist_in_ledger(self):
        models = {row["model"] for row in self.data["results"]}
        legacy = self.data["systemOneV1"]
        for row in (self.data["systemOne"]["rows"] + self.data["systemOneV2"]["rows"]
                    + legacy["rows"] + legacy["realUseCase"]["rows"]):
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
        v2 = json.loads((ROOT / "results/2026-10-09-system1-v2-v1-roster"
                         "/mercury-decide-free-system1-v2.json").read_text())["summary"]
        self.assertEqual(v2["errored"], 0)
        self.assertEqual(v2["generations"], 800)
        rows = [r for r in self.data["results"] if r["model"] == model]
        self.assertEqual(len(rows), 3)
        expected = {"system1-v2": round(v2["pass_at_1"] * 100, 1),
                    "system1-legacy": round(s1["pass_at_1"] * 100, 1),
                    "phishing-eval": phish["detection"]["f1"] * 100}
        for row in rows:
            self.assertEqual(row["score"], expected[row["suite"]])
            self.assertTrue((ROOT / row["report"]).is_file())
        legacy = self.data["systemOneV1"]
        for chart in [legacy, legacy["realUseCase"]]:
            mercury = next(r for r in chart["rows"] if r["modelKey"] == model)
            self.assertEqual(mercury["score"], expected[
                "system1-legacy" if chart is legacy else "phishing-eval"])
        # The accuracy Wilson interval is not an F1 confidence interval.
        mercury_phish = next(r for r in legacy["realUseCase"]["rows"]
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

    def test_v2_counts_and_scores_match_measured_artifacts(self):
        current = self.data["systemOneV2"]
        tasks = SUITES["system1-v2"]
        self.assertEqual(current["version"], 2)
        self.assertEqual(current["scenarios"], len(tasks))
        self.assertEqual(current["questions"], sum(len(t["questions"]) for t in tasks))
        self.assertEqual(current["generations"], current["questions"] * current["samples"])
        self.assertEqual(current["suiteHash"], suite_hash(tasks))
        self.assertEqual(len(current["families"]), 10)
        self.assertEqual(sum(f["scenarios"] for f in current["families"]), 200)
        self.assertEqual(sum(f["questions"] for f in current["families"]), 400)
        self.assertNotIn("realUseCase", current)
        ledger = [r for r in self.data["results"] if r["suite"] == "system1-v2"]
        self.assertEqual(len(ledger), len(current["rows"]))
        for row in current["rows"]:
            with self.subTest(model=row["model"]):
                run = json.loads((ROOT / row["sourceJson"]).read_text())
                summary = run["summary"]
                self.assertEqual(summary["generations"], 800)
                self.assertEqual(summary["errored"], row.get("transportErrors", 0))
                if summary["errored"]:
                    self.assertIn(str(summary["errored"]), row["note"])
                self.assertEqual(summary["config"]["concurrency"], 1)
                self.assertEqual(row["score"], round(summary["pass_at_1"] * 100, 1))
                self.assertEqual(row["secPerQ"], round(summary["cost"]["seconds"], 3))
                self.assertEqual(row["outTok"], round(summary["cost"]["output_tokens"], 2))
                self.assertEqual(row["wall"], round(summary["wall_seconds"], 2))
                self.assertEqual(row["ciBounds"], [v * 100 for v in summary["solve_rate_ci"]])
                self.assertEqual(row["suiteHash"], current["suiteHash"])
                measured = next(r for r in ledger if r["model"] == row["modelKey"])
                self.assertEqual(measured["datasetVersion"], 2)
                self.assertEqual(measured["suiteHash"], current["suiteHash"])
                self.assertEqual(measured["sourceJson"], row["sourceJson"])
                self.assertEqual(measured["score"], row["score"])
        self.assertIn("64-candidate", current["note"])
        self.assertIn("three open questions", current["note"])

    def test_v3_counts_and_scores_match_measured_artifacts(self):
        v3 = self.data["systemOne"]
        tasks = SUITES["system1"]
        self.assertEqual(v3["version"], 3)
        self.assertEqual(v3["scenarios"], len(tasks))
        self.assertEqual(v3["questions"], sum(len(t["questions"]) for t in tasks))
        self.assertEqual(v3["generations"], v3["questions"] * v3["samples"])
        self.assertEqual(v3["suiteHash"], suite_hash(tasks))
        self.assertEqual({f["id"] for f in v3["families"]},
                         {t["id"].rsplit("_", 1)[0] for t in tasks})
        self.assertEqual(sum(f["scenarios"] for f in v3["families"]), 200)
        ledger = [r for r in self.data["results"] if r["suite"] == "system1"]
        self.assertEqual(len(ledger), len(v3["rows"]))
        self.assertNotIn("inception/mercury-decide:free", {r["model"] for r in ledger})
        for row in v3["rows"]:
            with self.subTest(model=row["model"]):
                run = json.loads((ROOT / row["sourceJson"]).read_text())
                summary, results = run["summary"], run["results"]
                self.assertEqual(summary["generations"], 200)
                self.assertEqual(summary["errored"], 0)
                self.assertEqual(summary["config"]["concurrency"], 1)
                self.assertEqual(summary["suite_hash"], v3["suiteHash"])
                self.assertEqual(row["score"], round(summary["pass_at_1"] * 100, 1))
                self.assertEqual(row["groupAcc"], round(summary["group_accuracy"] * 100, 1))
                self.assertEqual(row["secPerQ"], round(summary["cost"]["seconds"], 3))
                self.assertEqual(row["ciBounds"], [v * 100 for v in summary["solve_rate_ci"]])
                for family in v3["families"]:
                    passed = [r["passed"] for r in results
                              if r["task"].startswith(family["id"] + "_")]
                    self.assertEqual(v3["familyScores"][row["modelKey"]][family["id"]],
                                     round(100 * sum(passed) / len(passed), 1))
                measured = next(r for r in ledger if r["model"] == row["modelKey"])
                self.assertEqual(measured["datasetVersion"], 3)
                self.assertEqual(measured["score"], row["score"])
                self.assertEqual(measured["sourceJson"], row["sourceJson"])
                self.assertTrue((ROOT / measured["report"]).is_file())
        page = (DOCS / "system-one.html").read_text()
        self.assertIn('data-suites="system1"', page)
        self.assertIn('id="s1-family-scores"', page)
        self.assertIn('href="system-one-v2.html"', page)
        for other in ("system-one-v2.html", "system-one-v1.html", "index.html"):
            self.assertIn('href="system-one.html"', (DOCS / other).read_text())

    def test_v1_reference_is_versioned_and_linked(self):
        legacy = self.data["systemOneV1"]
        self.assertEqual((legacy["version"], legacy["scenarios"], legacy["questions"]), (1, 23, 49))
        self.assertEqual(legacy["generations"], 98)
        self.assertTrue(legacy["realUseCase"]["rows"])
        for row in self.data["results"]:
            if row["suite"] == "system1-legacy":
                self.assertEqual(row["datasetVersion"], 1)
        main = (DOCS / "system-one.html").read_text()
        v2 = (DOCS / "system-one-v2.html").read_text()
        archive = (DOCS / "system-one-v1.html").read_text()
        self.assertIn('href="system-one-v1.html"', main)
        self.assertIn('href="system-one-v1.html"', v2)
        self.assertIn('href="system-one.html"', archive)
        self.assertIn('data-suites="system1"', main)
        self.assertIn('data-suites="system1-v2"', v2)
        self.assertIn('data-suites="system1-legacy,phishing-eval"', archive)
        self.assertIn("200 distinct scenarios and 400 scored questions", v2)
        self.assertIn("Benchmark v1 reference", archive)
        self.assertNotIn("98.0%", main)
        self.assertNotIn('id="s1-real"', main)

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
                                            capture_output=True, text=True, timeout=10, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
        for page in PAGES:
            with self.subTest(page=page):
                html = (DOCS / page).read_text()
                scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
                for script in scripts:
                    result = subprocess.run(["node", "--check"], input=script, text=True,
                                            capture_output=True, timeout=10, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

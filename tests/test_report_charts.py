"""The skimmable views: text bars, scoreboard, scatter, per-task heatmap."""
import unittest

from benchkit import report


def _run(label, solve, by_task, harness="claude-code", extra=None, seconds=10.0):
    s = dict(kind="agentic", pass_at_1=solve, generations=24, tasks=len(by_task),
             mean_efficiency=0.5, by_task=by_task, by_difficulty={"easy": solve},
             harness=dict(harness=harness),
             config=dict(label=label, model="claude-opus-5-5", thinking=False,
                         max_tokens=0, samples=3, concurrency=2, base_url="(harness)",
                         extra=extra or {}),
             cost=dict(generations=24, tokens_reported=24, input_tokens=9000.0,
                       output_tokens=1000.0, seconds=seconds))
    return dict(summary=s, results=[], _path=f"{label}.json")


class TestBars(unittest.TestCase):
    def test_bar_is_fixed_width(self):
        for frac in (0, 0.05, 0.5, 0.999, 1, 1.2):
            self.assertEqual(len(report._bar(frac)), 12)  # 10 cells + backticks
        self.assertEqual(report._bar(1), "`██████████`")
        self.assertEqual(report._bar(None), "")

    def test_compact(self):
        self.assertEqual(report._compact(108348), "108k")
        self.assertEqual(report._compact(1500), "1.5k")
        self.assertEqual(report._compact(None), "—")


class TestLabels(unittest.TestCase):
    def test_effort_distinguishes_same_model_runs(self):
        runs = [_run("a", 0.5, {}, extra={"effort": "low"}),
                _run("b", 0.5, {}, extra={"effort": "medium"})]
        short = report._run_short(runs, ["a", "b"])
        self.assertEqual(len(set(short)), 2)
        self.assertIn("effort=low", short[0])

    def test_harness_prefixed_when_runs_span_harnesses(self):
        runs = [_run("a", 0.5, {}), _run("b", 0.5, {}, harness="opencode")]
        short = report._run_short(runs, ["a", "b"])
        self.assertTrue(short[0].startswith("claude-code "))
        self.assertTrue(short[1].startswith("opencode "))


class TestSections(unittest.TestCase):
    def setUp(self):
        self.runs = [_run("a", 1.0, {"t1": 1.0, "t2": 1.0, "t3": 0.0}, seconds=40.0),
                     _run("b", 0.5, {"t1": 1.0, "t2": 0.0, "t3": 0.0},
                          harness="opencode", seconds=10.0)]
        self.md = report.build(self.runs, title="t")

    def test_glance_comes_before_results(self):
        self.assertLess(self.md.index("## At a glance"), self.md.index("## Results"))
        glance = self.md.split("## At a glance")[1].split("## Results")[0]
        self.assertIn("claude-code · OFF", glance)
        self.assertIn("quadrantChart", glance)

    def test_scatter_points_are_row_numbers(self):
        glance = self.md.split("## At a glance")[1].split("## Results")[0]
        self.assertIn("    1: [0.96, 0.96]", glance)
        self.assertIn("    2: [0.25, 0.50]", glance)

    def test_heatmap_puts_disagreements_first_and_folds_agreement(self):
        heat = self.md.split("## Task by task")[1].split("## ")[0]
        self.assertIn("| `t2` | 🟩 100 | 🟥 0 |", heat)
        self.assertNotIn("| `t1` |", heat)
        self.assertIn("every run solved** (1): `t1`", heat)
        self.assertIn("every run failed** (1): `t3`", heat)

    def test_single_run_has_no_scatter(self):
        md = report.build(self.runs[:1], title="t")
        self.assertNotIn("quadrantChart", md)
        self.assertIn("| `t3` | 🟥 0 |", md)

    def test_fully_errored_run_is_flagged_and_left_off_the_scatter(self):
        broken = _run("c", 0.0, {"t1": 0.0}, harness="pi", seconds=0.5)
        broken["summary"]["errored"] = 24
        md = report.build(self.runs + [broken], title="t")
        glance = md.split("## At a glance")[1].split("## Results")[0]
        self.assertIn("⚠ 24/24 errored", glance)
        self.assertNotIn("    3:", glance)
        self.assertIn("    1: [0.96, 0.96]", glance)


if __name__ == "__main__":
    unittest.main()

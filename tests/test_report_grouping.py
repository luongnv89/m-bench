"""Re-runs of one label are samples of one run, not separate runs (issue #89).

`bench run` writes `<label>.1.json`, `<label>.2.json` when the label repeats.
The report pools files that share a label *and* a `suite_hash` (issue #88);
files that predate `suite_hash` are never pooled. Grouping is read-only.
"""
import copy
import json
import os
import tempfile
import unittest

from benchkit import cli, report

HASH = "a" * 64


def _read(path):
    with open(path) as f:
        return f.read()


def _run(path, label="m think-OFF", pass_at_1=0.5, generations=4, samples=2,
         suite_hash=HASH, thinking=False, agent=False, by_task=None, extra=None,
         **more):
    summary = dict(
        config=dict(base_url="http://h/v1", model="m", label=label, thinking=thinking,
                    max_tokens=6000, samples=samples, concurrency=1,
                    extra=extra or {}),
        tasks=2, generations=generations, pass_at_1=pass_at_1,
        pass_all_samples=0.5, pass_any_sample=0.5, wall_seconds=100.0,
        mean_completion_tokens=100.0, median_completion_tokens=100,
        mean_tok_s=10.0, aggregate_tok_s=5.0, mean_ttft=None,
        by_task=by_task or {"t1": pass_at_1, "t2": pass_at_1},
        by_difficulty={"easy": pass_at_1, "medium": None, "hard": None},
        truncated=1, errored=0)
    if suite_hash:
        summary.update(suite_hash=suite_hash, schema_version=1)
    if agent:
        summary.update(kind="agentic", agent_score=more.pop("agent_score"),
                       mean_efficiency=more.pop("mean_efficiency"),
                       total_tool_calls=more.pop("total_tool_calls"),
                       valid_call_rate=more.pop("valid_call_rate"),
                       mean_par_calls=5.0, mean_tool_calls=6.0, mean_turns=7.0,
                       malformed_args=0, unknown_tools=0, hit_turn_limit=1,
                       stalled_no_tool_call=0)
    summary.update(more)
    return dict(summary=summary, results=[], _path=path)


class TestGroupRuns(unittest.TestCase):
    def test_same_label_same_hash_is_one_group(self):
        runs = [_run("a.json"), _run("a.1.json"), _run("a.2.json")]
        groups = report.group_runs(runs)
        self.assertEqual(len(groups), 1)
        self.assertEqual([m["_path"] for m in groups[0]["members"]],
                         ["a.json", "a.1.json", "a.2.json"])
        self.assertEqual(groups[0]["suite_hash"], HASH)
        self.assertEqual(groups[0]["label"], "m think-OFF")

    def test_different_hash_stays_separate(self):
        groups = report.group_runs([_run("a.json"), _run("a.1.json", suite_hash="b" * 64)])
        self.assertEqual(len(groups), 2)

    def test_missing_hash_stays_separate(self):
        runs = [_run("a.json", suite_hash=None), _run("a.1.json", suite_hash=None)]
        groups = report.group_runs(runs)
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(g["key"] is None for g in groups))
        self.assertEqual(report.unhashed_label_collisions(runs), ["m think-OFF"])

    def test_hashed_and_unhashed_never_mix(self):
        groups = report.group_runs([_run("a.json"), _run("a.1.json", suite_hash=None)])
        self.assertEqual(len(groups), 2)

    def test_label_collision_across_setups_is_not_pooled(self):
        runs = [_run("a.json"), _run("a.1.json", thinking=True)]
        self.assertEqual(len(report.group_runs(runs)), 2)

    def test_label_collision_across_effort_is_not_pooled(self):
        runs = [_run("a.json", extra={"effort": "low"}),
                _run("a.1.json", extra={"effort": "high"})]
        self.assertEqual(len(report.group_runs(runs)), 2)

    def test_different_labels_stay_separate_in_order(self):
        runs = [_run("b.json", label="B"), _run("a.json", label="A"),
                _run("b.1.json", label="B")]
        self.assertEqual([g["label"] for g in report.group_runs(runs)], ["B", "A"])

    def test_inputs_are_not_mutated(self):
        runs = [_run("a.json", pass_at_1=1.0), _run("a.1.json", pass_at_1=0.0)]
        before = copy.deepcopy(runs)
        for g in report.group_runs(runs):
            report.pool(g)
        self.assertEqual(runs, before)


class TestPool(unittest.TestCase):
    def test_single_member_is_returned_as_is(self):
        r = _run("a.json")
        self.assertIs(report.pool(report.group_runs([r])[0]), r)

    def test_pass_at_1_weighted_by_generations_and_samples_summed(self):
        runs = [_run("a.json", pass_at_1=1.0, generations=4, samples=2),
                _run("a.1.json", pass_at_1=0.0, generations=12, samples=6)]
        s = report.pool(report.group_runs(runs)[0])["summary"]
        self.assertAlmostEqual(s["pass_at_1"], 4 / 16)
        self.assertEqual(s["generations"], 16)
        self.assertEqual(s["config"]["samples"], 8)
        self.assertEqual(s["truncated"], 2)
        self.assertAlmostEqual(s["by_task"]["t1"], 2 / 8)
        self.assertAlmostEqual(s["by_difficulty"]["easy"], 4 / 16)
        self.assertAlmostEqual(s["wall_seconds"], 100.0)
        self.assertIsNone(s["median_completion_tokens"])
        self.assertEqual(s["suite_hash"], HASH)

    def test_pooled_samples_lower_the_noise_floor(self):
        runs = [_run("a.json"), _run("a.1.json")]
        s = report.pool(report.group_runs(runs)[0])["summary"]
        self.assertLess(report.noise_floor(s["config"]["samples"]),
                        report.noise_floor(2))

    def test_agent_score_is_pooled_solve_times_pooled_efficiency(self):
        runs = [_run("a.json", agent=True, pass_at_1=1.0, generations=4,
                     agent_score=0.8, mean_efficiency=0.8, total_tool_calls=10,
                     valid_call_rate=1.0),
                _run("a.1.json", agent=True, pass_at_1=0.5, generations=4,
                     agent_score=0.2, mean_efficiency=0.4, total_tool_calls=30,
                     valid_call_rate=0.5)]
        s = report.pool(report.group_runs(runs)[0])["summary"]
        self.assertAlmostEqual(s["pass_at_1"], 0.75)
        # efficiency is weighted by solved generations: 4 and 2
        self.assertAlmostEqual(s["mean_efficiency"], (0.8 * 4 + 0.4 * 2) / 6)
        self.assertAlmostEqual(s["agent_score"], s["pass_at_1"] * s["mean_efficiency"])
        self.assertAlmostEqual(s["valid_call_rate"], (10 + 15) / 40)
        self.assertEqual(s["hit_turn_limit"], 2)
        self.assertEqual(s["kind"], "agentic")


class TestBuild(unittest.TestCase):
    def test_reruns_render_as_one_row(self):
        runs = [_run("a.json", pass_at_1=1.0), _run("a.1.json", pass_at_1=0.0),
                _run("b.json", label="other", pass_at_1=0.5)]
        md = report.build(runs, title="t")
        results = md.split("## Results")[1].split("```")[0]
        self.assertEqual(results.count("m think-OFF"), 1)
        self.assertIn("50.0 %", results)
        self.assertIn("pooled: 2 re-runs", md)
        self.assertIn("pass@1 per re-run 100.0, 0.0", md)
        self.assertIn("`a.json`, `a.1.json`", md)

    def test_no_group_keeps_every_file(self):
        runs = [_run("a.json"), _run("a.1.json")]
        md = report.build(runs, title="t", group=False)
        self.assertNotIn("pooled:", md)
        self.assertEqual(md.split("## Raw data")[1].count("m think-OFF"), 2)

    def test_unhashed_reruns_are_separate_with_caveat(self):
        runs = [_run("a.json", suite_hash=None), _run("a.1.json", suite_hash=None)]
        md = report.build(runs, title="t")
        self.assertNotIn("pooled:", md)
        self.assertIn("predate `suite_hash`", md)


class TestCliReport(unittest.TestCase):
    def _files(self, d):
        paths = []
        for name, p in (("a.json", 1.0), ("a.1.json", 0.0)):
            path = os.path.join(d, name)
            r = _run(name, pass_at_1=p)
            r.pop("_path")
            with open(path, "w") as f:
                json.dump(r, f)
            paths.append(path)
        return paths

    def test_report_pools_and_leaves_inputs_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._files(d)
            before = {p: _read(p) for p in paths}
            out = os.path.join(d, "out.md")
            cli.main(["report", *paths, "--out", out])
            md = _read(out)
            self.assertIn("pooled: 2 re-runs", md)
            self.assertEqual({p: _read(p) for p in paths}, before)
            self.assertEqual(sorted(os.listdir(d)), ["a.1.json", "a.json", "out.md"])

    def test_report_no_group_flag(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._files(d)
            out = os.path.join(d, "out.md")
            cli.main(["report", *paths, "--out", out, "--no-group"])
            self.assertNotIn("pooled:", _read(out))


if __name__ == "__main__":
    unittest.main()

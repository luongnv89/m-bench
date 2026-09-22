"""Solve rate and efficiency as separate headlines, per-task cost (#86), and
3-sample harness defaults with confidence intervals instead of a fixed
8-point noise rule (#87)."""
import json
import unittest
from unittest import mock

from benchkit import cli, report, runner, stats
from benchkit.agentic import loop
from benchkit.harness import runner as hrunner
from benchkit.harness.base import Harness, HarnessResult
from benchkit.suites import SUITES


def _cfg(samples=1):
    return runner.Config(samples=samples, concurrency=1)


def _row(task, passed, sample=0, **kw):
    r = dict(task=task, difficulty="easy", sample=sample, passed=passed, error="",
             tok_s=None, ttft=None, elapsed=2.0, completion_tokens=100)
    r.update(kw)
    return r


class TestWilson(unittest.TestCase):
    def test_known_values(self):
        lo, hi = stats.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=4)
        lo, hi = stats.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=4)
        self.assertAlmostEqual(hi, 0.7634, places=4)
        lo, hi = stats.wilson(10, 10)
        self.assertAlmostEqual(lo, 0.7225, places=4)
        self.assertAlmostEqual(hi, 1.0)

    def test_no_generations_is_no_interval(self):
        self.assertIsNone(stats.wilson(0, 0))
        self.assertIsNone(stats.wilson(1, None))
        self.assertIsNone(stats.rate_interval(None, 8))
        self.assertIsNone(stats.rate_interval(0.5, 0))

    def test_interval_narrows_with_more_generations(self):
        a, b = stats.rate_interval(0.5, 8), stats.rate_interval(0.5, 80)
        self.assertLess(b[1] - b[0], a[1] - a[0])

    def test_newcombe_difference(self):
        lo, hi = stats.newcombe(0.5, 10, 0.5, 10)
        self.assertLess(lo, 0)
        self.assertGreater(hi, 0)
        lo, hi = stats.newcombe(1.0, 10, 0.0, 10)
        self.assertGreater(lo, 0)
        self.assertIsNone(stats.newcombe(0.5, None, 0.5, 10))


class TestSummaryHeadline(unittest.TestCase):
    """Every summary producer carries separate headline numbers and cost."""

    def test_one_shot_runner(self):
        rows = [_row("t1", True, prompt_tokens=50),
                _row("t1", False, sample=1, prompt_tokens=70, completion_tokens=300),
                dict(task="t2", difficulty="easy", sample=0, passed=False,
                     error="generation failed: down", tok_s=None, ttft=None,
                     elapsed=None, completion_tokens=None)]
        s = runner.summarize(rows, _cfg(2), 10.0, 2)
        self.assertAlmostEqual(s["solve_rate"], 1 / 3)
        self.assertEqual(s["solve_rate"], s["pass_at_1"])
        lo, hi = stats.rate_interval(1 / 3, 3)
        self.assertEqual(s["solve_rate_ci"], [lo, hi])
        self.assertIsNone(s["efficiency"])        # no efficiency outside agentic
        t1 = s["cost_by_task"]["t1"]
        self.assertEqual(t1["samples"], 2)
        self.assertEqual(t1["tokens_reported"], 2)
        self.assertAlmostEqual(t1["input_tokens"], 60)
        self.assertAlmostEqual(t1["output_tokens"], 200)
        self.assertAlmostEqual(t1["seconds"], 2.0)
        # a generation that reported no usage is null, never 0
        t2 = s["cost_by_task"]["t2"]
        self.assertEqual(t2["tokens_reported"], 0)
        self.assertIsNone(t2["input_tokens"])
        self.assertIsNone(t2["output_tokens"])
        self.assertIsNone(t2["seconds"])
        self.assertEqual(s["cost"]["generations"], 3)
        self.assertEqual(s["cost"]["tokens_reported"], 2)
        json.dumps(s)                              # stays serialisable

    def test_tokens_of(self):
        self.assertEqual(runner.tokens_of(dict(input_tokens=5, completion_tokens=2)), (5, 2))
        self.assertEqual(runner.tokens_of(dict(prompt_tokens=5, completion_tokens=2)), (5, 2))
        # an old tool-loop row never recorded input: unrecorded, not 0
        self.assertEqual(runner.tokens_of(dict(completion_tokens=9)), (None, 9))
        self.assertEqual(runner.tokens_of(dict(input_tokens=0, completion_tokens=0)),
                         (None, None))
        self.assertEqual(runner.tokens_of(dict(completion_tokens=None)), (None, None))

    def test_agentic_loop_reports_efficiency_separately(self):
        rows = [_row("t1", True, efficiency=0.5, input_tokens=1000, tool_calls=4,
                     failed_calls=0, turns=3, malformed_args=0, unknown_tools=0,
                     stop_reason="finished", par_calls=2),
                _row("t1", False, sample=1, efficiency=None, input_tokens=900,
                     tool_calls=6, failed_calls=1, turns=5, malformed_args=0,
                     unknown_tools=0, stop_reason="finished", par_calls=2)]
        s = loop.summarize(rows, _cfg(2), 5.0, 1)
        self.assertEqual(s["solve_rate"], 0.5)
        self.assertEqual(s["efficiency"], 0.5)
        self.assertEqual(s["efficiency"], s["mean_efficiency"])
        self.assertAlmostEqual(s["cost_by_task"]["t1"]["input_tokens"], 950)
        # the composite is still there for old readers, but is not the headline
        self.assertEqual(s["agent_score"], 0.25)

    def test_agentic_loop_records_input_tokens(self):
        task = SUITES["agentic"][0]
        usage = mock.Mock(completion_tokens=7, prompt_tokens=120)
        msg = mock.Mock(content="done", tool_calls=[])
        client = mock.Mock()
        client.chat.completions.create.return_value = mock.Mock(
            usage=usage, choices=[mock.Mock(message=msg)])
        r = loop.run_task(client, _cfg(), task, 0, max_turns=1)
        self.assertEqual(r["input_tokens"], 120)
        self.assertEqual(r["completion_tokens"], 7)
        self.assertIsNotNone(r["elapsed"])

    def test_harness_that_reports_no_tokens_records_null(self):
        class Silent(Harness):
            name = "silent"

            def available(self):
                return True, ""

            def run(self, workdir, prompt, timeout=900, thinking=False):
                # did work, but emitted no usage at all
                return HarnessResult(tool_calls=2, turns=1, stop_reason="finished")

        tasks = SUITES["agentic"][:2]
        s, results = hrunner.run(Silent(), tasks, _cfg())
        for t in tasks:
            c = s["cost_by_task"][t["id"]]
            self.assertEqual(c["tokens_reported"], 0)
            self.assertIsNone(c["input_tokens"])
            self.assertIsNone(c["output_tokens"])
            self.assertIsNotNone(c["seconds"])
        self.assertIsNone(s["cost"]["input_tokens"])
        self.assertIn("solve_rate", s)
        self.assertIn("efficiency", s)
        json.dumps(dict(summary=s, results=results))


def _agentic_run(path, label, solve, eff, gens=24, cost=True, results=None):
    s = dict(kind="agentic", pass_at_1=solve, mean_efficiency=eff,
             agent_score=solve * eff, generations=gens, tasks=8,
             config=dict(label=label, model="m", thinking=False, max_tokens=0,
                         samples=3, concurrency=2, base_url="http://h/v1"),
             by_task={"t1": solve}, by_difficulty={}, wall_seconds=10.0,
             mean_tool_calls=5.0, mean_par_calls=4.0, mean_turns=6.0,
             valid_call_rate=1.0, hit_turn_limit=0, mean_completion_tokens=10)
    if cost:
        s["cost"] = dict(generations=gens, tokens_reported=gens, input_tokens=5000.0,
                         output_tokens=300.0, seconds=12.5)
        s["cost_by_task"] = {"t1": dict(samples=3, tokens_reported=3, input_tokens=5000.0,
                                        output_tokens=300.0, seconds=12.5)}
    return dict(summary=s, results=results or [], _path=path)


class TestReport(unittest.TestCase):
    def test_headline_shows_solve_rate_and_efficiency_separately(self):
        md = report.build([_agentic_run("a.json", "a", 0.75, 0.4),
                           _agentic_run("b.json", "b", 0.5, 1.0)], title="t")
        head = md.split("## Headline")[1].split("## Results")[0]
        self.assertIn("| Run | Solve rate (95% CI) | Efficiency | Tokens per task "
                      "| Time per task |", head)
        ci = stats.rate_interval(0.75, 24)
        self.assertIn(f"75.0 % ({ci[0] * 100:.0f}–{ci[1] * 100:.0f})", head)
        self.assertIn("| 40.0 % |", head)
        self.assertIn("5,000 in / 300 out", head)
        self.assertIn("12.5 s", head)
        # the higher solver leads even though its efficiency is lower
        results = md.split("## Results")[1].split("## Cost per task")[0]
        self.assertIn("| **a** |", results)

    def test_cost_per_task_section(self):
        md = report.build([_agentic_run("a.json", "a", 0.75, 0.4)], title="t")
        cost = md.split("## Cost per task")[1].split("```")[0]
        self.assertIn("| `t1` | 5,000 / 300 · 12.5 s |", cost)

    def test_unreported_tokens_say_so_and_skip_the_chart(self):
        r = _agentic_run("a.json", "a", 0.75, 0.4)
        r["summary"]["cost"].update(tokens_reported=0, input_tokens=None,
                                    output_tokens=None)
        r["summary"]["cost_by_task"]["t1"].update(tokens_reported=0, input_tokens=None,
                                                  output_tokens=None)
        md = report.build([r], title="t")
        self.assertIn("not reported", md.split("## Headline")[1].split("## Results")[0])
        self.assertIn("| `t1` | not reported · 12.5 s |", md)
        self.assertIn("recorded as null", md)
        self.assertNotIn("tokens per task (in + out)", md)

    def test_old_file_rebuilds_cost_from_its_results(self):
        rows = [dict(task="t1", difficulty="easy", sample=i, passed=True,
                     input_tokens=1000, completion_tokens=100, elapsed=4.0)
                for i in range(2)]
        old = _agentic_run("old.json", "old", 1.0, 1.0, gens=2, cost=False, results=rows)
        before = json.dumps(old, sort_keys=True)
        md = report.build([old], title="t")
        self.assertIn("1,000 in / 100 out", md)
        self.assertIn("| `t1` | 1,000 / 100 · 4.0 s |", md)
        self.assertEqual(json.dumps(old, sort_keys=True), before)   # not mutated

    def test_tokens_chart_needs_both_sides_on_every_row(self):
        new = _agentic_run("h.json", "h", 1.0, 1.0)
        md = report.build([new], title="t")
        self.assertIn("tokens per task (in + out)", md)
        rows = [dict(task="t1", difficulty="easy", sample=0, passed=True,
                     completion_tokens=1300, elapsed=4.0)]      # old loop: no input
        old = _agentic_run("o.json", "o", 1.0, 1.0, gens=1, cost=False, results=rows)
        md = report.build([new, old], title="t")
        self.assertIn("— in / 1,300 out", md)
        self.assertNotIn("tokens per task (in + out)", md)

    def test_old_file_without_results_reports_not_recorded(self):
        old = _agentic_run("old.json", "old", 1.0, 1.0, cost=False)
        del old["summary"]["generations"]
        md = report.build([old], title="t")
        self.assertIn("not recorded", md)
        self.assertNotIn("## Cost per task", md)
        # generations fall back to tasks x samples, so a CI still renders
        self.assertNotIn("(CI n/a)", md)

    def test_caveats_quote_intervals_not_a_fixed_rule(self):
        md = report.build([_agentic_run("a.json", "a", 0.75, 0.4),
                           _agentic_run("b.json", "b", 0.5, 1.0)], title="t")
        caveats = md.split("## Caveats")[1]
        self.assertIn("95% Wilson interval", caveats)
        self.assertIn("Newcombe", caveats)
        self.assertNotIn("8 points", md)
        self.assertNotIn("noise floor", md)

    def test_pooled_cost_is_weighted_by_reporting_generations(self):
        a = _agentic_run("a.json", "a", 0.5, 1.0, gens=3)
        b = _agentic_run("a.1.json", "a", 0.5, 1.0, gens=3)
        for r in (a, b):
            r["summary"]["suite_hash"] = "h" * 64
        b["summary"]["cost_by_task"]["t1"].update(tokens_reported=1, input_tokens=1000.0,
                                                  seconds=2.5)
        s = report.pool(report.group_runs([a, b])[0])["summary"]
        t1 = s["cost_by_task"]["t1"]
        self.assertEqual(t1["samples"], 6)
        self.assertEqual(t1["tokens_reported"], 4)
        self.assertAlmostEqual(t1["input_tokens"], (5000 * 3 + 1000) / 4)
        self.assertAlmostEqual(t1["seconds"], 7.5)
        self.assertEqual(s["cost"]["generations"], 6)
        self.assertEqual(s["efficiency"], 1.0)


class TestPoolMixedInput(unittest.TestCase):
    def test_pooled_input_is_none_when_a_member_never_recorded_it(self):
        a = _agentic_run("a.json", "a", 0.5, 1.0, gens=3)
        b = _agentic_run("a.1.json", "a", 0.5, 1.0, gens=3)
        for r in (a, b):
            r["summary"]["suite_hash"] = "h" * 64
        b["summary"]["cost"]["input_tokens"] = None
        s = report.pool(report.group_runs([a, b])[0])["summary"]
        self.assertIsNone(s["cost"]["input_tokens"])
        self.assertAlmostEqual(s["cost"]["output_tokens"], 300.0)


class TestCli(unittest.TestCase):
    def _samples(self, *argv):
        return cli._build_parser().parse_args(list(argv)).samples

    def test_harness_and_setup_runs_default_to_three_samples(self):
        self.assertEqual(cli.HARNESS_SAMPLES, 3)
        self.assertEqual(self._samples("harness", "run"), 3)
        self.assertEqual(self._samples("setup", "run"), 3)
        self.assertEqual(self._samples("harness", "run", "--samples", "5"), 5)

    def test_other_commands_keep_their_defaults(self):
        self.assertEqual(self._samples("run"), 2)

    def test_headline_lines(self):
        s = _agentic_run("a.json", "a", 0.75, 0.4)["summary"]
        lines = "\n".join(cli._headline_lines(s))
        self.assertIn("solve rate             75.0 %  (95% CI", lines)
        self.assertIn("n=24", lines)
        self.assertIn("efficiency             40.0 %", lines)
        self.assertIn("5,000 in / 300 out", lines)
        self.assertIn("time / task            12.5 s", lines)
        s["cost"] = dict(generations=24, tokens_reported=0, input_tokens=None,
                         output_tokens=None, seconds=1.0)
        self.assertIn("not reported", "\n".join(cli._headline_lines(s)))
        s["cost"] = dict(generations=24, tokens_reported=24, input_tokens=None,
                         output_tokens=50.0, seconds=1.0)
        self.assertIn("— in / 50 out", "\n".join(cli._headline_lines(s)))


if __name__ == "__main__":
    unittest.main()

"""System One suite: exact-match scoring, data lint, and the summary contract.

The s1 runner turns every task's questions into one scored unit each: `passed`
is a normalised exact match against the question's answer key (the option
letter counts the same as the option text; verbose, reasoned or empty replies
fail), and the summary is the shared one — accuracy arrives as
solve_rate/pass_at_1, speed as tokens, tok/s and TTFT. `bench validate` for
this kind is a data lint: each answer must be one of its own options.

Nothing here touches a real endpoint: `runner._client` and `runner.generate`
are stubbed throughout.
"""
import unittest
from unittest import mock

from benchkit import fingerprint, runner, s1_runner
from benchkit.suites import SUITES

TASKS = [
    dict(id="triage", difficulty="easy",
         state="Email: 'You won a prize! Send a $50 fee to claim it.'",
         questions=[
             dict(question="Is it spam?", options=["yes", "no"], answer="yes"),
             dict(question="Deliver to inbox?",
                  options=["yes", "no"], answer="no"),
         ]),
    dict(id="code_check", difficulty="hard",
         state="Header: 'REF: ZX-4821-Q'",
         questions=[
             dict(question="What is the reference code?", answer="ZX-4821-Q"),
         ]),
]


def _cfg(samples=1):
    return runner.Config(samples=samples, concurrency=1)


class TestNorm(unittest.TestCase):
    def test_case_whitespace_punctuation(self):
        self.assertEqual(s1_runner._norm("  Yes.\n"), "yes")
        self.assertEqual(s1_runner._norm('"B"'), "b")
        self.assertEqual(s1_runner._norm("Multi   WORD  ticket"), "multi word ticket")
        self.assertEqual(s1_runner._norm("(yes)"), "yes")

    def test_empty(self):
        self.assertEqual(s1_runner._norm(None), "")
        self.assertEqual(s1_runner._norm("   "), "")


class TestScore(unittest.TestCase):
    Q = dict(question="Is it spam?", options=["yes", "no"], answer="yes")

    def _ok(self, text):
        return s1_runner._score(self.Q, text)[0]

    def test_accepted_forms(self):
        for reply in ("yes", "Yes", "YES!", "a", "A", "a) yes", "A. yes",
                      "a yes", ' "Yes" '):
            with self.subTest(reply=reply):
                self.assertTrue(self._ok(reply))

    def test_rejected_forms(self):
        for reply in ("no", "b", "b) yes", "The answer is A",
                      "yes, definitely", "", "   ", None,
                      "sorry, i can't tell"):
            with self.subTest(reply=reply):
                self.assertFalse(self._ok(reply))

    def test_wrong_letter_with_right_text_fails(self):
        # "b) yes" asserts option B (no) while writing "yes": contradictory
        # replies are failures, whichever half a reader believes
        self.assertFalse(self._ok("b) yes"))

    def test_open_question_matches_only_the_answer(self):
        q = dict(question="What is the code?", answer="ZX-4821-Q")
        self.assertTrue(s1_runner._score(q, "ZX-4821-Q")[0])
        self.assertTrue(s1_runner._score(q, "zx-4821-q")[0])
        self.assertFalse(s1_runner._score(q, "ZX9")[0])
        self.assertFalse(s1_runner._score(q, "a")[0])


class TestLint(unittest.TestCase):
    def _task(self, **kw):
        t = dict(id="x", difficulty="easy", state="s",
                 questions=[dict(question="q?", options=["a", "b"], answer="a")])
        t.update(kw)
        return t

    def test_shipped_suite_passes(self):
        self.assertEqual(s1_runner.validate(SUITES["system1"]), 0)

    def test_answer_must_be_an_option(self):
        bad = [self._task(questions=[dict(question="q?", options=["a", "b"],
                                         answer="c")])]
        self.assertEqual(s1_runner.validate(bad), 1)

    def test_answer_membership_is_normalised(self):
        ok = [self._task(questions=[dict(question="q?", options=["Yes", "No"],
                                        answer="yes")])]
        self.assertEqual(s1_runner.validate(ok), 0)

    def test_open_question_needs_no_options(self):
        ok = [self._task(questions=[dict(question="q?", answer="42")])]
        self.assertEqual(s1_runner.validate(ok), 0)
        bad = [self._task(questions=[dict(question="q?", answer="")])]
        self.assertEqual(s1_runner.validate(bad), 1)

    def test_missing_state_fails(self):
        self.assertEqual(s1_runner.validate([self._task(state="")]), 1)

    def test_empty_questions_fail(self):
        self.assertEqual(s1_runner.validate([self._task(questions=[])]), 1)

    def test_bad_difficulty_fails(self):
        self.assertEqual(s1_runner.validate([self._task(difficulty="trivial")]), 1)

    def test_duplicate_options_fail(self):
        bad = [self._task(questions=[dict(question="q?", options=["Yes", "yes"],
                                         answer="Yes")])]
        self.assertEqual(s1_runner.validate(bad), 1)

    def test_duplicate_ids_fail(self):
        two = [self._task(), self._task()]
        self.assertEqual(s1_runner.validate(two), 2)

    def test_malformed_entries_lint_cleanly(self):
        # malformed data must be reported as lint problems naming the task,
        # never as a traceback that kills the whole validate pass
        numeric = [self._task(id="num", questions=[
            dict(question="q?", options=["7", "8"], answer=7)])]
        self.assertEqual(s1_runner.validate(numeric), 1)
        non_dict_q = [self._task(id="qstr", questions=["q?"])]
        self.assertEqual(s1_runner.validate(non_dict_q), 1)
        self.assertEqual(s1_runner.validate(["not a task"]), 1)


class TestRun(unittest.TestCase):
    """The stubbed-endpoint contract: same summary shape as the other runners."""

    def setUp(self):
        patcher = mock.patch.object(runner, "_client", return_value=mock.Mock())
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, answers, tasks=TASKS, samples=1, **kw):
        def fake(client, cfg, task, idx, system=None):
            return dict(task=task["id"], difficulty=task["difficulty"],
                        sample=idx, text=answers.get(task["id"], ""),
                        ttft=0.01, elapsed=0.02, prompt_tokens=10,
                        completion_tokens=2, tok_s=100.0)
        with mock.patch.object(runner, "generate", side_effect=fake):
            return s1_runner.run(tasks, _cfg(samples), **kw)

    def test_summary_contract(self):
        summary, results = self._run({"triage/q1": "yes", "triage/q2": "B",
                                      "code_check/q1": "ZX-4821-Q"})
        self.assertEqual(summary["kind"], "s1")
        self.assertEqual(summary["tasks"], 3)          # scored units = questions
        self.assertEqual(summary["generations"], 3)
        self.assertEqual(summary["pass_at_1"], 1.0)
        self.assertEqual(summary["solve_rate"], summary["pass_at_1"])
        self.assertIsNotNone(summary["solve_rate_ci"])
        self.assertEqual(set(summary["by_task"]),
                         {"triage/q1", "triage/q2", "code_check/q1"})
        self.assertEqual(summary["by_difficulty"]["easy"], 1.0)
        self.assertEqual(summary["by_difficulty"]["hard"], 1.0)
        self.assertAlmostEqual(summary["mean_ttft"], 0.01)
        self.assertEqual(summary["cost"]["input_tokens"], 10)
        self.assertEqual(summary["schema_version"], fingerprint.SCHEMA_VERSION)
        # the hash covers the original tasks (state + questions + answers),
        # not the flattened per-question items
        self.assertEqual(summary["suite_hash"], fingerprint.suite_hash(TASKS))
        for r in results:
            self.assertTrue(r["passed"])
            self.assertIn("given", r)

    def test_wrong_answers_drop_accuracy_per_question(self):
        summary, results = self._run({"triage/q1": "yes",
                                      "triage/q2": "yes",   # expected no
                                      "code_check/q1": "ZX9"})
        self.assertAlmostEqual(summary["pass_at_1"], 1 / 3)
        self.assertEqual(summary["by_task"]["triage/q1"], 1.0)
        self.assertEqual(summary["by_task"]["triage/q2"], 0.0)
        self.assertEqual(summary["by_task"]["code_check/q1"], 0.0)
        r = next(r for r in results if r["task"] == "triage/q2")
        self.assertFalse(r["passed"])
        self.assertEqual(r["given"], "yes")
        self.assertIn("expected 'no'", r["error"])

    def test_verbose_and_empty_replies_fail(self):
        summary, _ = self._run({"triage/q1": "The answer is A.",
                                "triage/q2": "", "code_check/q1": "ZX-4821-Q"})
        self.assertAlmostEqual(summary["pass_at_1"], 1 / 3)

    def test_every_sample_scored(self):
        summary, results = self._run({"triage/q1": "a", "triage/q2": "b",
                                      "code_check/q1": "ZX-4821-Q"}, samples=2)
        self.assertEqual(summary["generations"], 6)
        self.assertEqual(len(results), 6)
        self.assertEqual(summary["pass_all_samples"], 1.0)

    def test_generation_failure_fails_one_question_not_the_suite(self):
        def fake(client, cfg, task, idx, system=None):
            if task["id"] == "triage/q1":
                raise RuntimeError("endpoint down")
            return dict(task=task["id"], difficulty=task["difficulty"],
                        sample=idx, text="no", ttft=None, elapsed=0.01,
                        prompt_tokens=None, completion_tokens=1, tok_s=None)
        with mock.patch.object(runner, "generate", side_effect=fake):
            summary, results = s1_runner.run(TASKS[:1], _cfg())
        self.assertEqual(len(results), 2)
        failed = next(r for r in results if r["task"] == "triage/q1")
        self.assertFalse(failed["passed"])
        self.assertTrue(failed["error"].startswith("generation failed"))
        self.assertEqual(summary["errored"], 1)
        self.assertEqual(summary["pass_at_1"], 0.5)

    def test_sdk_retries_do_not_multiply_gateway_retries(self):
        client = mock.Mock()
        with mock.patch.object(runner, "_client", return_value=client), \
                mock.patch.object(runner, "generate", side_effect=RuntimeError("quota")):
            s1_runner.run(TASKS[:1], _cfg())
        client.with_options.assert_called_once_with(max_retries=0)

    def test_uses_the_decision_system_prompt(self):
        seen = {}

        def fake(client, cfg, task, idx, system=None):
            seen["system"] = system
            return dict(task=task["id"], difficulty=task["difficulty"],
                        sample=idx, text="yes", ttft=0.01, elapsed=0.02,
                        prompt_tokens=10, completion_tokens=1, tok_s=50.0)
        with mock.patch.object(runner, "generate", side_effect=fake):
            s1_runner.run(TASKS[:1], _cfg())
        self.assertIs(seen["system"], s1_runner.SYSTEM)


class TestReport(unittest.TestCase):
    """The s1 summary renders as accuracy through the non-agentic branch."""

    def _run(self, label="s1 candidate", kind="s1"):
        return dict(summary=dict(
            kind=kind, pass_at_1=0.9, generations=49, tasks=49,
            suite_hash="h" * 64,
            config=dict(label=label, model="m", thinking=False, max_tokens=32,
                        samples=1, concurrency=4, base_url="http://h/v1"),
            by_task={"triage/q1": 1.0},
            by_difficulty={"easy": 1.0, "medium": 0.8, "hard": 0.5},
            wall_seconds=5.0, mean_completion_tokens=3, truncated=0, errored=0,
            cost=dict(generations=49, tokens_reported=49, input_tokens=500.0,
                      output_tokens=3.0, seconds=0.1),
            cost_by_task={"triage/q1": dict(samples=1, tokens_reported=1,
                                            input_tokens=500.0,
                                            output_tokens=3.0, seconds=0.1)}),
            results=[], _path="s.json")

    def test_accuracy_labels_everywhere(self):
        from benchkit import report
        # two runs, distinct labels: not pooled, so the scatter renders too
        md = report.build([self._run("candidate a"), self._run("candidate b")],
                          title="s1")
        self.assertIn("| Run | Accuracy (95% CI) |", md)
        self.assertIn("| Run | Accuracy | easy | medium | hard |", md)
        self.assertIn("Accuracy (%)", md)
        self.assertIn("accuracy over exact-match answers", md)
        self.assertIn("Accuracy vs tokens per task", md)
        self.assertNotIn("pass@1", md)

    def test_s1_caveats(self):
        from benchkit import report
        md = report.build([self._run()], title="s1")
        caveats = md.split("## Caveats")[1]
        self.assertIn("exact match", caveats)
        self.assertIn("deliberating", caveats)
        self.assertNotIn("Python code generation", caveats)

    def test_codegen_runs_keep_pass1_label(self):
        from benchkit import report
        md = report.build([self._run(label="gen", kind="codegen")], title="c")
        self.assertIn("| Run | pass@1 (95% CI) |", md)
        self.assertIn("pass@1 (%)", md)


if __name__ == "__main__":
    unittest.main()

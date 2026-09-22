"""suite_hash + schema_version on every result summary (issue #88).

Re-runs are grouped by `suite_hash`, so it must be deterministic across
processes (no `hash()`), change whenever what is scored changes, and be stamped
by every runner that produces a summary. Readers must accept old files that
predate both fields.
"""
import copy
import os
import subprocess
import sys
import unittest
from unittest import mock

from benchkit import fingerprint, runner
from benchkit.agentic import loop
from benchkit.harness import runner as hrunner
from benchkit.suites import SUITES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg():
    return runner.Config(samples=1, concurrency=1)


class TestSuiteHash(unittest.TestCase):
    def test_hex_sha256(self):
        h = fingerprint.suite_hash(SUITES["core16"])
        self.assertEqual(len(h), 64)
        int(h, 16)

    def test_stable_across_processes_and_hash_seeds(self):
        code = ("from benchkit.suites import SUITES;"
                "from benchkit.fingerprint import suite_hash;"
                "print(suite_hash(SUITES['all']), suite_hash(SUITES['agentic-all']))")
        outs = set()
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.add(subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                                    capture_output=True, text=True, check=True).stdout)
        self.assertEqual(len(outs), 1)
        here = f"{fingerprint.suite_hash(SUITES['all'])} " \
               f"{fingerprint.suite_hash(SUITES['agentic-all'])}\n"
        self.assertEqual(outs.pop(), here)

    def test_task_order_does_not_matter(self):
        tasks = SUITES["core16"]
        self.assertEqual(fingerprint.suite_hash(tasks),
                         fingerprint.suite_hash(list(reversed(tasks))))

    def test_different_subsets_differ(self):
        tasks = SUITES["core16"]
        self.assertNotEqual(fingerprint.suite_hash(tasks),
                            fingerprint.suite_hash(tasks[:-1]))
        self.assertNotEqual(fingerprint.suite_hash(SUITES["core16"]),
                            fingerprint.suite_hash(SUITES["hard12"]))

    def test_editing_a_task_changes_the_hash(self):
        base = fingerprint.suite_hash(SUITES["core16"])
        for field in ("prompt", "tests", "difficulty"):
            tasks = copy.deepcopy(SUITES["core16"])
            tasks[0][field] = tasks[0][field] + "x"
            self.assertNotEqual(fingerprint.suite_hash(tasks), base, field)

    def test_editing_agentic_files_changes_the_hash(self):
        tasks = [dict(t) for t in SUITES["agentic"]]
        base = fingerprint.suite_hash(tasks)
        files = dict(tasks[0]["files"])
        k = next(iter(files))
        files[k] += "\n# changed\n"
        tasks[0]["files"] = files
        self.assertNotEqual(fingerprint.suite_hash(tasks), base)

    def test_par_changes_the_hash(self):
        tasks = SUITES["agentic"]
        base = fingerprint.suite_hash(tasks)
        real = loop.par_calls
        with mock.patch.object(loop, "par_calls",
                               side_effect=lambda t: (real(t) or 0) + 1):
            self.assertNotEqual(fingerprint.suite_hash(tasks), base)

    def test_task_module_source_is_covered(self):
        tasks = SUITES["agentic"]
        base = fingerprint.suite_hash(tasks)
        with mock.patch.object(fingerprint, "_module_text",
                               side_effect=lambda m: "edited " + m):
            self.assertNotEqual(fingerprint.suite_hash(tasks), base)


class TestSchemaVersion(unittest.TestCase):
    def test_stamp_adds_both_fields(self):
        s = fingerprint.stamp({"pass_at_1": 0.5}, SUITES["core16"])
        self.assertEqual(s["schema_version"], fingerprint.SCHEMA_VERSION)
        self.assertEqual(s["suite_hash"], fingerprint.suite_hash(SUITES["core16"]))
        self.assertEqual(s["pass_at_1"], 0.5)

    def test_old_summary_without_fields_reads_as_version_0(self):
        self.assertEqual(fingerprint.schema_version({"pass_at_1": 1.0}), 0)
        self.assertEqual(fingerprint.schema_version(None), 0)
        self.assertEqual(fingerprint.schema_version({"schema_version": 1}), 1)


class TestEveryRunnerStamps(unittest.TestCase):
    """The three producers of summaries: one-shot, agentic loop, harness."""

    def _check(self, summary, tasks):
        self.assertEqual(summary["schema_version"], fingerprint.SCHEMA_VERSION)
        self.assertEqual(summary["suite_hash"], fingerprint.suite_hash(tasks))

    def test_one_shot_runner(self):
        tasks = SUITES["core16"][:2]
        with mock.patch.object(runner, "_client"), \
                mock.patch.object(runner, "generate", side_effect=RuntimeError("down")):
            summary, results = runner.run(tasks, _cfg())
        self.assertEqual(len(results), 2)
        self._check(summary, tasks)

    def test_agentic_loop(self):
        tasks = SUITES["agentic"][:2]
        fake = lambda client, cfg, task, i, max_turns: dict(  # noqa: E731
            task=task["id"], difficulty=task["difficulty"], sample=i, passed=True)
        with mock.patch.object(runner, "_client"), \
                mock.patch.object(loop, "run_task", side_effect=fake), \
                mock.patch.object(loop, "summarize", return_value={}):
            summary, _ = loop.run(tasks, _cfg())
        self._check(summary, tasks)

    def test_harness_runner(self):
        tasks = SUITES["agentic"][:2]
        h = mock.Mock()
        h.available.return_value = (True, "")
        h.describe.return_value = {"name": "fake"}
        fake = lambda harness, task, i, **kw: dict(  # noqa: E731
            task=task["id"], difficulty=task["difficulty"], sample=i, passed=True)
        with mock.patch.object(hrunner, "run_task", side_effect=fake), \
                mock.patch.object(hrunner.agentic_loop, "summarize", return_value={}):
            summary, _ = hrunner.run(h, tasks, _cfg())
        self._check(summary, tasks)
        self.assertEqual(summary["harness"], {"name": "fake"})


if __name__ == "__main__":
    unittest.main()

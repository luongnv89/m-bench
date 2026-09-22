"""Scoring cannot be gamed by editing or reading the tests (issues #83, #84).

#83: agentic tasks are scored against the tests they shipped with, so rewriting
tests.py -- to `print("OK")`, or an `assert True` -- does not pass a task.

#84: agent subprocesses (every harness adapter via `stream_events`, and the
built-in loop's `run_python`) run in a sandbox that cannot read the hidden
tests, the checkout they live in, or the directory they are scored in.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchkit import sandbox
from benchkit.agentic import tasks as easy
from benchkit.agentic import tasks_hard as hard
from benchkit.agentic.env import Workspace
from benchkit.harness.stream import stream_events

TASKS = {t["id"]: t for t in easy.TASKS + hard.TASKS}


def _solved_ws(task_id):
    """A workspace in the state the task's oracle leaves it: a genuine solve."""
    ws = Workspace(TASKS[task_id]["files"])
    TASKS[task_id]["oracle"](ws)
    return ws


def _score(ws, task_id):
    return TASKS[task_id]["check"](ws)


class TestPrintOkReplacementFails(unittest.TestCase):
    """Replacing tests.py with print("OK") never passes (#83 criterion 1)."""

    NAMED = ("add_missing_function", "find_bug_by_search", "implement_from_spec",
             "decoy_bug", "verify_no_change_needed")

    def test_named_tasks_fail(self):
        for tid in self.NAMED:
            with self.subTest(task=tid):
                ws = Workspace(TASKS[tid]["files"])
                ws.files["tests.py"] = 'print("OK")\n'
                solved, _detail = _score(ws, tid)
                self.assertFalse(solved, f"{tid} passed with tests.py = print('OK')")

    def test_every_visible_test_task_fails(self):
        # Beyond the named five: no task scored on tests.py accepts the swap.
        for tid, t in TASKS.items():
            if "tests.py" not in t["files"]:
                continue
            with self.subTest(task=tid):
                ws = Workspace(t["files"])
                ws.files["tests.py"] = 'print("OK")\n'
                self.assertFalse(_score(ws, tid)[0])

    def test_genuine_solutions_still_pass(self):
        for tid in self.NAMED + ("fix_divide_bug", "wrong_test_not_code"):
            with self.subTest(task=tid):
                solved, detail = _score(_solved_ws(tid), tid)
                self.assertTrue(solved, detail)


class TestAssertTrueEditsFail(unittest.TestCase):
    """`assert True` edits fail fix_divide_bug and wrong_test_not_code (#83 c.2)."""

    def test_fix_divide_bug_assert_true(self):
        ws = Workspace(TASKS["fix_divide_bug"]["files"])
        # keeps exactly 4 asserts, which the old count-based check accepted
        ws.files["tests.py"] = ws.files["tests.py"].replace(
            'assert divide(1, 0) is None, "dividing by zero must return None, not raise"',
            "assert True")
        self.assertEqual(ws.files["tests.py"].count("assert"), 4)
        solved, detail = _score(ws, "fix_divide_bug")
        self.assertFalse(solved)
        self.assertIn("tests.py was modified", detail)

    def test_fix_divide_bug_assert_true_even_with_code_fixed(self):
        ws = _solved_ws("fix_divide_bug")
        ws.files["tests.py"] = ws.files["tests.py"].replace(
            "assert divide(9, 3) == 3", "assert True")
        self.assertFalse(_score(ws, "fix_divide_bug")[0])

    def _wrong_test_ws(self, old, new):
        ws = Workspace(TASKS["wrong_test_not_code"]["files"])
        self.assertIn(old, ws.files["tests.py"])
        ws.files["tests.py"] = ws.files["tests.py"].replace(old, new)
        return ws

    WRONG = "assert business_days(D(2024, 1, 1), D(2024, 1, 8)) == 6"

    def test_wrong_test_not_code_assert_true(self):
        ws = self._wrong_test_ws(self.WRONG, "assert True")
        self.assertLessEqual(ws.changed_lines("tests.py"), 4)
        solved, detail = _score(ws, "wrong_test_not_code")
        self.assertFalse(solved)
        self.assertIn("no longer checks", detail)

    def test_wrong_test_not_code_deleted_assert(self):
        ws = self._wrong_test_ws(self.WRONG + "\n", "")
        self.assertFalse(_score(ws, "wrong_test_not_code")[0])

    def test_wrong_test_not_code_weakening_another_assert(self):
        ws = self._wrong_test_ws(self.WRONG, self.WRONG.replace("== 6", "== 5"))
        ws.files["tests.py"] = ws.files["tests.py"].replace(
            "assert business_days(D(2024, 1, 2), D(2024, 1, 3)) == 1", "assert True")
        self.assertFalse(_score(ws, "wrong_test_not_code")[0])

    def test_wrong_test_not_code_inequality_weakenings_fail(self):
        for weak in ("!= 6", "<= 5", ">= 5", "< 6"):
            with self.subTest(edit=weak):
                ws = self._wrong_test_ws(self.WRONG, self.WRONG.replace("== 6", weak))
                self.assertFalse(_score(ws, "wrong_test_not_code")[0])

    def test_mutant_runs_add_no_detectable_files(self):
        # tests.py must not be able to tell a mutant run from a real one
        ws = self._wrong_test_ws(self.WRONG, self.WRONG.replace("== 6", "== 5"))
        seen = []
        real_check = ws.check

        def spy(path, extra_files=None):
            seen.append(set(extra_files or {}))
            return real_check(path, extra_files)

        ws.check = spy
        self.assertTrue(_score(ws, "wrong_test_not_code")[0])
        self.assertEqual(len(seen), 9)          # own run + 4 cases x (+1, -1)
        self.assertTrue(all(keys <= {"business_days.py"} for keys in seen))

    def test_wrong_test_not_code_equivalent_fix_passes(self):
        # A differently written but equivalent correction is still accepted.
        ws = self._wrong_test_ws(
            self.WRONG, "n = business_days(D(2024, 1, 1), D(2024, 1, 8))\nassert 5 == n")
        solved, detail = _score(ws, "wrong_test_not_code")
        self.assertTrue(solved, detail)

    def test_wrong_test_not_code_still_fails_unfixed(self):
        ws = Workspace(TASKS["wrong_test_not_code"]["files"])
        self.assertFalse(_score(ws, "wrong_test_not_code")[0])


class TestSandboxConfiguration(unittest.TestCase):
    def test_protected_paths_cover_package_repo_and_scoring_root(self):
        paths = sandbox.protected_paths()
        pkg = os.path.realpath(os.path.dirname(sandbox.__file__))
        tasks_hard_file = os.path.realpath(hard.__file__)
        for target in (pkg, tasks_hard_file, sandbox.scoring_root()):
            self.assertTrue(any(target == p or target.startswith(p + os.sep)
                                for p in paths), f"{target} not protected")

    def test_scoring_root_is_not_an_agent_workspace_parent(self):
        tmp = os.path.realpath(tempfile.gettempdir())
        self.assertNotEqual(sandbox.scoring_root(), tmp)
        self.assertTrue(sandbox.scoring_root().startswith(tmp + os.sep))

    def test_check_scores_inside_the_scoring_root(self):
        ws = Workspace({"where.py": "import os; print(os.path.realpath(os.getcwd()))\n"})
        code, out = ws.check("where.py")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.strip().startswith(sandbox.scoring_root() + os.sep), out)

    def test_disabled_leaves_argv_alone(self):
        with mock.patch.dict(os.environ, {"BENCH_SANDBOX": "0"}):
            self.assertEqual(sandbox.mechanism(), "disabled")
            self.assertEqual(sandbox.wrap(["x", "y"]), ["x", "y"])
            self.assertFalse(sandbox.describe()["hidden_tests_protected"])

    def test_no_mechanism_is_reported_not_hidden(self):
        with mock.patch.object(sandbox.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {"BENCH_SANDBOX": ""}):
            self.assertEqual(sandbox.mechanism(), "none")
            self.assertEqual(sandbox.wrap(["x"]), ["x"])
            d = sandbox.describe()
            self.assertEqual(d["mechanism"], "none")
            self.assertFalse(d["hidden_tests_protected"])

    def _fake_git(self, root, common, worktrees, rc=0):
        porcelain = "".join(f"worktree {w}\nHEAD 0\ndetached\n\n" for w in worktrees)

        def run(argv, **kw):
            if "--git-common-dir" in argv:
                return mock.Mock(returncode=0, stdout=common + "\n")
            if argv[3:5] == ["worktree", "list"]:
                return mock.Mock(returncode=rc, stdout=porcelain)
            raise AssertionError(argv)
        return mock.patch.object(sandbox.subprocess, "run", side_effect=run)

    def test_worktree_denies_main_checkout_and_siblings(self):
        with tempfile.TemporaryDirectory() as t:
            t = os.path.realpath(t)
            main, wt, sib = (os.path.join(t, n) for n in ("main", "wt", "sib"))
            with mock.patch.object(sandbox, "_repo_root", return_value=wt), \
                    self._fake_git(wt, os.path.join(main, ".git"), [main, wt, sib]):
                paths = sandbox.protected_paths()
            for target in (main, wt, sib, os.path.join(main, "benchkit", "agentic")):
                self.assertTrue(any(target == p or target.startswith(p + os.sep)
                                    for p in paths), f"{target} not protected")

    def test_worktree_main_checkout_denied_even_if_listing_fails(self):
        with tempfile.TemporaryDirectory() as t:
            t = os.path.realpath(t)
            main, wt = os.path.join(t, "main"), os.path.join(t, "wt")
            with mock.patch.object(sandbox, "_repo_root", return_value=wt), \
                    self._fake_git(wt, os.path.join(main, ".git"), [], rc=128):
                paths = sandbox.protected_paths()
            self.assertIn(main, paths)
            self.assertIn(wt, paths)

    def test_worktree_listing_errors_are_not_fatal(self):
        with mock.patch.object(sandbox.subprocess, "run", side_effect=OSError("no git")):
            self.assertEqual(sandbox._git_worktrees("/nowhere"), [])
        with mock.patch.object(sandbox.subprocess, "run",
                               side_effect=sandbox.subprocess.TimeoutExpired("git", 10)):
            self.assertEqual(sandbox._git_worktrees("/nowhere"), [])

    def test_warning_names_the_gap(self):
        import io
        buf = io.StringIO()
        with mock.patch.object(sandbox, "_warned", False), \
                mock.patch.dict(os.environ, {"BENCH_SANDBOX": "0"}):
            sandbox.warn_if_unprotected(buf)
        self.assertIn("hidden tests", buf.getvalue())


_HAS_SANDBOX = (sys.platform == "darwin" and sandbox.mechanism() == "sandbox-exec")

# a script an agent could run: print the hidden tests it can reach, if any
_SNOOP = '''import glob, os, sys
leaked = []
for path in sys.argv[1:]:
    for p in [path] + glob.glob(os.path.join(path, "**", "*"), recursive=True):
        try:
            with open(p) as f:
                if "0033123456789" in f.read():
                    leaked.append(p)
        except OSError:
            pass
print("LEAKED" if leaked else "SAFE", leaked[:3])
'''


@unittest.skipUnless(_HAS_SANDBOX, "no sandbox mechanism on this platform")
class TestHiddenTestsUnreadable(unittest.TestCase):
    """An agent inside a task workspace cannot read hidden tests (#84)."""

    def setUp(self):
        self.targets = [os.path.realpath(hard.__file__), sandbox.scoring_root()]
        root = sandbox._repo_root()
        if root:
            self.targets += [os.path.join(root, "results"), os.path.join(root, ".git")]

    def test_unsandboxed_snoop_would_leak(self):
        # guards the test itself: the snooper does find the tests when allowed
        import subprocess
        r = subprocess.run([sys.executable, "-c", _SNOOP, os.path.realpath(hard.__file__)],
                           capture_output=True, text=True)
        self.assertIn("LEAKED", r.stdout)

    def test_harness_agent_cannot_read_hidden_tests(self):
        # stream_events is where every adapter (pi, opencode, claude-code,
        # devin) launches its agent.
        work = tempfile.mkdtemp(prefix="benchkit-test-agent-")
        res, rc, err = stream_events(
            [sys.executable, "-c", _SNOOP, *self.targets], cwd=work,
            env=dict(os.environ), handler=lambda ev, r, s: None, timeout=60)
        lines = res.raw_log
        self.assertEqual(rc, 0, err)
        self.assertIn("SAFE", lines)
        self.assertNotIn("LEAKED", lines)

    def test_harness_agent_cannot_write_into_the_checkout(self):
        root = sandbox._repo_root()
        if not root:
            self.skipTest("not a checkout")
        target = os.path.join(root, "results", ".sandbox-write-probe")
        work = tempfile.mkdtemp(prefix="benchkit-test-agent-")
        stream_events([sys.executable, "-c", f"open({target!r}, 'w').write('x')"],
                      cwd=work, env=dict(os.environ),
                      handler=lambda ev, r, s: None, timeout=60)
        self.assertFalse(os.path.exists(target))

    def test_run_python_cannot_read_hidden_tests(self):
        args = ", ".join(repr(t) for t in self.targets)
        ws = Workspace({"snoop.py": "import sys\nsys.argv[1:] = [%s]\n%s" % (args, _SNOOP)})
        out = ws.run_python("snoop.py")
        self.assertIn("SAFE", out)
        self.assertNotIn("LEAKED", out)

    def test_python_still_runs_in_the_sandbox(self):
        ws = Workspace({"hello.py": "print('hello from the sandbox')\n"})
        self.assertIn("hello from the sandbox", ws.run_python("hello.py"))

    def test_scoring_still_reads_hidden_tests(self):
        # check() is not sandboxed: the oracle solution passes its hidden tests
        solved, detail = _score(_solved_ws("hidden_spec_compliance"),
                                "hidden_spec_compliance")
        self.assertTrue(solved, detail)


if __name__ == "__main__":
    unittest.main()

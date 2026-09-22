"""Keep what scores a run out of reach of the agent being scored (issue #84).

A harness agent gets a real shell on this machine, and the built-in loop's
`run_python` executes whatever the model writes. Both run as the same user as
benchkit, so file permissions protect nothing: an agent could simply read the
hidden tests out of `benchkit/agentic/tasks_hard.py`, out of `results/` (whose
traces quote them), or out of the git history.

This module wraps every agent-side subprocess in an OS sandbox that denies read
and write access to:

- the installed ``benchkit`` package (the hidden tests live in its source);
- the repository checkout it was loaded from, if any (``.git`` history,
  ``results/``, docs), and when that checkout is a git worktree, the main
  checkout and every sibling worktree too (each holds its own copy of the
  hidden tests);
- the scoring directory where `Workspace.check` materialises hidden tests.

Python virtualenvs inside the checkout stay readable, so an agent whose
``python3`` resolves to the repo's ``.venv`` can still run code.

Mechanisms: ``sandbox-exec`` on macOS. Where none is available (Linux today)
the command runs unwrapped and `describe()` reports ``"none"`` so the result
file says the hidden tests were *not* protected, rather than implying they were.
``BENCH_SANDBOX=0`` turns wrapping off explicitly (recorded as ``"disabled"``).
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

_PKG_DIR = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))


def _repo_root():
    """The checkout benchkit was loaded from, or None for a plain install."""
    parent = os.path.dirname(_PKG_DIR)
    if os.path.isfile(os.path.join(parent, "pyproject.toml")):
        return parent
    return None


def _git_common_dir(root):
    """The shared .git of a worktree checkout: it holds the whole history."""
    try:
        out = subprocess.run(["git", "-C", root, "rev-parse", "--git-common-dir"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    d = out.stdout.strip()
    if out.returncode != 0 or not d:
        return None
    return os.path.realpath(os.path.join(root, d))


def _git_worktrees(root):
    """Every working tree of the repository *root* belongs to (main included)."""
    try:
        out = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [os.path.realpath(line[len("worktree "):])
            for line in out.stdout.splitlines()
            if line.startswith("worktree ") and line[len("worktree "):].strip()]


def scoring_root():
    """The directory `Workspace.check` scores in: protected, never an agent's cwd.

    A dedicated subdirectory of the temp dir, so a concurrently running agent
    cannot find another task's hidden tests while they are being scored. Agent
    workspaces are siblings of it (plain `mkdtemp()`), never children.
    """
    uid = getattr(os, "getuid", lambda: "user")()
    root = os.path.join(tempfile.gettempdir(), f"benchkit-scoring-{uid}")
    os.makedirs(root, mode=0o700, exist_ok=True)
    return os.path.realpath(root)


def protected_paths():
    """Directories an agent may neither read nor write."""
    paths = [_PKG_DIR, scoring_root()]
    root = _repo_root()
    if root:
        paths.append(root)
        common = _git_common_dir(root)
        if common:
            paths.append(common)
            # From a worktree the common dir is <main checkout>/.git: the main
            # checkout's working tree holds the hidden tests and results/ too.
            if (os.path.basename(common) == ".git"
                    and common != os.path.realpath(os.path.join(root, ".git"))):
                paths.append(os.path.dirname(common))
        paths += _git_worktrees(root)
    # Drop any path already covered by another one.
    paths = sorted(set(paths))
    return [p for p in paths
            if not any(p != q and p.startswith(q + os.sep) for q in paths)]


def readable_exceptions(protected=None):
    """Directories inside a protected path that must stay readable.

    Every virtualenv (a dir holding ``pyvenv.cfg``) at the top of the checkout,
    plus the running interpreter's prefixes when they live under a protected
    path — otherwise ``python3`` itself would fail to start in the sandbox.
    """
    protected = protected_paths() if protected is None else protected
    out = set()
    root = _repo_root()
    if root:
        try:
            for name in os.listdir(root):
                d = os.path.join(root, name)
                if os.path.isfile(os.path.join(d, "pyvenv.cfg")):
                    out.add(os.path.realpath(d))
        except OSError:
            pass
    for prefix in (sys.prefix, sys.base_prefix):
        p = os.path.realpath(prefix)
        if any(p == q or p.startswith(q + os.sep) for q in protected):
            out.add(p)
    return sorted(out)


def installed_copies(allowed):
    """A non-editable benchkit installed inside a re-allowed virtualenv."""
    out = []
    for venv in allowed:
        out += glob.glob(os.path.join(venv, "lib", "python*", "site-packages", "benchkit"))
        out += glob.glob(os.path.join(venv, "Lib", "site-packages", "benchkit"))
    return sorted(os.path.realpath(p) for p in out)


def mechanism():
    """``"sandbox-exec"``, ``"none"`` (no sandbox here) or ``"disabled"``."""
    if os.environ.get("BENCH_SANDBOX", "").strip().lower() in ("0", "off", "false", "no"):
        return "disabled"
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    return "none"


def _profile(n_denied, n_allowed, n_redenied=0):
    """SBPL profile; paths arrive as -D parameters so nothing needs escaping."""
    lines = ["(version 1)", "(allow default)"]
    lines += [f'(deny file-read* file-write* (subpath (param "DENY{i}")))'
              for i in range(n_denied)]
    # Later rules win: re-allow reading (only) the virtualenvs...
    lines += [f'(allow file-read* (subpath (param "ALLOW{i}")))'
              for i in range(n_allowed)]
    # ...except any copy of benchkit installed inside one of them.
    lines += [f'(deny file-read* file-write* (subpath (param "REDENY{i}")))'
              for i in range(n_redenied)]
    return "\n".join(lines)


def wrap(argv):
    """Return *argv* wrapped so it cannot read or write the protected paths."""
    if mechanism() != "sandbox-exec":
        return list(argv)
    denied = protected_paths()
    allowed = readable_exceptions(denied)
    out = [shutil.which("sandbox-exec") or "sandbox-exec"]
    for i, p in enumerate(denied):
        out += ["-D", f"DENY{i}={p}"]
    redenied = installed_copies(allowed)
    for i, p in enumerate(allowed):
        out += ["-D", f"ALLOW{i}={p}"]
    for i, p in enumerate(redenied):
        out += ["-D", f"REDENY{i}={p}"]
    out += ["-p", _profile(len(denied), len(allowed), len(redenied))]
    return out + list(argv)


def describe():
    """What a result file records about hidden-test protection.

    Local filesystem only: network access is left open (harnesses call hosted
    models), so a public copy of the repository stays fetchable.
    """
    m = mechanism()
    return {"mechanism": m, "hidden_tests_protected": m == "sandbox-exec",
            "scope": "local filesystem"}


_warned = False


def warn_if_unprotected(stream=None):
    """Say once, loudly, when agents can read the hidden tests."""
    global _warned
    m = mechanism()
    if m == "sandbox-exec" or _warned:
        return
    _warned = True
    why = ("BENCH_SANDBOX=0" if m == "disabled"
           else "no sandbox mechanism is available on this platform")
    print(f"warning: agent subprocesses are not sandboxed ({why}); they can read "
          "the hidden tests of agentic-hard tasks, so those scores are not "
          "tamper-proof.", file=stream or sys.stderr)

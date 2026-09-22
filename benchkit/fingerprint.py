"""Stamp result summaries with what was measured, so old and new runs are comparable.

A change to a task's prompt, tests, files, scoring predicate or par silently
invalidates comparisons with older results. Every summary therefore carries:

- ``schema_version`` — the layout of the result file. Bump it when a field
  changes meaning; readers treat a missing value as ``0`` (pre-versioning).
- ``suite_hash`` — a sha256 over exactly the tasks that were run. Two result
  files with the same ``suite_hash`` scored the same tasks the same way.

The hash must be identical across processes, machines and Python versions
(re-runs are grouped by it), so it never uses ``hash()``, ``repr()`` of objects
or ``inspect.getsource`` of lambdas. It covers:

- each task's data fields (id, difficulty, prompt, tests, files), sorted by id;
- each agentic task's par (its oracle's minimum tool-call count);
- the source text of every module that defines a task's callables (``check``,
  ``oracle``) plus the agentic workspace, whose behaviour decides scoring. Line
  endings are normalised so a CRLF checkout hashes the same.
"""
import hashlib
import json
import sys

SCHEMA_VERSION = 1

_DATA_FIELDS = ("id", "difficulty", "prompt", "tests", "files")
_ENV_MODULE = "benchkit.agentic.env"


def _module_text(name):
    path = getattr(sys.modules.get(name), "__file__", None)
    if not path:
        return ""
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n").decode("utf-8")


def _canonical(tasks):
    from .agentic.loop import par_calls  # lazy: loop imports runner

    entries, modules = [], set()
    for t in sorted(tasks, key=lambda t: t["id"]):
        e = {k: t[k] for k in _DATA_FIELDS if k in t}
        for k, v in t.items():
            if callable(v):
                modules.add(v.__module__)
        if callable(t.get("oracle")):
            e["par"] = par_calls(t)
            modules.add(_ENV_MODULE)
        entries.append(e)
    return {"tasks": entries,
            "sources": {m: _module_text(m) for m in sorted(modules)}}


def suite_hash(tasks):
    """Deterministic sha256 hex digest of the task definitions that were run."""
    blob = json.dumps(_canonical(tasks), sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("ascii")).hexdigest()


def stamp(summary, tasks):
    """Add ``schema_version`` and ``suite_hash`` to a summary in place; return it."""
    summary["schema_version"] = SCHEMA_VERSION
    summary["suite_hash"] = suite_hash(tasks)
    return summary


def schema_version(summary):
    """Schema version of a stored summary; ``0`` for files written before it existed."""
    return (summary or {}).get("schema_version", 0)

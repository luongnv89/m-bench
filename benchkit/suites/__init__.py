"""Task suites. A suite is a list of dicts; the fields depend on its kind.

Codegen tasks (core16, hard12) carry `prompt` + `tests` — Python source
appended after the model's code and executed — and each has a reference
solution in benchkit.references so `bench validate` can prove the tests are
passable before blaming a model. Agentic tasks carry `files`, `check` and
`oracle`, validated by running the oracle. System One tasks carry a `state`
plus typed `questions`, validated by a data lint (each answer must be one of
its own options).
"""
from ..agentic.tasks import TASKS as AGENTIC
from ..agentic.tasks_hard import TASKS as AGENTIC_HARD
from .core16 import TASKS as CORE16
from .hard12 import TASKS as HARD12
from .system1 import TASKS as SYSTEM1

SUITES = {
    "core16": CORE16,
    "hard12": HARD12,
    "all": CORE16 + HARD12,
    "system1": SYSTEM1,
    "agentic": AGENTIC,
    "agentic-hard": AGENTIC_HARD,
    "agentic-all": AGENTIC + AGENTIC_HARD,
}

# "codegen": one-shot, scored by hidden unit tests on the emitted code.
# "agentic": multi-turn tool calling, scored by a predicate over the final workspace.
# "s1":      one-shot decision questions over a state, scored by exact match.
KINDS = {"core16": "codegen", "hard12": "codegen", "all": "codegen",
         "system1": "s1",
         "agentic": "agentic", "agentic-hard": "agentic", "agentic-all": "agentic"}

DESCRIPTIONS = {
    "core16": "16 general coding tasks — algorithms, data structures, parsing, Python idiom",
    "hard12": "12 hard tasks — built when core16 saturated; parsers, DP, cron, bigint, transactions",
    "all": "core16 + hard12, 28 tasks",
    "system1": "23 decision scenarios (49 questions) — a state plus typed "
               "questions scored by exact match: speed + accuracy for "
               "System One endpoints",
    "agentic": "8 multi-turn tool-calling tasks — read/edit/run files to reach a goal state",
    "agentic-hard": "8 ranking tasks — hidden tests, decoys, cascades, restraint, perf budgets",
    "agentic-all": "agentic + agentic-hard, 16 tasks",
}


def kind(name):
    return KINDS.get(name, "codegen")


def get(name):
    if name not in SUITES:
        raise SystemExit(f"unknown suite {name!r}; choose from {', '.join(SUITES)}")
    return SUITES[name]

"""Independent answer keys and quality checks for the System One v2 data (`system1-v2`)."""
import unittest
from collections import Counter

from benchkit import fingerprint, s1_runner
from benchkit.suites import SUITES, kind
from benchkit.suites.system1_v2 import FAMILIES, TASKS

PRIMARY_KEYS = {
    "policy": "refund|reject|request proof|reject|refund|request proof|replacement|reject|refund|request proof|reject|refund|replacement|reject|replacement|refund|request proof|replacement|refund|reject",
    "triage": "P1|P0|P3|P1|P0|P3|P3|P2|P3|P0|P0|P0|P1|P2|P3|P2|P2|P3|P2|P0",
    "access": "allow|deny|allow|deny|allow|deny|allow|deny|deny|deny|deny|allow|deny|deny|allow|deny|allow|deny|deny|allow",
    "events": "shipped|paid|cancelled|cancelled|shipped|shipped|shipped|shipped|refunded|refunded|cancelled|paid|shipped|cancelled|shipped|pending|refunded|cancelled|pending|refunded",
    "time": "yes|no|no|yes|yes|no|no|yes|yes|no|no|yes|yes|no|no|no|no|no|yes|no",
    "money": "settled|outstanding|overpaid|settled|outstanding|settled|settled|overpaid|outstanding|settled|settled|overpaid|settled|outstanding|settled|overpaid|settled|outstanding|overpaid|settled",
    "inventory": "fill all|fill partial|wait|fill all|fill all|fill partial|fill all|wait|fill all|wait|fill all|wait|fill all|fill partial|wait|fill all|fill all|fill partial|fill partial|fill all",
    "dependencies": "deploy|archive|notify|archive|archive|notify|archive|archive|none|archive|archive|deploy|none|none|none|notify|notify|archive|none|none",
    "evidence": "supported|refuted|conflicting|unknown|supported|refuted|conflicting|unknown|supported|refuted|conflicting|unknown|supported|refuted|conflicting|unknown|supported|refuted|conflicting|unknown",
    "records": "selected|selected|selected|selected|selected|conflict|conflict|conflict|conflict|conflict|deleted|deleted|deleted|deleted|deleted|missing|missing|missing|missing|missing",
}

NUMERIC_KEYS = {
    "events": [2, 1, 2, 1, 2, 2, 2, 2, 3, 2, 1, 1, 2, 2, 2, 0, 2, 1, 0, 3],
    "money": [2000, 2000, 2000, 1000, 51, 51, 999, 999, 150, 150,
              0, 0, 800, 800, 95, 95, 189, 189, 745, 745],
    "inventory": [6, 6, 0, 1, 6, 2, 5, 0, 3, 0, 4, 0, 10, 7, 0, 3, 5, 5, 1, 2],
}


class TestSystemOneDataset(unittest.TestCase):
    def test_size_coverage_and_unique_prompts(self):
        self.assertEqual(len(TASKS), 200)
        self.assertIs(SUITES["system1-v2"], TASKS)
        self.assertEqual(kind("system1-v2"), "s1")
        self.assertEqual(Counter(t["id"].rsplit("_", 1)[0] for t in TASKS),
                         Counter({family: 20 for family in FAMILIES}))
        self.assertEqual(Counter(t["difficulty"] for t in TASKS),
                         Counter(medium=40, hard=160))
        self.assertEqual(len({t["id"] for t in TASKS}), 200)
        self.assertEqual(len({t["state"] for t in TASKS}), 200)
        items = s1_runner._items(TASKS)
        self.assertEqual(len(items), 400)
        self.assertEqual(len({q["prompt"] for q in items}), 400)
        self.assertEqual(sum("options" not in q for q in items), 20)

    def test_independent_primary_keys_and_class_balance(self):
        for family, keys in PRIMARY_KEYS.items():
            tasks = [t for t in TASKS if t["id"].startswith(family + "_")]
            actual = [t["questions"][0]["answer"] for t in tasks]
            with self.subTest(family=family):
                self.assertEqual(actual, keys.split("|"))
                self.assertLessEqual(max(Counter(actual).values()), 12)

    def test_independent_numeric_keys(self):
        for family, keys in NUMERIC_KEYS.items():
            actual = [t["questions"][1]["answer"] for t in TASKS
                      if t["id"].startswith(family + "_")]
            with self.subTest(family=family):
                self.assertEqual(actual, list(map(str, keys)))

    def test_secondary_edge_cases(self):
        expected = {
            "policy_05": "R1", "policy_06": "R2", "policy_07": "R3",
            "policy_08": "R5", "policy_15": "R3", "policy_16": "R4",
            "triage_11": "security", "triage_12": "operations", "triage_14": "billing",
            "access_06": "DENY", "access_07": "GRANT", "access_09": "DEFAULT",
            "time_05": "valid", "time_06": "expired", "time_11": "maintenance",
            "time_12": "valid", "time_15": "revoked", "time_20": "not yet valid",
            "dependencies_05": "ready", "dependencies_06": "failed dependency",
            "dependencies_09": "insufficient slots", "dependencies_19": "disabled",
            "dependencies_20": "failed dependency", "evidence_07": "unknown",
            "evidence_11": "conflicting", "evidence_13": "refuted",
            "evidence_16": "unknown", "records_01": "REF-1-Q", "records_05": "REF-5-Q",
            "records_06": "NONE", "records_11": "NONE", "records_16": "NONE",
        }
        by_id = {t["id"]: t for t in TASKS}
        for tid, answer in expected.items():
            with self.subTest(task=tid):
                self.assertEqual(by_id[tid]["questions"][1]["answer"], answer)

    def test_answer_scoring_and_shuffled_positions(self):
        positions = {}
        for task in TASKS:
            self.assertEqual(s1_runner._lint(task), [], task["id"])
            for q in task["questions"]:
                self.assertTrue(s1_runner._score(q, q["answer"])[0])
                options = q.get("options")
                if not options:
                    continue
                index = options.index(q["answer"])
                positions.setdefault(len(options), Counter())[index] += 1
                self.assertTrue(s1_runner._score(q, chr(65 + index))[0])
                for other in options:
                    if other != q["answer"]:
                        self.assertFalse(s1_runner._score(q, other)[0])
        for size, counts in positions.items():
            with self.subTest(options=size):
                self.assertEqual(set(counts), set(range(size)))
                self.assertLess(max(counts.values()) / sum(counts.values()), 0.7)

    def test_counterfactuals_change_the_decision(self):
        pairs = {
            "policy": [(1, 2), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18), (19, 20)],
            "triage": [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (13, 14), (15, 16), (17, 18), (19, 20)],
            "access": [(1, 2), (3, 4), (5, 6), (7, 8), (15, 16), (17, 18), (19, 20)],
            "time": [(1, 2), (5, 6), (7, 8), (11, 12), (13, 14), (18, 19)],
            "money": [(1, 2), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18), (19, 20)],
            "inventory": [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18), (19, 20)],
            "dependencies": [(1, 2), (5, 6)],
        }
        by_id = {t["id"]: t for t in TASKS}
        for family, pairs_in_family in pairs.items():
            for left, right in pairs_in_family:
                a, b = by_id[f"{family}_{left:02d}"], by_id[f"{family}_{right:02d}"]
                with self.subTest(family=family, pair=(left, right)):
                    self.assertNotEqual(a["questions"][0]["answer"], b["questions"][0]["answer"])

    def test_reconstruction_and_legacy_fingerprint(self):
        rebuilt = [t for build in FAMILIES.values() for t in build()]
        self.assertEqual(rebuilt, TASKS)
        legacy = SUITES["system1-legacy"]
        self.assertEqual(kind("system1-legacy"), "s1")
        self.assertEqual(len(legacy), 23)
        self.assertEqual(sum(len(t["questions"]) for t in legacy), 49)
        self.assertEqual(fingerprint.suite_hash(legacy),
                         "79ff3d7d9b04330f6bae5fa8a723f8dbc93f0c229cb7a49b7df10ecf5fdb9fd0")
        self.assertNotEqual(fingerprint.suite_hash(TASKS), fingerprint.suite_hash(legacy))


if __name__ == "__main__":
    unittest.main()

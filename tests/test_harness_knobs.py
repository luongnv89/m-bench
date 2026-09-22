"""--effort (claude-code) and --variant (opencode) reach the adapter (#85)."""
import unittest

from benchkit.cli import _build_parser, _harness_config, _harness_kwargs
from benchkit.harness import ClaudeCodeHarness, HarnessConfig, OpenCodeHarness, get

_CMDS = (["harness", "run"], ["setup", "run"])


def _args(argv):
    return _build_parser().parse_args(argv)


def _run_args(**over):
    base = {"label": "", "thinking": False, "samples": 1,
            "concurrency": 2, "test_timeout": 60}
    base.update(over)
    return type("A", (), base)()


class TestKnobParsing(unittest.TestCase):
    def test_parsers_accept_effort_and_variant(self):
        for cmd in _CMDS:
            with self.subTest(cmd=cmd):
                a = _args(cmd + ["--harness", "claude-code", "--effort", "high"])
                self.assertEqual(a.effort, "high")
                self.assertEqual(a.variant, "")
                a = _args(cmd + ["--harness", "opencode", "--variant", "max"])
                self.assertEqual(a.variant, "max")
                self.assertEqual(a.effort, "")

    def test_kwargs_route_each_flag_to_its_harness(self):
        for cmd in _CMDS:
            with self.subTest(cmd=cmd):
                self.assertEqual(
                    _harness_kwargs(_args(cmd + ["--harness", "claude-code", "--effort", "high"])),
                    {"effort": "high"})
                self.assertEqual(
                    _harness_kwargs(_args(cmd + ["--harness", "opencode", "--variant", "max"])),
                    {"variant": "max"})
                self.assertEqual(_harness_kwargs(_args(cmd + ["--harness", "pi"])), {})

    def test_kwargs_reject_flag_on_wrong_harness(self):
        cases = [
            ["--harness", "pi", "--effort", "high"],
            ["--harness", "opencode", "--effort", "high"],
            ["--harness", "claude-code", "--variant", "max"],
            ["--harness", "devin", "--variant", "max"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit):
                    _harness_kwargs(_args(["harness", "run"] + argv))


class TestKnobAdapters(unittest.TestCase):
    def test_adapters_receive_the_value_via_get(self):
        cc = get("claude-code", HarnessConfig(model="m"), effort="high")
        oc = get("opencode", HarnessConfig(provider="p", model="m"), variant="max")
        self.assertIsInstance(cc, ClaudeCodeHarness)
        self.assertEqual(cc.effort, "high")
        self.assertIsInstance(oc, OpenCodeHarness)
        self.assertEqual(oc.variant, "max")


class TestKnobConfig(unittest.TestCase):
    def test_config_records_effort_in_extra_and_label(self):
        h = ClaudeCodeHarness(HarnessConfig(model="opus"), effort="high")
        cfg = _harness_config(_run_args(), h, "(harness)")
        self.assertEqual(cfg.extra["effort"], "high")
        self.assertNotIn("variant", cfg.extra)
        self.assertIn("effort-high", cfg.label)

    def test_config_records_variant_in_extra_and_label(self):
        h = OpenCodeHarness(HarnessConfig(provider="p", model="m"), variant="max")
        cfg = _harness_config(_run_args(), h, "(harness)", live=True)
        self.assertEqual(cfg.extra, {"live": True, "variant": "max"})
        self.assertIn("variant-max", cfg.label)

    def test_config_unchanged_when_no_knob_set(self):
        """Default runs keep the labels (and file names) they always had."""
        h = ClaudeCodeHarness(HarnessConfig(model="opus"))
        cfg = _harness_config(_run_args(), h, "(harness)")
        self.assertEqual(cfg.extra, {})
        self.assertEqual(cfg.label, "claude-code opus think-OFF")

    def test_explicit_label_is_kept_but_value_still_recorded(self):
        h = OpenCodeHarness(HarnessConfig(provider="p", model="m"), variant="max")
        cfg = _harness_config(_run_args(label="mine"), h, "(harness)")
        self.assertEqual(cfg.label, "mine")
        self.assertEqual(cfg.extra["variant"], "max")


if __name__ == "__main__":
    unittest.main()

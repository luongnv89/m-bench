"""--effort (claude-code) and --variant (opencode) reach the adapter (#85)."""
import pytest

from benchkit.cli import _build_parser, _harness_config, _harness_kwargs
from benchkit.harness import ClaudeCodeHarness, HarnessConfig, OpenCodeHarness, get


def _args(argv):
    return _build_parser().parse_args(argv)


@pytest.mark.parametrize("cmd", [["harness", "run"], ["setup", "run"]])
def test_parsers_accept_effort_and_variant(cmd):
    a = _args(cmd + ["--harness", "claude-code", "--effort", "high"])
    assert a.effort == "high" and a.variant == ""
    a = _args(cmd + ["--harness", "opencode", "--variant", "max"])
    assert a.variant == "max" and a.effort == ""


@pytest.mark.parametrize("cmd", [["harness", "run"], ["setup", "run"]])
def test_kwargs_route_each_flag_to_its_harness(cmd):
    assert _harness_kwargs(_args(cmd + ["--harness", "claude-code", "--effort", "high"])) \
        == {"effort": "high"}
    assert _harness_kwargs(_args(cmd + ["--harness", "opencode", "--variant", "max"])) \
        == {"variant": "max"}
    assert _harness_kwargs(_args(cmd + ["--harness", "pi"])) == {}


@pytest.mark.parametrize("argv", [
    ["--harness", "pi", "--effort", "high"],
    ["--harness", "opencode", "--effort", "high"],
    ["--harness", "claude-code", "--variant", "max"],
    ["--harness", "devin", "--variant", "max"],
])
def test_kwargs_reject_flag_on_wrong_harness(argv):
    with pytest.raises(SystemExit):
        _harness_kwargs(_args(["harness", "run"] + argv))


def test_adapters_receive_the_value_via_get():
    cc = get("claude-code", HarnessConfig(model="m"), effort="high")
    oc = get("opencode", HarnessConfig(provider="p", model="m"), variant="max")
    assert isinstance(cc, ClaudeCodeHarness) and cc.effort == "high"
    assert isinstance(oc, OpenCodeHarness) and oc.variant == "max"


def _run_args(**over):
    base = {"label": "", "thinking": False, "samples": 1,
            "concurrency": 2, "test_timeout": 60}
    base.update(over)
    return type("A", (), base)()


def test_config_records_effort_in_extra_and_label():
    h = ClaudeCodeHarness(HarnessConfig(model="opus"), effort="high")
    cfg = _harness_config(_run_args(), h, "(harness)")
    assert cfg.extra["effort"] == "high"
    assert "variant" not in cfg.extra
    assert "effort-high" in cfg.label


def test_config_records_variant_in_extra_and_label():
    h = OpenCodeHarness(HarnessConfig(provider="p", model="m"), variant="max")
    cfg = _harness_config(_run_args(), h, "(harness)", live=True)
    assert cfg.extra == {"live": True, "variant": "max"}
    assert "variant-max" in cfg.label


def test_config_unchanged_when_no_knob_set():
    """Default runs keep the labels (and file names) they always had."""
    h = ClaudeCodeHarness(HarnessConfig(model="opus"))
    cfg = _harness_config(_run_args(), h, "(harness)")
    assert cfg.extra == {}
    assert cfg.label == "claude-code opus think-OFF"


def test_explicit_label_is_kept_but_value_still_recorded():
    h = OpenCodeHarness(HarnessConfig(provider="p", model="m"), variant="max")
    cfg = _harness_config(_run_args(label="mine"), h, "(harness)")
    assert cfg.label == "mine" and cfg.extra["variant"] == "max"

"""Adapter for Devin CLI (https://devin.ai — the Cognition coding agent).

Driven headless with `devin -p <prompt> --export <path>`, which runs the prompt
non-interactively and writes an ATIF-v1 trajectory file after every turn. The
export is the telemetry channel: each `agent` step carries `tool_calls[]`,
`observation.results[]` and per-inference `metrics` (prompt/completion/cached
tokens), and `final_metrics` carries the run totals. Devin's stdout in print
mode is only the final response text, so nothing is folded from the stream —
everything below comes from the export file.

### Pointing it at a model

Devin speaks to Cognition's hosted service only; there is no OpenAI-compatible
mode and `--endpoint` is refused in `available()`. `--model` takes the ids and
aliases `devin models list` prints (`swe-2-max`, `opus`, `claude-opus-5`, …).
`list_models()` parses that listing into (family, model) pairs — the family id
(`swe-2`, `claude-opus-5`, …) stands in for the provider column so `-m` matching
and result labels behave like the other adapters.

### Keeping the run honest

Devin has no `--tools` pinning and no single "no extensions" flag, so isolated
mode is assembled from three levers:

| Lever | What it strips |
|---|---|
| `XDG_CONFIG_HOME=<staged empty>` | user `config.json` (hooks, permissions, model default), `mcp_config.json` (every user-scope MCP server), `~/.config/{devin,cognition}/skills`, XDG `AGENTS.md` |
| `XDG_DATA_HOME=<staged>` | session DB and CLI state — the `--no-session` counterpart. `credentials.toml` is symlinked back in or every task would run unauthenticated |
| `--config <throwaway>` | `read_config_from` all false (no AGENTS.md/cursor/windsurf/claude imports — pi's `--no-context-files` counterpart) and `subagents_enabled: false` (the `Task` counterpart: subagents are the one built-in that can be pointed at another model) |

What it cannot strip, and `describe()` says so on every result:

- Skills under HOME-relative dirs (`~/.agents/skills`, `~/.claude/skills`,
  `~/.codeium/*/skills`) still load — Devin discovers them by filesystem path,
  not config, and there is no documented off switch. Redirecting HOME would
  break auth and licensing, so the leak is documented rather than fixed. The
  `<available_skills>` blob is verified to still be injected in isolated runs.
- `web_search`/`webfetch`/`skill`/`mcp_*` tools stay in the tool list; the
  permission system only scopes `read/edit/grep/glob/exec`, so they cannot be
  denied. With MCP config stripped the `mcp_*` tools have no server to reach.
- `subagents_enabled: false` does not shorten the tool list — `run_subagent`
  and the profile block remain advertised; whether calls are refused is
  unverified.

`--permission-mode dangerous` is the headless requirement, not an isolation
choice: print mode cannot prompt, and the workspace is a throwaway temp
directory — the same reasoning as opencode's `--auto` and claude-code's
`bypassPermissions`. It is passed in live mode too, for the same reason.

`--respect-workspace-trust false` likewise: the temp workspace is untrusted by
definition and print mode cannot show the trust prompt.

### Telemetry, and what is missing

- tool calls and the trace come from `tool_calls[].function_name` on `agent`
  steps; turns are the count of those steps;
- input/output tokens are the per-step `metrics` sums (`prompt_tokens` already
  includes the cached portion — `cached_tokens` is a subset, never added);
- **`failed_calls` is not measurable.** ATIF observations carry no error flag —
  a failed shell command returns its stderr as ordinary result content. Any
  explicit `is_error`/`error` fields are counted defensively, but a `0` here
  means *not measured*, not *nothing failed*;
- **`reasoning_tokens` is not measurable.** Steps carry `reasoning_content`
  text but no token count — those tokens are inside `completion_tokens`;
- **`stop_reason` is derived, not exported.** rc 0 plus a parsed export reads
  `finished`; there is no field for it, and no `--max-turns` equivalent — an
  internal turn cap, if hit, is indistinguishable from finishing.
"""
import json
import os
import re
import shutil
import subprocess

from .base import Harness, HarnessConfig, HarnessResult
from .stream import StreamTimeout, stream_events

#: staged dirs the adapter builds per task, siblings of the workspace
CONFIG_HOME = "xdg-config"
DATA_HOME = "xdg-data"
CONFIG_JSON = "devin-config.json"
EXPORT_JSON = "export.json"

#: throwaway config for isolated runs — see module docstring
_ISOLATED_CONFIG = {
    "agent": {"subagents_enabled": False},
    "read_config_from": {
        "agents_standard": False,
        "cursor": False,
        "windsurf": False,
        "claude": False,
    },
}

#: env inherited from a parent Devin session or user shell that would change
#: the child's behaviour mid-benchmark (model, permission mode, sandbox, or
#: the parent session's own db marker)
_SCRUB_PREFIXES = ("DEVIN_",)
_SCRUB_VARS = ("CHISEL_SESSION_DB",)


def _creds_path():
    return os.path.expanduser("~/.local/share/devin/credentials.toml")


class DevinHarness(Harness):
    name = "devin"

    def __init__(self, cfg=None):
        c = cfg or HarnessConfig()
        # `provider`/`base_url`/`api_key` exist only so the shared CLI flags
        # are accepted; Devin has no provider or endpoint concept.
        self.provider = c.provider
        self.model = c.model
        self.base_url = c.base_url
        self.binary = c.binary or "devin"
        #: live mode: the user's daily setup — real config, MCP servers, skills
        self.live = bool(c.live)
        self.extra_args = list(c.extra_args)

    # --- discovery ------------------------------------------------------
    def _version(self):
        path = shutil.which(self.binary)
        if not path:
            return None, f"{self.binary} not found on PATH"
        try:
            v = subprocess.run([path, "version"], capture_output=True, text=True,
                               timeout=60, stdin=subprocess.DEVNULL
                               ).stdout.strip().splitlines()[-1]
            return v, None
        except Exception as e:  # noqa: BLE001
            return None, f"{self.binary} version failed: {e}"

    def _authed(self):
        path = shutil.which(self.binary)
        try:
            out = subprocess.run([path, "auth", "status"], capture_output=True,
                                 text=True, timeout=30,
                                 stdin=subprocess.DEVNULL).stdout
        except Exception as e:  # noqa: BLE001
            return False, f"{self.binary} auth status failed: {e}"
        if "Logged in" not in out:
            return False, "not logged in — `devin auth login` first"
        return True, "logged in"

    @property
    def uses_endpoint(self):
        # Same contract as the other adapters: true only when --endpoint was
        # passed. Devin cannot honour one, so available() refuses the run.
        return bool(self.base_url)

    @property
    def model_spec(self):
        return f"{self.provider}/{self.model}" if self.provider else self.model

    def probe(self):
        v, err = self._version()
        if err:
            return False, err
        return True, f"{v} — uses your Devin authentication"

    def available(self):
        v, err = self._version()
        if err:
            return False, err
        if self.base_url:
            return False, ("devin serves Cognition-hosted models only and has "
                           "no OpenAI-compatible mode; --endpoint is unsupported")
        if not self.model:
            return False, (f"{v}: no model selected — pass --model "
                           f"(see `bench harness models --harness devin`)")
        ok, detail = self._authed()
        if not ok:
            return False, f"{v}: {detail}"
        return True, f"{v} via your Devin auth ({self.model_spec})"

    def list_models(self):
        """Parse `devin models list` into (family, model) pairs.

        The listing is `Family Name (family-id)` headers over indented model
        rows (`model-id   Display Name [context, price]`); `aliases:` rows are
        skipped. The family id stands in for provider so `-m` matching and
        labels look like the other adapters.
        """
        path = shutil.which(self.binary)
        if not path:
            return []
        try:
            out = subprocess.run([path, "models", "list"], capture_output=True,
                                 text=True, timeout=60,
                                 stdin=subprocess.DEVNULL).stdout
        except Exception:  # noqa: BLE001 — enumeration is best-effort
            return []
        entries, family = [], None
        for line in out.splitlines():
            m = re.match(r"^\S.*?\((\S+)\)\s*$", line)
            if m:                       # family header: `SWE-2 (swe-2)`
                family = m.group(1)
                continue
            m = re.match(r"^\s{2,}(\S+)", line)
            if m and family and not line.lstrip().startswith("aliases:"):
                entries.append((family, m.group(1)))
        return entries

    def describe(self):
        ok, detail = self.available()
        d = dict(
            harness=self.name, model=self.model, model_spec=self.model_spec,
            base_url=self.base_url,
            source="endpoint" if self.uses_endpoint else "devin-auth",
            api="cognition-hosted",
            live=self.live, available=ok, detail=detail)
        if self.live:
            # which isolation levers were dropped, so nobody reads a live score
            # as a measurement of the model alone
            d["disabled_isolation"] = [
                "XDG_CONFIG_HOME redirect (user config, hooks, MCP servers, "
                "XDG skills)",
                "XDG_DATA_HOME redirect (session db)",
                "--config throwaway (read_config_from off, subagents off)",
            ]
        d["caveats"] = ([
                "live mode: Devin ran with your own config — MCP servers, "
                "hooks, skills, rules imports and subagents all enabled. A "
                "component that calls another model contaminates this "
                "measurement.",
                "--permission-mode dangerous is required for print mode "
                "(it cannot prompt); the workspace is a throwaway temp dir.",
            ] if self.live else [
                "isolated mode strips the XDG config tree (user config, MCP "
                "servers, XDG skills) and disables rules imports and "
                "subagents, but HOME-relative skill dirs (~/.agents, "
                "~/.claude, ~/.codeium) still load — Devin has no off switch.",
                "web_search/webfetch/skill/mcp_* tools remain listed; the "
                "permission system cannot pin or deny them.",
                "failed_calls is always 0: ATIF observations carry no error "
                "flag, so a failing command inside exec is not distinguishable "
                "from a failed tool call.",
                "reasoning_tokens is always 0: steps carry reasoning_content "
                "text but no token count; those tokens are inside "
                "completion_tokens.",
                "--thinking does not toggle devin runs; effort is encoded in "
                "the model variant (e.g. swe-2-medium vs swe-2-max).",
            ])
        return d

    # --- workspace ------------------------------------------------------
    def prepare(self, container):
        """Task files in container/work; Devin's staged state beside it.

        All staged paths derive from `container`/`workdir`, never from `self`:
        one instance serves every task on a thread pool, so state kept on the
        adapter would hand one task another task's config home.
        """
        workdir = os.path.join(container, "work")
        os.makedirs(workdir, exist_ok=True)
        if not self.live:
            st = self._staging(workdir)
            os.makedirs(st["xdg_config"], exist_ok=True)
            os.makedirs(os.path.join(st["xdg_data"], "devin"), exist_ok=True)
            creds = _creds_path()
            link = os.path.join(st["xdg_data"], "devin", "credentials.toml")
            if os.path.exists(creds) and not os.path.exists(link):
                os.symlink(creds, link)
            with open(st["config"], "w") as f:
                json.dump(_ISOLATED_CONFIG, f)
        return workdir

    def _staging(self, workdir):
        """This task's staged paths, derived from its workdir alone."""
        container = os.path.dirname(workdir)
        return {
            "xdg_config": os.path.join(container, CONFIG_HOME),
            "xdg_data": os.path.join(container, DATA_HOME),
            "config": os.path.join(container, CONFIG_JSON),
            "export": os.path.join(container, EXPORT_JSON),
        }

    # --- execution ------------------------------------------------------
    def _argv(self, prompt, workdir):
        argv = [
            self.binary, "-p", prompt,
            "--model", self.model,
            "--permission-mode", "dangerous",      # print mode cannot prompt
            "--respect-workspace-trust", "false",  # temp workspace is untrusted
            "--export", self._staging(workdir)["export"],
        ]
        if not self.live:
            argv += ["--config", self._staging(workdir)["config"]]
        return argv + self.extra_args

    def run(self, workdir, prompt, timeout=900, thinking=False):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(_SCRUB_PREFIXES) and k not in _SCRUB_VARS}
        if not self.live:
            st = self._staging(workdir)
            env["XDG_CONFIG_HOME"] = st["xdg_config"]
            env["XDG_DATA_HOME"] = st["xdg_data"]
        try:
            res, rc, err_tail = stream_events(
                self._argv(prompt, workdir), cwd=workdir, env=env,
                handler=_devin_handler, timeout=timeout, label="devin")
        except StreamTimeout:
            return HarnessResult(stop_reason="timeout",
                                 error=f"devin exceeded {timeout}s")
        except Exception as e:  # noqa: BLE001
            return HarnessResult(stop_reason="error", error=f"{type(e).__name__}: {e}")

        _fold_export(self._staging(workdir)["export"], res)
        if res.stop_reason == "unknown" and res.turns:
            res.stop_reason = "finished"
        if rc != 0 and not res.error:
            res.stop_reason = "error"
            tail = [line for line in (err_tail or "").strip().splitlines()
                    if line.strip()]
            res.error = tail[-1][:200] if tail else f"exit {rc}"
        return res


def _devin_handler(ev, res, state):
    """No-op: devin's print-mode stdout is response text, not a JSONL stream.

    Telemetry comes from the ATIF export afterwards; this handler exists only
    so stream_events provides process management, timeouts and bounded tails.
    """


def _fold_export(path, res):
    """Fold the ATIF export file into *res* — the real telemetry source."""
    try:
        with open(path) as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return
    for step in doc.get("steps") or []:
        if step.get("source") != "agent":
            continue
        res.turns += 1
        m = step.get("metrics") or {}
        res.input_tokens += m.get("prompt_tokens") or 0
        res.output_tokens += m.get("completion_tokens") or 0
        for tc in step.get("tool_calls") or []:
            res.tool_calls += 1
            res.trace.append(tc.get("function_name", "?"))
        for r in (step.get("observation") or {}).get("results") or []:
            if r.get("is_error") or r.get("error"):
                res.failed_calls += 1

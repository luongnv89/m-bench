#!/usr/bin/env python3
"""The standard System One decision endpoint — one stable URL, swappable model.

Applications and the `system1` bench suite always talk to
`http://localhost:8123/v1` (OpenAI chat-completions subset). Which model
answers is a deployment detail behind `S1_BACKEND`:

- `typesafe`  TypeSafe Jev — the measured baseline (results/2026-09-30).
              Each rendered s1 prompt is parsed back into
              (state, question, options) and issued as one `choice` call to
              POST {TYPESAFE_BASE_URL}/systemone. Open questions (no options)
              fall back to a choice over deduped state tokens — the
              documented "select instead of generate" pattern; disclose it in
              the run report.
- `nimble`    Bespoke-Nimble served by Ollama >= 0.35 — Ollama implements the
              same `/v1/systemone` contract as TypeSafe, so this reuses the
              identical translation and answer shape pointed at
              `NIMBLE_BASE_URL` (default the local Ollama). No API key.
- `laya`      convaiinnovations/laya in-process (`pip install laya`, a ~33 ms
              ModernBERT encoder). `predict(state, questions)` takes the same
              Jev question shape and returns the same answer shape; it runs in
              a thread executor so it never blocks the loop. Model dir comes
              from `LAYA_MODEL_DIR`.
- `kev`       jaredpalmer/kev served by `python -m kev.serve` — a local
              Jev-style decision model implementing the same `/v1/systemone`
              contract, so this reuses the identical translation pointed at
              `KEV_BASE_URL`. No API key.
- `clef`      Cloudflare/clef (or clef-flash) in-process — the release ships
              `joint_schema_model.py`, whose `systemone()` takes a
              `/v1/systemone` request body and returns the same response
              body. Loaded once at startup via `load_release_model` (bf16,
              CUDA), each request runs in a thread executor, and the native
              `/v1/systemone` route forwards verbatim to it — the phishing
              service's SDK needs no changes. Needs a torch+transformers
              interpreter (the kev venv); repo from `CLEF_REPO`.
- `systemone` Any native System One API at `S1_DECISION_URL`, including
              OpenRouter's /api/alpha/decisions. Supports the benchmark chat
              surface and native SDK requests at /v1/systemone.
- `proxy`     Any OpenAI-compatible server (vLLM, llama.cpp, ollama chat)
              serving a candidate decision model — e.g. a merged Nimble GGUF.
              Requests and streaming responses are forwarded verbatim to
              `S1_UPSTREAM`; the client cannot tell it left the Jev backend.

Swapping Jev for a candidate that satisfies the contract is therefore an env
change, not an application change — and `./bench run --suite system1` against
this URL measures the candidate through exactly the same transport the
baseline was measured through (see docs/S1-ENDPOINT.md).

Env:
    S1_BACKEND         typesafe (default) | nimble | laya | kev | clef | proxy | systemone
    S1_PORT            listen port (default 8123)
    TYPESAFE_API_KEY   bearer key for the typesafe backend
    TYPESAFE_BASE_URL  default https://api.typesafe.ai/v1
    NIMBLE_BASE_URL    default http://localhost:11434/v1 (Ollama >= 0.35)
    NIMBLE_MODEL       model id sent to Ollama's /v1/systemone (default nimble)
    KEV_BASE_URL       default http://localhost:8009/v1 (kev.serve)
    KEV_MODEL          model id sent to kev's /v1/systemone (default kev-latest)
    LAYA_MODEL_DIR     HF id or local dir for the laya checkpoint
                       (default ~/models/laya-typed-decisions)
    CLEF_REPO          HF id or local dir of a clef release
                       (default Cloudflare/clef-flash)
    CLEF_DEVICE        torch device for the clef backbone (default cuda)
    S1_UPSTREAM        proxy backend base URL, e.g. http://localhost:8001/v1
    S1_DECISION_URL    full native decision URL (systemone backend), default
                       https://api.typesafe.ai/v1/systemone; supports OpenRouter
                       https://openrouter.ai/api/alpha/decisions
    S1_API_KEY         explicit upstream bearer key (systemone/proxy only)
    S1_MODEL           model id to advertise/forward (default jev-latest for
                       systemone/typesafe; proxy forwards client model if unset)
"""
import json
import os
import re
import time
import uuid

from aiohttp import ClientSession, ClientTimeout, web

BACKEND = os.environ.get("S1_BACKEND", "typesafe")
PORT = int(os.environ.get("S1_PORT", "8123"))
UPSTREAM = os.environ.get("S1_UPSTREAM", "").rstrip("/")  # proxy backend
S1_KEY = os.environ.get("S1_API_KEY", "")
MODEL_OVERRIDE = os.environ.get("S1_MODEL", "")
TS_BASE = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai/v1")
TS_KEY = os.environ.get("TYPESAFE_API_KEY", "")
TS_MODEL = os.environ.get("S1_MODEL", "jev-latest")
DECISION_URL = os.environ.get("S1_DECISION_URL", f"{TS_BASE.rstrip('/')}/systemone")
NIMBLE_BASE = os.environ.get("NIMBLE_BASE_URL", "http://localhost:11434/v1")
NIMBLE_MODEL = os.environ.get("NIMBLE_MODEL", "nimble")
KEV_BASE = os.environ.get("KEV_BASE_URL", "http://localhost:8009/v1")
KEV_MODEL = os.environ.get("KEV_MODEL", "kev-latest")
LAYA_DIR = os.environ.get(
    "LAYA_MODEL_DIR",
    os.path.expanduser("~/models/laya-typed-decisions"))
CLEF_REPO = os.environ.get("CLEF_REPO", "Cloudflare/clef-flash")
CLEF_DEVICE = os.environ.get("CLEF_DEVICE", "cuda")

# Fixed trailers emitted by benchkit.s1_runner._render — parse anchors.
CHOICE_TAIL = "\nAnswer with the option letter or its exact text, and nothing else."
OPEN_TAIL = "\nAnswer as briefly as possible — a few words at most, and nothing else."
OPTION_LINE = re.compile(r"^[A-Z]\) (.+)$")


def parse_rendered(prompt):
    """(state, question, options) back out of one rendered s1 user prompt."""
    if not prompt.startswith("State:\n"):
        raise ValueError("prompt does not start with 'State:'")
    body = prompt[len("State:\n"):]
    if body.endswith(CHOICE_TAIL):
        body, opt_block = body[: -len(CHOICE_TAIL)].rsplit("\nOptions:\n", 1)
        options = [m.group(1) for line in opt_block.split("\n")
                   if (m := OPTION_LINE.match(line))]
        if not options:
            raise ValueError("Options block parsed empty")
    elif body.endswith(OPEN_TAIL):
        body = body[: -len(OPEN_TAIL)]
        options = []
    else:
        raise ValueError("unrecognised s1 answer trailer")
    state, question = body.rsplit("\n\nQuestion: ", 1)
    return state, question.strip(), options


def candidates(state):
    """Open-question candidates: deduped state tokens (max 64)."""
    seen, out = set(), []
    for tok in state.split():
        t = tok.strip("\"'`.,;:()[]{}")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= 64:
            break
    return out


# ---------------------------------------------------------------- backends ---

def _s1_question(state, question, options):
    """The (state, questions) payload every Jev-shape backend shares."""
    opts = options or candidates(state)
    return {"state": state,
            "questions": {"q": {"type": "choice", "instructions": question,
                                "criteria": {o: None for o in opts}}}}


async def ask_systemone(session, base_url, model, state, question, options,
                        headers=None):
    """One Choice question to a /v1/systemone endpoint (Jev API shape).

    Used by both `typesafe` (api.typesafe.ai, Bearer key) and `nimble`
    (Ollama >= 0.35 implements the same contract, no key).
    """
    payload = _s1_question(state, question, options)
    payload["model"] = model
    body = await post_decisions(session, f"{base_url.rstrip('/')}/systemone",
                                payload, headers)
    ans = body["answers"]["q"]
    return ans["choice"], body.get("usage") or {}, body.get("model")


class DecisionQuotaError(RuntimeError):
    """An explicitly exhausted daily allowance is not transient throttling."""

    def __init__(self, body):
        self.body = body
        super().__init__("upstream daily decision quota exhausted")


def decision_retry_delay(headers, metadata, attempt):
    """Respect numeric Retry-After and OpenRouter reset metadata, capped at 65s."""
    delay = 1 + 2 * attempt
    try:
        delay = max(delay, float(headers.get("Retry-After", "0")))
    except (TypeError, ValueError):
        pass
    if isinstance(metadata, dict):
        limits = metadata.get("headers") or {}
        if isinstance(limits, dict):
            try:
                reset = float(limits.get("X-RateLimit-Reset", "0")) / 1000
                delay = max(delay, reset - time.time() + 0.5)
            except (TypeError, ValueError):
                pass
    return min(delay, 65)


async def post_decisions(session, url, payload, headers=None):
    """Call a native decision endpoint; retry only transient upstream failures."""
    last_err = None
    for attempt in range(3):
        delay = 1 + 2 * attempt
        try:
            async with session.post(url, json=payload,
                                    headers=headers or {}) as r:
                body = await r.json(content_type=None)
                if r.status == 200:
                    return body
                error = body.get("error") if isinstance(body, dict) else None
                metadata = error.get("metadata") if isinstance(error, dict) else None
                if (r.status == 429 and isinstance(metadata, dict)
                        and metadata.get("limit_source") == "openrouter_free_tier_daily"):
                    raise DecisionQuotaError(body)
                delay = decision_retry_delay(r.headers, metadata, attempt)
                last_err = f"upstream {r.status}: {str(body)[:300]}"
                if r.status not in (429, 500, 502, 503, 504):
                    break
        except DecisionQuotaError:
            raise
        except Exception as e:  # noqa: BLE001 — surface the last failure, retry transient
            last_err = str(e)
        if attempt < 2:
            import asyncio
            await asyncio.sleep(delay)
    raise RuntimeError(last_err or "upstream failed")


async def _answer_via(request, body, ask, fallback_model, upstream_name):
    """Shared handle: parse prompt -> ask -> chat response."""
    user = next((m.get("content", "") for m in reversed(body.get("messages", []))
                 if m.get("role") == "user"), "")
    try:
        state, question, options = parse_rendered(user)
    except ValueError as e:
        return _err(400, f"s1 prompt parse: {e}", "invalid_request_error")
    try:
        answer, u, shown = await ask(request.app, state, question, options,
                                     body.get("model"))
    except DecisionQuotaError as e:
        return web.json_response(e.body, status=429)
    except Exception as e:  # noqa: BLE001
        return _err(502, f"{upstream_name} upstream: {e}")
    usage = {"prompt_tokens": u.get("input_tokens") or 0,
             "completion_tokens": u.get("output_tokens") or 0,
             "total_tokens": (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)}
    return await _chat_response(request, body, shown or fallback_model,
                                answer, usage)


async def handle_typesafe(request, body):
    """Translate one chat completion into a TypeSafe judgment."""
    async def ask(app, state, question, options, model):
        m = model if (model or "").startswith("jev") else TS_MODEL
        return await ask_systemone(
            app["session"], TS_BASE, m, state, question, options,
            headers={"Authorization": f"Bearer {TS_KEY}"})
    return await _answer_via(request, body, ask, TS_MODEL, "typesafe")


async def handle_nimble(request, body):
    """Translate into a Bespoke-Nimble judgment via Ollama's /v1/systemone."""
    async def ask(app, state, question, options, model):
        m = model if model else NIMBLE_MODEL
        return await ask_systemone(
            app["session"], NIMBLE_BASE, m, state, question, options)
    return await _answer_via(request, body, ask, NIMBLE_MODEL, "nimble")


async def handle_kev(request, body):
    """Translate into a Kev judgment via kev.serve's /v1/systemone."""
    async def ask(app, state, question, options, model):
        m = model if model else KEV_MODEL
        return await ask_systemone(
            app["session"], KEV_BASE, m, state, question, options)
    return await _answer_via(request, body, ask, KEV_MODEL, "kev")


async def handle_laya(request, body):
    """Translate into a laya predict() call, run in a thread executor."""
    async def ask(app, state, question, options, model):
        agent = app.get("laya")
        if agent is None:
            raise RuntimeError("laya model not loaded")
        payload = _s1_question(state, question, options)
        import asyncio
        res = await asyncio.get_running_loop().run_in_executor(
            None, agent.predict, payload["state"], payload["questions"])
        ans = res["answers"]["q"]
        return ans["choice"], res.get("usage") or {}, res.get("model")
    return await _answer_via(request, body, ask,
                             os.path.basename(LAYA_DIR.rstrip("/")) or "laya",
                             "laya")


async def _clef_systemone(app, body):
    """Run clef's joint_schema_model.systemone() off the event loop."""
    import asyncio
    jsm = app.get("clef_jsm")
    if jsm is None:
        raise RuntimeError("clef model not loaded")
    return await asyncio.get_running_loop().run_in_executor(
        None, jsm.systemone, app["clef_model"], app["clef_processor"], body)


async def handle_clef(request, body):
    """Translate into a clef decision via joint_schema_model.systemone()."""
    async def ask(app, state, question, options, model):
        payload = _s1_question(state, question, options)
        payload["model"] = model or _clef_model_id()
        res = await _clef_systemone(app, payload)
        return res["answers"]["q"]["choice"], res.get("usage") or {}, res.get("model")
    return await _answer_via(request, body, ask, _clef_model_id(), "clef")


def _clef_model_id():
    return os.path.basename(CLEF_REPO.rstrip("/")) or "clef"


def upstream_headers():
    """Never forward client credentials or implicitly reuse another provider's key."""
    return {"Authorization": f"Bearer {S1_KEY}"} if S1_KEY else {}


async def handle_systemone(request, body):
    """Translate benchmark chat prompts to a configurable native decision URL."""
    async def ask(app, state, question, options, model):
        payload = _s1_question(state, question, options)
        payload["model"] = MODEL_OVERRIDE or model or TS_MODEL
        result = await post_decisions(app["session"], DECISION_URL, payload,
                                      upstream_headers())
        return (result["answers"]["q"]["choice"], result.get("usage") or {},
                result.get("model"))
    return await _answer_via(request, body, ask, TS_MODEL, "systemone")


async def systemone(request):
    """Native SDK surface: preserve typed questions and calibrated answers verbatim."""
    if BACKEND not in ("systemone", "clef"):
        return _err(400, f"native /v1/systemone not supported on backend {BACKEND}",
                    "invalid_request_error")
    try:
        body = await request.json()
        if not isinstance(body, dict) or "state" not in body or not body.get("questions"):
            return _err(400, "state and questions are required", "invalid_request_error")
    except Exception:  # noqa: BLE001
        return _err(400, "bad json", "invalid_request_error")
    if BACKEND == "clef":
        body["model"] = body.get("model") or _clef_model_id()
        try:
            return web.json_response(await _clef_systemone(request.app, body))
        except Exception as e:  # noqa: BLE001
            return _err(502, f"clef: {e}")
    body["model"] = MODEL_OVERRIDE or body.get("model") or TS_MODEL
    try:
        result = await post_decisions(request.app["session"], DECISION_URL,
                                      body, upstream_headers())
        return web.json_response(result)
    except DecisionQuotaError as e:
        return web.json_response(e.body, status=429)
    except Exception as e:  # noqa: BLE001
        return _err(502, f"systemone upstream: {e}")


async def handle_proxy(request, body):
    """Forward an OpenAI chat completion (stream or not) to S1_UPSTREAM."""
    if not UPSTREAM:
        return _err(500, "S1_BACKEND=proxy needs S1_UPSTREAM=<base-url>")
    session = request.app["session"]
    if MODEL_OVERRIDE:
        body = dict(body, model=MODEL_OVERRIDE)
    try:
        async with session.post(f"{UPSTREAM}/chat/completions", json=body,
                                headers=upstream_headers()) as up:
            if body.get("stream"):
                resp = web.StreamResponse(status=up.status, headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache"})
                await resp.prepare(request)
                async for data in up.content.iter_any():
                    await resp.write(data)
                await resp.write_eof()
                return resp
            return web.json_response(await up.json(content_type=None),
                                     status=up.status)
    except Exception as e:  # noqa: BLE001
        return _err(502, f"proxy upstream: {e}")


HANDLERS = {"typesafe": handle_typesafe, "nimble": handle_nimble,
            "laya": handle_laya, "kev": handle_kev, "clef": handle_clef,
            "proxy": handle_proxy, "systemone": handle_systemone}


# ------------------------------------------------------------ openai surface ---

def _err(status, message, type_="server_error"):
    return web.json_response({"error": {"message": message, "type": type_}},
                             status=status)


def _chunk(cid, model, delta, finish=None, usage=None):
    c = {"id": cid, "object": "chat.completion.chunk",
         "created": int(time.time()), "model": model, "choices": []}
    if delta is not None:
        c["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish}]
    if usage is not None:
        c["usage"] = usage
    return f"data: {json.dumps(c)}\n\n"


async def _chat_response(request, body, model, answer, usage):
    """An answer string as an OpenAI chat completion, streamed on request."""
    if not body.get("stream"):
        return web.json_response({
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion", "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": answer}}],
            "usage": usage})
    resp = web.StreamResponse(status=200, headers={
        "Content-Type": "text/event-stream", "Cache-Control": "no-cache",
        "Connection": "keep-alive"})
    await resp.prepare(request)
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    await resp.write(_chunk(cid, model, {"role": "assistant"}).encode())
    await resp.write(_chunk(cid, model, {"content": answer}).encode())
    await resp.write(_chunk(cid, model, {}, "stop").encode())
    await resp.write(_chunk(cid, model, None, usage=usage).encode())
    await resp.write(b"data: [DONE]\n\n")
    await resp.write_eof()
    return resp


async def chat_completions(request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err(400, "bad json")
    return await HANDLERS[BACKEND](request, body)


async def models(request):
    if BACKEND == "proxy" and UPSTREAM and not MODEL_OVERRIDE:
        try:
            async with request.app["session"].get(
                    f"{UPSTREAM}/models", headers=upstream_headers()) as up:
                return web.json_response(await up.json(content_type=None),
                                         status=up.status)
        except Exception as e:  # noqa: BLE001
            return _err(502, f"proxy upstream: {e}")
    ids = {"typesafe": ["jev-latest"], "nimble": [NIMBLE_MODEL],
           "kev": [KEV_MODEL], "systemone": [TS_MODEL], "clef": [_clef_model_id()],
           "proxy": [MODEL_OVERRIDE] if MODEL_OVERRIDE else [],
           "laya": [os.path.basename(LAYA_DIR.rstrip("/")) or "laya"],
           }.get(BACKEND, [])
    return web.json_response({"object": "list", "data": [
        {"id": i, "object": "model", "owned_by": BACKEND} for i in ids]})


async def health(request):
    upstream = {"typesafe": TS_BASE, "nimble": NIMBLE_BASE, "kev": KEV_BASE,
                "laya": LAYA_DIR, "clef": CLEF_REPO, "proxy": UPSTREAM,
                "systemone": DECISION_URL}.get(BACKEND, "")
    return web.json_response({"ok": True, "backend": BACKEND,
                              "upstream": upstream})


async def on_startup(app):
    if BACKEND not in HANDLERS:
        raise SystemExit(f"unknown S1_BACKEND {BACKEND!r}; "
                         f"choose from {', '.join(HANDLERS)}")
    if BACKEND == "typesafe" and not TS_KEY:
        raise SystemExit("TYPESAFE_API_KEY is not set")
    if BACKEND == "proxy" and not UPSTREAM:
        raise SystemExit("S1_BACKEND=proxy needs S1_UPSTREAM=<base-url>")
    app["session"] = ClientSession(timeout=ClientTimeout(total=1800))
    if BACKEND == "laya":
        import asyncio
        import laya
        print(f"loading laya from {LAYA_DIR} …", flush=True)
        app["laya"] = await asyncio.get_running_loop().run_in_executor(
            None, laya.load, LAYA_DIR)
        print("laya loaded", flush=True)
    if BACKEND == "clef":
        import asyncio
        import sys
        from huggingface_hub import snapshot_download
        print(f"loading clef from {CLEF_REPO} on {CLEF_DEVICE} …", flush=True)

        def _load_clef():
            path = snapshot_download(CLEF_REPO)
            sys.path.insert(0, path)
            import joint_schema_model as jsm
            return jsm, *jsm.load_release_model(path, device=CLEF_DEVICE)
        (app["clef_jsm"], app["clef_model"],
         app["clef_processor"]) = await asyncio.get_running_loop(
            ).run_in_executor(None, _load_clef)
        print("clef loaded", flush=True)
    upstream = {"typesafe": TS_BASE, "nimble": NIMBLE_BASE, "kev": KEV_BASE,
                "laya": LAYA_DIR, "clef": CLEF_REPO, "proxy": UPSTREAM,
                "systemone": DECISION_URL}.get(BACKEND, "")
    print(f"s1-gateway on :{PORT}  backend={BACKEND}  upstream={upstream}", flush=True)


async def on_cleanup(app):
    await app["session"].close()


app = web.Application()
app.router.add_get("/v1/models", models)
app.router.add_get("/health", health)
app.router.add_post("/v1/chat/completions", chat_completions)
app.router.add_post("/v1/systemone", systemone)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=PORT, print=None)

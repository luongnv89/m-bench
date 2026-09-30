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
- `proxy`     Any OpenAI-compatible server (vLLM, llama.cpp, ollama chat)
              serving a candidate decision model — e.g. a merged Nimble GGUF.
              Requests and streaming responses are forwarded verbatim to
              `S1_UPSTREAM`; the client cannot tell it left the Jev backend.

Swapping Jev for a candidate that satisfies the contract is therefore an env
change, not an application change — and `./bench run --suite system1` against
this URL measures the candidate through exactly the same transport the
baseline was measured through (see docs/S1-ENDPOINT.md).

Env:
    S1_BACKEND         typesafe (default) | nimble | laya | kev | proxy
    S1_PORT            listen port (default 8123)
    TYPESAFE_API_KEY   bearer key for the typesafe backend
    TYPESAFE_BASE_URL  default https://api.typesafe.ai/v1
    NIMBLE_BASE_URL    default http://localhost:11434/v1 (Ollama >= 0.35)
    NIMBLE_MODEL       model id sent to Ollama's /v1/systemone (default nimble)
    KEV_BASE_URL       default http://localhost:8009/v1 (kev.serve)
    KEV_MODEL          model id sent to kev's /v1/systemone (default kev-latest)
    LAYA_MODEL_DIR     HF id or local dir for the laya checkpoint
                       (default ~/models/laya-typed-decisions)
    S1_UPSTREAM        proxy backend base URL, e.g. http://localhost:8001/v1
    S1_MODEL           model id to advertise/forward (typesafe default
                       jev-latest; proxy default: upstream's own `model` field)
"""
import json
import os
import re
import time
import uuid

from aiohttp import ClientSession, ClientTimeout, web

BACKEND = os.environ.get("S1_BACKEND", "typesafe")
PORT = int(os.environ.get("S1_PORT", "8123"))
UPSTREAM = os.environ.get("S1_UPSTREAM", "")          # proxy backend
TS_BASE = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai/v1")
TS_KEY = os.environ.get("TYPESAFE_API_KEY", "")
TS_MODEL = os.environ.get("S1_MODEL", "jev-latest")
NIMBLE_BASE = os.environ.get("NIMBLE_BASE_URL", "http://localhost:11434/v1")
NIMBLE_MODEL = os.environ.get("NIMBLE_MODEL", "nimble")
KEV_BASE = os.environ.get("KEV_BASE_URL", "http://localhost:8009/v1")
KEV_MODEL = os.environ.get("KEV_MODEL", "kev-latest")
LAYA_DIR = os.environ.get(
    "LAYA_MODEL_DIR",
    os.path.expanduser("~/models/laya-typed-decisions"))

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
    last_err = None
    for attempt in range(3):
        try:
            async with session.post(f"{base_url}/systemone", json=payload,
                                    headers=headers or {}) as r:
                body = await r.json(content_type=None)
                if r.status == 200:
                    ans = body["answers"]["q"]
                    return ans["choice"], body.get("usage") or {}, body.get("model")
                last_err = f"upstream {r.status}: {str(body)[:300]}"
                if r.status not in (429, 500, 502, 503, 504):
                    break
        except Exception as e:  # noqa: BLE001 — surface the last failure, retry transient
            last_err = str(e)
        if attempt < 2:
            import asyncio
            await asyncio.sleep(1 + 2 * attempt)
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


async def handle_proxy(request, body):
    """Forward an OpenAI chat completion (stream or not) to S1_UPSTREAM."""
    if not UPSTREAM:
        return _err(500, "S1_BACKEND=proxy needs S1_UPSTREAM=<base-url>")
    session = request.app["session"]
    try:
        async with session.post(f"{UPSTREAM}/chat/completions", json=body) as up:
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
            "laya": handle_laya, "kev": handle_kev, "proxy": handle_proxy}


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
    if BACKEND == "proxy" and UPSTREAM:
        try:
            async with request.app["session"].get(f"{UPSTREAM}/models") as up:
                return web.json_response(await up.json(content_type=None),
                                         status=up.status)
        except Exception as e:  # noqa: BLE001
            return _err(502, f"proxy upstream: {e}")
    ids = {"typesafe": ["jev-latest"], "nimble": [NIMBLE_MODEL],
           "kev": [KEV_MODEL],
           "laya": [os.path.basename(LAYA_DIR.rstrip("/")) or "laya"],
           }.get(BACKEND, [])
    return web.json_response({"object": "list", "data": [
        {"id": i, "object": "model", "owned_by": BACKEND} for i in ids]})


async def health(request):
    upstream = {"typesafe": TS_BASE, "nimble": NIMBLE_BASE, "kev": KEV_BASE,
                "laya": LAYA_DIR, "proxy": UPSTREAM}.get(BACKEND, "")
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
    upstream = {"typesafe": TS_BASE, "nimble": NIMBLE_BASE, "kev": KEV_BASE,
                "laya": LAYA_DIR, "proxy": UPSTREAM}.get(BACKEND, "")
    print(f"s1-gateway on :{PORT}  backend={BACKEND}  upstream={upstream}")


async def on_cleanup(app):
    await app["session"].close()


app = web.Application()
app.router.add_get("/v1/models", models)
app.router.add_get("/health", health)
app.router.add_post("/v1/chat/completions", chat_completions)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=PORT, print=None)

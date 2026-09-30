#!/usr/bin/env python3
"""OpenAI-compatible shim over convaiinnovations/laya on 127.0.0.1:8804.

laya is a System One decision model, not a text generator: Router().predict
scores typed questions over a state in a single forward pass. This shim
translates the deterministic "State: / Question: / Options:" prompts that
benchkit/s1_runner.py::_render emits into one typed `choice` call, and
streams the chosen option's letter back as SSE deltas, so the stock OpenAI
client contract in benchkit/runner.py::generate (stream:true, ttft at first
content chunk, final usage chunk) works unchanged.

Endpoints: GET /v1/models, GET /health, POST /v1/chat/completions.
Requests may name either "laya" or "convaiinnovations/laya".

laya and its torch stack are imported lazily — this file loads, lints and
answers --help on machines without them. --load-on-start moves the import
and checkpoint download to startup so a serving failure surfaces early.
"""

import argparse
import asyncio
import json
import logging
import re
import time

from aiohttp import web

HOST = "127.0.0.1"
PORT = 8804

# Both ids are listed and accepted: the bench may be pointed at either.
MODEL_IDS = ("laya", "convaiinnovations/laya")

# What a request gets when laya has no typed answer for it — an honest
# decline, never a guessed option letter.
DECLINE = "unanswerable"

# Same request-body ceiling family as router.py: the prompts this serves are
# tiny, but an unbounded buffer is still a mistake (issue #39).
CLIENT_MAX_SIZE = 4 * 1024 * 1024

# The rendered system1 user prompt (benchkit/s1_runner.py::_render):
#   State:\n<state>\n\nQuestion: <q>\nOptions:\nA) ..\nB) ..\n<instruction>
# or, for the open short-answer form:
#   State:\n<state>\n\nQuestion: <q>\n<instruction>
_S1 = re.compile(
    r"^State:\n(?P<state>.*?)\n\nQuestion: (?P<question>[^\n]*)\n(?P<rest>.*)\Z",
    re.DOTALL)
_OPTION = re.compile(r"^[A-Z]\)\s+(?P<text>.*\S)\s*$")

log = logging.getLogger("laya-shim")


def parse_s1_prompt(text):
    """(state, question, options) from one rendered system1 prompt, or None.

    `options` is [] for the open short-answer form (no Options: block), so
    callers can route that question to the decline path without another pass.
    """
    m = _S1.match(text or "")
    if not m:
        return None
    options = []
    lines = m["rest"].splitlines()
    if lines and lines[0].strip() == "Options:":
        for line in lines[1:]:
            om = _OPTION.match(line)
            if not om:
                break  # the instruction line ends the block
            options.append(om["text"].strip())
    return m["state"].strip(), m["question"].strip(), options


def laya_questions(question, options):
    """The typed-questions mapping laya's Router.predict expects.

    One `choice` question. Criteria keys are synthetic option_<letter> ids —
    arbitrary option text (dates, sentences, punctuation) never enters key
    space — and the real option text rides along as each key's description.
    """
    criteria = {f"option_{chr(ord('a') + i)}": text
                for i, text in enumerate(options)}
    return {"q": {"type": "choice", "instructions": question,
                  "criteria": criteria}}


def answer_letter(result, options):
    """The chosen option's letter ('a'..'z') from a predict result, or ""."""
    answers = (result or {}).get("answers") or {}
    choice = answers.get("q", {}).get("choice") if isinstance(answers, dict) else None
    m = re.fullmatch(r"option_([a-z])", str(choice or ""))
    if m and ord(m.group(1)) - ord("a") < len(options):
        return m.group(1)
    if isinstance(choice, str):
        # Fallback for a predict result that echoes the option text or a
        # bare letter rather than the synthetic criteria key.
        c = choice.strip().lower()
        if len(c) == 1 and c.isalpha() and ord(c) - ord("a") < len(options):
            return c
        for i, o in enumerate(options):
            if c == o.strip().lower():
                return chr(ord("a") + i)
    return ""


def _default_router_factory():
    # Deliberately lazy: laya pulls in torch and downloads checkpoints, so it
    # is imported only when serving actually starts.
    from laya import Router
    return Router(preload=True)


def _usage(prompt_text, answer):
    """Approximate token accounting — laya reports no token counts."""
    pt = max(1, len(prompt_text) // 4)
    ct = max(1, len(answer) // 4)
    return {"prompt_tokens": pt, "completion_tokens": ct,
            "total_tokens": pt + ct}


def _error(status, message, code=None, type_="invalid_request_error"):
    err = {"message": message, "type": type_}
    if code:
        err["code"] = code
    return web.json_response({"error": err}, status=status)


async def _get_router(app):
    """The laya Router instance, built once on first use (or at startup)."""
    st = app["shim"]
    if st["router"] is None:
        async with st["lock"]:
            if st["router"] is None:
                factory = st["router_factory"] or _default_router_factory
                loop = asyncio.get_running_loop()
                st["router"] = await loop.run_in_executor(None, factory)
    return st["router"]


async def handle_models(request):
    data = [{"id": m, "object": "model", "created": 0, "owned_by": "laya-shim"}
            for m in MODEL_IDS]
    return web.json_response({"object": "list", "data": data})


async def handle_health(request):
    return web.json_response({"status": "ok"})


async def handle_chat(request):
    try:
        raw = await request.read()
    except web.HTTPRequestEntityTooLarge:
        return _error(413, "request body too large", code="request_too_large")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return _error(400, "invalid JSON body")
    if not isinstance(payload, dict):
        return _error(400, "invalid JSON body")

    model = payload.get("model") or ""
    if model not in MODEL_IDS:
        return _error(404, f"unknown model {model!r}; available: "
                           f"{list(MODEL_IDS)}", code="model_not_found")

    # Everything else in the body (stream_options, chat_template_kwargs,
    # temperature, max_tokens, …) is accepted and ignored on purpose.
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        return _error(400, "'messages' must be a list")
    user = next((m.get("content") for m in reversed(messages)
                 if isinstance(m, dict) and m.get("role") == "user"), None)
    if not isinstance(user, str) or not user.strip():
        return _error(400, "missing user message")

    parsed = parse_s1_prompt(user)
    if parsed is None:
        # Not a system1-shaped prompt: a decision endpoint cannot type it,
        # so it declines rather than guesses.
        state, question, options = "", user, []
    else:
        state, question, options = parsed

    if not options:
        answer = DECLINE
    else:
        try:
            router = await _get_router(request.app)
        except ImportError as e:
            log.error("laya import failed: %s", e)
            return _error(503, f"laya is not installed: {e}", type_="api_error")
        except Exception as e:  # noqa: BLE001 — a dead model must answer 5xx
            log.error("laya router startup failed: %s", e)
            return _error(503, f"laya router failed to start: {e}",
                          type_="api_error")
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, router.predict, state, laya_questions(question, options))
        except Exception as e:  # noqa: BLE001 — report, don't hang the suite
            log.error("laya predict failed: %s", e)
            return _error(502, f"laya predict failed: {e}", type_="api_error")
        answer = answer_letter(result, options) or DECLINE

    usage = _usage(user, answer)
    if payload.get("stream"):
        return await _stream(request, model, answer, usage)
    return web.json_response(_completion(model, answer, usage))


def _completion(model, answer, usage):
    return {"id": f"chatcmpl-laya-{int(time.time() * 1000)}",
            "object": "chat.completion", "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": answer}}],
            "usage": usage}


async def _stream(request, model, answer, usage):
    """One content chunk, a stop chunk, a usage chunk, then [DONE].

    That is the sequence vLLM emits under stream_options.include_usage and
    what runner.generate reads: ttft lands on the first content chunk, and
    `choices: []` + usage rides the last chunk before the terminator.
    """
    resp = web.StreamResponse(status=200, headers={
        "Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
    await resp.prepare(request)
    base = {"id": f"chatcmpl-laya-{int(time.time() * 1000)}",
            "object": "chat.completion.chunk", "created": int(time.time()),
            "model": model}
    chunks = [
        dict(base, choices=[{"index": 0,
                             "delta": {"role": "assistant",
                                       "content": answer},
                             "finish_reason": None}]),
        dict(base, choices=[{"index": 0, "delta": {},
                             "finish_reason": "stop"}]),
        dict(base, choices=[], usage=usage),
    ]
    for ch in chunks:
        await resp.write(f"data: {json.dumps(ch)}\n\n".encode())
    await resp.write(b"data: [DONE]\n\n")
    await resp.write_eof()
    return resp


async def on_start(app):
    if app["shim"]["preload"]:
        await _get_router(app)
        log.info("laya router loaded")


def create_app(router_factory=None, preload=False):
    """router_factory: injectable () -> Router for tests; default lazily
    imports laya on first use. preload: build the Router at startup.

    State lives in one dict: it is mutated lazily after startup, and aiohttp
    deprecates assigning new app keys once the app has started.
    """
    app = web.Application(client_max_size=CLIENT_MAX_SIZE)
    app["shim"] = {"router": None, "router_factory": router_factory,
                   "lock": asyncio.Lock(), "preload": preload}
    app.on_startup.append(on_start)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/v1/chat/completions", handle_chat)
    return app


def main(argv=None):
    p = argparse.ArgumentParser(
        description="OpenAI-compatible shim over convaiinnovations/laya")
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--load-on-start", action="store_true",
                   help="import laya and load checkpoints at startup instead "
                        "of on the first request")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(preload=args.load_on_start)
    log.info("laya-shim listening on %s:%s (models: %s)",
             args.host, args.port, ", ".join(MODEL_IDS))
    web.run_app(app, host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()

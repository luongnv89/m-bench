#!/usr/bin/env python3
"""OpenAI-compatible shim in front of TypeSafe's System One endpoint (Jev).

Jev is not a chat model: it evaluates a `state` against typed `questions` and
returns structured answers (choice / noul / score). The bench's `system1`
suite asks exactly that shape through chat completions, so this shim serves
`POST /v1/chat/completions`, parses the rendered s1 prompt back into
(state, question, options), issues one TypeSafe Choice per call, and streams
the picked option back as an ordinary chat completion.

Mapping (documented in the run's report):

- options listed -> {"type": "choice", "criteria": {option: null, ...}}
  answered by `answers.q.choice` — the option text verbatim.
- no options (open short answer) -> Jev has no free-text primitive, so the
  shim plays the documented "select instead of generate" pattern: a Choice
  over candidate values = the whitespace-split tokens of the state (deduped).
  Candidate coverage is a shim-side decision; report it, don't hide it.
- usage.input_tokens/output_tokens -> prompt_tokens/completion_tokens.

The OpenAI surface is the subset benchkit's s1 runner uses: GET /v1/models,
POST /v1/chat/completions (stream + non-stream, include_usage). Everything
else — system prompt, chat_template_kwargs, max_tokens — is ignored.

Env:
    TYPESAFE_API_KEY   required — bearer key from https://console.typesafe.ai
    TYPESAFE_BASE_URL  default https://api.typesafe.ai/v1
    SHIM_PORT          default 8123

Run:  TYPESAFE_API_KEY=... python3 configs/typesafe-jev-shim.py
Then: BENCH_BASE_URL=http://localhost:8123/v1 BENCH_MODEL=jev-latest \\
      ./bench run --suite system1 --samples 2 --label "typesafe-jev s1"
"""
import json
import os
import re
import time
import uuid

from aiohttp import ClientSession, ClientTimeout, web

UPSTREAM = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai/v1")
API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
PORT = int(os.environ.get("SHIM_PORT", "8123"))
MODEL = "jev-latest"

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
    """Candidate values for an open question: deduped state tokens (max 64).

    'Select instead of generate' needs the true value among the candidates;
    whitespace tokens cover short extraction answers (codes, dates, names).
    """
    seen, out = set(), []
    for tok in state.split():
        t = tok.strip("\"'`.,;:()[]{}")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= 64:
            break
    return out


async def ask_typesafe(session, model, state, question, options):
    """One Choice question -> (answer text, usage dict, upstream model id)."""
    opts = options or candidates(state)
    payload = {
        "state": state,
        "model": model,
        "questions": {
            "q": {
                "type": "choice",
                "instructions": question,
                "criteria": {o: None for o in opts},
            }
        },
    }
    last_err = None
    for attempt in range(3):
        try:
            async with session.post(
                f"{UPSTREAM}/systemone",
                json=payload,
                headers={"Authorization": f"Bearer {API_KEY}"},
            ) as r:
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


def _chunk(cid, model, delta, finish=None, usage=None):
    c = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
         "model": model, "choices": []}
    if delta is not None:
        c["choices"] = [{"index": 0, "delta": delta, "finish_reason": finish}]
    if usage is not None:
        c["usage"] = usage
    return f"data: {json.dumps(c)}\n\n"


async def chat_completions(request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"error": {"message": "bad json"}}, status=400)
    model = body.get("model") or MODEL
    user = next((m.get("content", "") for m in reversed(body.get("messages", []))
                 if m.get("role") == "user"), "")
    try:
        state, question, options = parse_rendered(user)
    except ValueError as e:
        return web.json_response(
            {"error": {"message": f"s1 prompt parse: {e}",
                       "type": "invalid_request_error"}}, status=400)
    try:
        answer, u, upstream_model = await ask_typesafe(
            request.app["session"], model, state, question, options)
    except Exception as e:  # noqa: BLE001
        return web.json_response(
            {"error": {"message": f"typesafe upstream: {e}",
                       "type": "server_error"}}, status=502)

    shown = upstream_model or model
    usage = {"prompt_tokens": u.get("input_tokens", 0),
             "completion_tokens": u.get("output_tokens", 0),
             "total_tokens": (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)}

    if body.get("stream"):
        resp = web.StreamResponse(status=200, headers={
            "Content-Type": "text/event-stream", "Cache-Control": "no-cache",
            "Connection": "keep-alive"})
        await resp.prepare(request)
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        await resp.write(_chunk(cid, shown, {"role": "assistant"}).encode())
        await resp.write(_chunk(cid, shown, {"content": answer}).encode())
        await resp.write(_chunk(cid, shown, {}, "stop").encode())
        await resp.write(_chunk(cid, shown, None, usage=usage).encode())
        await resp.write(b"data: [DONE]\n\n")
        await resp.write_eof()
        return resp

    return web.json_response({
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion", "created": int(time.time()),
        "model": shown,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": answer}}],
        "usage": usage})


async def models(request):
    return web.json_response({"object": "list", "data": [
        {"id": MODEL, "object": "model", "owned_by": "typesafe"}]})


async def health(request):
    return web.json_response({"ok": True, "upstream": UPSTREAM})


async def on_startup(app):
    if not API_KEY:
        raise SystemExit("TYPESAFE_API_KEY is not set")
    app["session"] = ClientSession(timeout=ClientTimeout(total=120))
    print(f"typesafe-jev-shim on :{PORT}  upstream={UPSTREAM}  model={MODEL}")


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

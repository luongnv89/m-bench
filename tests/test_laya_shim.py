"""Tests for laya-shim.py — the OpenAI-compatible layer over convaiinnovations/laya.

The shim translates the rendered system1 prompt ("State: / Question: /
Options:") into a laya Router.predict typed-choice call and streams the
chosen option's letter back as SSE. laya itself is never imported here — the
Router is stubbed — so these tests run on machines without torch, which is
also what makes the lazy-import design testable in the first place.
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from aiohttp.test_utils import TestClient, TestServer

from benchkit import s1_runner
from benchkit.suites import SUITES

_spec = importlib.util.spec_from_file_location(
    "laya_shim", os.path.join(REPO_ROOT, "laya-shim.py"))
laya_shim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(laya_shim)


def _prompt(state, question, options=None):
    """A real rendered system1 user prompt for a single question."""
    q = {"question": question, "answer": (options or ["x"])[0]}
    if options is not None:
        q["options"] = options
    return s1_runner._render({"state": state}, q)


class TestModuleLoadsWithoutLaya(unittest.TestCase):
    """The import contract: no laya/torch at module load time."""

    def test_laya_not_imported_by_loading_the_shim(self):
        # _spec.loader.exec_module above already ran; a hard `import laya`
        # at top level would have put it in sys.modules by now.
        self.assertIsNone(sys.modules.get("laya"))

    def test_help_runs(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "laya-shim.py"), "--help"],
            capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--port", proc.stdout)
        self.assertIn("--load-on-start", proc.stdout)


class TestParseS1Prompt(unittest.TestCase):
    def test_two_option_prompt(self):
        text = _prompt("Store policy: full refund within 30 days.",
                       "Is the customer eligible?", ["yes", "no"])
        state, question, options = laya_shim.parse_s1_prompt(text)
        self.assertEqual(state, "Store policy: full refund within 30 days.")
        self.assertEqual(question, "Is the customer eligible?")
        self.assertEqual(options, ["yes", "no"])

    def test_four_option_prompt_multiline_state(self):
        state_in = "Ticket header:\nREF: ZX-4821-Q\nReceived: 2026-09-30"
        text = _prompt(state_in, "Which queue should own this ticket?",
                       ["billing", "technical support", "sales", "legal"])
        state, question, options = laya_shim.parse_s1_prompt(text)
        self.assertEqual(state, state_in)
        self.assertEqual(question, "Which queue should own this ticket?")
        self.assertEqual(options,
                         ["billing", "technical support", "sales", "legal"])

    def test_open_question_has_empty_options(self):
        text = _prompt("Ticket header:\nREF: ZX-4821-Q",
                       "What is the ticket's reference code?")
        state, question, options = laya_shim.parse_s1_prompt(text)
        self.assertEqual(question, "What is the ticket's reference code?")
        self.assertEqual(options, [])

    def test_every_shipped_prompt_parses(self):
        """The parser must accept every prompt the suite can ever send."""
        n = 0
        for task in SUITES["system1"]:
            for q in task["questions"]:
                parsed = laya_shim.parse_s1_prompt(s1_runner._render(task, q))
                self.assertIsNotNone(parsed, f"unparseable: {task['id']}")
                state, question, options = parsed
                self.assertEqual(state, task["state"].strip())
                self.assertEqual(question, q["question"].strip())
                self.assertEqual(options, q.get("options") or [])
                n += 1
        self.assertGreater(n, 0)

    def test_non_s1_prompt_returns_none(self):
        for text in ("hello world", "", None, "State:\nno question here"):
            with self.subTest(text=text):
                self.assertIsNone(laya_shim.parse_s1_prompt(text))


class TestLayaMapping(unittest.TestCase):
    def test_questions_dict_shape(self):
        qs = laya_shim.laya_questions("Is it spam?", ["yes", "no"])
        self.assertEqual(qs, {"q": {"type": "choice",
                                    "instructions": "Is it spam?",
                                    "criteria": {"option_a": "yes",
                                                 "option_b": "no"}}})

    def test_answer_letter_from_criteria_key(self):
        result = {"answers": {"q": {"choice": "option_c"}}}
        self.assertEqual(laya_shim.answer_letter(
            result, ["yes", "no", "cannot determine", "maybe"]), "c")

    def test_answer_letter_fallback_to_verbatim_text(self):
        result = {"answers": {"q": {"choice": "Cannot Determine"}}}
        self.assertEqual(laya_shim.answer_letter(
            result, ["yes", "no", "cannot determine"]), "c")

    def test_answer_letter_fallback_to_bare_letter(self):
        result = {"answers": {"q": {"choice": "B"}}}
        self.assertEqual(laya_shim.answer_letter(result, ["yes", "no"]), "b")

    def test_answer_letter_empty_on_missing_or_out_of_range(self):
        self.assertEqual(laya_shim.answer_letter(None, ["yes"]), "")
        self.assertEqual(laya_shim.answer_letter({}, ["yes"]), "")
        self.assertEqual(laya_shim.answer_letter(
            {"answers": {"q": {"choice": "option_z"}}}, ["yes", "no"]), "")
        self.assertEqual(laya_shim.answer_letter(
            {"answers": "not-a-dict"}, ["yes", "no"]), "")


class FakeRouter:
    """Stands in for laya.Router: records predict calls, returns `choice`."""

    def __init__(self, choice):
        self.choice = choice
        self.calls = []

    def predict(self, state, questions):
        self.calls.append((state, questions))
        return {"answers": {"q": {"choice": self.choice}},
                "routing": {"model": "english"}}


class TestShimEndpoints(unittest.IsolatedAsyncioTestCase):
    """Real aiohttp server + client; only the laya Router is stubbed."""

    @classmethod
    def tearDownClass(cls):
        # IsolatedAsyncioTestCase leaves no current event loop, which makes
        # the legacy asyncio.get_event_loop() calls in test_router.py raise
        # RuntimeError on Python >= 3.12. Restore one so this file does not
        # break tests that run after it alphabetically.
        super().tearDownClass()
        asyncio.set_event_loop(asyncio.new_event_loop())

    async def _client(self, fake):
        server = TestServer(
            laya_shim.create_app(router_factory=lambda: fake))
        await server.start_server()
        self.addCleanup(server.close)
        client = TestClient(server)
        self.addCleanup(client.close)
        return client

    @staticmethod
    def _payload(user_content, model="laya", stream=True):
        return {"model": model,
                "messages": [{"role": "system", "content": s1_runner.SYSTEM},
                             {"role": "user", "content": user_content}],
                "max_tokens": 32,
                "stream": stream,
                "stream_options": {"include_usage": True},
                # the runner always sends these — the shim must ignore them
                "chat_template_kwargs": {"enable_thinking": False,
                                         "preserve_thinking": False}}

    @staticmethod
    def _sse_chunks(body):
        chunks = []
        for line in body.splitlines():
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data != "[DONE]":
                chunks.append(json.loads(data))
        return chunks

    async def test_models_lists_both_ids(self):
        client = await self._client(FakeRouter("option_a"))
        async with client.get("/v1/models") as r:
            self.assertEqual(r.status, 200)
            body = await r.json()
        self.assertEqual(body["object"], "list")
        ids = [m["id"] for m in body["data"]]
        self.assertIn("laya", ids)
        self.assertIn("convaiinnovations/laya", ids)

    async def test_streamed_round_trip_emits_letter_then_usage_then_done(self):
        fake = FakeRouter("option_c")
        client = await self._client(fake)
        prompt = _prompt("Order: {\"status\": \"shipped\"}",
                         "What is the order's status?",
                         ["pending", "shipped", "delivered", "cancelled"])
        async with client.post("/v1/chat/completions",
                               json=self._payload(prompt)) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.content_type, "text/event-stream")
            body = await r.text()

        self.assertIn("data: [DONE]", body)
        chunks = self._sse_chunks(body)
        # chunk 1: the answer letter (ttft lands here for the runner)
        self.assertEqual(chunks[0]["choices"][0]["delta"]["content"], "c")
        self.assertIsNone(chunks[0]["choices"][0]["finish_reason"])
        # chunk 2: finish_reason stop
        self.assertEqual(chunks[1]["choices"][0]["finish_reason"], "stop")
        # final chunk: no choices, usage present
        self.assertEqual(chunks[-1]["choices"], [])
        self.assertGreater(chunks[-1]["usage"]["total_tokens"], 0)

        # and laya saw the parsed typed call, not the raw prompt
        self.assertEqual(len(fake.calls), 1)
        state, questions = fake.calls[0]
        self.assertEqual(state, "Order: {\"status\": \"shipped\"}")
        self.assertEqual(questions["q"]["type"], "choice")
        self.assertEqual(questions["q"]["instructions"],
                         "What is the order's status?")
        self.assertEqual(questions["q"]["criteria"],
                         {"option_a": "pending", "option_b": "shipped",
                          "option_c": "delivered", "option_d": "cancelled"})

    async def test_open_question_declines_without_calling_laya(self):
        fake = FakeRouter("option_a")
        client = await self._client(fake)
        prompt = _prompt("Ticket header:\nREF: ZX-4821-Q",
                         "What is the ticket's reference code?")
        async with client.post("/v1/chat/completions",
                               json=self._payload(prompt)) as r:
            self.assertEqual(r.status, 200)
            body = await r.text()
        self.assertEqual(fake.calls, [])
        chunks = self._sse_chunks(body)
        self.assertEqual(chunks[0]["choices"][0]["delta"]["content"],
                         laya_shim.DECLINE)

    async def test_non_streamed_completion(self):
        fake = FakeRouter("option_b")
        client = await self._client(fake)
        prompt = _prompt("Email: 'send $50 to claim prize'",
                         "Is this spam?", ["yes", "no"])
        payload = self._payload(prompt, model="convaiinnovations/laya",
                                stream=False)
        async with client.post("/v1/chat/completions", json=payload) as r:
            self.assertEqual(r.status, 200)
            body = await r.json()
        self.assertEqual(body["object"], "chat.completion")
        self.assertEqual(body["choices"][0]["message"]["content"], "b")
        self.assertEqual(body["choices"][0]["finish_reason"], "stop")
        self.assertIn("total_tokens", body["usage"])

    async def test_unparseable_prompt_declines_not_crashes(self):
        fake = FakeRouter("option_a")
        client = await self._client(fake)
        async with client.post(
                "/v1/chat/completions",
                json=self._payload("just chat, no structure")) as r:
            self.assertEqual(r.status, 200)
            body = await r.text()
        self.assertEqual(fake.calls, [])
        self.assertIn(laya_shim.DECLINE, body)

    async def test_unknown_model_404_bad_json_400(self):
        client = await self._client(FakeRouter("option_a"))
        async with client.post(
                "/v1/chat/completions",
                json=self._payload("x", model="gpt-4")) as r:
            self.assertEqual(r.status, 404)
            body = await r.json()
        self.assertEqual(body["error"]["code"], "model_not_found")
        async with client.post(
                "/v1/chat/completions", data=b"{oops",
                headers={"Content-Type": "application/json"}) as r:
            self.assertEqual(r.status, 400)


if __name__ == "__main__":
    unittest.main()

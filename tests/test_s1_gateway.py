"""Native decision and authenticated proxy gateway wiring, using local upstreams."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from benchkit.s1_runner import _render


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        spec = importlib.util.spec_from_file_location(
            "s1_gateway_test", Path(__file__).parents[1] / "configs/s1_gateway.py")
        self.gateway = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gateway)
        self.calls = []
        self.response = {
            "model": "resolved-model", "answers": {
                "q": {"type": "choice", "choice": "blue", "confidence": 0.9}},
            "usage": {"input_tokens": 12, "output_tokens": 3, "cost": 0}}
        self.status = 200

        async def upstream(request):
            self.calls.append((request.path, await request.json(),
                               request.headers.get("Authorization")))
            return web.json_response(self.response, status=self.status)

        app = web.Application()
        app.router.add_post("/alpha/decisions", upstream)
        app.router.add_post("/v1/systemone", upstream)
        app.router.add_post("/v1/chat/completions", upstream)
        self.upstream = TestServer(app)
        await self.upstream.start_server()
        g = self.gateway
        g.BACKEND = "systemone"
        g.DECISION_URL = str(self.upstream.make_url("/alpha/decisions"))
        g.MODEL_OVERRIDE = g.TS_MODEL = "candidate/free"
        g.S1_KEY = "upstream-test-key"
        self.client = TestClient(TestServer(g.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.upstream.close()

    def chat_body(self, stream=False):
        return {"model": "old-client-model", "stream": stream, "messages": [
            {"role": "user", "content": _render(
                {"state": "The sky is blue."},
                {"question": "What color is the sky?", "options": ["blue", "red"]})}]}

    async def test_chat_translates_prompt_and_reports_real_usage(self):
        r = await self.client.post("/v1/chat/completions", json=self.chat_body(),
                                   headers={"Authorization": "Bearer client-secret"})
        body = await r.json()
        self.assertEqual(r.status, 200)
        self.assertEqual(body["choices"][0]["message"]["content"], "blue")
        self.assertEqual(body["model"], "resolved-model")
        self.assertEqual(body["usage"]["total_tokens"], 15)
        path, payload, auth = self.calls[0]
        self.assertEqual(path, "/alpha/decisions")
        self.assertEqual(payload["model"], "candidate/free")
        self.assertEqual(payload["questions"]["q"]["criteria"], {"blue": None, "red": None})
        self.assertEqual(auth, "Bearer upstream-test-key")

    async def test_native_questions_and_answers_are_preserved(self):
        payload = {"state": {"email": "example"}, "model": "old-model",
                   "questions": {"p": {"type": "noul", "instructions": "Malicious?",
                                       "criteria": {"true": "yes", "false": "no"}},
                                 "s": {"type": "score", "criteria": ["benign", "harmful"]}}}
        self.response["answers"] = {"p": {"type": "noul", "noul": 0.8},
                                    "s": {"type": "score", "score": 0.9,
                                          "confidence": 0.7}}
        r = await self.client.post("/v1/systemone", json=payload)
        self.assertEqual(await r.json(), self.response)
        self.assertEqual(self.calls[0][1]["questions"], payload["questions"])
        self.assertEqual(self.calls[0][1]["state"], payload["state"])
        self.assertEqual(self.calls[0][1]["model"], "candidate/free")

    async def test_models_advertises_pinned_decision_model(self):
        r = await self.client.get("/v1/models")
        self.assertEqual((await r.json())["data"][0]["id"], "candidate/free")
        self.assertEqual(self.calls, [])

    async def test_streaming_returns_decision_and_usage(self):
        r = await self.client.post("/v1/chat/completions", json=self.chat_body(stream=True))
        text = await r.text()
        chunks = [json.loads(line[6:]) for line in text.splitlines()
                  if line.startswith("data: ") and line != "data: [DONE]"]
        self.assertEqual(chunks[1]["choices"][0]["delta"]["content"], "blue")
        self.assertEqual(chunks[-1]["usage"]["total_tokens"], 15)
        self.assertIn("data: [DONE]", text)

    async def test_invalid_input_never_calls_upstream(self):
        for payload in [[], {}, {"state": "test", "questions": {}}]:
            r = await self.client.post("/v1/systemone", json=payload)
            self.assertEqual(r.status, 400)
        r = await self.client.post("/v1/chat/completions", json={"messages": []})
        self.assertEqual(r.status, 400)
        self.assertEqual(self.calls, [])

    async def test_upstream_error_is_not_an_answer(self):
        self.status = 401
        self.response = {"error": {"message": "unauthorized"}}
        r = await self.client.post("/v1/systemone", json={"state": "x", "questions": {"q": {}}})
        self.assertEqual(r.status, 502)
        self.assertIn("401", (await r.json())["error"]["message"])
        self.assertEqual(len(self.calls), 1)

    async def test_transient_errors_retry_but_are_bounded(self):
        self.status = 429
        self.response = {"error": {"message": "rate limited"}}
        with patch("asyncio.sleep", return_value=None):
            r = await self.client.post("/v1/systemone", json={"state": "x", "questions": {"q": {}}})
        self.assertEqual(r.status, 502)
        self.assertEqual(len(self.calls), 3)

    async def test_retry_delay_respects_reset_and_is_bounded(self):
        delay = self.gateway.decision_retry_delay
        with patch.object(self.gateway.time, "time", return_value=100):
            self.assertEqual(delay({}, {"headers": {"X-RateLimit-Reset": "110000"}}, 0), 10.5)
            self.assertEqual(delay({"Retry-After": "12"}, None, 0), 12)
            self.assertEqual(delay({"Retry-After": "1000"}, None, 0), 65)
            self.assertEqual(delay({"Retry-After": "bad"},
                                   {"headers": {"X-RateLimit-Reset": "bad"}}, 1), 3)

    async def test_per_minute_quota_waits_for_reported_reset(self):
        self.status = 429
        self.response = {"error": {"code": 429, "message": "minute limit",
                                   "metadata": {"limit_source": "openrouter_free_tier_per_minute",
                                                "headers": {"X-RateLimit-Reset": "110000"}}}}
        with patch.object(self.gateway.time, "time", return_value=100), \
                patch("asyncio.sleep", return_value=None) as sleep:
            r = await self.client.post("/v1/systemone", json={"state": "x", "questions": {"q": {}}})
        self.assertEqual(r.status, 502)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [10.5, 10.5])

    async def test_daily_quota_is_not_retried_and_metadata_is_preserved(self):
        self.status = 429
        self.response = {"error": {"code": 429, "message": "daily quota exhausted",
                                   "metadata": {"limit_source": "openrouter_free_tier_daily",
                                                "headers": {"X-RateLimit-Remaining": "0"}}}}
        for route, payload in [
                ("/v1/systemone", {"state": "x", "questions": {"q": {}}}),
                ("/v1/chat/completions", self.chat_body())]:
            r = await self.client.post(route, json=payload)
            self.assertEqual(r.status, 429)
            self.assertEqual(await r.json(), self.response)
        self.assertEqual(len(self.calls), 2)

    async def test_existing_systemone_url_and_key_still_work(self):
        g = self.gateway
        answer, usage, model = await g.ask_systemone(
            g.app["session"], str(self.upstream.make_url("/v1/")), "jev-latest",
            "The sky is blue.", "Color?", ["blue", "red"],
            headers={"Authorization": "Bearer typesafe-test-key"})
        self.assertEqual((answer, model), ("blue", "resolved-model"))
        self.assertEqual(usage["input_tokens"], 12)
        self.assertEqual(self.calls[0][0], "/v1/systemone")
        self.assertEqual(self.calls[0][2], "Bearer typesafe-test-key")

    async def test_proxy_override_and_explicit_auth(self):
        g = self.gateway
        g.BACKEND = "proxy"
        g.UPSTREAM = str(self.upstream.make_url("/v1"))
        r = await self.client.post("/v1/chat/completions", json=self.chat_body())
        self.assertEqual(r.status, 200)
        self.assertEqual(self.calls[0][1]["model"], "candidate/free")
        self.assertEqual(self.calls[0][2], "Bearer upstream-test-key")
        g.MODEL_OVERRIDE = ""
        g.S1_KEY = ""
        await self.client.post("/v1/chat/completions", json=self.chat_body(),
                               headers={"Authorization": "Bearer client-secret"})
        self.assertEqual(self.calls[-1][1]["model"], "old-client-model")
        self.assertIsNone(self.calls[-1][2])

    async def test_open_questions_keep_documented_token_fallback(self):
        body = self.chat_body()
        body["messages"][0]["content"] = _render(
            {"state": "The sky is blue."}, {"question": "Color?"})
        r = await self.client.post("/v1/chat/completions", json=body)
        self.assertEqual(r.status, 200)
        self.assertEqual(list(self.calls[0][1]["questions"]["q"]["criteria"]),
                         ["The", "sky", "is", "blue"])

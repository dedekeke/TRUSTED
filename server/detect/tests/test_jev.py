"""JevLLM against a fake jev27b_mlx server (same /health and /v1/decide shapes as jev27b_mlx/server.py)."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pets_detect_v3 import jev  # noqa: E402
from pets_detect_v3.jev import DOMAINS, JevLLM, make_llm  # noqa: E402
from pets_detect_v3.llm_v3 import TableLLMv3  # noqa: E402
from pets_detect_v3.pipeline import ART9_DOMAIN  # noqa: E402
from test_detect_v3 import prof  # noqa: E402

ATTENTION = {"attention": "bidirectional"}
SEEN = []


class _FakeJev(BaseHTTPRequestHandler):
    def do_GET(self):
        self._send({"model": "fake-4bit", "prompt_attention": ATTENTION})

    def do_POST(self):
        r = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        q = r["question"]
        SEEN.append(q)
        keys = ["false", "true"] if q["type"] == "noul" else list(q["criteria"])
        pick = {"privacy_role": "sensitive_attribute", "subtype": "HEALTH_DATA", "subject": DOMAINS[0]}
        want = next((v for k, v in pick.items() if k.split("_")[-1] in q["instructions"]), "true")
        p = [.9 if k == want else .1 / (len(keys) - 1) for k in keys]
        self._send({"options": keys, "probabilities": p, "choice": keys[p.index(max(p))]})

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


class TestJev(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _FakeJev)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.host = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        SEEN.clear()
        ATTENTION["attention"] = "bidirectional"

    def test_labels_from_option_probabilities(self):
        with tempfile.TemporaryDirectory() as d:
            llm = JevLLM(self.host, cache_dir=d)
            ps = [prof(column="bp"), prof(column="hetu")]
            dom = llm.domain("visits", ps, True)
            self.assertEqual(dom, DOMAINS[0])
            ans = llm.label_columns("visits", ps, [("x", "y", .3)] * 2, [0], dom, True)
            self.assertEqual(set(ans), {0})
            a = ans[0]
            self.assertEqual((a["privacy_role"], a["subtype"], a["art9"]), ("sensitive_attribute", "HEALTH_DATA", True))
            self.assertAlmostEqual(a["confidence"], .9)
            self.assertIn("sensitive_attribute 0.90", a["reason"])
            self.assertEqual(llm.model, "fake-4bit")
            n = len(SEEN)  # domain + role + subtype + art9
            self.assertEqual(n, 4)
            JevLLM(self.host, cache_dir=d).label_columns("visits", ps, [("x", "y", .3)] * 2, [0], dom, True)
            self.assertEqual(len(SEEN), n)  # second run served from cache

    def test_causal_server_is_refused(self):
        ATTENTION["attention"] = "causal"
        with tempfile.TemporaryDirectory() as d:
            llm = JevLLM(self.host, cache_dir=d)
            self.assertFalse(llm.available())
            self.assertEqual(llm.label_columns("t", [prof()], [None], [0], "", True), {})

    def test_no_server_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(JevLLM("http://127.0.0.1:9", cache_dir=d).domain("t", [prof()], True), "")

    def test_person_domains_still_trigger_art9_rules(self):
        self.assertEqual([bool(ART9_DOMAIN.search(x)) for x in DOMAINS], [True, True, True, False, False, False, False])

    def test_backend_switch(self):
        old = os.environ.get("DETECT_LLM_BACKEND")
        try:
            os.environ.pop("DETECT_LLM_BACKEND", None)
            self.assertIsInstance(make_llm("qwen2.5:7b"), JevLLM)
            os.environ["DETECT_LLM_BACKEND"] = "ollama"
            llm = make_llm("qwen2.5:7b")
            self.assertNotIsInstance(llm, JevLLM)
            self.assertIsInstance(llm, TableLLMv3)
        finally:
            os.environ.pop("DETECT_LLM_BACKEND", None) if old is None else os.environ.update(DETECT_LLM_BACKEND=old)

    def test_role_descriptions_cover_every_role(self):
        self.assertEqual(set(jev.ROLE_DESC), set(jev.ROLES))


if __name__ == "__main__":
    unittest.main()

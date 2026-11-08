"""Run: python3 -m unittest discover -s tests   (from server/detect)"""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pandas as pd

from pets_detect import patterns as P
from pets_detect.llm import LocalLLM
from pets_detect.profiler import mask_shape, profile_column
from pets_detect.rules import tier1


class TestChecksums(unittest.TestCase):
    def test_hetu(self):
        self.assertTrue(P.hetu_valid("070889-9652"))
        self.assertTrue(P.hetu_valid("271206A922C"))
        self.assertTrue(P.hetu_valid("200278907W"))
        self.assertFalse(P.hetu_valid("070889-9653"))
        self.assertFalse(P.hetu_valid("47109723"))

    def test_iban_luhn(self):
        self.assertTrue(P.iban_valid("FI38 9164 7381 0403 83"))
        self.assertFalse(P.iban_valid("FI38 9164 7381 0403 84"))
        self.assertTrue(P.luhn_valid("4111111111111111"))
        self.assertFalse(P.luhn_valid("4111111111111112"))

    def test_mask_shape_hides_values(self):
        self.assertEqual(mask_shape("070889-9652"), "9x6-9x4")
        self.assertNotIn("Oscar", mask_shape("Oscar Lindberg"))


def _prof(values, name="c01", idx=3):
    return profile_column("t", "tbl", name, pd.Series(values), idx, 10, np.random.default_rng(0))


class TestRules(unittest.TestCase):
    def test_value_rules_without_names(self):
        self.assertEqual(tier1(_prof(["070889-9652", "251263-976J", "271206A922C"] * 10)).subtype, "NATIONAL_ID")
        self.assertEqual(tier1(_prof([f"a{i}@x.example" for i in range(30)])).subtype, "EMAIL")
        self.assertEqual(tier1(_prof([f"10.0.{i}.{i}" for i in range(30)])).privacy_role, "technical_identifier")

    def test_prefixed_id_is_not_hostname(self):
        d = tier1(_prof([f"KC-{1000 + i}" for i in range(40)] * 2))
        self.assertEqual(d.privacy_role, "technical_identifier")
        self.assertNotEqual(d.subtype, "HOSTNAME")


class TestGuardrail(unittest.TestCase):
    def test_rejects_llm_answers_that_contradict_statistics(self):
        from pets_detect.pipeline import implausible
        campaign = _prof(["C-01", "C-02", "none"] * 50)
        self.assertIsNotNone(implausible("record_key", campaign))
        self.assertIsNotNone(implausible("technical_identifier", campaign))
        self.assertIsNotNone(implausible("free_text", _prof(["sms", "app", "totp"] * 50)))
        self.assertIsNone(implausible("record_key", _prof([f"R{i:05d}" for i in range(200)])))


class _FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._send({"models": [{"name": "fake:latest"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["format"]["properties"]["privacy_role"]["enum"]
        assert body["options"]["temperature"] == 0
        ans = {"privacy_role": "sensitive_attribute", "subtype": "FINANCIAL_DATA", "confidence": .8,
               "reason": "salary-like amounts in an HR export"}
        self._send({"message": {"content": json.dumps(ans)}})

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class TestLLM(unittest.TestCase):
    def test_fake_server_roundtrip_and_cache(self):
        srv = HTTPServer(("127.0.0.1", 0), _FakeOllama)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory() as tmp:
            llm = LocalLLM("fake", f"http://127.0.0.1:{srv.server_port}", cache_dir=tmp)
            p = _prof(["3 987,96", "3 106,52", "2 450,00"] * 10)
            d = llm.classify(p, [], tier1(p))
            self.assertEqual((d.privacy_role, d.source), ("sensitive_attribute", "llm"))
            srv.shutdown()
            d2 = llm.classify(p, [], tier1(p))
            self.assertEqual(d2.subtype, "FINANCIAL_DATA")

    def test_no_server_falls_back(self):
        llm = LocalLLM("fake", "http://127.0.0.1:9", cache_dir=tempfile.mkdtemp())
        self.assertIsNone(llm.classify(_prof(["x"] * 5), [], None))


if __name__ == "__main__":
    unittest.main()

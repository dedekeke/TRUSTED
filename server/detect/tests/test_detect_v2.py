"""Unit tests for detect v2 (run from server/detect: python3 -m unittest discover -s tests)."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pets_detect_v2.pipeline import guardrail  # noqa: E402
from pets_detect_v2.report import sanitize, pick_winner  # noqa: E402
from pets_detect_v2.table_llm import TableLLM, column_card  # noqa: E402


def prof(**kw):
    p = {"column": "c05", "table": "t", "shapes": ["9x6-9x4"], "samples": ["x"], "unique_ratio": .5, "n_unique": 50,
         "null_frac": 0.0, "num_min": None, "num_max": None, "frac_numeric": 0.0, "mean_words": 1.0, "fk_to": [],
         "m_url": 0.0, "m_iban": 0.0, "m_plate": 0.0, "m_email": 0.0, "m_phone": 0.0, "m_hetu": 0.0, "m_ipv4": 0.0,
         "m_mac": 0.0, "m_pan": 0.0, "m_pan_masked": 0.0}
    p.update(kw)
    return p


class TestGuardrail(unittest.TestCase):
    def test_record_key_needs_unique(self):
        self.assertIsNotNone(guardrail(prof(unique_ratio=.3), "record_key"))
        self.assertIsNone(guardrail(prof(unique_ratio=1.0), "record_key"))

    def test_free_text_needs_words(self):
        self.assertIsNotNone(guardrail(prof(mean_words=1.2), "free_text"))

    def test_pattern_subtype_needs_matching_values(self):
        self.assertIsNotNone(guardrail(prof(), "direct_identifier", "IBAN"))
        self.assertIsNone(guardrail(prof(m_iban=.9), "direct_identifier", "IBAN"))


class TestSanitize(unittest.TestCase):
    def test_no_raw_values(self):
        s = sanitize("values '070889-9652' and oscar@mail.example, also \"Oscar Lindberg\" 20460")
        for raw in ("070889-9652", "oscar@mail.example", "Oscar Lindberg", "20460"):
            self.assertNotIn(raw, s)
        self.assertIn("9x6-9x4", s)

    def test_keeps_small_numbers(self):
        self.assertIn("95%", sanitize("95% of values are dates"))


class TestWinner(unittest.TestCase):
    def run_(self, f1a, f1b, ra, rb):
        mk = lambda f, r: {"overall": {"macro_f1": f, "sensitive_recall": r}}
        return pick_winner({"runs": {"v1_blind": mk(f1a, ra), "v2_blind": mk(f1b, rb)}})[0]

    def test_criterion_1(self):
        self.assertEqual(self.run_(.80, .75, .5, .9), "v1")

    def test_criterion_2_when_close(self):
        self.assertEqual(self.run_(.757, .766, .78, .85), "v2")


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._send({"models": [{"name": "fake:1"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        props = body["format"]["properties"]
        if "table_domain" in props:
            out = {"table_domain": "pay roll of employees", "data_subject": "employee"}
        else:
            p = body["messages"][0]["content"]
            sens = "2 968,36" in p.split("COLUMN TO CLASSIFY:")[1]
            out = {"evidence": "pay" if sens else "code", "privacy_role": "sensitive_attribute" if sens
                   else "non_sensitive", "subtype": "FINANCIAL_DATA" if sens else "CATEGORY", "art9": False,
                   "confidence": .9}
        self._send({"message": {"content": json.dumps(out)}})

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class TestTableLLM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_answers_map_to_the_right_column(self, tmp=Path("/tmp")):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            llm = TableLLM("fake:1", f"http://127.0.0.1:{self.srv.server_port}", cache_dir=d)
            ps = [prof(column="c01", samples=["A1"]), prof(column="c02", samples=["2 968,36", "3 554,82"]),
                  prof(column="c03", samples=["AY-PS"])]
            dom, ans = llm.label_table("(hidden)", ps, [("record_key", "RECORD_ID", .99)] * 3, [1, 2], False)
            self.assertIn("employee", dom)
            self.assertEqual(set(ans), {1, 2})
            self.assertEqual(ans[1]["privacy_role"], "sensitive_attribute")
            self.assertEqual(ans[2]["privacy_role"], "non_sensitive")
            llm2 = TableLLM("fake:1", f"http://127.0.0.1:{self.srv.server_port}", cache_dir=d)
            llm2.label_table("(hidden)", ps, [("record_key", "RECORD_ID", .99)] * 3, [1, 2], False)
            self.assertEqual(llm2.calls, 0)

    def test_unsure_columns_get_no_guess(self):
        self.assertNotIn("current_guess", column_card(0, prof(), None, False))
        self.assertIn("current_guess", column_card(0, prof(), ("record_key", "RECORD_ID", .9), False))

    def test_unavailable_server_falls_back(self):
        llm = TableLLM("fake:1", "http://127.0.0.1:9", cache_dir="/tmp/v2-test-none")
        self.assertEqual(llm.label_table("t", [prof()], [None], [0], False), ("", {}))


if __name__ == "__main__":
    unittest.main()

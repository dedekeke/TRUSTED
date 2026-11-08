"""Unit tests for detect v3 (run from server/detect: python3 -m unittest discover -s tests)."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pets_detect_v3.llm_v3 import column_card, distribution  # noqa: E402
from pets_detect_v3.naming import NameScorer, is_code_like, mixed_view  # noqa: E402
from pets_detect_v3.router import Router  # noqa: E402

CAT = pd.DataFrame({"dataset": ["a", "a", "b"], "table": ["t", "t", "u"],
                    "column": ["patient_hetu", "arrival_ts", "customer_name"]})


class TestNaming(unittest.TestCase):
    def setUp(self):
        self.s = NameScorer(CAT)

    def test_codes_carry_nothing(self):
        for n in ("c07", "x3", "f_12", "col5", "a1b2c3d4"):
            self.assertTrue(is_code_like(n), n)
            self.assertEqual(self.s.score(n, [n], None)[0], 0.0)

    def test_words_are_informative_even_if_unseen(self):
        info, _ = self.s.score("sentiment", ["sentiment", "intent"], "zzz")
        self.assertGreaterEqual(info, 0.7)

    def test_vocabulary_and_hints_add_confidence(self):
        self.assertGreater(self.s.score("patient_hetu", ["patient_hetu"], "zzz")[0],
                           self.s.score("sentiment", ["sentiment"], "zzz")[0])

    def test_vocabulary_excludes_the_scored_dataset(self):
        a = self.s.score("arrival_mode", ["arrival_mode"], "a")[0]
        b = self.s.score("arrival_mode", ["arrival_mode"], "b")[0]
        self.assertLess(a, b)

    def test_word_among_codes_is_weaker(self):
        self.assertLess(self.s.score("salary", ["c01", "c02", "salary"], None)[0],
                        self.s.score("salary", ["name", "salary"], None)[0])

    def test_mixed_view_is_stable(self):
        p = {"dataset": "d", "table": "t", "column": "x_name", "col_index": 3, "table_columns": ["x_name"]}
        self.assertEqual(mixed_view(p)["column"], mixed_view(p)["column"])


class TestRouterWeight(unittest.TestCase):
    def w(self, mode, info, visible=True):
        r = Router.__new__(Router)
        r.mode = mode
        return r.weight(info, visible)

    def test_no_name_context_uses_values(self):
        self.assertEqual(self.w("A1", 0.0, visible=False), 0.0)

    def test_any_name_context_uses_knn(self):
        self.assertEqual(self.w("A1", 0.0, visible=True), 1.0)
        self.assertEqual(self.w("A1", 0.8), 1.0)

    def test_single_source_modes(self):
        self.assertEqual(self.w("knn", 0.0, False), 1.0)
        self.assertEqual(self.w("logreg", 1.0), 0.0)


def prof(**kw):
    p = {"column": "c05", "table": "t", "shapes": ["9"], "samples": ["0", "0", "0", "0"], "unique_ratio": .0001,
         "n_unique": 2, "null_frac": 0.0, "num_min": 0.0, "num_max": 1.0, "num_mean": .17, "num_decimals": 0.0,
         "frac_numeric": 1.0, "mean_words": 1.0, "fk_to": [], "n_rows": 1000, "top_values": [("0", 834), ("1", 166)]}
    p.update(kw)
    return p


class TestDistribution(unittest.TestCase):
    def test_low_cardinality_shows_all_values_with_shares(self):
        d = distribution(prof())
        self.assertIn("0 83%", d)
        self.assertIn("1 17%", d)

    def test_card_replaces_samples(self):
        c = column_card(0, prof(), None, False)
        self.assertNotIn("samples", c)
        self.assertIn("values", c)
        self.assertEqual(c["mean"], .17)

    def test_rare_values_are_marked(self):
        d = distribution(prof(n_unique=3, top_values=[("home", 990), ("icu", 9), ("died", 1)]))
        self.assertIn("died <1%", d)


if __name__ == "__main__":
    unittest.main()

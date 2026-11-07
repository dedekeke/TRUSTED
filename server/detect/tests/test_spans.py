"""Unit tests for the span detector (run from server/detect: python3 -m unittest discover -s tests)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pets_detect_v2.spans import regex, spoken  # noqa: E402
from pets_detect_v2.spans.merge import assign_entities, merge  # noqa: E402
from pets_detect_v2.spans.run import example_html  # noqa: E402
from pets_detect_v2.spans.tagger import Dictionaries, Tagger  # noqa: E402


def found(text, fn):
    return [(s["label"], text[s["start"]:s["end"]]) for s in fn(text)]


class TestRegex(unittest.TestCase):
    def test_checksums(self):
        self.assertIn(("NATIONAL_ID", "070889-9652"), found("hetu 070889-9652.", regex.find))
        self.assertNotIn("NATIONAL_ID", [l for l, _ in found("hetu 070889-9653.", regex.find)])  # bad check char
        self.assertIn(("IBAN", "FI75 9563 3224 8375 95"), found("tili FI75 9563 3224 8375 95", regex.find))

    def test_private_ip_is_not_personal(self):
        labs = found("router 192.168.1.1, julkinen 100.84.190.65", regex.find)
        self.assertEqual(labs, [("IP_ADDRESS", "100.84.190.65")])

    def test_context_spans(self):
        self.assertIn(("PAYMENT_CARD", "3259"), found("the card ending 3259.", regex.find))
        self.assertIn(("SECRET", "petri1970"), found("salasanani on petri1970! jos", regex.find))
        self.assertIn(("AGE", "71"), found("Olen 71-vuotias", regex.find))

    def test_b2_misses_spoken(self):
        self.assertEqual(regex.b2_spans("hetu on 050182 viiva 941 j"), [])


class TestSpoken(unittest.TestCase):
    def test_phone_words(self):
        t = "numerosta nolla neljä neljä, kuusi kolme yksi, nolla neljä yksi yhdeksän, jossa"
        self.assertEqual(found(t, spoken.find), [("PHONE", "nolla neljä neljä, kuusi kolme yksi, nolla neljä yksi yhdeksän")])

    def test_iban_words(self):
        t = "tilille f i seitsemän kuusi, yhdeksän kuusi kahdeksan kolme, neljä kahdeksan"
        self.assertEqual(found(t, spoken.find)[0][0], "IBAN")

    def test_hetu_and_email(self):
        self.assertIn(("NATIONAL_ID", "070889 streck 965 2"),
                      found("personbeteckningen är 070889 streck 965 2", spoken.find))
        self.assertIn(("EMAIL", "akotkaaho snabel-a nordmail punkt example"),
                      found("Din e-post är akotkaaho snabel-a nordmail punkt example, ok?", spoken.find))

    def test_ordinary_words_are_not_numbers(self):
        self.assertEqual(spoken.find("I have three kids and one dog"), [])


class TestMerge(unittest.TestCase):
    def test_priority_and_widening(self):
        sp = [{"start": 0, "end": 10, "label": "PHONE", "source": "tagger", "confidence": .5},
              {"start": 2, "end": 8, "label": "NATIONAL_ID", "source": "regex", "confidence": .99},
              {"start": 20, "end": 25, "label": "ADDRESS", "source": "regex", "confidence": .8},
              {"start": 15, "end": 30, "label": "ADDRESS", "source": "tagger", "confidence": .7}]
        m = merge(sp)
        self.assertEqual([(s["label"], s["start"], s["end"]) for s in m],
                         [("NATIONAL_ID", 2, 8), ("ADDRESS", 15, 30)])

    def test_entity_ids(self):
        t1, t2 = "Asiakas Oscar Lindberg soitti", "Kiitos Oscar"
        g = {"c1": [("r1", t1, [{"start": 8, "end": 22, "label": "PERSON"}]),
                    ("r2", t2, [{"start": 7, "end": 12, "label": "PERSON"}])]}
        assign_entities(g)
        self.assertEqual(g["c1"][0][2][0]["entity_id"], g["c1"][1][2][0]["entity_id"])


class TestTagger(unittest.TestCase):
    def test_learns_names_from_context(self):
        recs = []
        for n in ("Aino Virtanen", "Mika Korhonen", "Sari Nieminen", "Juha Mäkinen", "Liisa Laine") * 20:
            t = f"Asiakas {n} soitti tänään"
            recs.append((t, [{"start": 8, "end": 8 + len(n), "label": "PERSON"}]))
            recs.append(("Lasku lähetettiin tänään", []))
        tg = Tagger(Dictionaries()).fit(recs)
        out = tg.predict("Asiakas Pekka Salonen soitti tänään")
        self.assertTrue(any(s["label"] == "PERSON" and "Salonen" in "Asiakas Pekka Salonen soitti tänään"[s["start"]:s["end"]]
                            for s in out))


class TestExamples(unittest.TestCase):
    def test_no_raw_pii_in_examples(self):
        t = "Asiakas Oscar Lindberg, hetu 070889-9652"
        gold = [{"start": 8, "end": 22, "label": "PERSON"}, {"start": 29, "end": 40, "label": "NATIONAL_ID"}]
        pred = [{"start": 29, "end": 40, "label": "NATIONAL_ID"}]  # the name is missed
        h = example_html(t, pred, gold)
        self.assertNotIn("Oscar", h)
        self.assertNotIn("070889", h)
        self.assertIn("MISSED PERSON", h)


if __name__ == "__main__":
    unittest.main()

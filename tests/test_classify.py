"""Classifier tests: correctness on known cases + determinism.

Offline and deterministic (no network), so they run inside the Nix sandbox
during `nix build`.
"""

import unittest

from nixdoc_sentiment import categories as C
from nixdoc_sentiment.classify import classify_record
from nixdoc_sentiment.schema import Record


def mk(text, title=None):
    return Record(id="t:1", source="test", native_id="1",
                  url="http://x", created_utc="2025-01-01T00:00:00Z",
                  author="a", title=title, text=text, query="q")


class TestClassifier(unittest.TestCase):
    def test_real_hn_negative_sample(self):
        # Verbatim shape of a real HN comment observed from the Algolia API.
        text = ("I found the NixOS documentation to be very poor and the lack "
                "of a single set of best practices to be frustrating.")
        r = classify_record(mk(text))
        self.assertTrue(r["doc_relevant"])
        self.assertIn("frustration", r["feelings"])
        self.assertLess(r["polarity"], 0.0)
        self.assertEqual(r["expectation"], "not_met")

    def test_positive_sample_met(self):
        text = ("The nix.dev documentation is excellent and well documented; "
                "it answered my question and the examples are great.")
        r = classify_record(mk(text))
        self.assertTrue(r["doc_relevant"])
        self.assertGreater(r["polarity"], 0.0)
        self.assertEqual(r["expectation"], "met")
        self.assertIn("examples", r["aspects"])

    def test_aspect_detection_multi(self):
        text = ("The manual is outdated and the wiki is fragmented; as a "
                "beginner the learning curve was steep.")
        r = classify_record(mk(text))
        for asp in ("accuracy", "structure", "onboarding"):
            self.assertIn(asp, r["aspects"])

    def test_non_doc_relevant_dropped(self):
        r = classify_record(mk("The package builds fine on aarch64 now."))
        self.assertFalse(r["doc_relevant"])
        self.assertEqual(r["aspects"], [])

    def test_word_boundary_no_false_positive(self):
        # "docs" must not match inside another word.
        # 'docs' must not substring-match 'docker'; no doc terms present.
        r = classify_record(mk("the docker daemon restarted"))
        self.assertFalse(r["doc_relevant"])

    def test_polarity_range(self):
        for r in (classify_record(mk("poor bad useless broken confusing")),
                  classify_record(mk("clear helpful useful great excellent"))):
            self.assertGreaterEqual(r["polarity"], -1.0)
            self.assertLessEqual(r["polarity"], 1.0)

    def test_deterministic(self):
        text = "The docs are confusing and outdated; I gave up and wrote my own."
        a = classify_record(mk(text))
        b = classify_record(mk(text))
        self.assertEqual(a, b)

    def test_scheme_version_stamped(self):
        r = classify_record(mk("the documentation is fine"))
        self.assertEqual(r["scheme_version"], C.SCHEME_VERSION)

    def test_negation_suppresses_positive(self):
        # "not helpful" must not count as positive; "not documented" is negative.
        r = classify_record(mk("The docs are not helpful and this is not documented."))
        self.assertNotIn("helpful", r["cues"]["polarity"]["positive"])
        self.assertLessEqual(r["polarity"], 0.0)

    def test_negation_suppresses_feeling(self):
        r = classify_record(mk("Honestly the manual is not frustrating at all."))
        self.assertNotIn("frustration", r["feelings"])

    def test_conditional_love_not_delight(self):
        # A wish, not delight about the docs -> delight must not fire.
        r = classify_record(mk("I would love better documentation for flakes."))
        self.assertNotIn("delight", r["feelings"])

    def test_superlative_not_delight_generic(self):
        # "the best" on an alternative/aspiration must not read as delight.
        r = classify_record(mk("The Arch wiki is the best way to learn; nixos docs lag."))
        self.assertNotIn("delight", r["feelings"])

    def test_genuine_delight_survives(self):
        r = classify_record(mk("I love the nixos documentation, the examples are amazing."))
        self.assertIn("delight", r["feelings"])



if __name__ == "__main__":
    unittest.main()

"""Characterization tests for Word comparison helpers."""

from django.test import SimpleTestCase

from word.service.compare import (
    align_paragraphs_indexed,
    auto_thresholds,
    ratio,
    split_sentences,
    tokenize_words,
    u_normalize,
)


class WordComparisonHelperTests(SimpleTestCase):
    """Protect legacy Word comparison behavior during view decomposition."""

    def test_normalize_removes_zero_width_and_collapses_whitespace(self):
        self.assertEqual(u_normalize("  A\u00A0\u200B  B\r\n "), "A B")

    def test_split_sentences_packs_short_sentences(self):
        self.assertEqual(split_sentences("One. Two? Three!"), ["One. Two? Three!"])
        self.assertEqual(split_sentences(""), [])

    def test_tokenize_words_keeps_punctuation_tokens(self):
        self.assertEqual(tokenize_words("Hello, AW!"), ["Hello", ",", "AW", "!"])

    def test_ratio_uses_sequence_matcher_similarity(self):
        self.assertEqual(ratio("same", "same"), 1.0)
        self.assertLess(ratio("abc", "xyz"), 0.5)

    def test_auto_thresholds_return_legacy_defaults_for_empty_inputs(self):
        self.assertEqual(auto_thresholds([], []), (0.92, 0.86))

    def test_align_paragraphs_keeps_equal_insert_delete_and_replace_shapes(self):
        first_lines = [(0, "same"), (1, "old text"), (2, "removed")]
        second_lines = [(0, "same"), (1, "new text"), (2, "added")]
        aligned = align_paragraphs_indexed(first_lines, second_lines, 0.99, 0.50)
        self.assertEqual(aligned[0], (0, "same", 0, "same", "equal"))
        self.assertIn((1, "old text", 1, "new text", "replace"), aligned)

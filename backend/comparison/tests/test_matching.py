from django.test import SimpleTestCase

from comparison.contracts import CompareError, resolve_options, PRESETS
from comparison.matching import compare_text
from comparison.contracts import TextBlock


class MatchingTests(SimpleTestCase):
    def test_presets_and_invalid_thresholds(self):
        self.assertEqual(resolve_options({}).equal_ratio, .92)
        self.assertEqual(PRESETS['strict']['weak_equal_ratio'], .85)
        for values in [(float('nan'), .5), (.8, .9), (True, .5), (.8, 0)]:
            with self.subTest(values=values), self.assertRaises(CompareError):
                resolve_options({'preset': 'custom', 'equal_ratio': values[0], 'weak_equal_ratio': values[1]})

    def test_high_similarity_never_hides_number_change(self):
        rows = compare_text([TextBlock('The allowed pressure is 100 bar.', 'P1')],
                            [TextBlock('The allowed pressure is 101 bar.', 'P2')], resolve_options({}))
        self.assertEqual(rows[0].change, 'replace')
        self.assertEqual(rows[0].strength, 'strong')
        self.assertIn('101', rows[0].new)

    def test_unrelated_candidates_are_not_consumed(self):
        rows = compare_text([TextBlock('abc', 'P1')], [TextBlock('xyz', 'P2')], resolve_options({}))
        self.assertEqual([row.change for row in rows], ['delete', 'insert'])
        self.assertEqual([row.new for row in rows if row.new_location], ['xyz'])

    def test_repeated_blocks_preserve_every_occurrence(self):
        old = [TextBlock(text, str(i)) for i, text in enumerate(['same', 'same', 'old'])]
        new = [TextBlock(text, str(i)) for i, text in enumerate(['same', 'new', 'same', 'last'])]
        rows = compare_text(old, new, resolve_options({}))
        self.assertCountEqual([r.old_location for r in rows if r.old_location], ['0', '1', '2'])
        self.assertCountEqual([r.new_location for r in rows if r.new_location], ['0', '1', '2', '3'])

    def test_whitespace_change_is_visible(self):
        rows = compare_text([TextBlock('A  B', 'P1')], [TextBlock('A B', 'P2')], resolve_options({}))
        self.assertEqual(rows[0].change, 'replace')

    def test_possible_match_and_weak_boundary_keep_both_sources(self):
        options = resolve_options({'preset': 'custom', 'equal_ratio': .9, 'weak_equal_ratio': .5})
        rows = compare_text([TextBlock('ab', 'Old')], [TextBlock('ac', 'New')], options)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].change, 'replace')
        self.assertEqual(rows[0].strength, 'possible')
        self.assertEqual(rows[0].similarity, .5)

    def test_every_preset_keeps_exact_and_changed_content_separate(self):
        for preset in PRESETS:
            with self.subTest(preset=preset):
                old = [TextBlock('The allowed pressure is 100 bar.', 'Old')]
                new = [TextBlock('The allowed pressure is 101 bar.', 'New')]
                rows = compare_text(old, new, resolve_options({'preset': preset}))
                self.assertFalse(any(row.change == 'equal' for row in rows))
                self.assertEqual(sum(bool(row.old_location) for row in rows), 1)
                self.assertEqual(sum(bool(row.new_location) for row in rows), 1)

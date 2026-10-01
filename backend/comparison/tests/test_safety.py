from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from comparison.contracts import CompareError, resolve_options, TextBlock
from comparison.matching import compare_text
from comparison.packaging import create_package, read_package
from comparison.tests.test_jobs import word
from comparison.tests.test_excel import book
from comparison.excel import inspect_excel


class ComparisonSafetyTests(SimpleTestCase):
    def test_package_is_deterministic_and_only_contains_fixed_members(self):
        data = word('Test content')
        def package():
            return create_package(SimpleUploadedFile('a.docx', data), SimpleUploadedFile('b.docx', data))[0].read()
        first, second = package(), package()
        self.assertEqual(first, second)
        with ZipFile(BytesIO(first)) as archive:
            self.assertEqual(sorted(archive.namelist()), ['first', 'manifest.json', 'second'])
        family, files = read_package(BytesIO(first))
        self.assertEqual(family, 'word')
        self.assertEqual(files, [data, data])

    def test_tampered_member_fails_individual_digest(self):
        data = word('Test content')
        package, _ = create_package(SimpleUploadedFile('a.docx', data), SimpleUploadedFile('b.docx', data))
        target = BytesIO()
        with ZipFile(package) as original, ZipFile(target, 'w') as changed:
            for name in original.namelist():
                changed.writestr(name, b'changed' if name == 'second' else original.read(name))
        with self.assertRaises(CompareError) as raised:
            read_package(BytesIO(target.getvalue()))
        self.assertEqual(raised.exception.code, 'COMPARE_INPUT_CORRUPT')

    def test_candidate_budget_fails_explicitly_and_checkpoint_can_cancel(self):
        old = [TextBlock('A', '1'), TextBlock('B', '2')]
        new = [TextBlock('C', '1'), TextBlock('D', '2')]
        with patch('comparison.matching.MAX_CANDIDATES', 1), self.assertRaises(CompareError):
            compare_text(old, new, resolve_options({}))
        from jobs.contracts import JobCancelled
        def cancel():
            raise JobCancelled()
        with self.assertRaises(JobCancelled):
            compare_text(old, new, resolve_options({}), cancel)

    def test_expensive_content_matching_still_returns_guidance(self):
        old = book([['Name'], ['A'], ['B']])
        new = book([['Name'], ['C'], ['D']])
        with patch('comparison.excel_matching.MAX_CANDIDATES', 1):
            result = inspect_excel(old, new, {}, resolve_options({}, 'excel'))
        self.assertTrue(result['matching']['requires_input'])
        self.assertIn('identity', result['matching']['reason'].lower())

from datetime import datetime, timezone
from unittest.mock import patch

from django import forms
from django.test import SimpleTestCase
from django.utils import translation
from django.utils.formats import date_format


class DisplayDateTests(SimpleTestCase):
    def test_english_and_turkish_ui_use_numeric_turkish_dates(self):
        value = datetime(2026, 10, 13, 15, 5, 6)
        for language in ('en-us', 'tr'):
            with self.subTest(language=language), translation.override(language):
                self.assertEqual(date_format(value), '13.10.2026')
                self.assertEqual(date_format(value, 'DATETIME_FORMAT'), '13.10.2026 15:05:06')

    def test_date_inputs_display_turkish_dates_and_keep_iso_compatibility(self):
        with translation.override('en-us'):
            field = forms.DateField()
            self.assertEqual(field.widget.format_value(datetime(2026, 10, 13)), '13.10.2026')
            self.assertEqual(field.clean('13.10.2026').isoformat(), '2026-10-13')
            self.assertEqual(field.clean('2026-10-13').isoformat(), '2026-10-13')

    def test_pdf_report_creation_time_uses_istanbul_even_on_utc_host(self):
        from pdf.comparer.pdf_extractor import PDFDocument
        from pdf.comparer.report_generator import HTMLReportGenerator
        from pdf.comparer.text_comparator import ComparisonOptions, ComparisonResult, PDFComparator

        document = PDFDocument('fixture.pdf', 0, [], {})
        result = ComparisonResult(
            document, document, PDFComparator().compare_text('', ''), ComparisonOptions()
        )
        fixed_now = datetime(2026, 10, 13, 22, 5, 6, tzinfo=timezone.utc)
        with patch('pdf.comparer.report_generator.datetime') as clock:
            clock.now.side_effect = lambda tz=None: fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)
            output = HTMLReportGenerator().generate_report(result)
        self.assertIn('14.10.2026 01:05:06', output)

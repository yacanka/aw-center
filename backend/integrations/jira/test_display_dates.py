from django.test import SimpleTestCase

from integrations.jira.client import ISO_time_to_string


class JiraDisplayDateTests(SimpleTestCase):
    def test_source_updated_date_uses_istanbul_day(self):
        self.assertEqual(ISO_time_to_string('2026-10-13T22:05:06+00:00'), '14.10.2026')

    def test_naive_legacy_timestamp_keeps_its_calendar_date(self):
        self.assertEqual(ISO_time_to_string('2026-10-13 22:05:06.000'), '13.10.2026')

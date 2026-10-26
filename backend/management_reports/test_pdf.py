"""Content and pagination regressions for saved management-report PDFs."""

from copy import deepcopy
from io import BytesIO
from unittest import TestCase

from pypdf import PdfReader

from management_reports.pdf import build_report_pdf


def sample_report():
    metrics = {
        "document_count": 12,
        "issued_count": 9,
        "approved_count": 6,
        "approval_percentage": 50.0,
        "scheduled_count": 10,
        "schedule_variance": -1,
        "high_risk_count": 2,
        "action_overdue_count": 3,
        "action_due_soon_count": 4,
        "unassigned_count": 1,
        "pending_review_count": 2,
        "pending_approval_count": 1,
        "data_quality_issue_count": 0,
    }
    return {
        "id": "24faad96-6ed6-4254-8e1e-a32dc62257c0",
        "title": "Haftalık Yönetim Özeti - Özgür",
        "management_note": "İnceleme kapasitesi için karar bekleniyor. Çözüm: ek ekip.",
        "captured_at": "2026-10-27T12:30:00+03:00",
        "week_start": "2026-10-26",
        "schema_version": 1,
        "project_slugs": ["ozgur"],
        "totals": metrics,
        "projects": [{"slug": "ozgur", "display_name": "Özgür", **metrics}],
        "priorities": [{
            "document_id": "doc-1", "project_slug": "ozgur",
            "project_name": "Özgür", "name": "Gövde inceleme dosyası",
            "status": "authority_review", "score": 65, "level": "high",
            "stage_age_days": 35, "reason": "Otorite incelemesi uzadı.",
            "owner": "Çağrı Şahin", "next_action_due_date": "2026-10-30",
        }],
    }


def unavailable_comparison():
    return {"available": False, "baseline": None, "elapsed_days": None, "deltas": None}


class ManagementReportPdfTests(TestCase):
    def text(self, data):
        return "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)

    def test_searchable_pdf_preserves_turkish_and_capture_context(self):
        report = sample_report()
        before = deepcopy(report)
        data = build_report_pdf(report, unavailable_comparison())
        text = self.text(data)

        self.assertTrue(data.startswith(b"%PDF-"))
        for value in (report["title"], "Özgür", "Çağrı Şahin", "Gövde inceleme dosyası"):
            self.assertIn(value, text)
        self.assertIn("2026-10-27", text)
        self.assertIn("No previous-week report", text)
        self.assertIn("Authority approved", text)
        self.assertEqual(report, before)

    def test_comparison_has_dates_and_net_deltas(self):
        comparison = {
            "available": True,
            "baseline": {"id": "baseline", "title": "Previous week",
                         "captured_at": "2026-10-20T12:30:00+03:00", "week_start": "2026-10-19"},
            "elapsed_days": 7,
            "deltas": {key: 0 for key in sample_report()["totals"]},
        }
        comparison["deltas"].update({"approved_count": 3, "approval_percentage": 25.0,
                                      "action_overdue_count": -2, "document_count": 1})
        text = self.text(build_report_pdf(sample_report(), comparison))
        self.assertIn("2026-10-20", text)
        self.assertIn("Net change", text)
        self.assertIn("+3", text)
        self.assertIn("+25.0 pp", text)
        self.assertIn("-2", text)

    def test_long_note_and_markup_are_escaped_and_paginate_without_losing_content(self):
        report = sample_report()
        report["title"] = "<b>Literal title & context</b>"
        report["management_note"] = ("Ölçüm & karar <review> ayrıntıları. " * 55) + " END-OF-NOTE"
        report["priorities"][0]["name"] = "x" * 256
        report["priorities"][0]["reason"] = "Uzayan inceleme için karar gerekiyor. " * 12
        report["priorities"] = [deepcopy(report["priorities"][0]) for _ in range(5)]
        data = build_report_pdf(report, unavailable_comparison())
        reader = PdfReader(BytesIO(data))
        text = self.text(data)
        self.assertIn("Literal title & context", text)
        self.assertIn("<review>", text)
        self.assertIn("END-OF-NOTE", text)
        self.assertGreater(len(reader.pages), 1)
        self.assertTrue(all(page.mediabox.width > 0 for page in reader.pages))

    def test_empty_report_explains_zero_denominator(self):
        report = sample_report()
        report["totals"] = {key: 0 for key in report["totals"]}
        report["projects"] = [{"slug": "ozgur", "display_name": "Özgür", **report["totals"]}]
        report["priorities"] = []
        text = self.text(build_report_pdf(report, unavailable_comparison()))
        self.assertIn("No active documents", text)
        self.assertIn("No risk priorities", text)

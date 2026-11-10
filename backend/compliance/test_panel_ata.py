"""Independent document Panel/ATA selections keep their canonical relation."""
from orgs.models import Panel
from .test_document_identity import DocumentIdentityTests


class DocumentPanelAtaTests(DocumentIdentityTests):
    def setUp(self):
        super().setUp()
        self.first = Panel.objects.create(project=self.project, name="Systems", ata="27-00")
        self.second = Panel.objects.create(project=self.project, name="Systems", ata="28-00")
        self.other = Panel.objects.create(project=self.project, name="Structures", ata="53-00")

    def test_create_and_partial_update_reject_incompatible_ata_without_history_change(self):
        rejected = self.create(panel=self.first.pk, ata="28-00")
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertIn("ata", rejected.data["errors"])
        accepted = self.create(panel=self.first.pk, ata="27-00")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        from .models import ComplianceDocument
        document = ComplianceDocument.objects.get(pk=accepted.data["id"])
        history_count = document.history.count()
        url = self.base + f"{document.pk}/"
        for payload in ({"ata": "28-00"}, {"panel": self.second.pk, "ata": "27-00"}, {"panel": None, "ata": "27-00"}):
            response = self.client.patch(url, {"version": 1, **payload}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        document.refresh_from_db()
        self.assertEqual(document.version, 1)
        self.assertEqual(document.panel_id, self.first.pk)
        self.assertEqual(document.history.count(), history_count)
        updated = self.client.patch(url, {"version": 1, "panel": self.second.pk, "ata": "28-00"}, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["ata"], "28-00")
        self.assertEqual(updated.data["version"], 2)

    def test_ata_and_panel_filters_intersect_independently_and_schema_exposes_ata(self):
        self.create(name="First", panel=self.first.pk)
        self.create(name="Second", panel=self.second.pk)
        self.create(name="Third", panel=self.other.pk)
        self.assertEqual(self.client.get(self.base, {"ata": ["28-00"]}).data["count"], 1)
        self.assertEqual(self.client.get(self.base, {"panel": [self.first.pk, self.second.pk]}).data["count"], 2)
        by_name = self.client.get(self.base, {"panel_name": ["Systems"]})
        self.assertEqual(by_name.data["count"], 2)
        narrowed = self.client.get(self.base, {"panel_name": ["Systems"], "ata": ["28-00"]})
        self.assertEqual(narrowed.data["count"], 1)
        self.assertEqual(narrowed.data["results"][0]["name"], "Second")
        self.assertEqual(self.client.get(self.base, {"panel": [self.first.pk], "ata": ["28-00"]}).data["count"], 0)
        fields = {field["key"]: field for field in self.client.get(self.base + "fields/").data["fields"]}
        self.assertEqual(fields["ata"]["filter_kind"], "select")
        self.assertEqual(fields["ata"]["option_source"], "atas")

    def test_name_filter_accepts_the_full_panel_name_length(self):
        self.first.name = "P" * 255
        self.first.save()
        self.create(name="Long panel", panel=self.first.pk)
        response = self.client.get(self.base, {"panel_name": [self.first.name], "ordering": "panel_name"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)

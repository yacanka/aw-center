"""Private business metadata must not change technical authorization or outputs."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from zipfile import ZipFile

from django.test import SimpleTestCase, override_settings
from docx import Document

from awcenter.workflow_test_utils import private_workflow_configuration
from excel.cover_pages import resolve_project_label, create_cover_page_archive, REQUIRED_COLUMNS
from projects.registry import PROJECT_DEFINITIONS, find_project_by_jira_component, get_project_definition


class PrivateProjectConfigurationTests(SimpleTestCase):
    def setUp(self):
        self.configuration = self.enterContext(private_workflow_configuration())
        self.path = Path(self.configuration["PROJECT_CONFIGURATION_FILE"])

    def test_component_and_alias_use_external_metadata_without_changing_capabilities(self):
        data = json.loads(self.path.read_text())
        data["projects"]["hys"].update(jira_component="Örnek Bileşen", aliases=["ORNEK"])
        self.path.write_text(json.dumps(data))
        for component in (" ÖRNEK BİLEŞEN ", "orneK"):
            with self.subTest(component=component):
                definition = find_project_by_jira_component(component)
                self.assertIsNotNone(definition)
                self.assertEqual(definition.slug, "hys")
                self.assertEqual(definition.dcc_label, "Example hys")
                self.assertEqual(definition.capabilities, ("jira", "compliance", "organization"))
        self.assertIsNone(PROJECT_DEFINITIONS["hys"].jira_component)

    @override_settings(PROJECT_CONFIGURATION_FILE="")
    def test_technical_catalog_remains_available_without_business_configuration(self):
        self.assertEqual(get_project_definition("hys").slug, "hys")
        self.assertEqual(PROJECT_DEFINITIONS["hurkus"].capabilities, ("jira",))
        from rest_framework.exceptions import APIException
        with self.assertRaises(APIException) as raised:
            find_project_by_jira_component("Example Component")
        self.assertEqual(raised.exception.default_code, "PROJECT_CONFIGURATION_UNAVAILABLE")

    def test_invalid_policy_cannot_change_handlers_or_grant_capabilities(self):
        original = json.loads(self.path.read_text())
        invalid = []
        modified = deepcopy(original)
        modified["projects"]["hys"]["capabilities"] = ["jira", "admin"]
        invalid.append(modified)
        modified = deepcopy(original)
        modified["projects"]["hys"]["dcc_template_name"] = "../outside.docx"
        invalid.append(modified)
        modified = deepcopy(original)
        modified["projects"]["hys"]["aliases"] = ["PIKU"]
        invalid.append(modified)
        modified = deepcopy(original)
        del modified["projects"]["hys"]
        invalid.append(modified)
        for data in invalid:
            with self.subTest(case=invalid.index(data)):
                self.path.write_text(json.dumps(data))
                from rest_framework.exceptions import APIException
                with self.assertRaises(APIException) as raised:
                    find_project_by_jira_component("HYS")
                self.assertNotIn(str(self.path), str(raised.exception))
                self.assertEqual(PROJECT_DEFINITIONS["hys"].capabilities, ("jira", "compliance", "organization"))

    def test_cover_page_matching_is_external_and_keeps_case_insensitive_contains(self):
        self.assertEqual(resolve_project_label("prefix-example-suffix"), "Example Work Package")
        self.assertEqual(resolve_project_label("OTHER-1"), "Example Project")

    @override_settings(COVER_PAGE_TEMPLATE_PATH="/missing-synthetic-template.docx")
    def test_cover_zip_keeps_first_row_label_for_every_docx(self):
        import pandas as pd
        rows = []
        for number in ("EXAMPLE/001", "OTHER/002"):
            row = {key: "Synthetic" for key in REQUIRED_COLUMNS}
            row["Cover Page Number"] = number
            rows.append(row)
        output = self.path.with_name("covers.zip")
        with patch("excel.cover_pages.update_progress"):
            create_cover_page_archive("synthetic-job", pd.DataFrame(rows), output)
        with ZipFile(output) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            for name in archive.namelist():
                doc = Document(BytesIO(archive.read(name)))
                self.assertEqual(doc.paragraphs[1].text, "Example Work Package")

    def test_custom_docx_uses_private_label_with_xml_escaping_and_stable_filename(self):
        import pandas as pd
        data = json.loads(self.path.read_text())
        data["cover_pages"]["match_label"] = "Example & Work <Package>"
        self.path.write_text(json.dumps(data))
        template = self.path.with_name("template.docx")
        doc = Document()
        doc.add_paragraph("{{ project_name }}")
        doc.save(template)
        row = {key: "Synthetic" for key in REQUIRED_COLUMNS}
        row["Cover Page Number"] = "EXAMPLE/001"
        output = self.path.with_name("custom-covers.zip")
        with override_settings(COVER_PAGE_TEMPLATE_PATH=template), patch("excel.cover_pages.update_progress"):
            create_cover_page_archive("synthetic-job", pd.DataFrame([row]), output)
        with ZipFile(output) as archive:
            self.assertEqual(archive.namelist(), ["0001-EXAMPLE_001.docx"])
            doc = Document(BytesIO(archive.read(archive.namelist()[0])))
            self.assertEqual(doc.paragraphs[0].text, "Example & Work <Package>")

    def test_multi_component_resolution_reads_one_configuration_snapshot(self):
        from projects.registry import get_project_configuration
        from integrations.jira.services.project_resolver import resolve_projects_from_jira_components
        with patch('projects.registry.get_project_configuration', wraps=get_project_configuration) as read:
            result = resolve_projects_from_jira_components(['HYS', 'PIKU', 'HYS'])
        self.assertEqual([item.slug for item in result], ['hys', 'piku'])
        self.assertEqual(read.call_count, 1)

"""Private business metadata must not change technical authorization or outputs."""

import json
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from zipfile import ZipFile

from django.test import SimpleTestCase, override_settings
from docx import Document

from awcenter.workflow_test_utils import private_workflow_configuration
from excel.cover_pages import resolve_project_label, create_cover_page_archive, REQUIRED_COLUMNS
from projects.configuration import ProjectConfigurationError
from projects.registry import (
    PROJECT_DEFINITIONS, find_project_by_jira_component, get_project_definition,
    get_project_integration_definition,
)


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

    def test_invalid_template_and_unknown_fields_preserve_component_and_policy(self):
        data = json.loads(self.path.read_text())
        data["projects"]["hys"].update(
            dcc_template_name="../outside.docx", capabilities=["admin"], dcc_controller="unknown",
        )
        self.path.write_text(json.dumps(data))
        definition = find_project_by_jira_component("HYS")
        self.assertIsNone(definition.dcc_template_name)
        self.assertEqual(definition.mail_template_name, "hys_mail_template")
        self.assertEqual(definition.capabilities, PROJECT_DEFINITIONS["hys"].capabilities)
        self.assertEqual(definition.dcc_controller, PROJECT_DEFINITIONS["hys"].dcc_controller)

    def test_valid_alias_and_template_survive_missing_component_and_invalid_mail(self):
        from integrations.jira.services.template_resolver import resolve_dcc_template_path

        data = json.loads(self.path.read_text())
        data["projects"] = {"hys": {
            "aliases": ["Alias", None, " ALIAS "], "dcc_template_name": "example.docx",
            "mail_template_name": "invalid/name", "dcc_label": 42,
        }}
        self.path.write_text(json.dumps(data))
        definition = find_project_by_jira_component("alias")
        self.assertEqual(definition.slug, "hys")
        self.assertIsNone(definition.mail_template_name)
        self.assertIsNone(definition.dcc_label)
        self.assertIsNone(definition.jira_component)
        template = self.path.with_name("example.docx")
        Document().save(template)
        with patch("integrations.jira.services.template_resolver.TEMPLATE_DIR", template.parent):
            self.assertEqual(resolve_dcc_template_path(definition), template.resolve())

    def test_invalid_alias_list_preserves_component(self):
        data = json.loads(self.path.read_text())
        for aliases in ("Alias", ["Alias"] * 21):
            with self.subTest(aliases=aliases):
                data["projects"]["hys"]["aliases"] = aliases
                self.path.write_text(json.dumps(data))
                self.assertEqual(find_project_by_jira_component("HYS").slug, "hys")
                self.assertIsNone(find_project_by_jira_component("Alias"))

    def test_single_configured_project_is_sufficient(self):
        data = json.loads(self.path.read_text())
        record = data["projects"]["hys"]
        data["projects"] = {"hys": record, "unknown": record}
        self.path.write_text(json.dumps(data))
        self.assertEqual(find_project_by_jira_component("HYS").slug, "hys")
        self.assertEqual(get_project_integration_definition("hys").dcc_template_name, record["dcc_template_name"])
        self.assertIsNone(find_project_by_jira_component("PIKU"))
        with self.assertRaises(ProjectConfigurationError):
            get_project_integration_definition("piku")

    def test_shared_component_is_ambiguous_but_unique_names_still_resolve(self):
        data = json.loads(self.path.read_text())
        data["projects"]["hys"]["aliases"] = [" piku "]
        data["projects"]["piku"]["aliases"] = ["piku-alias"]
        self.path.write_text(json.dumps(data))
        self.assertIsNone(find_project_by_jira_component("PIKU"))
        self.assertEqual(find_project_by_jira_component("piku-alias").slug, "piku")
        self.assertEqual(find_project_by_jira_component("HYS").slug, "hys")

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

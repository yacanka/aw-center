"""Synthetic private workflow configuration for tests and spawned test workers."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import override_settings


@contextmanager
def private_workflow_configuration():
    from projects.registry import PROJECT_DEFINITIONS

    projects = {
        slug: {
            "jira_component": slug.upper(), "aliases": [], "dcc_label": f"Example {slug}",
            "dcc_template_name": f"{slug}_dcc_template.docx", "mail_template_name": f"{slug}_mail_template",
        }
        for slug, definition in PROJECT_DEFINITIONS.items() if "jira" in definition.capabilities
    }
    with TemporaryDirectory() as directory:
        settings = {}
        for key, name, content in (
            ("PROJECT_CONFIGURATION_FILE", "projects.json", {
                "schema_version": 1, "projects": projects,
                "cover_pages": {"match_text": "EXAMPLE", "match_label": "Example Work Package", "default_label": "Example Project"},
            }),
            ("DDF_ASSESSMENT_POLICY_FILE", "ddf.json", {
                "schema_version": 1, "prompt_prefix": "Synthetic classification instructions.\nComments:\n        ",
            }),
        ):
            path = Path(directory) / name
            path.write_text(json.dumps(content), encoding="utf-8")
            path.chmod(0o600)
            settings[key] = str(path)
        with override_settings(**settings), patch.dict(os.environ, settings):
            yield settings

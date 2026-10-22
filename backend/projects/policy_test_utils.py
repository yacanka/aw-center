"""Synthetic private DCC policy fixtures shared by document regression tests."""

from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import override_settings


@contextmanager
def private_dcc_policy():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "policy.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "panel_responsibles": {
                "flight": "Required Reviewer",
                "human factor": "Human Reviewer",
                "electrical systems/e3": "Electrical Reviewer",
            },
        }), encoding="utf-8")
        path.chmod(0o600)
        with override_settings(GOKBEY_DCC_POLICY_FILE=str(path)):
            yield path

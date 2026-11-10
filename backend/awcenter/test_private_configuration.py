"""Private configuration stays outside sources, including flattened images."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from awcenter.private_configuration import PrivateConfigurationError, read_private_json


class PrivateConfigurationLocationTests(SimpleTestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.source = self.directory / "app"
        self.assets = self.source / "document-templates"
        self.assets.mkdir(parents=True)
        self.enterContext(patch("awcenter.private_configuration.REPOSITORY_ROOT", self.directory))
        self.enterContext(override_settings(
            AWCENTER_DEPLOYMENT_MODE="container", BASE_DIR=self.source,
            CUSTOM_TEMPLATE_DIR=self.assets,
        ))

    def write_configuration(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "projects.json"
        path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        path.chmod(0o600)
        return path

    def read_configuration(self, path):
        with override_settings(PROJECT_CONFIGURATION_FILE=str(path)):
            return read_private_json("PROJECT_CONFIGURATION_FILE")

    def test_container_accepts_its_canonical_read_only_asset_mount(self):
        path = self.write_configuration(self.assets)
        self.assertEqual(self.read_configuration(path), {"schema_version": 1})

    def test_container_accepts_external_configuration_without_treating_filesystem_root_as_source(self):
        path = self.write_configuration(self.directory / "external")
        self.assertEqual(self.read_configuration(path), {"schema_version": 1})

    def test_container_rejects_source_and_writable_artifact_paths(self):
        for directory in (self.source / "awcenter", self.source / "private_media"):
            with self.subTest(directory=directory.name):
                path = self.write_configuration(directory)
                with self.assertRaises(PrivateConfigurationError):
                    self.read_configuration(path)

    def test_configured_template_directory_cannot_allow_an_arbitrary_source_path(self):
        path = self.write_configuration(self.source / "awcenter")
        with override_settings(CUSTOM_TEMPLATE_DIR=path.parent):
            with self.assertRaises(PrivateConfigurationError):
                self.read_configuration(path)

    def test_writable_artifact_storage_cannot_supply_private_configuration(self):
        for directory in (self.directory / "artifacts", self.assets):
            with self.subTest(directory=directory.name):
                path = self.write_configuration(directory)
                with override_settings(PRIVATE_MEDIA_ROOT=directory):
                    with self.assertRaises(PrivateConfigurationError):
                        self.read_configuration(path)

    def test_development_retains_the_entire_checkout_boundary(self):
        path = self.write_configuration(self.assets)
        with override_settings(AWCENTER_DEPLOYMENT_MODE="development"):
            with self.assertRaises(PrivateConfigurationError):
                self.read_configuration(path)

    def test_canonical_mount_cannot_link_back_into_sources(self):
        if os.name != "posix":
            self.skipTest("Symbolic-link fixture requires POSIX")
        source_path = self.write_configuration(self.source / "awcenter")
        self.assets.rmdir()
        self.assets.symlink_to(source_path.parent, target_is_directory=True)
        with self.assertRaises(PrivateConfigurationError):
            self.read_configuration(self.assets / source_path.name)

    def test_canonical_asset_mount_retains_posix_private_file_permissions(self):
        if os.name != "posix":
            self.skipTest("POSIX file modes are not Windows ACLs")
        path = self.write_configuration(self.assets)
        path.chmod(0o644)
        with self.assertRaises(PrivateConfigurationError):
            self.read_configuration(path)

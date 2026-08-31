"""Unit tests for immutable release manifest and SBOM generation."""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_release_metadata, deployment_preflight, verify_release_image


class ReleaseMetadataTests(unittest.TestCase):
    def test_production_environment_template_covers_compose_inputs(self):
        root = Path(__file__).resolve().parents[1]
        template_path = root / ".env.example"
        template_lines = template_path.read_text(encoding="utf-8").splitlines()
        template_keys = [
            line.partition("=")[0].strip()
            for line in template_lines
            if line.strip() and not line.lstrip().startswith("#") and "=" in line
        ]
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        compose_inputs = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", compose))

        self.assertEqual(len(template_keys), len(set(template_keys)))
        self.assertEqual(compose_inputs - set(template_keys), set())
        self.assertIn("COMPOSE_PROFILES", template_keys)

        values = deployment_preflight.read_env_file(template_path)
        for feature in (
            "DOCPROOF_ENABLED",
            "DOORS_ENABLED",
            "JIRA_ENABLED",
            "TEAMCENTER_ENABLED",
            "WINDOWS_BRIDGE_ENABLED",
        ):
            self.assertEqual(values[feature], "false")
        self.assertEqual(values["AWCENTER_MAIL_TRANSPORT"], "disabled")
        self.assertNotIn("AWCENTER_ENV_FILE", values)

    def test_sbom_is_deterministic_and_contains_both_lock_ecosystems(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "requirements.txt").write_text(
                "Django==5.2.1\n# generated\n",
                encoding="utf-8",
            )
            (root / "frontend/package-lock.json").write_text(
                json.dumps(
                    {
                        "packages": {
                            "": {"name": "aw-center"},
                            "node_modules/vue": {"name": "vue", "version": "3.5.0"},
                            "node_modules/tool/node_modules/estree-walker": {
                                "version": "3.0.3"
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                build_release_metadata,
                "git",
                return_value="2026-08-12T10:00:00+03:00",
            ):
                first = build_release_metadata.build_sbom(root, "release-1", "abc123")
                second = build_release_metadata.build_sbom(root, "release-1", "abc123")

            self.assertEqual(first, second)
            self.assertEqual(first["metadata"]["timestamp"], "2026-08-12T10:00:00+03:00")
            self.assertEqual(
                {(item["name"], item["version"]) for item in first["components"]},
                {
                    ("django", "5.2.1"),
                    ("vue", "3.5.0"),
                    ("estree-walker", "3.0.3"),
                },
            )

    def test_release_files_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend/dist").mkdir(parents=True)
            (root / "frontend/dist/index.html").write_text("app", encoding="utf-8")
            source = root / "source.txt"
            source.write_text("content", encoding="utf-8")
            link = root / "linked.txt"
            link.symlink_to(source)

            with mock.patch.object(
                build_release_metadata,
                "git",
                return_value="linked.txt",
            ):
                with self.assertRaises(SystemExit):
                    build_release_metadata.release_files(root)

    def test_release_files_reject_directory_and_broken_symlinks(self):
        for link_target in ("target-directory", "missing-target"):
            with self.subTest(link_target=link_target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "frontend/dist").mkdir(parents=True)
                (root / "frontend/dist/index.html").write_text("app", encoding="utf-8")
                (root / "target-directory").mkdir()
                link = root / "linked-entry"
                link.symlink_to(root / link_target, target_is_directory=True)

                with mock.patch.object(
                    build_release_metadata,
                    "git",
                    return_value="linked-entry",
                ):
                    with self.assertRaisesRegex(SystemExit, "symlink"):
                        build_release_metadata.release_files(root)

    def test_release_files_require_built_frontend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            with self.assertRaisesRegex(SystemExit, "built frontend"):
                build_release_metadata.release_files(root)

    def test_image_verification_requires_exact_artifact_and_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = root / "expected"
            actual = root / "actual"
            expected.mkdir()
            actual.mkdir()
            (expected / "index.html").write_text("app", encoding="utf-8")
            (actual / "index.html").write_text("app", encoding="utf-8")
            digest = "sha256:" + "a" * 64
            expected_entries = verify_release_image.tree_entries(expected)
            manifest = {
                "schema": 2,
                "release": "release-1",
                "commit": "b" * 40,
                "frontend": {
                    "root": "frontend/dist",
                    "tree_sha256": verify_release_image.tree_digest(expected_entries),
                    "files": len(expected_entries),
                },
                "files": [
                    {
                        "path": f"frontend/dist/{path}",
                        **metadata,
                    }
                    for path, metadata in expected_entries.items()
                ],
            }

            self.assertEqual(
                verify_release_image.resolved_image_digest(
                    {"containerimage.digest": digest}
                ),
                digest,
            )
            self.assertEqual(
                expected_entries,
                verify_release_image.tree_entries(actual),
            )
            self.assertEqual(
                verify_release_image.verify_manifest_frontend(manifest, expected_entries),
                ("release-1", "b" * 40),
            )
            (actual / "index.html").write_text("changed", encoding="utf-8")
            self.assertNotEqual(
                verify_release_image.tree_entries(expected),
                verify_release_image.tree_entries(actual),
            )

    def test_image_verification_rejects_mutable_metadata(self):
        with self.assertRaisesRegex(SystemExit, "immutable image digest"):
            verify_release_image.resolved_image_digest({"containerimage.digest": "latest"})

    def test_deployment_preflight_requires_digest_and_matching_real_passwords(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificate = root / "tls.crt"
            private_key = root / "tls.key"
            models = root / "models"
            certificate.write_text("certificate", encoding="utf-8")
            private_key.write_text("private key", encoding="utf-8")
            private_key.chmod(0o600)
            models.mkdir()
            values = {
                "AWCENTER_RELEASE": "release-1",
                "AWCENTER_IMAGE": "registry.internal/aw-center@sha256:" + "a" * 64,
                "AWCENTER_HOST": "awcenter.internal",
                "SECRET_KEY": "s" * 64,
                "DATABASE_URL": "postgres://awcenter:strong-password@database:5432/awcenter",
                "POSTGRES_PASSWORD": "strong-password",
                "REDIS_PASSWORD": "redis-password-strong-12345",
                "TLS_CERTIFICATE_FILE": str(certificate),
                "TLS_PRIVATE_KEY_FILE": str(private_key),
                "MODEL_DIRECTORY": str(models),
            }

            self.assertEqual(deployment_preflight.validate(values), [])
            for database_url in (
                "postgres://awcenter:strong-password@external.internal:5432/awcenter",
                "postgres://other:strong-password@database:5432/awcenter",
                "postgres://awcenter:strong-password@database:5432/other",
                "postgres://awcenter:strong-password@database:5433/awcenter",
            ):
                with self.subTest(database_url=database_url):
                    values["DATABASE_URL"] = database_url
                    self.assertIn(
                        "DATABASE_URL_TOPOLOGY",
                        deployment_preflight.validate(values),
                    )
            values["DATABASE_URL"] = (
                "postgres://awcenter:strong-password@database:5432/awcenter"
            )
            values["AWCENTER_IMAGE"] = "awcenter:latest"
            values["POSTGRES_PASSWORD"] = "replace-password"
            self.assertEqual(
                deployment_preflight.validate(values),
                ["AWCENTER_IMAGE", "POSTGRES_PASSWORD"],
            )

    def test_release_evidence_writers_do_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_output = root / "release-manifest.json"
            image_output = root / "image-verification.json"

            build_release_metadata.write_json(build_output, {"schema": 2})
            verify_release_image.write_json(image_output, {"schema": 2})

            with self.assertRaisesRegex(SystemExit, "already exists"):
                build_release_metadata.write_json(build_output, {"schema": 3})
            with self.assertRaisesRegex(SystemExit, "already exists"):
                verify_release_image.write_json(image_output, {"schema": 3})
            self.assertEqual(json.loads(build_output.read_text()), {"schema": 2})
            self.assertEqual(json.loads(image_output.read_text()), {"schema": 2})

    def test_deployment_preflight_binds_release_manifest_to_image_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "release-manifest.json"
            verification_path = root / "image-verification.json"
            digest = "a" * 64
            manifest = {
                "schema": 2,
                "release": "release-1",
                "commit": "b" * 40,
                "frontend": {
                    "root": "frontend/dist",
                    "tree_sha256": "c" * 64,
                    "files": 2,
                },
                "files": [],
            }
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            verification = {
                "schema": 2,
                "release": "release-1",
                "commit": "b" * 40,
                "release_manifest_sha256": deployment_preflight._file_sha256(
                    manifest_path
                ),
                "image_digest": f"sha256:{digest}",
                "frontend_tree_sha256": "c" * 64,
                "frontend_files": 2,
            }
            verification_path.write_text(
                json.dumps(verification),
                encoding="utf-8",
            )
            values = {
                "AWCENTER_RELEASE": "release-1",
                "AWCENTER_IMAGE": f"registry.internal/aw-center@sha256:{digest}",
            }

            self.assertEqual(
                deployment_preflight.validate_release_evidence(
                    values, manifest_path, verification_path
                ),
                [],
            )
            values["AWCENTER_IMAGE"] = "registry.internal/aw-center@sha256:" + "d" * 64
            self.assertEqual(
                deployment_preflight.validate_release_evidence(
                    values, manifest_path, verification_path
                ),
                ["IMAGE_DIGEST_MISMATCH"],
            )

    def test_deployment_preflight_rejects_symlinked_runtime_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certificate = root / "tls.crt"
            private_key = root / "tls.key"
            models = root / "models"
            certificate.write_text("certificate", encoding="utf-8")
            private_key.write_text("private key", encoding="utf-8")
            private_key.chmod(0o600)
            models.mkdir()
            certificate_link = root / "certificate-link"
            private_key_link = root / "private-key-link"
            models_link = root / "models-link"
            certificate_link.symlink_to(certificate)
            private_key_link.symlink_to(private_key)
            models_link.symlink_to(models, target_is_directory=True)
            values = {
                "TLS_CERTIFICATE_FILE": str(certificate_link),
                "TLS_PRIVATE_KEY_FILE": str(private_key_link),
                "MODEL_DIRECTORY": str(models_link),
            }

            self.assertEqual(
                deployment_preflight._validate_runtime_paths(values),
                ["TLS_CERTIFICATE_FILE", "TLS_PRIVATE_KEY_FILE", "MODEL_DIRECTORY"],
            )

    def test_windows_bridge_profile_is_explicit_and_fail_closed(self):
        values = {
            "WINDOWS_BRIDGE_ENABLED": "true",
            "AWCENTER_BRIDGE_HOST": "bridge.internal",
            "WINDOWS_BRIDGE_TRUST_PROXY_HEADERS": "true",
            "WINDOWS_BRIDGE_CLIENT_FINGERPRINTS": "a" * 64,
        }

        self.assertIn(
            "WINDOWS_BRIDGE_COMPOSE_PROFILE",
            deployment_preflight._validate_windows_bridge(values),
        )
        self.assertIn(
            "WINDOWS_BRIDGE_PROFILE_WITHOUT_ENABLEMENT",
            deployment_preflight._validate_windows_bridge(
                {"COMPOSE_PROFILES": "windows-bridge"}
            ),
        )
        self.assertIn(
            "AWCENTER_BRIDGE_HOST",
            deployment_preflight._validate_windows_bridge(
                {
                    **values,
                    "COMPOSE_PROFILES": "windows-bridge",
                    "AWCENTER_BRIDGE_HOST": "bridge.invalid",
                }
            ),
        )

    def test_deployment_preflight_rejects_template_environment(self):
        root = Path(__file__).resolve().parents[1]
        values = deployment_preflight.read_env_file(root / ".env.example")

        errors = deployment_preflight.validate(values)

        self.assertIn("AWCENTER_IMAGE", errors)
        self.assertIn("AWCENTER_RELEASE", errors)
        self.assertIn("AWCENTER_HOST", errors)
        self.assertIn("SECRET_KEY", errors)
        self.assertIn("DATABASE_URL", errors)
        self.assertIn("POSTGRES_PASSWORD", errors)
        self.assertIn("REDIS_PASSWORD", errors)
        self.assertIn("TLS_CERTIFICATE_FILE", errors)
        self.assertIn("TLS_PRIVATE_KEY_FILE", errors)
        self.assertIn("MODEL_DIRECTORY", errors)


if __name__ == "__main__":
    unittest.main()

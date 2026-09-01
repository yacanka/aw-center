"""Unit tests for the conservative Django + Vue launcher."""

from __future__ import annotations

import json
import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from scripts.launcher.cli import build_parser, project_path
from scripts.launcher.dependencies import install_backend, prepare_offline
from scripts.launcher.discovery import discover_project
from scripts.launcher.model import LauncherError, Project, Scope
from scripts.launcher.offline_manifest import (
    command_version,
    verify_offline_manifest,
    write_offline_manifest,
)
from scripts.launcher.packaging import package_offline, write_zip
from scripts.launcher.runtime import (
    dev,
    frontend_env,
    runtime_env,
    test as run_repository_tests,
)


def create_project(root: Path) -> Project:
    """Create the minimum discoverable Django and Vue layout for a test."""
    backend = root / "backend"
    frontend = root / "frontend"
    backend.mkdir()
    frontend.mkdir()
    manage_py = backend / "manage.py"
    manage_py.write_text("os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')\n", encoding="utf-8")
    package_json = frontend / "package.json"
    manifest = {"scripts": {"dev": "vite"}, "dependencies": {"vue": "3"}}
    package_json.write_text(json.dumps(manifest), encoding="utf-8")
    requirements = root / "requirements.txt"
    requirements.write_text("Django==5.2\n", encoding="utf-8")
    return Project(root, manage_py, package_json, requirements)


def create_sensitive_runtime_files(project: Project) -> None:
    """Create files that an offline package must never contain."""
    (project.root / ".env").write_text("SECRET_KEY=secret", encoding="utf-8")
    runtime_file = project.root / ".runtime/state.txt"
    runtime_file.parent.mkdir()
    runtime_file.write_text("state", encoding="utf-8")
    backup_file = project.root / "backups/production.dump"
    backup_file.parent.mkdir()
    backup_file.write_text("database-secret", encoding="utf-8")


class DiscoveryTests(unittest.TestCase):
    """Validate generic repository discovery without AW Center constants."""

    def test_discovers_backend_and_vue_frontend(self) -> None:
        """Conventional backend/frontend directories should be selected."""
        with tempfile.TemporaryDirectory() as temporary:
            expected = create_project(Path(temporary))
            actual = discover_project(expected.root)
        self.assertEqual(actual.manage_py.name, "manage.py")
        self.assertEqual(actual.package_json.parent.name, "frontend")

class DependencyTests(unittest.TestCase):
    """Validate explicit online and offline dependency behavior."""

    @mock.patch("scripts.launcher.dependencies.write_offline_manifest")
    @mock.patch("scripts.launcher.dependencies.run")
    def test_offline_preparation_builds_missing_wheels(
        self, run_mock: mock.Mock, manifest_mock: mock.Mock
    ) -> None:
        """Source-only dependencies should be built into the wheel bundle."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            offline_dir = project.root / "offline"
            prepare_offline(project, Scope(frontend=False), offline_dir)

        command, working_directory = run_mock.call_args.args
        self.assertEqual(command[1:4], ["-m", "pip", "wheel"])
        self.assertIn("--wheel-dir", command)
        self.assertIn(offline_dir / "wheels", command)
        self.assertNotIn("--only-binary=:all:", command)
        self.assertEqual(working_directory, project.root)
        manifest_mock.assert_called_once_with(project, Scope(frontend=False), offline_dir)

    @mock.patch("scripts.launcher.dependencies.run")
    @mock.patch("scripts.launcher.dependencies.ensure_virtual_environment")
    def test_offline_backend_install_uses_only_prepared_wheels(
        self, ensure_mock: mock.Mock, run_mock: mock.Mock
    ) -> None:
        """Offline pip installation must disable all package indexes."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            wheels = project.root / "offline/wheels"
            wheels.mkdir(parents=True)
            (wheels / "Django.whl").write_bytes(b"wheel")
            install_backend(project, "offline", project.root / "offline")
        command = run_mock.call_args_list[0].args[0]
        self.assertIn("--no-index", command)
        self.assertIn(wheels, command)
        ensure_mock.assert_called_once_with(project, create=True)

    @mock.patch("scripts.launcher.dependencies.run")
    @mock.patch("scripts.launcher.dependencies.required_tool", return_value="npm")
    def test_offline_npm_cache_does_not_install_in_workspace(
        self, _: mock.Mock, run_mock: mock.Mock
    ) -> None:
        """Cache preparation should use an isolated tree and disable lifecycle scripts."""
        from scripts.launcher.dependencies import populate_npm_cache

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            (project.frontend / "package-lock.json").write_text("{}\n", encoding="utf-8")
            populate_npm_cache(project, project.root / "offline/npm-cache")
            command, working_directory = run_mock.call_args.args
            self.assertNotEqual(working_directory, project.frontend)
            self.assertEqual(command[1], "ci")
            self.assertIn("--ignore-scripts", command)

    @mock.patch("scripts.launcher.offline_manifest.subprocess.run")
    @mock.patch(
        "scripts.launcher.offline_manifest.required_tool",
        return_value=r"C:\\Program Files\\nodejs\\npm.cmd",
    )
    def test_toolchain_version_uses_resolved_windows_command_shim(
        self, required_tool_mock: mock.Mock, run_mock: mock.Mock
    ) -> None:
        """Manifest creation should invoke the resolved Windows npm.cmd shim."""
        run_mock.return_value = mock.Mock(returncode=0, stdout="10.9.2\n")

        self.assertEqual(command_version("npm"), "10.9.2")

        required_tool_mock.assert_called_once_with("npm")
        run_mock.assert_called_once_with(
            [r"C:\\Program Files\\nodejs\\npm.cmd", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )


class RuntimeTests(unittest.TestCase):
    """Protect non-persistent and explicit runtime behavior."""

    def test_runtime_configuration_is_process_only(self) -> None:
        """Runtime helpers should return overrides without profile or env-file state."""
        values = runtime_env("127.0.0.1", 8000, 5173)
        self.assertEqual(values["PORT"], "8000")
        self.assertNotIn("AWCENTER_ENV_FILE", values)
        self.assertEqual(frontend_env("http://127.0.0.1:8000"), {
            "VITE_API_URL": "http://127.0.0.1:8000"
        })

    @mock.patch("scripts.launcher.runtime.supervise")
    @mock.patch("scripts.launcher.runtime.start")
    @mock.patch("scripts.launcher.runtime.ensure_virtual_environment")
    @mock.patch("scripts.launcher.runtime.require_port")
    @mock.patch("scripts.launcher.runtime.django")
    def test_dev_does_not_migrate_without_explicit_flag(
        self,
        django_mock: mock.Mock,
        _: mock.Mock,
        __: mock.Mock,
        start_mock: mock.Mock,
        ___: mock.Mock,
    ) -> None:
        """Starting development must not mutate the database by default."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            dev(project, Scope(frontend=False), host="127.0.0.1", backend_port=8000,
                frontend_port=5173, no_backend_reload=False, migrate=False)
        django_mock.assert_not_called()

    @mock.patch("scripts.launcher.runtime.run")
    @mock.patch("scripts.launcher.runtime.django")
    @mock.patch("scripts.launcher.runtime.ensure_virtual_environment")
    def test_backend_gate_includes_launcher_regressions(
        self, _environment: mock.Mock, django_mock: mock.Mock, run_mock: mock.Mock
    ) -> None:
        """The public test command must validate its own orchestration layer."""

        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            run_repository_tests(project, Scope(frontend=False))

        django_mock.assert_called_once_with(project, ["test"])
        command, cwd = run_mock.call_args.args
        self.assertEqual(command[:3], [project.python, "-m", "unittest"])
        self.assertIn("scripts.test_launcher_jobs", command)
        self.assertEqual(cwd, project.root)


class PackagingTests(unittest.TestCase):
    """Validate deterministic source packaging and secret exclusions."""

    @mock.patch("scripts.launcher.packaging.git_paths")
    def test_offline_package_excludes_env_and_generated_state(self, git_mock: mock.Mock) -> None:
        """Tracked secrets and runtime state must still be excluded from a ZIP."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            create_sensitive_runtime_files(project)
            names_to_track = (
                "requirements.txt",
                "backend/manage.py",
                "frontend/package.json",
                ".env",
                ".runtime/state.txt",
                "backups/production.dump",
            )
            git_mock.return_value = [Path(name) for name in names_to_track]
            output = project.root / "bundle.zip"
            package_offline(project, Scope(), project.root / "offline", output, include_packages=False)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
        self.assertIn("backend/manage.py", names)
        self.assertNotIn(".env", names)
        self.assertNotIn(".runtime/state.txt", names)
        self.assertNotIn("backups/production.dump", names)

    def test_zip_rejects_symlink_sources(self) -> None:
        """An untracked symlink cannot exfiltrate a file outside the repository."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / f"{root.name}-sensitive.txt"
            outside.write_text("sensitive", encoding="utf-8")
            link = root / "leak.txt"
            link.symlink_to(outside)
            try:
                with self.assertRaises(LauncherError):
                    write_zip(
                        root / "bundle.zip",
                        [(link, Path("leak.txt"))],
                        allowed_roots=(root,),
                    )
            finally:
                outside.unlink(missing_ok=True)

    def test_zip_rejects_archive_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "safe.txt"
            source.write_text("safe", encoding="utf-8")
            with self.assertRaises(LauncherError):
                write_zip(
                    root / "bundle.zip",
                    [(source, Path("../escape.txt"))],
                    allowed_roots=(root,),
                )

    @mock.patch("scripts.launcher.offline_manifest.git_commit", return_value="abc123")
    def test_offline_manifest_detects_artifact_tampering(self, _commit: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            (project.frontend / "package-lock.json").write_text("{}", encoding="utf-8")
            wheels = project.root / "offline/wheels"
            wheels.mkdir(parents=True)
            wheel = wheels / "demo-1-py3-none-any.whl"
            wheel.write_bytes(b"wheel")
            write_offline_manifest(project, Scope(), project.root / "offline")
            verify_offline_manifest(project, Scope(), project.root / "offline")
            wheel.write_bytes(b"tampered")
            with self.assertRaises(LauncherError):
                verify_offline_manifest(project, Scope(), project.root / "offline")


class CliTests(unittest.TestCase):
    """Validate the focused public command surface."""

    def test_required_commands_and_runtime_parameters_remain_available(self) -> None:
        """Local, packaging, and offline workflows keep their focused parameters."""
        parser = build_parser()
        development = parser.parse_args(["dev", "--backend-port", "8010", "--migrate"])
        package = parser.parse_args(["package-offline", "--ignore-packages"])
        prepare = parser.parse_args(["prepare-offline", "--skip-frontend"])
        self.assertEqual(development.backend_port, 8010)
        self.assertTrue(development.migrate)
        self.assertTrue(package.ignore_packages)
        self.assertTrue(prepare.skip_frontend)

    def test_launcher_does_not_supervise_production(self) -> None:
        """Production lifecycle belongs to the deployment orchestrator."""

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["prod"])

    def test_relative_paths_resolve_from_project_root(self) -> None:
        """Outputs should not depend on the shell's current working directory."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            self.assertEqual(project_path(project, "offline"), (project.root / "offline").resolve())


if __name__ == "__main__":
    unittest.main()

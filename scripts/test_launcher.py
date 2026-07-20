"""Unit tests for the conservative Django + Vue launcher."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts.launcher.cli import build_parser, project_path
from scripts.launcher.dependencies import install_backend
from scripts.launcher.discovery import discover_project, infer_wsgi_application
from scripts.launcher.model import LauncherError, Project, Scope
from scripts.launcher.packaging import package_offline
from scripts.launcher.runtime import dev, frontend_env, production_argv, runtime_env


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


class DiscoveryTests(unittest.TestCase):
    """Validate generic repository discovery without AW Center constants."""

    def test_discovers_backend_and_vue_frontend(self) -> None:
        """Conventional backend/frontend directories should be selected."""
        with tempfile.TemporaryDirectory() as temporary:
            expected = create_project(Path(temporary))
            actual = discover_project(expected.root)
        self.assertEqual(actual.manage_py.name, "manage.py")
        self.assertEqual(actual.package_json.parent.name, "frontend")

    def test_wsgi_application_is_inferred_from_manage_py(self) -> None:
        """Production should derive its WSGI import instead of hard-coding a project."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            self.assertEqual(infer_wsgi_application(project), "demo.wsgi:application")


class DependencyTests(unittest.TestCase):
    """Validate explicit online and offline dependency behavior."""

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
            populate_npm_cache(project, project.root / "offline/npm-cache")
            command, working_directory = run_mock.call_args.args
            self.assertNotEqual(working_directory, project.frontend)
            self.assertIn("--ignore-scripts", command)


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

    def test_custom_production_command_expands_safe_placeholders(self) -> None:
        """A configured server command should be tokenized without a shell."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            command = production_argv(
                project,
                "0.0.0.0",
                9000,
                "{python} -m waitress --call {wsgi} --port {port}",
            )
        self.assertEqual(command[0], str(project.python))
        self.assertIn("demo.wsgi:application", command)
        self.assertIn("9000", command)


class PackagingTests(unittest.TestCase):
    """Validate deterministic source packaging and secret exclusions."""

    @mock.patch("scripts.launcher.packaging.git_paths")
    def test_offline_package_excludes_env_and_generated_state(self, git_mock: mock.Mock) -> None:
        """Tracked secrets and runtime state must still be excluded from a ZIP."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            create_sensitive_runtime_files(project)
            names_to_track = ("requirements.txt", "backend/manage.py", "frontend/package.json",
                              ".env", ".runtime/state.txt")
            git_mock.return_value = [Path(name) for name in names_to_track]
            output = project.root / "bundle.zip"
            package_offline(project, Scope(), project.root / "offline", output, include_packages=False)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
        self.assertIn("backend/manage.py", names)
        self.assertNotIn(".env", names)
        self.assertNotIn(".runtime/state.txt", names)


class CliTests(unittest.TestCase):
    """Validate the focused public command surface."""

    def test_required_commands_and_runtime_parameters_remain_available(self) -> None:
        """Dev, prod, packaging, and offline preparation must keep their parameters."""
        parser = build_parser()
        development = parser.parse_args(["dev", "--backend-port", "8010", "--migrate"])
        production = parser.parse_args(["prod", "--no-build", "--backend-port", "9000"])
        package = parser.parse_args(["package-offline", "--ignore-packages"])
        prepare = parser.parse_args(["prepare-offline", "--skip-frontend"])
        self.assertEqual(development.backend_port, 8010)
        self.assertTrue(development.migrate)
        self.assertTrue(production.no_build)
        self.assertTrue(package.ignore_packages)
        self.assertTrue(prepare.skip_frontend)

    def test_relative_paths_resolve_from_project_root(self) -> None:
        """Outputs should not depend on the shell's current working directory."""
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(Path(temporary))
            self.assertEqual(project_path(project, "offline"), (project.root / "offline").resolve())


if __name__ == "__main__":
    unittest.main()

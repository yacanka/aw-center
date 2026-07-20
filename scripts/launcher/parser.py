"""Focused argument parser definitions for launcher subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Protocol


class Subparsers(Protocol):
    """Minimal argparse subparser collection used by command builders."""

    def add_parser(self, name: str, **kwargs: str) -> argparse.ArgumentParser:
        """Add and return one command parser."""
        ...


def build_parser() -> argparse.ArgumentParser:
    """Build the public command parser without legacy aliases."""
    parser = argparse.ArgumentParser(
        description="Conservative launcher for a repository containing Django and Vue."
    )
    parser.add_argument("--root", type=Path, help="Project root; normally discovered automatically.")
    commands = parser.add_subparsers(dest="command", required=True)
    add_setup(commands)
    add_check_and_test(commands)
    add_development(commands)
    add_production(commands)
    add_offline_commands(commands)
    return parser


def add_setup(commands: Subparsers) -> None:
    """Register dependency setup arguments."""
    setup = commands.add_parser("setup", help="Install backend and frontend dependencies.")
    add_scope(setup)
    setup.add_argument("--mode", choices=("online", "offline"), default="online")
    add_offline_dir(setup)


def add_check_and_test(commands: Subparsers) -> None:
    """Register read-only check and test commands."""
    project_check = commands.add_parser("check", help="Run read-only project checks.")
    project_test = commands.add_parser("test", help="Run repository-owned tests.")
    add_scope(project_check)
    add_scope(project_test)


def add_development(commands: Subparsers) -> None:
    """Register development server arguments."""
    development = commands.add_parser("dev", help="Run Django and Vue development servers.")
    add_scope(development)
    add_server_options(development, frontend=True)
    development.add_argument("--no-backend-reload", action="store_true")
    development.add_argument("--migrate", action="store_true", help="Apply migrations before startup.")


def add_production(commands: Subparsers) -> None:
    """Register production validation and server arguments."""
    production = commands.add_parser("prod", help="Build and run the production WSGI service.")
    add_server_options(production, frontend=False)
    production.add_argument("--migrate", action="store_true", help="Apply migrations explicitly.")
    production.add_argument("--no-build", action="store_true", help="Skip the Vue build.")
    production.add_argument("--no-collectstatic", action="store_true")
    production.add_argument("--skip-checks", action="store_true")
    production.add_argument(
        "--production-command",
        help="Server argv with optional {python}, {wsgi}, {host}, and {port} placeholders.",
    )


def add_offline_commands(commands: Subparsers) -> None:
    """Register offline preparation and packaging commands."""
    prepare = commands.add_parser("prepare-offline", help="Download dependencies for offline use.")
    add_scope(prepare)
    add_offline_dir(prepare)
    package = commands.add_parser("package-offline", help="Create an offline project ZIP.")
    add_scope(package)
    add_offline_dir(package)
    package.add_argument("--offline-zip", default="project-offline.zip")
    package.add_argument("--ignore-packages", action="store_true")
    changes = commands.add_parser("package-changes", help="ZIP current Git changes.")
    changes.add_argument("--changes-zip")


def add_scope(parser: argparse.ArgumentParser) -> None:
    """Add consistent backend/frontend selection flags."""
    parser.add_argument("--skip-backend", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")


def add_offline_dir(parser: argparse.ArgumentParser) -> None:
    """Add the common offline dependency directory option."""
    parser.add_argument("--offline-dir", default="offline")


def add_server_options(parser: argparse.ArgumentParser, *, frontend: bool) -> None:
    """Add explicit server bind options for a runtime command."""
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    if frontend:
        parser.add_argument("--frontend-port", type=int, default=5173)

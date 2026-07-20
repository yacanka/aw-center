"""Command-line interface for the Django + Vue launcher."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dependencies import install, prepare_offline
from .discovery import discover_project
from .model import LauncherError, Project, Scope
from .packaging import package_changes, package_offline
from .parser import build_parser
from .runtime import check, dev, prod, test


def main(arguments: list[str] | None = None) -> int:
    """Parse arguments, discover the project, and execute one workflow."""
    try:
        args = build_parser().parse_args(arguments)
        project = discover_project(args.root)
        print_context(project, args.command)
        dispatch(project, args)
        return 0
    except (LauncherError, OSError, ValueError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1


def dispatch(project: Project, args: argparse.Namespace) -> None:
    """Dispatch one parsed command to its focused workflow."""
    scope = scope_from(args)
    if args.command == "setup":
        install(project, scope, args.mode, project_path(project, args.offline_dir))
    elif args.command == "check":
        check(project, scope)
    elif args.command == "test":
        test(project, scope)
    elif args.command == "dev":
        dev_command(project, scope, args)
    elif args.command == "prod":
        prod_command(project, args)
    elif args.command == "prepare-offline":
        prepare_offline(project, scope, project_path(project, args.offline_dir))
    elif args.command == "package-offline":
        package_offline_command(project, scope, args)
    elif args.command == "package-changes":
        output = project_path(project, args.changes_zip) if args.changes_zip else None
        package_changes(project, output)


def dev_command(project: Project, scope: Scope, args: argparse.Namespace) -> None:
    """Adapt development CLI arguments to the runtime workflow."""
    dev(
        project,
        scope,
        host=args.host,
        backend_port=args.backend_port,
        frontend_port=args.frontend_port,
        no_backend_reload=args.no_backend_reload,
        migrate=args.migrate,
    )


def prod_command(project: Project, args: argparse.Namespace) -> None:
    """Adapt production CLI arguments to the runtime workflow."""
    prod(
        project,
        host=args.host,
        port=args.backend_port,
        migrate=args.migrate,
        build=not args.no_build,
        collect_static=not args.no_collectstatic,
        checks=not args.skip_checks,
        production_command=args.production_command,
    )


def package_offline_command(project: Project, scope: Scope, args: argparse.Namespace) -> None:
    """Adapt offline packaging arguments to stable project-relative paths."""
    package_offline(
        project,
        scope,
        project_path(project, args.offline_dir),
        project_path(project, args.offline_zip),
        include_packages=not args.ignore_packages,
    )


def scope_from(args: argparse.Namespace) -> Scope:
    """Build a scope for commands that expose skip flags."""
    return Scope(
        backend=not getattr(args, "skip_backend", False),
        frontend=not getattr(args, "skip_frontend", False),
    )


def project_path(project: Project, value: str) -> Path:
    """Resolve a user path relative to the discovered project root."""
    path = Path(value).expanduser()
    return (path if path.is_absolute() else project.root / path).resolve()


def print_context(project: Project, command: str) -> None:
    """Print the discovered context before any mutation or child process starts."""
    print(f"Project:  {project.root}")
    print(f"Backend:  {project.backend}")
    print(f"Frontend: {project.frontend}")
    print(f"Command:  {command}", flush=True)

#!/usr/bin/env python3
"""Command-line entry point for the AW Center development starter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import starter_core


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the starter."""
    parser = argparse.ArgumentParser(description="AW Center project starter")
    parser.add_argument("command", choices=["check", "install", "check-backend", "start"])
    parser.add_argument("--skip-backend", action="store_true", help="Skip backend package install")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend package install")
    parser.add_argument("--host", default="127.0.0.1", help="Development server host")
    parser.add_argument("--backend-port", default=8000, type=int, help="Django development port")
    parser.add_argument("--frontend-port", default=5173, type=int, help="Vite development port")
    return parser


def main() -> int:
    """Run the requested starter command."""
    args = build_parser().parse_args()
    try:
        dispatch(args)
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


def dispatch(args: argparse.Namespace) -> None:
    """Dispatch starter commands to their implementation."""
    if args.command == "check":
        starter_core.print_check_results(starter_core.check_environment())
    elif args.command == "install":
        install_requested_packages(args)
    elif args.command == "check-backend":
        require_environment_then_check_backend()
    elif args.command == "start":
        require_environment_then_start(args)


def install_requested_packages(args: argparse.Namespace) -> None:
    """Install selected backend and frontend package sets."""
    if not args.skip_backend:
        starter_core.install_backend()
    if not args.skip_frontend:
        starter_core.install_frontend()
    starter_core.ensure_backend_env()


def require_environment_then_check_backend() -> None:
    """Validate local tools before running Django checks."""
    starter_core.fail_when_missing(starter_core.check_environment())
    starter_core.run_backend_checks()


def require_environment_then_start(args: argparse.Namespace) -> None:
    """Validate local tools before running both development servers."""
    starter_core.fail_when_missing(starter_core.check_environment())
    starter_core.start_servers(args.host, args.backend_port, args.frontend_port)


if __name__ == "__main__":
    raise SystemExit(main())

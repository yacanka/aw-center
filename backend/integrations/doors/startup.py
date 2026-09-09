"""Resolve the installed desktop client without starting a COM-owned lifetime."""

import os
import re
from pathlib import Path

from .exceptions import DoorsConnectionError


def registered_executable(program_id: str) -> Path:
    """Resolve a ProgID's local COM server in either Windows registry view.

    Only its executable is used; registry command arguments are never replayed.
    A normally launched GUI stays open when disposable worker proxies are released.
    """
    try:
        import winreg
    except ImportError:
        raise DoorsConnectionError("DOORS client discovery requires Windows.") from None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, program_id + r"\CLSID", 0, winreg.KEY_READ | view
            ) as key:
                class_id = winreg.QueryValueEx(key, None)[0]
            with winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, rf"CLSID\{class_id}\LocalServer32",
                0, winreg.KEY_READ | view,
            ) as key:
                command = winreg.QueryValueEx(key, None)[0]
            executable = parse_server_executable(os.path.expandvars(command))
            if executable.is_file():
                return executable
        except (OSError, ValueError, TypeError):
            continue
    raise DoorsConnectionError(
        "DOORS executable could not be resolved. Check DOORS_OLE_PROG_ID or set DOORS_EXECUTABLE.",
        "DOORS_EXECUTABLE_UNAVAILABLE",
    )


def parse_server_executable(command: str) -> Path:
    """Extract quoted or legacy unquoted LocalServer32 executable paths."""
    match = re.match(r'^\s*(?:"([^"]+\.exe)"|(.+?\.exe))(?=\s|$)', command, re.IGNORECASE)
    if match is None:
        raise ValueError("Invalid DOORS COM server registration.")
    return Path(match.group(1) or match.group(2))

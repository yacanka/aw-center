"""Isolated pre-import verifier: only sys, nt and _sha256 builtins may load.

CMD authenticates Python's executable/DLLs and UTF-8 encoding startup closure
before this file runs under -I -S -B -X utf8. Never import a stdlib/source module
until verify_runtime has authenticated the entire reviewed archive inventory.
"""
import sys

if "nt" not in sys.builtin_module_names or "_sha256" not in sys.builtin_module_names:
    raise SystemExit("[error] The reviewed Python builtin trust closure is unavailable.")

import nt
import _sha256


class IntegrityError(Exception):
    pass


def _regular(path):
    information = nt.lstat(path)
    if information.st_mode & 0o170000 != 0o100000 or getattr(information, "st_file_attributes", 0) & 0x400:
        raise IntegrityError()


def _directory(path):
    information = nt.lstat(path)
    if information.st_mode & 0o170000 != 0o040000 or getattr(information, "st_file_attributes", 0) & 0x400:
        raise IntegrityError()


def _hash(path):
    digest = _sha256.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_runtime(root, inventory):
    """Verify exact files and directories against shipped pins, never receipts."""
    expected = {}
    directories = {""}
    with open(inventory, "rb") as stream:
        for raw_line in stream:
            line = raw_line.decode("utf-8")
            digest, separator, relative = line.rstrip("\n").partition("|")
            if not separator or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise IntegrityError()
            pieces = relative.split("/")
            if pieces[0] != "python" or any(not p or p in {".", ".."} or any(c in p for c in '\\:|"\r\n') for p in pieces):
                raise IntegrityError()
            if relative in expected:
                raise IntegrityError()
            expected[relative] = digest
            for index in range(1, len(pieces)):
                directories.add("/".join(pieces[:index]))
    if not expected:
        raise IntegrityError()
    _directory(root)
    pending = [""]
    found = set()
    while pending:
        relative_directory = pending.pop()
        path = root + ("/" + relative_directory if relative_directory else "")
        _directory(path)
        for name in nt.listdir(path):
            relative = relative_directory + "/" + name if relative_directory else name
            candidate = root + "/" + relative
            if relative == ".awcenter-tool.json":
                _regular(candidate)
                continue
            if relative in directories:
                _directory(candidate)
                pending.append(relative)
                continue
            if relative not in expected:
                raise IntegrityError()
            _regular(candidate)
            if _hash(candidate) != expected[relative]:
                raise IntegrityError()
            found.add(relative)
    if found != set(expected):
        raise IntegrityError()


def main():
    try:
        # Arguments are fixed launcher protocol, not executable manifest values.
        root, inventory, source_root, action = sys.argv[1:5]
        verify_runtime(root, inventory)
        if action == "verify":
            return 0
        sys.path.insert(0, source_root)
        if action in {"check-home", "initialize-home"}:
            from pathlib import Path
            home = Path(sys.argv[5])
            if action == "check-home":
                from scripts.launcher.installation_permissions import require_private
                require_private(home)
            else:
                from scripts.launcher.installation_state import private_directory
                for path in (home, home / "cache", home / "cache/runtimes", home / "runtimes"):
                    private_directory(path)
            return 0
        if action != "launch":
            raise IntegrityError()
        from scripts.launcher.cli import main as launcher_main
        return launcher_main(sys.argv[5:])
    except (IntegrityError, OSError, ValueError, IndexError):
        print("[error] Managed Python integrity or owner-permission verification failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Reproduce reviewed Python inventories from the catalog-pinned official archive.

Usage: python scripts/launcher/generate_python_inventory.py ARCHIVE [OUTPUT_DIR]
Review generated manifests together with catalog updates; do not run at install.
"""
import hashlib
import json
from pathlib import Path
import sys
import tarfile


def generate(archive, destination):
    catalog = json.loads(Path(__file__).with_name("installation_catalog.json").read_text())["python"]
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != catalog["sha256"]:
        raise ValueError("Archive does not match the reviewed catalog SHA-256")
    records = {}
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            if not member.isfile() or not member.name.startswith("python/"):
                raise ValueError("Expected the reviewed file-only Python archive")
            if any(c in member.name for c in '|\r\n"%&!<>^') or ".." in member.name.split("/"):
                raise ValueError("Unsafe native inventory member")
            records[member.name] = hashlib.sha256(source.extractfile(member).read()).hexdigest()
    startup = {name: digest for name, digest in records.items() if name.count("/") == 1}
    for module in ("__init__", "aliases", "utf_8"):
        for relative in (f"python/Lib/encodings/{module}.py", f"python/Lib/encodings/__pycache__/{module}.cpython-311.pyc"):
            startup[relative] = records[relative]
    for filename, values in (("installation_python.sha256", records), ("installation_python_startup.sha256", startup)):
        (destination / filename).write_bytes("".join(f"{digest}|{name}\n" for name, digest in sorted(values.items())).encode("ascii"))


if __name__ == "__main__":
    generate(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent)

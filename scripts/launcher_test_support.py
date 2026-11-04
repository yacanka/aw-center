"""Standard-library project fixture shared by launcher and Manager tests."""
import json
from pathlib import Path

from scripts.launcher.model import Project


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


import shutil
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class FrontendArtifactTests(SimpleTestCase):
    """Verify production SPA artifact checks fail closed."""

    def setUp(self):
        """Create an isolated representative Vite artifact."""

        self.directory = Path(tempfile.mkdtemp())
        self.assets = self.directory / "assets"
        self.static_root = self.directory / "static"
        self.assets.mkdir()
        (self.static_root / "assets").mkdir(parents=True)
        self.override = override_settings(
            FRONTEND_DIST_DIR=self.directory,
            FRONTEND_ASSETS_DIR=self.assets,
            STATIC_ROOT=self.static_root,
            ALLOWED_HOSTS=["testserver"],
            SECURE_SSL_REDIRECT=False,
        )
        self.override.enable()

    def tearDown(self):
        """Remove isolated frontend files and settings."""

        self.override.disable()
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_valid_artifact_is_served_for_nested_spa_route(self):
        """The command accepts matching HTML, assets, and Django fallback."""

        self.write_valid_artifact()

        call_command("verify_frontend_artifact", verbosity=0)

    def test_missing_referenced_asset_blocks_deployment(self):
        """A stale index cannot point at a missing immutable asset."""

        self.write_valid_artifact()
        (self.assets / "app.js").unlink()

        with self.assertRaisesMessage(CommandError, "missing or empty"):
            call_command("verify_frontend_artifact", verbosity=0)

    def test_unsafe_asset_path_blocks_deployment(self):
        """A shell cannot escape the configured immutable asset directory."""

        (self.directory / "outside.js").write_text("unsafe", encoding="utf-8")
        self.write_index("/core/assets/../outside.js")
        (self.assets / "app.css").write_text("body{}", encoding="utf-8")
        (self.static_root / "assets" / "app.css").write_text("body{}", encoding="utf-8")

        with self.assertRaisesMessage(CommandError, "unsafe asset path"):
            call_command("verify_frontend_artifact", verbosity=0)

    def test_missing_collected_asset_blocks_deployment(self):
        """A valid dist file is insufficient when collectstatic output is stale."""

        self.write_valid_artifact()
        (self.static_root / "assets" / "app.js").unlink()

        with self.assertRaisesMessage(CommandError, "Collected frontend asset"):
            call_command("verify_frontend_artifact", verbosity=0)

    def test_shell_requires_both_javascript_and_css(self):
        """An incomplete build cannot pass with only one entry asset type."""

        (self.assets / "app.js").write_text("export{}", encoding="utf-8")
        self.write_index("/core/assets/app.js", stylesheet="")

        with self.assertRaisesMessage(CommandError, "JavaScript and CSS"):
            call_command("verify_frontend_artifact", verbosity=0)

    def write_valid_artifact(self):
        """Write a minimal non-empty Vite-style shell and assets."""

        (self.assets / "app.js").write_text("export{}", encoding="utf-8")
        (self.assets / "app.css").write_text("body{}", encoding="utf-8")
        (self.static_root / "assets" / "app.js").write_text("export{}", encoding="utf-8")
        (self.static_root / "assets" / "app.css").write_text("body{}", encoding="utf-8")
        self.write_index("/core/assets/app.js")

    def write_index(self, script, stylesheet="/core/assets/app.css"):
        """Write a bounded SPA shell with configurable asset references."""

        link = f'<link rel="stylesheet" href="{stylesheet}">' if stylesheet else ""
        html = f'<!doctype html><html><head>{link}</head><body><script src="{script}"></script></body></html>'
        (self.directory / "index.html").write_text(html, encoding="utf-8")

"""Tests for bounded Linux PowerPoint conversion helpers."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from PIL import Image

from pptxgallery import converters


class PresentationConverterTests(SimpleTestCase):
    @override_settings(PPTX_CONVERSION_TIMEOUT_SECONDS=42)
    @patch("pptxgallery.converters.subprocess.run")
    def test_external_commands_are_bounded_and_shell_free(self, run_mock):
        converters._run_command(["soffice", "--headless"])

        run_mock.assert_called_once_with(
            ["soffice", "--headless"],
            check=True,
            capture_output=True,
            timeout=42,
        )

    def test_slide_payload_is_reencoded_and_thumbnail_is_bounded(self):
        source = BytesIO()
        Image.new("RGB", (1024, 768), "blue").save(source, format="PNG")
        source.seek(0)

        image_data, thumb_data = converters.normalized_slide_payloads(source)

        with Image.open(BytesIO(image_data)) as image:
            self.assertEqual(image.size, (1024, 768))
        with Image.open(BytesIO(thumb_data)) as thumb:
            self.assertLessEqual(max(thumb.size), 512)

    @patch("pptxgallery.converters._run_command")
    def test_renderer_rejects_missing_libreoffice_output(self, _run_command):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "did not produce"):
                converters.render_pptx_to_images(
                    Path(directory) / "input.pptx",
                    Path(directory),
                )

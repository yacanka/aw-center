"""Tests for safe cross-platform PowerPoint conversion adapters."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from pptxgallery import converters


class PresentationConverterTests(SimpleTestCase):
    """Verify adapter selection, subprocess bounds, and temporary cleanup."""

    @patch.object(converters, "pythoncom", None)
    @patch.object(converters, "win32com", None)
    def test_non_windows_runtime_selects_soffice(self):
        """Linux and macOS use the LibreOffice conversion adapter."""

        self.assertIs(converters._select_exporter(), converters.convert_pptx_with_soffice)

    @override_settings(PPTX_CONVERSION_TIMEOUT_SECONDS=42)
    @patch("pptxgallery.converters.subprocess.run")
    def test_external_commands_are_bounded_and_shell_free(self, run_mock):
        """Conversion binaries receive argument arrays, output capture, and a timeout."""

        converters._run_command(["soffice", "--headless"])

        run_mock.assert_called_once_with(
            ["soffice", "--headless"], check=True, capture_output=True, timeout=42
        )

    @patch("pptxgallery.converters._save_slides")
    @patch("pptxgallery.converters._select_exporter")
    def test_conversion_cleans_work_directory(self, select_exporter, save_slides):
        """Successful conversion removes all intermediate artifacts."""

        work_directories = []

        def exporter(presentation, work_directory, dpi):
            work_directories.append(work_directory)
            output = work_directory / "slide-1.png"
            output.write_bytes(b"image")
            return [output]

        select_exporter.return_value = exporter
        presentation = self._presentation()

        converters.convert_pptx_to_images(presentation)

        self.assertFalse(work_directories[0].exists())
        save_slides.assert_called_once()
        self.assertEqual(presentation.status, "ready")

    @patch("pptxgallery.converters._select_exporter")
    def test_failed_conversion_sets_failed_status_and_cleans(self, select_exporter):
        """Adapter failures leave no work directory and mark the record failed."""

        work_directories = []

        def failing_exporter(presentation, work_directory, dpi):
            work_directories.append(work_directory)
            raise RuntimeError("conversion failed")

        select_exporter.return_value = failing_exporter
        presentation = self._presentation()

        with self.assertRaises(RuntimeError):
            converters.convert_pptx_to_images(presentation)

        self.assertFalse(work_directories[0].exists())
        self.assertEqual(presentation.status, "failed")

    @staticmethod
    def _presentation():
        """Return a minimal presentation double for orchestration tests."""

        presentation = MagicMock()
        presentation.file.path = str(Path("input.pptx"))
        presentation.status = "pending"
        return presentation

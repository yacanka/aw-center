from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from media_tools.services import (
    MediaParameters,
    build_ffmpeg_command,
    calculate_estimated_bytes,
    estimate_output_size,
    parse_parameters,
)


class MediaToolsServiceTests(TestCase):
    """Verify media conversion validation and preview calculations."""

    def test_parse_parameters_rejects_unsupported_extension(self):
        """Unsupported output formats are rejected before subprocess execution."""

        with self.assertRaises(ValueError):
            parse_parameters({"output_extension": "exe"})

    def test_estimate_uses_requested_bitrates_when_duration_exists(self):
        """Size preview uses video and audio bitrate when duration is available."""

        parameters = MediaParameters("mp4", video_bitrate_kbps=800, audio_bitrate_kbps=128)

        estimated_bytes = calculate_estimated_bytes(1000, 10, parameters)

        self.assertEqual(estimated_bytes, 1160000)

    @override_settings(FFMPEG_EXECUTABLE="/opt/bin/ffmpeg")
    def test_build_ffmpeg_command_uses_configured_executable(self):
        """FFmpeg command uses the executable configured from settings."""

        command = build_ffmpeg_command(
            input_path=Path("input.mov"),
            output_path=Path("output.mp4"),
            parameters=MediaParameters("mp4", width=1280, height=720, video_bitrate_kbps=1200),
        )

        self.assertEqual(command[0], "/opt/bin/ffmpeg")
        self.assertIn("scale=1280:720", command)
        self.assertIn("1200k", command)

    def test_preview_falls_back_to_source_ratio_without_probe(self):
        """Preview still returns an estimate when ffprobe metadata is unavailable."""

        upload = SimpleUploadedFile("sample.jpg", b"1234567890", content_type="image/jpeg")
        parameters = MediaParameters("webp", width=100)

        result = estimate_output_size(upload, parameters)

        self.assertEqual(result["method"], "source-ratio")
        self.assertEqual(result["estimated_bytes"], 7)

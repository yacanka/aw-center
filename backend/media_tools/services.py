import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

ALLOWED_EXTENSIONS = {"mp4", "mov", "webm", "mkv", "avi", "mp3", "wav", "jpg", "jpeg", "png", "webp", "gif"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


@dataclass(frozen=True)
class MediaParameters:
    """Validated user parameters for FFmpeg conversion."""

    output_extension: str
    width: int | None = None
    height: int | None = None
    video_bitrate_kbps: int | None = None
    audio_bitrate_kbps: int | None = None


def parse_parameters(data: dict) -> MediaParameters:
    """Parse and validate conversion parameters from a request payload."""

    extension = normalize_extension(data.get("output_extension"))
    return MediaParameters(
        output_extension=extension,
        width=parse_optional_int(data.get("width"), "width", 16, 7680),
        height=parse_optional_int(data.get("height"), "height", 16, 4320),
        video_bitrate_kbps=parse_optional_int(data.get("video_bitrate_kbps"), "video bitrate", 1, 200000),
        audio_bitrate_kbps=parse_optional_int(data.get("audio_bitrate_kbps"), "audio bitrate", 1, 10000),
    )


def validate_upload(uploaded_file: UploadedFile) -> str:
    """Validate uploaded media and return its normalized extension."""

    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file is larger than 500 MB.")
    extension = normalize_extension(Path(uploaded_file.name).suffix)
    return extension


def estimate_output_size(uploaded_file: UploadedFile, parameters: MediaParameters) -> dict:
    """Estimate output size before conversion using probe metadata and bitrates."""

    input_extension = validate_upload(uploaded_file)
    with temporary_upload(uploaded_file, input_extension) as input_path:
        duration = probe_duration(input_path)
    estimated_bytes = calculate_estimated_bytes(uploaded_file.size, duration, parameters)
    return {
        "estimated_bytes": estimated_bytes,
        "duration_seconds": duration,
        "method": "bitrate" if duration and has_bitrate(parameters) else "source-ratio",
    }


def convert_uploaded_media(uploaded_file: UploadedFile, parameters: MediaParameters) -> Path:
    """Convert an uploaded media file and return the generated file path."""

    input_extension = validate_upload(uploaded_file)
    output_path = conversion_output_path(parameters.output_extension)
    with temporary_upload(uploaded_file, input_extension) as input_path:
        run_ffmpeg(input_path, output_path, parameters)
    return output_path


def normalize_extension(value: object) -> str:
    """Normalize and allowlist a media extension."""

    extension = str(value or "").lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported media extension.")
    return extension


def parse_optional_int(value: object, label: str, minimum: int, maximum: int) -> int | None:
    """Parse an optional integer and enforce inclusive boundaries."""

    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label} value.") from error
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{label.capitalize()} must be between {minimum} and {maximum}.")
    return parsed


def temporary_upload(uploaded_file: UploadedFile, extension: str):
    """Persist an uploaded file temporarily for FFmpeg/FFprobe execution."""

    suffix = f".{extension}"
    temporary_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        for chunk in uploaded_file.chunks():
            temporary_file.write(chunk)
        temporary_file.close()
        return TemporaryPath(Path(temporary_file.name))
    except Exception:
        os.unlink(temporary_file.name)
        raise


class TemporaryPath:
    """Context manager that removes a temporary path on exit."""

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.path.unlink(missing_ok=True)


def probe_duration(input_path: Path) -> float | None:
    """Return media duration in seconds when FFprobe can read it."""

    ffprobe_path = get_ffprobe_path()
    command = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(input_path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
        duration = json.loads(completed.stdout).get("format", {}).get("duration")
        return float(duration) if duration else None
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return None


def calculate_estimated_bytes(source_bytes: int, duration: float | None, parameters: MediaParameters) -> int:
    """Calculate a conservative output size estimate from user settings."""

    if duration and has_bitrate(parameters):
        total_kbps = (parameters.video_bitrate_kbps or 0) + (parameters.audio_bitrate_kbps or 0)
        return max(1, int(total_kbps * 1000 / 8 * duration))
    resize_factor = 0.75 if parameters.width or parameters.height else 1
    return max(1, int(source_bytes * resize_factor))


def has_bitrate(parameters: MediaParameters) -> bool:
    """Return whether the user provided any bitrate target."""

    return bool(parameters.video_bitrate_kbps or parameters.audio_bitrate_kbps)


def run_ffmpeg(input_path: Path, output_path: Path, parameters: MediaParameters) -> None:
    """Run FFmpeg with validated arguments and a bounded timeout."""

    command = build_ffmpeg_command(input_path, output_path, parameters)
    subprocess.run(command, capture_output=True, text=True, timeout=300, check=True)


def build_ffmpeg_command(input_path: Path, output_path: Path, parameters: MediaParameters) -> list[str]:
    """Build a shell-free FFmpeg command from validated parameters."""

    command = [settings.FFMPEG_EXECUTABLE, "-y", "-i", str(input_path)]
    if parameters.width or parameters.height:
        command.extend(["-vf", f"scale={parameters.width or -2}:{parameters.height or -2}"])
    if parameters.video_bitrate_kbps:
        command.extend(["-b:v", f"{parameters.video_bitrate_kbps}k"])
    if parameters.audio_bitrate_kbps:
        command.extend(["-b:a", f"{parameters.audio_bitrate_kbps}k"])
    command.append(str(output_path))
    return command


def conversion_output_path(extension: str) -> Path:
    """Create a unique output path for the converted media."""

    output_dir = settings.MEDIA_ROOT / "conversions"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"converted-{uuid4().hex}.{extension}"


def get_ffprobe_path() -> str:
    """Infer the FFprobe executable path from the configured FFmpeg path."""

    ffmpeg_path = Path(settings.FFMPEG_EXECUTABLE)
    if ffmpeg_path.name == "ffmpeg":
        return "ffprobe"
    return str(ffmpeg_path.with_name("ffprobe"))
